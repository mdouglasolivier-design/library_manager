from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class LibraryBook(models.Model):
    _name = 'library.book'
    _description = 'Library Book'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Title', required=True, tracking=True)
    author = fields.Char(required=True, tracking=True)
    cover_image = fields.Image(string='Cover', max_width=1024, max_height=1024)
    isbn = fields.Char(string='ISBN', copy=False)
    category = fields.Selection([
        ('fiction', 'Fiction'),
        ('science', 'Science'),
        ('technology', 'Technology'),
        ('history', 'History'),
        ('religion', 'Religion'),
        ('other', 'Other'),
    ], default='other')
    description = fields.Text()
    pages = fields.Integer()
    published_date = fields.Date()
    active = fields.Boolean(default=True)

    state = fields.Selection([
        ('available', 'Available'),
        ('borrowed', 'Borrowed'),
        ('lost', 'Lost'),
    ], default='available', tracking=True, required=True)

    borrower_id = fields.Many2one('res.partner', string='Borrowed By', tracking=True)
    borrow_date = fields.Date()
    due_date = fields.Date()
    is_overdue = fields.Boolean(
        compute='_compute_is_overdue', search='_search_is_overdue')

    loan_ids = fields.One2many('library.loan', 'book_id', string='Loan History')
    loan_count = fields.Integer(compute='_compute_loan_count')

    _sql_constraints = [
        ('isbn_unique', 'unique(isbn)', 'This ISBN already exists!'),
    ]

    @api.depends('state', 'due_date')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for book in self:
            book.is_overdue = bool(
                book.state == 'borrowed' and book.due_date and book.due_date < today
            )

    def _search_is_overdue(self, operator, value):
        today = fields.Date.today()
        positive = (operator == '=') == bool(value)
        if positive:
            return [('state', '=', 'borrowed'), ('due_date', '<', today)]
        return ['|', '|',
                ('state', '!=', 'borrowed'),
                ('due_date', '=', False),
                ('due_date', '>=', today)]

    @api.depends('loan_ids')
    def _compute_loan_count(self):
        for book in self:
            book.loan_count = len(book.loan_ids)

    @api.constrains('pages')
    def _check_pages(self):
        for book in self:
            if book.pages < 0:
                raise ValidationError("Number of pages cannot be negative.")

    def action_borrow(self):
        today = fields.Date.today()
        for book in self:
            if book.state != 'available':
                raise UserError("Only available books can be lent.")
            if not book.borrower_id:
                raise UserError("Please select a borrower first.")
            due = today + timedelta(days=14)
            book.write({
                'state': 'borrowed',
                'borrow_date': today,
                'due_date': due,
            })
            self.env['library.loan'].create({
                'book_id': book.id,
                'borrower_id': book.borrower_id.id,
                'borrow_date': today,
                'due_date': due,
            })

    def action_return(self):
        for book in self:
            book.loan_ids.filtered(lambda l: l.state == 'borrowed').action_mark_returned()
        self.write({
            'state': 'available',
            'borrower_id': False,
            'borrow_date': False,
            'due_date': False,
        })

    def action_mark_lost(self):
        self.write({'state': 'lost'})

    def action_view_loans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Loans',
            'res_model': 'library.loan',
            'view_mode': 'list,form',
            'domain': [('book_id', '=', self.id)],
            'context': {'default_book_id': self.id},
        }
