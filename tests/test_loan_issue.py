from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase

from .common import create_test_ebook_file


class TestEbookBorrowingRequest(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ebook = self.env['library.ebook'].create({
            'name': 'Borrow Request Test eBook',
            'website_published': True,
        })
        create_test_ebook_file(self.env, self.ebook)
        self.reader = self._create_user(
            'ebook-request-reader', [self.env.ref('base.group_portal')])
        self.other_reader = self._create_user(
            'ebook-request-other', [self.env.ref('base.group_portal')])
        self.librarian = self._create_user(
            'ebook-request-librarian',
            [
                self.env.ref('base.group_user'),
                self.env.ref('library_manager.group_library_librarian'),
            ])
        self.parameters = self.env['ir.config_parameter'].sudo()
        self.parameters.set_param(
            'library_manager.ebook_approval_required', 'True')
        self.parameters.set_param(
            'library_manager.ebook_max_active_loans', '0')
        self.parameters.set_param(
            'library_manager.ebook_max_concurrent_loans', '0')

    def _create_user(self, login, groups):
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, [group.id for group in groups])],
        })

    def test_member_submits_own_pending_request(self):
        borrowing_request = self.env[
            'library.ebook.request'
        ].with_user(self.reader).submit_for_current_user(self.ebook.id)

        self.assertEqual(borrowing_request.borrower_id, self.reader.partner_id)
        self.assertEqual(borrowing_request.state, 'pending')
        self.assertFalse(borrowing_request.loan_id)

    def test_member_cannot_request_ebook_without_protected_file(self):
        ebook_without_file = self.env['library.ebook'].create({
            'name': 'Published eBook Without File',
            'website_published': True,
        })
        with self.assertRaises(ValidationError):
            self.env[
                'library.ebook.request'
            ].with_user(self.reader).submit_for_current_user(
                ebook_without_file.id)

    def test_librarian_approval_creates_member_loan_and_access(self):
        borrowing_request = self.env[
            'library.ebook.request'
        ].with_user(self.reader).submit_for_current_user(self.ebook.id)

        borrowing_request.with_user(self.librarian).action_approve()

        self.assertEqual(borrowing_request.state, 'approved')
        self.assertEqual(borrowing_request.loan_id.borrower_id, self.reader.partner_id)
        self.assertEqual(borrowing_request.loan_id.ebook_id, self.ebook)
        self.assertTrue(borrowing_request.loan_id.access_ids)
        self.assertEqual(
            borrowing_request.loan_id.due_date,
            fields.Date.today() + timedelta(days=14))

    def test_member_cannot_approve_or_view_another_members_request(self):
        borrowing_request = self.env[
            'library.ebook.request'
        ].with_user(self.reader).submit_for_current_user(self.ebook.id)
        other_requests = self.env[
            'library.ebook.request'
        ].with_user(self.other_reader).search([
            ('id', '=', borrowing_request.id),
        ])

        self.assertFalse(other_requests)
        with self.assertRaises(AccessError):
            borrowing_request.with_user(self.reader).action_approve()

    def test_full_concurrent_capacity_creates_reservation(self):
        self.parameters.set_param(
            'library_manager.ebook_max_concurrent_loans', '1')
        self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.other_reader.partner_id.id,
        })

        reservation = self.env[
            'library.ebook.request'
        ].with_user(self.reader).submit_for_current_user(self.ebook.id)

        self.assertEqual(reservation._name, 'library.ebook.reservation')
        self.assertEqual(reservation.borrower_id, self.reader.partner_id)
        self.assertEqual(reservation.state, 'pending')

    def test_member_cannot_create_a_request_when_ebook_is_at_capacity(self):
        self.parameters.set_param(
            'library_manager.ebook_max_concurrent_loans', '1')
        self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.other_reader.partner_id.id,
        })

        with self.assertRaises(ValidationError):
            self.env['library.ebook.request'].with_user(self.reader).create({
                'ebook_id': self.ebook.id,
            })

    def test_member_active_loan_limit_is_enforced(self):
        self.parameters.set_param(
            'library_manager.ebook_max_active_loans', '1')
        self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.reader.partner_id.id,
        })

        with self.assertRaises(UserError):
            self.env[
                'library.ebook.request'
            ].with_user(self.reader).submit_for_current_user(self.ebook.id)

    def test_auto_approval_creates_loan(self):
        self.parameters.set_param(
            'library_manager.ebook_approval_required', 'False')

        borrowing_request = self.env[
            'library.ebook.request'
        ].with_user(self.reader).submit_for_current_user(self.ebook.id)

        self.assertEqual(borrowing_request.state, 'approved')
        self.assertEqual(borrowing_request.loan_id.borrower_id, self.reader.partner_id)
