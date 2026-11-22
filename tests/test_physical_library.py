from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestPhysicalLibrary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.book = self.env['library.book'].create({
            'name': 'Multi-copy Physical Book',
            'author': 'Test Author',
            'total_copies': 2,
            'website_published': True,
        })
        self.borrower = self.env['res.users'].create({
            'name': 'Physical Borrower',
            'login': 'physical-borrower',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.other_borrower = self.env['res.users'].create({
            'name': 'Other Physical Borrower',
            'login': 'other-physical-borrower',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.librarian = self.env['res.users'].create({
            'name': 'Physical Librarian',
            'login': 'physical-librarian',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('library_manager.group_library_librarian').id,
            ])],
        })

    def _create_loan(self, borrower):
        today = fields.Date.today()
        return self.env['library.loan'].create({
            'book_id': self.book.id,
            'borrower_id': borrower.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })

    def test_inventory_tracks_each_copy_and_restores_one_on_return(self):
        first_loan = self._create_loan(self.borrower.partner_id)
        second_loan = self._create_loan(self.other_borrower.partner_id)

        self.assertEqual(self.book.borrowed_copies, 2)
        self.assertEqual(self.book.available_copies, 0)
        with self.assertRaises(UserError):
            self.book.action_return()
        self.assertEqual(first_loan.state, 'borrowed')
        self.assertEqual(second_loan.state, 'borrowed')
        with self.assertRaises(ValidationError):
            self._create_loan(self.env.user.partner_id)

        first_loan.action_mark_returned()

        self.assertEqual(first_loan.state, 'returned')
        self.assertEqual(second_loan.state, 'borrowed')
        self.assertEqual(self.book.returned_copies, 1)
        self.assertEqual(self.book.borrowed_copies, 1)
        self.assertEqual(self.book.available_copies, 1)

    def test_request_requires_confirmed_payment_before_approval(self):
        request_record = self.env[
            'library.book.request'
        ].with_user(self.borrower).submit_for_current_user(
            self.book.id,
            borrower_phone='+250788123456',
            payment_method='bank',
            payment_reference='BANK-REF-001')

        self.assertEqual(request_record.payment_status, 'pending')
        self.assertEqual(request_record.payment_amount, 6.0)
        self.assertEqual(request_record.borrower_id, self.borrower.partner_id)
        with self.assertRaises(UserError):
            request_record.with_user(self.librarian).action_approve()

        request_record.with_user(
            self.librarian).action_confirm_payment()
        request_record.with_user(self.librarian).action_approve()

        self.assertEqual(request_record.state, 'approved')
        self.assertEqual(request_record.loan_id.borrower_id,
                         self.borrower.partner_id)
        self.assertEqual(request_record.loan_id.payment_status, 'confirmed')
        self.assertEqual(self.book.available_copies, 1)

    def test_borrowers_cannot_confirm_payment_or_view_other_requests(self):
        own_request = self.env[
            'library.book.request'
        ].with_user(self.borrower).submit_for_current_user(
            self.book.id,
            borrower_phone='+250788123456',
            payment_method='bank')
        other_request = self.env[
            'library.book.request'
        ].with_user(self.other_borrower).search([
            ('id', '=', own_request.id),
        ])

        self.assertFalse(other_request)
        with self.assertRaises(AccessError):
            own_request.with_user(self.borrower).action_confirm_payment()

    def test_book_borrowing_price_is_fixed(self):
        self.assertEqual(self.book.price, 6.0)
        with self.assertRaises(ValidationError):
            self.book.write({'price': 9.0})
