from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLibraryReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.member = cls.env['res.partner'].create({'name': 'Report Member'})
        cls.book = cls.env['library.book'].create({
            'name': 'Report Book',
            'author': 'Report Author',
            'borrower_id': cls.member.id,
        })
        cls.book.action_borrow()
        cls.loan = cls.book.loan_ids
        cls.loan.due_date = fields.Date.today() - timedelta(days=3)

    def _render_html(self, report_name, ids, data=None):
        content, _kind = self.env['ir.actions.report']._render_qweb_html(
            report_name, ids, data=data)
        return content.decode() if isinstance(content, bytes) else str(content)

    def test_loan_receipt_renders(self):
        html = self._render_html('library_manager.report_loan_receipt', self.loan.ids)
        self.assertIn('Report Book', html)
        self.assertIn('Report Member', html)

    def test_member_card_renders(self):
        html = self._render_html('library_manager.report_member_card', self.member.ids)
        self.assertIn('Report Member', html)
        self.assertIn('LIB%06d' % self.member.id, html)

    def test_overdue_report_values_from_wizard_data(self):
        report = self.env['report.library_manager.report_overdue_list']
        values = report._get_report_values([], data={'form': {
            'date_as_of': fields.Date.to_string(fields.Date.today()),
            'borrower_ids': [],
        }})
        self.assertIn(self.loan, values['docs'])
        self.assertEqual(values['days_late'][self.loan.id], 3)

    def test_overdue_report_filters_by_borrower(self):
        other = self.env['res.partner'].create({'name': 'Someone Else'})
        report = self.env['report.library_manager.report_overdue_list']
        values = report._get_report_values([], data={'form': {
            'date_as_of': fields.Date.to_string(fields.Date.today()),
            'borrower_ids': [other.id],
        }})
        self.assertNotIn(self.loan, values['docs'])

    def test_overdue_report_from_selected_loans(self):
        report = self.env['report.library_manager.report_overdue_list']
        values = report._get_report_values(self.loan.ids)
        self.assertIn(self.loan, values['docs'])

    def test_overdue_report_renders(self):
        html = self._render_html(
            'library_manager.report_overdue_list', [],
            data={'form': {
                'date_as_of': fields.Date.to_string(fields.Date.today()),
                'borrower_ids': [],
            }})
        self.assertIn('Report Book', html)

    def test_wizard_returns_report_action(self):
        wizard = self.env['library.overdue.report.wizard'].create({})
        action = wizard.action_print()
        self.assertEqual(action['type'], 'ir.actions.report')
        self.assertEqual(action['report_name'], 'library_manager.report_overdue_list')

    def test_saved_filters_are_loaded(self):
        overdue = self.env.ref('library_manager.filter_loan_overdue')
        self.assertEqual(overdue.model_id, 'library.loan')
        self.assertTrue(self.env.ref('library_manager.export_loan_overview').export_fields)
