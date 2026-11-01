from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase

from .common import create_test_ebook_file


class TestLibrarySecurityRules(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ebook = self.env['library.ebook'].create({
            'name': 'Security Rules eBook',
            'website_published': True,
        })
        create_test_ebook_file(self.env, self.ebook)
        portal_group = self.env.ref('base.group_portal')
        self.reader = self._create_user('security-reader', portal_group)
        self.other_reader = self._create_user(
            'security-other-reader', portal_group)
        self.librarian = self.env['res.users'].create({
            'name': 'security-librarian',
            'login': 'security-librarian',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('library_manager.group_library_librarian').id,
            ])],
        })
        self.loan = self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.reader.partner_id.id,
        })
        self.request = self.env[
            'library.ebook.request'
        ].with_user(self.other_reader).create({'ebook_id': self.ebook.id})
        self.notification = self.env[
            'library.ebook.notification'
        ]._notify_partner(
            self.reader.partner_id, 'request_submitted', ebook=self.ebook)

    def _create_user(self, login, group):
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, [group.id])],
        })

    def test_member_private_records_are_scoped_to_their_partner(self):
        self.assertEqual(
            self.env['library.ebook.loan'].with_user(self.reader).search([]),
            self.loan)
        self.assertFalse(self.env[
            'library.ebook.loan'
        ].with_user(self.other_reader).search([('id', '=', self.loan.id)]))
        self.assertEqual(
            self.env['library.ebook.request'].with_user(
                self.other_reader).search([]),
            self.request)
        self.assertFalse(self.env[
            'library.ebook.request'
        ].with_user(self.reader).search([
            ('id', '=', self.request.id),
        ]))
        self.assertEqual(
            self.env['library.ebook.notification'].with_user(
                self.reader).search([]),
            self.notification)
        self.assertFalse(self.env[
            'library.ebook.notification'
        ].with_user(self.other_reader).search([
            ('id', '=', self.notification.id),
        ]))

    def test_member_cannot_read_private_asset_or_audit_records(self):
        with self.assertRaises(AccessError):
            self.env['library.ebook.asset'].with_user(self.reader).search([])
        with self.assertRaises(AccessError):
            self.env['library.ebook.audit'].with_user(self.reader).search([])
        with self.assertRaises(AccessError):
            self.env['library.ebook.audit'].with_user(
                self.librarian).create({
                    'event_type': 'loan_issued',
                    'ebook_id': self.ebook.id,
                })
