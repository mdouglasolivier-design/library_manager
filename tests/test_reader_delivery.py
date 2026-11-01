import base64
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from .common import create_test_ebook_file


@tagged('-at_install', 'post_install')
class TestEbookReaderDelivery(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.today()
        cls.ebook = cls.env['library.ebook'].create({
            'name': 'Protected Reader Delivery eBook',
            'website_published': True,
        })
        cls.reader = cls.env['res.users'].create({
            'name': 'Protected Reader Member',
            'login': 'protected-reader-member',
            'password': 'library-test-password',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.other_reader = cls.env['res.users'].create({
            'name': 'Other Protected Reader',
            'login': 'other-protected-reader',
            'password': 'library-test-password',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.pdf_content = b'%PDF-1.7\nProtected fixture bytes'
        cls.asset = cls.env['library.ebook.asset'].create({
            'ebook_id': cls.ebook.id,
            'filename': 'protected-reader.pdf',
            'file_format': 'pdf',
            'file_data': base64.b64encode(cls.pdf_content).decode('ascii'),
        })
        cls.loan = cls.env['library.ebook.loan'].create({
            'ebook_id': cls.ebook.id,
            'borrower_id': cls.reader.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })

    def test_member_with_active_loan_can_read_pdf(self):
        self.authenticate('protected-reader-member', 'library-test-password')

        page = self.url_open(
            '/my/library/ebooks/%s/read' % self.ebook.id)
        content = self.url_open(
            '/my/library/ebooks/%s/file' % self.ebook.id)

        self.assertEqual(page.status_code, 200)
        self.assertIn('Protected Reader Delivery eBook', page.text)
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content.content, self.pdf_content)
        self.assertEqual(content.headers.get('Cache-Control'), 'private, no-store')
        self.assertEqual(content.headers.get('Content-Disposition'),
                         'inline; filename="protected-reader.pdf"')

    def test_pdf_reader_supports_single_byte_ranges(self):
        self.authenticate('protected-reader-member', 'library-test-password')

        response = self.url_open(
            '/my/library/ebooks/%s/file' % self.ebook.id,
            headers={'Range': 'bytes=0-4'})

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, self.pdf_content[:5])
        self.assertEqual(
            response.headers.get('Content-Range'),
            'bytes 0-4/%s' % len(self.pdf_content))

    def test_invalid_byte_range_is_rejected(self):
        self.authenticate('protected-reader-member', 'library-test-password')

        response = self.url_open(
            '/my/library/ebooks/%s/file' % self.ebook.id,
            headers={'Range': 'bytes=999999-1000000'})

        self.assertEqual(response.status_code, 416)
        self.assertNotIn(self.pdf_content, response.content)

    def test_non_owner_cannot_read_or_download(self):
        self.authenticate('other-protected-reader', 'library-test-password')

        page = self.url_open(
            '/my/library/ebooks/%s/read' % self.ebook.id)
        content = self.url_open(
            '/my/library/ebooks/%s/file' % self.ebook.id)

        self.assertEqual(page.status_code, 403)
        self.assertEqual(content.status_code, 403)
        self.assertNotIn(self.pdf_content, content.content)

    def test_returned_loan_revokes_reader_and_file_access(self):
        self.authenticate('protected-reader-member', 'library-test-password')
        self.loan.action_mark_returned()

        page = self.url_open(
            '/my/library/ebooks/%s/read' % self.ebook.id)
        content = self.url_open(
            '/my/library/ebooks/%s/file' % self.ebook.id)

        self.assertEqual(page.status_code, 403)
        self.assertEqual(content.status_code, 403)

    def test_expired_loan_revokes_reader_and_file_access(self):
        today = fields.Date.today()
        self.loan.write({
            'borrow_date': today - timedelta(days=10),
            'due_date': today - timedelta(days=1),
        })
        self.authenticate('protected-reader-member', 'library-test-password')

        page = self.url_open(
            '/my/library/ebooks/%s/read' % self.ebook.id)
        content = self.url_open(
            '/my/library/ebooks/%s/file' % self.ebook.id)

        self.assertEqual(page.status_code, 403)
        self.assertEqual(content.status_code, 403)

    def test_missing_file_shows_clear_reader_state(self):
        ebook_without_asset = self.env['library.ebook'].create({
            'name': 'No Digital File eBook',
        })
        asset = create_test_ebook_file(self.env, ebook_without_asset)
        today = fields.Date.today()
        self.env['library.ebook.loan'].create({
            'ebook_id': ebook_without_asset.id,
            'borrower_id': self.reader.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=7),
        })
        asset.unlink()
        self.authenticate('protected-reader-member', 'library-test-password')

        response = self.url_open(
            '/my/library/ebooks/%s/read' % ebook_without_asset.id)

        self.assertEqual(response.status_code, 404)
        self.assertIn('library has not uploaded a digital file', response.text)

    def test_archived_ebook_revokes_file_access(self):
        self.authenticate('protected-reader-member', 'library-test-password')
        self.ebook.active = False

        response = self.url_open(
            '/my/library/ebooks/%s/file' % self.ebook.id)

        self.assertEqual(response.status_code, 403)

    def test_anonymous_visitor_cannot_download_file(self):
        response = self.url_open(
            '/my/library/ebooks/%s/file' % self.ebook.id)

        self.assertNotIn(self.pdf_content, response.content)
