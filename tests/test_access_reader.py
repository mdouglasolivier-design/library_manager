from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestEbookReaderAccess(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ebook = self.env['library.ebook'].create({
            'name': 'Reader Access Test Ebook',
            'author': 'Test Author',
        })
        today = fields.Date.today()
        self.loan = self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.env.user.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })
        self.access_model = self.env['library.ebook.access']

    def _create_user(self, login, groups):
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, [group.id for group in groups])],
        })

    def test_active_loan_grants_access_to_current_user(self):
        self.assertTrue(self.access_model.check_access(self.ebook.id))
        self.assertEqual(len(self.loan.access_ids), 1)
        self.assertTrue(self.loan.access_ids.is_active)

    def test_returning_ebook_revokes_access(self):
        self.loan.action_mark_returned()

        self.assertFalse(self.loan.access_ids.is_active)
        with self.assertRaises(AccessError):
            self.access_model.check_access(self.ebook.id)

    def test_loan_for_another_borrower_does_not_grant_access(self):
        self.loan.borrower_id = self.env['res.partner'].create({
            'name': 'Different Borrower',
        })

        with self.assertRaises(AccessError):
            self.access_model.check_access(self.ebook.id)

    def test_archived_ebook_is_not_accessible(self):
        self.ebook.active = False

        with self.assertRaises(AccessError):
            self.access_model.check_access(self.ebook.id)

    def test_future_loan_does_not_grant_access(self):
        self.loan.write({
            'borrow_date': fields.Date.today() + timedelta(days=1),
            'due_date': fields.Date.today() + timedelta(days=15),
        })

        with self.assertRaises(AccessError):
            self.access_model.check_access(self.ebook.id)

    def test_reader_cannot_create_a_loan(self):
        reader = self._create_user(
            'ebook-reader-no-loan',
            [self.env.ref('base.group_user')],
        )
        today = fields.Date.today()

        with self.assertRaises(AccessError):
            self.env['library.ebook.loan'].with_user(reader).create({
                'ebook_id': self.ebook.id,
                'borrower_id': reader.partner_id.id,
                'borrow_date': today,
                'due_date': today + timedelta(days=14),
            })

    def test_reader_cannot_see_another_members_loan(self):
        reader = self._create_user(
            'ebook-reader-private-loans',
            [self.env.ref('base.group_user')],
        )

        loans = self.env['library.ebook.loan'].with_user(reader).search([
            ('id', '=', self.loan.id),
        ])
        self.assertFalse(loans)

    def test_librarian_can_issue_a_loan_to_a_reader(self):
        reader = self._create_user(
            'ebook-reader-with-loan',
            [self.env.ref('base.group_user')],
        )
        librarian = self._create_user(
            'ebook-librarian',
            [
                self.env.ref('base.group_user'),
                self.env.ref('library_manager.group_library_librarian'),
            ],
        )
        today = fields.Date.today()
        self.env['library.ebook.loan'].with_user(librarian).create({
            'ebook_id': self.ebook.id,
            'borrower_id': reader.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })

        self.assertTrue(
            self.access_model.with_user(reader).check_access(self.ebook.id))
