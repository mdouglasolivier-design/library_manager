from odoo import api, fields, models


class ReportLibraryOverdue(models.AbstractModel):
    _name = 'report.library_manager.report_overdue_list'
    _description = 'Overdue Loans Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        """Return the loans to print.

        - Printed from the wizard: ``data['form']`` holds the date and borrowers.
        - Printed from the Loans list (Print menu): ``docids`` are the selected loans.
        """
        form = (data or {}).get('form')
        Loan = self.env['library.loan']

        if form:
            as_of = fields.Date.to_date(form.get('date_as_of')) or fields.Date.context_today(self)
            domain = [('state', '=', 'borrowed'), ('due_date', '<', as_of)]
            if form.get('borrower_ids'):
                domain.append(('borrower_id', 'in', form['borrower_ids']))
            loans = Loan.search(domain, order='due_date, borrower_id')
        else:
            as_of = fields.Date.context_today(self)
            loans = Loan.browse(docids).filtered(
                lambda loan: loan.state == 'borrowed'
                and loan.due_date and loan.due_date < as_of
            ).sorted(key=lambda loan: (loan.due_date, loan.borrower_id.id))

        return {
            'doc_ids': loans.ids,
            'doc_model': 'library.loan',
            'docs': loans,
            'date_as_of': as_of,
            'days_late': {loan.id: (as_of - loan.due_date).days for loan in loans},
        }
