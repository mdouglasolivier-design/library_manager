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
    is_overdue = fields.Boolean(compute='_compute_is_overdue')

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

    @api.constrains('pages')
    def _check_pages(self):
        for book in self:
            if book.pages < 0:
                raise ValidationError("Number of pages cannot be negative.")

    def action_borrow(self):
        for book in self:
            if not book.borrower_id:
                raise UserError("Please select a borrower first.")
            book.write({
                'state': 'borrowed',
                'borrow_date': fields.Date.today(),
                'due_date': fields.Date.today() + timedelta(days=14),
            })

    def action_return(self):
        self.write({
            'state': 'available',
            'borrower_id': False,
            'borrow_date': False,
            'due_date': False,
        })

    def action_mark_lost(self):
        self.write({'state': 'lost'})
