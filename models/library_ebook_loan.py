from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LibraryEbookLoan(models.Model):
    _name = 'library.ebook.loan'
    _description = 'Ebook Loan'
    _order = 'borrow_date desc, id desc'

    ebook_id = fields.Many2one(
        'library.ebook', string='Ebook', required=True,
        ondelete='restrict', index=True)
    borrower_id = fields.Many2one(
        'res.partner', string='Borrower', required=True, index=True)
    borrow_date = fields.Date(
        required=True, default=fields.Date.context_today, index=True)
    due_date = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self) + timedelta(days=14),
        index=True)
    return_date = fields.Date()
    state = fields.Selection(
        [('active', 'Active'), ('returned', 'Returned')],
        default='active', required=True, index=True)
    is_overdue = fields.Boolean(
        compute='_compute_is_overdue', search='_search_is_overdue')
    days_late = fields.Integer(compute='_compute_days_late')
    access_ids = fields.One2many(
        'library.ebook.access', 'loan_id', string='Access Grants', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        loans = super().create(vals_list)
        self.env['library.ebook.access'].sudo().create([
            {'loan_id': loan.id} for loan in loans
        ])
        return loans

    @api.depends('ebook_id.name', 'borrower_id.name')
    def _compute_display_name(self):
        for loan in self:
            loan.display_name = "%s / %s" % (
                loan.ebook_id.name or '', loan.borrower_id.name or '')

    @api.depends('state', 'due_date')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for loan in self:
            loan.is_overdue = bool(
                loan.state == 'active' and loan.due_date and loan.due_date < today)

    def _search_is_overdue(self, operator, value):
        today = fields.Date.today()
        positive = (operator == '=') == bool(value)
        if positive:
            return [('state', '=', 'active'), ('due_date', '<', today)]
        return ['|', '|',
                ('state', '!=', 'active'),
                ('due_date', '=', False),
                ('due_date', '>=', today)]

    @api.depends('state', 'due_date', 'return_date')
    def _compute_days_late(self):
        today = fields.Date.today()
        for loan in self:
            end_date = loan.return_date if loan.state == 'returned' else today
            if loan.due_date and end_date and end_date > loan.due_date:
                loan.days_late = (end_date - loan.due_date).days
            else:
                loan.days_late = 0

    @api.constrains('borrow_date', 'due_date', 'return_date', 'state')
    def _check_dates(self):
        for loan in self:
            if loan.due_date < loan.borrow_date:
                raise ValidationError(
                    "The due date cannot be before the borrow date.")
            if loan.return_date and loan.return_date < loan.borrow_date:
                raise ValidationError(
                    "The return date cannot be before the borrow date.")
            if loan.state == 'active' and loan.return_date:
                raise ValidationError(
                    "An active ebook loan cannot have a return date.")
            if loan.state == 'returned' and not loan.return_date:
                raise ValidationError(
                    "A returned ebook loan must have a return date.")

    @api.constrains('ebook_id', 'borrower_id', 'state')
    def _check_single_open_loan_per_borrower(self):
        for loan in self.filtered(lambda item: item.state == 'active'):
            other_open_loan = self.search_count([
                ('ebook_id', '=', loan.ebook_id.id),
                ('borrower_id', '=', loan.borrower_id.id),
                ('state', '=', 'active'),
                ('id', '!=', loan.id),
            ])
            if other_open_loan:
                raise ValidationError(
                    "This borrower already has an active loan for this ebook.")

    @api.constrains('ebook_id')
    def _check_ebook_is_active(self):
        for loan in self:
            if not loan.ebook_id.active:
                raise ValidationError("An archived ebook cannot be loaned.")

    def action_mark_returned(self):
        today = fields.Date.today()
        self.filtered(lambda loan: loan.state == 'active').write({
            'state': 'returned',
            'return_date': today,
        })
