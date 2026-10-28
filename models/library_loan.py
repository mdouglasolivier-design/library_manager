from odoo import models, fields, api
from odoo.exceptions import ValidationError


class LibraryLoan(models.Model):
    _name = 'library.loan'
    _description = 'Library Loan'
    _order = 'borrow_date desc, id desc'

    book_id = fields.Many2one(
        'library.book', string='Book', required=True,
        ondelete='restrict', index=True)
    borrower_id = fields.Many2one(
        'res.partner', string='Borrower', required=True, index=True)
    borrow_date = fields.Date(required=True, default=fields.Date.context_today)
    due_date = fields.Date(required=True)
    return_date = fields.Date()
    state = fields.Selection([
        ('borrowed', 'Borrowed'),
        ('returned', 'Returned'),
    ], default='borrowed', required=True)
    is_overdue = fields.Boolean(
        compute='_compute_is_overdue', search='_search_is_overdue')
    days_late = fields.Integer(compute='_compute_days_late')

    @api.depends('book_id.name', 'borrower_id.name')
    def _compute_display_name(self):
        for loan in self:
            loan.display_name = "%s / %s" % (
                loan.book_id.name or '', loan.borrower_id.name or '')

    @api.depends('state', 'due_date')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for loan in self:
            loan.is_overdue = bool(
                loan.state == 'borrowed' and loan.due_date and loan.due_date < today)

    def _search_is_overdue(self, operator, value):
        today = fields.Date.today()
        positive = (operator == '=') == bool(value)
        if positive:
            return [('state', '=', 'borrowed'), ('due_date', '<', today)]
        return ['|', '|',
                ('state', '!=', 'borrowed'),
                ('due_date', '=', False),
                ('due_date', '>=', today)]

    @api.depends('state', 'due_date', 'return_date')
    def _compute_days_late(self):
        today = fields.Date.today()
        for loan in self:
            end = loan.return_date if loan.state == 'returned' else today
            if loan.due_date and end and end > loan.due_date:
                loan.days_late = (end - loan.due_date).days
            else:
                loan.days_late = 0

    @api.constrains('borrow_date', 'due_date', 'return_date')
    def _check_dates(self):
        for loan in self:
            if loan.due_date < loan.borrow_date:
                raise ValidationError("The due date cannot be before the borrow date.")
            if loan.return_date and loan.return_date < loan.borrow_date:
                raise ValidationError("The return date cannot be before the borrow date.")

    @api.constrains('book_id', 'state')
    def _check_single_open_loan(self):
        for loan in self.filtered(lambda l: l.state == 'borrowed'):
            others = self.search_count([
                ('book_id', '=', loan.book_id.id),
                ('state', '=', 'borrowed'),
                ('id', '!=', loan.id),
            ])
            if others:
                raise ValidationError("This book already has an open loan.")

    def action_mark_returned(self):
        today = fields.Date.today()
        for loan in self.filtered(lambda l: l.state == 'borrowed'):
            loan.write({'state': 'returned', 'return_date': today})
            if loan.book_id.state == 'borrowed':
                loan.book_id.write({
                    'state': 'available',
                    'borrower_id': False,
                    'borrow_date': False,
                    'due_date': False,
                })