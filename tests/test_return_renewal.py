from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase

from .common import create_test_ebook_file


class TestEbookReturnAndRenewal(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ebook = self.env['library.ebook'].create({
            'name': 'Return and Renewal eBook',
            'website_published': True,
        })
        create_test_ebook_file(self.env, self.ebook)
        portal_group = self.env.ref('base.group_portal')
        self.reader = self._create_user('renewal-reader', portal_group)
        self.other_reader = self._create_user(
            'renewal-other-reader', portal_group)
        today = fields.Date.today()
        self.loan = self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.reader.partner_id.id,
            'borrow_date': today,
            'due_date': today + timedelta(days=14),
        })

    def _create_user(self, login, group):
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, [group.id])],
        })

    def test_member_can_renew_once_and_event_is_audited(self):
        original_due_date = self.loan.due_date

        self.loan.with_user(self.reader).action_renew()

        self.assertEqual(
            self.loan.due_date,
            original_due_date + timedelta(days=14))
        self.assertEqual(self.loan.renewal_count, 1)
        event = self.env['library.ebook.audit'].sudo().search([
            ('event_type', '=', 'loan_renewed'),
            ('loan_id', '=', self.loan.id),
        ], limit=1)
        self.assertTrue(event)
        self.assertEqual(event.actor_id, self.reader)

        with self.assertRaises(UserError):
            self.loan.with_user(self.reader).action_renew()

    def test_other_member_cannot_renew_loan(self):
        with self.assertRaises(AccessError):
            self.loan.with_user(self.other_reader).action_renew()

    def test_overdue_loan_cannot_be_renewed(self):
        yesterday = fields.Date.today() - timedelta(days=1)
        self.loan.write({
            'borrow_date': yesterday - timedelta(days=14),
            'due_date': yesterday,
        })

        with self.assertRaises(UserError):
            self.loan.with_user(self.reader).action_renew()

    def test_pending_reservation_prevents_renewal(self):
        self.env['library.ebook.reservation'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.other_reader.partner_id.id,
        })

        with self.assertRaises(UserError):
            self.loan.with_user(self.reader).action_renew()

    def test_return_records_date_and_audit_event(self):
        self.loan.action_mark_returned()

        self.assertEqual(self.loan.state, 'returned')
        self.assertEqual(self.loan.return_date, fields.Date.today())
        self.assertTrue(self.env['library.ebook.audit'].sudo().search([
            ('event_type', '=', 'loan_returned'),
            ('loan_id', '=', self.loan.id),
        ], limit=1))
