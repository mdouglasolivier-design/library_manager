import base64
from datetime import timedelta
from io import BytesIO
import zipfile

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase


def _create_user(env, login, groups):
    return env['res.users'].create({
        'name': login,
        'login': login,
        'password': 'library-security-test-password',
        'groups_id': [(6, 0, [env.ref(group).id for group in groups])],
    })


def _pdf_data():
    return b'%PDF-1.7\nLibrary security test fixture'


def _epub_data():
    content = BytesIO()
    with zipfile.ZipFile(content, 'w') as archive:
        archive.writestr(
            'mimetype',
            'application/epub+zip',
            compress_type=zipfile.ZIP_STORED,
        )
        archive.writestr(
            'META-INF/container.xml',
            '<container/>',
            compress_type=zipfile.ZIP_DEFLATED,
        )
    return content.getvalue()


def _create_asset(env, ebook, file_format='pdf'):
    content = _pdf_data() if file_format == 'pdf' else _epub_data()
    extension = file_format
    return env['library.ebook.asset'].create({
        'ebook_id': ebook.id,
        'filename': 'security-test.%s' % extension,
        'file_format': file_format,
        'file_data': base64.b64encode(content).decode('ascii'),
    })


class TestLibrarySecurityOwnership(TransactionCase):

    def setUp(self):
        super().setUp()
        self.reader = _create_user(
            self.env, 'security-hardening-reader',
            ['base.group_portal'])
        self.other_reader = _create_user(
            self.env, 'security-hardening-other-reader',
            ['base.group_portal'])
        self.occupant = _create_user(
            self.env, 'security-hardening-occupant',
            ['base.group_portal'])
        self.internal_user = _create_user(
            self.env, 'security-hardening-internal',
            ['base.group_user'])
        self.librarian = _create_user(
            self.env, 'security-hardening-librarian',
            ['base.group_user', 'library_manager.group_library_librarian'])
        self.administrator = _create_user(
            self.env, 'security-hardening-administrator',
            ['base.group_system'])

        Ebook = self.env['library.ebook']
        self.reader_ebook = Ebook.create({
            'name': 'Reader Owned Security eBook',
            'website_published': True,
        })
        self.other_ebook = Ebook.create({
            'name': 'Other Member Security eBook',
            'website_published': True,
        })
        self.request_ebook = Ebook.create({
            'name': 'Request Ownership Security eBook',
            'website_published': True,
        })
        self.reservation_ebook = Ebook.create({
            'name': 'Reservation Ownership Security eBook',
            'website_published': True,
        })
        self.asset_acl_ebook = Ebook.create({
            'name': 'Asset ACL Security eBook',
        })
        for ebook in (
                self.reader_ebook, self.other_ebook, self.request_ebook,
                self.reservation_ebook):
            _create_asset(self.env, ebook)

        today = fields.Date.today()
        Loan = self.env['library.ebook.loan']
        self.reader_loan = Loan.create({
            'ebook_id': self.reader_ebook.id,
            'borrower_id': self.reader.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })
        Loan.create({
            'ebook_id': self.other_ebook.id,
            'borrower_id': self.other_reader.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })

    def test_request_creation_uses_current_borrower_and_pending_state(self):
        borrowing_request = self.env[
            'library.ebook.request'
        ].with_user(self.reader).create({
            'ebook_id': self.request_ebook.id,
            'borrower_id': self.other_reader.partner_id.id,
            'state': 'approved',
        })

        self.assertEqual(
            borrowing_request.borrower_id, self.reader.partner_id)
        self.assertEqual(borrowing_request.state, 'pending')
        self.assertFalse(borrowing_request.loan_id)

    def test_member_cannot_cancel_another_members_request(self):
        borrowing_request = self.env[
            'library.ebook.request'
        ].with_user(self.other_reader).create({
            'ebook_id': self.request_ebook.id,
        })

        with self.assertRaises(AccessError):
            borrowing_request.with_user(self.reader).action_cancel()
        with self.assertRaises(AccessError):
            borrowing_request.with_user(self.reader).write({
                'state': 'cancelled',
            })
        self.assertEqual(borrowing_request.state, 'pending')

    def test_member_can_cancel_own_pending_request(self):
        borrowing_request = self.env[
            'library.ebook.request'
        ].with_user(self.reader).create({
            'ebook_id': self.request_ebook.id,
        })

        borrowing_request.with_user(self.reader).action_cancel()

        self.assertEqual(borrowing_request.state, 'cancelled')

    def test_reservation_creation_uses_current_borrower_and_pending_state(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'library_manager.ebook_max_concurrent_loans', '1')
        self.env['library.ebook.loan'].create({
            'ebook_id': self.reservation_ebook.id,
            'borrower_id': self.occupant.partner_id.id,
        })

        reservation = self.env[
            'library.ebook.reservation'
        ].with_user(self.reader).create({
            'ebook_id': self.reservation_ebook.id,
            'borrower_id': self.other_reader.partner_id.id,
            'state': 'fulfilled',
        })

        self.assertEqual(reservation.borrower_id, self.reader.partner_id)
        self.assertEqual(reservation.state, 'pending')
        self.assertFalse(reservation.loan_id)

    def test_member_cannot_cancel_another_members_reservation(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'library_manager.ebook_max_concurrent_loans', '1')
        self.env['library.ebook.loan'].create({
            'ebook_id': self.reservation_ebook.id,
            'borrower_id': self.occupant.partner_id.id,
        })
        reservation_model = self.env['library.ebook.reservation']
        reservation = reservation_model.with_user(self.other_reader).create({
            'ebook_id': self.reservation_ebook.id,
        })

        with self.assertRaises(AccessError):
            reservation.with_user(self.reader).action_cancel()
        with self.assertRaises(AccessError):
            reservation.with_user(self.reader).write({
                'state': 'cancelled',
            })
        self.assertEqual(reservation.state, 'pending')

    def test_member_can_cancel_own_pending_reservation(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'library_manager.ebook_max_concurrent_loans', '1')
        self.env['library.ebook.loan'].create({
            'ebook_id': self.reservation_ebook.id,
            'borrower_id': self.occupant.partner_id.id,
        })
        reservation = self.env[
            'library.ebook.reservation'
        ].with_user(self.reader).create({
            'ebook_id': self.reservation_ebook.id,
        })

        reservation.with_user(self.reader).action_cancel()

        self.assertEqual(reservation.state, 'cancelled')

    def test_notification_owner_can_mark_read_but_not_change_other_fields(self):
        notification = self.env[
            'library.ebook.notification'
        ]._notify_partner(
            self.reader.partner_id, 'request_submitted',
            ebook=self.request_ebook)
        reader_notification = notification.with_user(self.reader)

        reader_notification.action_mark_read()
        self.assertTrue(reader_notification.is_read)

        with self.assertRaises(AccessError):
            reader_notification.write({
                'notification_type': 'request_approved',
            })

    def test_member_cannot_mark_another_members_notification_read(self):
        notification = self.env[
            'library.ebook.notification'
        ]._notify_partner(
            self.other_reader.partner_id, 'request_submitted',
            ebook=self.request_ebook)

        with self.assertRaises(AccessError):
            notification.with_user(self.reader).action_mark_read()
        self.assertFalse(notification.is_read)
        self.assertFalse(self.env[
            'library.ebook.notification'
        ].with_user(self.reader).search([
            ('id', '=', notification.id),
        ]))

    def test_protected_asset_acl_for_portal_and_internal_users(self):
        asset_model = self.env['library.ebook.asset']
        asset = asset_model.browse(self.reader_loan.ebook_id.asset_ids.id)
        asset_values = {
            'ebook_id': self.asset_acl_ebook.id,
            'filename': 'forbidden.pdf',
            'file_format': 'pdf',
            'file_data': base64.b64encode(_pdf_data()).decode('ascii'),
        }

        for user in (self.reader, self.internal_user):
            with self.subTest(user=user.login, operation='read'):
                with self.assertRaises(AccessError):
                    asset_model.with_user(user).search([])
            with self.subTest(user=user.login, operation='create'):
                with self.assertRaises(AccessError):
                    asset_model.with_user(user).create(asset_values)
            with self.subTest(user=user.login, operation='write'):
                with self.assertRaises(AccessError):
                    asset.with_user(user).write({
                        'filename': 'changed.pdf',
                    })
            with self.subTest(user=user.login, operation='unlink'):
                with self.assertRaises(AccessError):
                    asset.with_user(user).unlink()

    def test_librarian_and_administrator_can_manage_protected_assets(self):
        for user in (self.librarian, self.administrator):
            ebook = self.env['library.ebook'].create({
                'name': 'Staff Asset ACL %s' % user.login,
            })
            asset_model = self.env['library.ebook.asset'].with_user(user)
            asset = asset_model.create({
                'ebook_id': ebook.id,
                'filename': 'staff.pdf',
                'file_format': 'pdf',
                'file_data': base64.b64encode(
                    _pdf_data()).decode('ascii'),
            })

            asset.write({'filename': 'staff-updated.pdf'})
            self.assertEqual(asset.filename, 'staff-updated.pdf')
            asset.unlink()
            self.assertFalse(asset.exists())


@tagged('-at_install', 'post_install')
class TestLibrarySecurityRoutes(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader = _create_user(
            cls.env, 'security-routes-reader', ['base.group_portal'])
        cls.other_reader = _create_user(
            cls.env, 'security-routes-other-reader', ['base.group_portal'])
        cls.internal_user = _create_user(
            cls.env, 'security-routes-internal', ['base.group_user'])
        cls.internal_ebook = cls.env['library.ebook'].create({
            'name': 'Security Route Internal Borrower eBook',
            'website_published': True,
        })
        cls.pdf_ebook = cls.env['library.ebook'].create({
            'name': 'Security Route PDF eBook',
            'website_published': True,
        })
        cls.epub_ebook = cls.env['library.ebook'].create({
            'name': 'Security Route EPUB eBook',
            'website_published': True,
        })
        cls.no_loan_ebook = cls.env['library.ebook'].create({
            'name': 'Security Route No Loan eBook',
            'website_published': True,
        })
        cls.other_member_ebook = cls.env['library.ebook'].create({
            'name': 'Security Route Other Member eBook',
            'website_published': True,
        })
        cls.pdf_content = _pdf_data()
        cls.epub_content = _epub_data()
        _create_asset(cls.env, cls.pdf_ebook)
        _create_asset(cls.env, cls.epub_ebook, 'epub')
        _create_asset(cls.env, cls.no_loan_ebook)
        _create_asset(cls.env, cls.other_member_ebook)
        _create_asset(cls.env, cls.internal_ebook)

        today = fields.Date.today()
        for ebook in (cls.pdf_ebook, cls.epub_ebook):
            cls.env['library.ebook.loan'].create({
                'ebook_id': ebook.id,
                'borrower_id': cls.reader.partner_id.id,
                'borrow_date': today,
                'due_date': today + timedelta(days=14),
            })
        cls.env['library.ebook.loan'].create({
            'ebook_id': cls.other_member_ebook.id,
            'borrower_id': cls.other_reader.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })
        cls.env['library.ebook.loan'].create({
            'ebook_id': cls.internal_ebook.id,
            'borrower_id': cls.internal_user.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })

        cls.csrf_loan_ebook = cls.env['library.ebook'].create({
            'name': 'CSRF Renewal eBook',
            'website_published': True,
        })
        _create_asset(cls.env, cls.csrf_loan_ebook)
        cls.csrf_loan = cls.env['library.ebook.loan'].create({
            'ebook_id': cls.csrf_loan_ebook.id,
            'borrower_id': cls.reader.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })
        cls.csrf_ebook = cls.env['library.ebook'].create({
            'name': 'CSRF Request eBook',
            'website_published': True,
        })
        _create_asset(cls.env, cls.csrf_ebook)
        cls.csrf_request = cls.env['library.ebook.request'].create({
            'ebook_id': cls.no_loan_ebook.id,
            'borrower_id': cls.reader.partner_id.id,
        })
        cls.csrf_reservation = cls.env[
            'library.ebook.reservation'
        ].create({
            'ebook_id': cls.no_loan_ebook.id,
            'borrower_id': cls.reader.partner_id.id,
        })
        cls.csrf_notification = cls.env[
            'library.ebook.notification'
        ]._notify_partner(
            cls.reader.partner_id, 'request_submitted',
            ebook=cls.no_loan_ebook)
        cls.reader.partner_id.phone = '555-0100'

    def test_no_loan_and_internal_user_cannot_download_files(self):
        self.authenticate(
            'security-routes-other-reader',
            'library-security-test-password')
        for ebook in (self.pdf_ebook, self.epub_ebook, self.no_loan_ebook):
            with self.subTest(login='other-reader', ebook=ebook.name):
                response = self.url_open(
                    '/my/library/ebooks/%s/file' % ebook.id)
                self.assertEqual(response.status_code, 403)
                self.assertNotIn(self.pdf_content, response.content)
                self.assertNotIn(self.epub_content, response.content)

        self.authenticate(
            'security-routes-internal', 'library-security-test-password')
        for ebook in (
                self.pdf_ebook, self.epub_ebook, self.no_loan_ebook,
                self.other_member_ebook):
            with self.subTest(login='internal-user', ebook=ebook.name):
                response = self.url_open(
                    '/my/library/ebooks/%s/file' % ebook.id)
                self.assertEqual(response.status_code, 403)
                self.assertNotIn(self.pdf_content, response.content)
                self.assertNotIn(self.epub_content, response.content)

    def test_internal_borrower_can_download_only_their_loaned_file(self):
        self.authenticate(
            'security-routes-internal', 'library-security-test-password')

        allowed = self.url_open(
            '/my/library/ebooks/%s/file' % self.internal_ebook.id)
        denied = self.url_open(
            '/my/library/ebooks/%s/file' % self.other_member_ebook.id)

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.content, self.pdf_content)
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn(self.pdf_content, denied.content)

    def test_reader_cannot_download_another_members_loaned_ebook(self):
        self.authenticate(
            'security-routes-reader', 'library-security-test-password')
        response = self.url_open(
            '/my/library/ebooks/%s/file' % self.other_member_ebook.id)

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(self.pdf_content, response.content)

    def test_epub_download_requires_the_borrowers_own_active_loan(self):
        self.authenticate(
            'security-routes-reader', 'library-security-test-password')
        response = self.url_open(
            '/my/library/ebooks/%s/file' % self.epub_ebook.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, self.epub_content)
        self.assertEqual(
            response.headers.get('Content-Type'), 'application/epub+zip')
        self.assertIn('attachment;', response.headers.get(
            'Content-Disposition', ''))

        self.authenticate(
            'security-routes-other-reader',
            'library-security-test-password')
        denied = self.url_open(
            '/my/library/ebooks/%s/file' % self.epub_ebook.id)
        self.assertEqual(denied.status_code, 403)
        self.assertNotIn(self.epub_content, denied.content)

    def test_malformed_and_multiple_byte_ranges_are_rejected(self):
        self.authenticate(
            'security-routes-reader', 'library-security-test-password')

        for range_header in (
                'bytes=abc',
                'bytes=0-1,4-5',
                'bytes=-0',
                'bytes=5-3'):
            with self.subTest(range_header=range_header):
                response = self.url_open(
                    '/my/library/ebooks/%s/file' % self.pdf_ebook.id,
                    headers={'Range': range_header})
                self.assertEqual(response.status_code, 416)
                self.assertNotIn(self.pdf_content, response.content)

    def test_all_borrower_post_routes_reject_missing_csrf_token(self):
        self.authenticate(
            'security-routes-reader', 'library-security-test-password')
        original_phone = self.reader.partner_id.phone
        post_paths = (
            '/my/library/ebooks/%s/request' % self.csrf_ebook.id,
            '/my/library/loans/%s/renew' % self.csrf_loan.id,
            '/my/library/requests/%s/cancel' % self.csrf_request.id,
            '/my/library/reservations/%s/cancel'
            % self.csrf_reservation.id,
            '/my/library/notifications/%s/read'
            % self.csrf_notification.id,
            '/my/library/account/update',
        )

        for path in post_paths:
            with self.subTest(path=path):
                response = self.url_open(
                    path, data={'csrf_test': 'missing'},
                    allow_redirects=False)
                self.assertEqual(response.status_code, 400)

        self.assertFalse(self.env[
            'library.ebook.request'
        ].search([
            ('ebook_id', '=', self.csrf_ebook.id),
            ('borrower_id', '=', self.reader.partner_id.id),
        ]))
        self.assertEqual(self.csrf_loan.renewal_count, 0)
        self.assertEqual(self.csrf_request.state, 'pending')
        self.assertEqual(self.csrf_reservation.state, 'pending')
        self.assertFalse(self.csrf_notification.is_read)
        self.assertEqual(self.reader.partner_id.phone, original_phone)
