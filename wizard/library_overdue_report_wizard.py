from odoo import fields, models


class LibraryOverdueReportWizard(models.TransientModel):
    _name = 'library.overdue.report.wizard'
    _description = 'Overdue Loans Report Wizard'

    date_as_of = fields.Date(
        string='Overdue As Of', required=True, default=fields.Date.context_today)
    borrower_ids = fields.Many2many(
        'res.partner', string='Borrowers',
        help="Leave empty to include every borrower.")

    def action_print(self):
        self.ensure_one()
        data = {
            'form': {
                'date_as_of': fields.Date.to_string(self.date_as_of),
                'borrower_ids': self.borrower_ids.ids,
            },
        }
        return self.env.ref(
            'library_manager.action_report_overdue_list'
        ).report_action(self, data=data)
