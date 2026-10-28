from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestLibraryBook(TransactionCase):

    def setUp(self):
        super().setUp()
        self.book = self.env['library.book'].create({
            'name': 'Test Book',
            'author': 'Test Author',
        })
        self.member = self.env['res.partner'].create({'name': 'Test Member'})

    def test_borrow_without_borrower_fails(self):
        with self.assertRaises(UserError):
            self.book.action_borrow()

    def test_borrow_and_return(self):
        self.book.borrower_id = self.member
        self.book.action_borrow()
        self.assertEqual(self.book.state, 'borrowed')
        self.assertTrue(self.book.due_date)
        self.book.action_return()
        self.assertEqual(self.book.state, 'available')
        self.assertFalse(self.book.borrower_id)

    def test_loan_history_is_recorded(self):
        self.book.borrower_id = self.member
        self.book.action_borrow()
        self.assertEqual(self.book.loan_count, 1)
        loan = self.book.loan_ids
        self.assertEqual(loan.state, 'borrowed')
        self.book.action_return()
        self.assertEqual(loan.state, 'returned')
        self.assertTrue(loan.return_date)
        self.assertEqual(self.book.loan_count, 1)

    def test_cannot_lend_twice(self):
        self.book.borrower_id = self.member
        self.book.action_borrow()
        with self.assertRaises(UserError):
            self.book.action_borrow()

    def test_overdue_search(self):
        self.book.borrower_id = self.member
        self.book.action_borrow()
        self.book.due_date = fields.Date.today() - timedelta(days=1)
        overdue = self.env['library.book'].search([('is_overdue', '=', True)])
        self.assertIn(self.book, overdue)