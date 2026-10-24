from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


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
