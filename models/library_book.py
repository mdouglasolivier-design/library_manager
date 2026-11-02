from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import AccessError, UserError, ValidationError


class LibraryBook(models.Model):
    _name = 'library.book'
    _description = 'Library Book'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char(string='Title', required=True, tracking=True)
    author = fields.Char(required=True, tracking=True)
    publisher = fields.Char()
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
    price = fields.Float(
        string='Borrowing Price (USD)', default=6.0, readonly=True)
    total_copies = fields.Integer(default=1, required=True, tracking=True)
    lost_copies = fields.Integer(default=0, required=True)
    available_copies = fields.Integer(
        compute='_compute_copy_counts', store=True)
    borrowed_copies = fields.Integer(
        compute='_compute_copy_counts', store=True)
    website_published = fields.Boolean(
        string='Published on Website', default=False, index=True)
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

    @api.depends(
        'total_copies', 'lost_copies', 'state', 'loan_ids.state',
        'loan_ids.return_date')
    def _compute_copy_counts(self):
        for book in self:
            open_loans = book.loan_ids.filtered(
                lambda loan: loan.state == 'borrowed')
            legacy_borrowed = int(
                book.state == 'borrowed'
                and bool(book.borrower_id)
                and not open_loans)
            legacy_lost = (
                book.total_copies
                if book.state == 'lost' and not open_loans
                and not book.lost_copies else 0)
            borrowed = len(open_loans) + legacy_borrowed
            available = max(
                book.total_copies - borrowed - book.lost_copies
                - legacy_lost, 0)
            book.borrowed_copies = borrowed
            book.available_copies = available

    @api.constrains('total_copies', 'lost_copies')
    def _check_copy_counts(self):
        for book in self:
            if book.total_copies < 0 or book.lost_copies < 0:
                raise ValidationError(
                    "Book copy counts cannot be negative.")
            open_loans = book.loan_ids.filtered(
                lambda loan: loan.state == 'borrowed')
            legacy_borrowed = int(
                book.state == 'borrowed' and bool(book.borrower_id)
                and not open_loans)
            if (book.lost_copies + len(open_loans) + legacy_borrowed
                    > book.total_copies):
                raise ValidationError(
                    "Lost and borrowed copies cannot exceed total copies.")

    @api.constrains('pages')
    def _check_pages(self):
        for book in self:
            if book.pages < 0:
                raise ValidationError("Number of pages cannot be negative.")

    def action_borrow(self):
        if not self._library_can_manage_inventory():
            raise AccessError(
                "Only a librarian or administrator can lend physical books.")
        today = fields.Date.today()
        for book in self:
            if not book.available_copies:
                raise UserError("No physical copies are available to lend.")
            if not book.borrower_id:
                raise UserError("Please select a borrower first.")
            due = today + timedelta(days=14)
            self.env['library.loan'].create({
                'book_id': book.id,
                'borrower_id': book.borrower_id.id,
                'borrow_date': today,
                'due_date': due,
                'payment_amount': 6.0,
            })

    def action_return(self):
        if not self._library_can_manage_inventory():
            raise AccessError(
                "Only a librarian or administrator can return physical books.")
        for book in self:
            open_loans = book.loan_ids.filtered(
                lambda loan: loan.state == 'borrowed')
            if len(open_loans) > 1:
                raise UserError(
                    "Return each physical copy from its individual loan record.")
            if open_loans:
                open_loans.action_mark_returned()
            elif book.state == 'borrowed':
                book.write({
                    'state': 'available',
                    'borrower_id': False,
                    'borrow_date': False,
                    'due_date': False,
                })

    def action_mark_lost(self):
        if not self._library_can_manage_inventory():
            raise AccessError(
                "Only a librarian or administrator can update inventory.")
        for book in self:
            if book.available_copies:
                book.write({
                    'lost_copies': book.lost_copies + book.available_copies,
                    'state': 'lost',
                })

    def _library_can_manage_inventory(self):
        return (
            self.env.su
            or self.env.user.has_group(
                'library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )

    @api.model_create_multi
    def create(self, vals_list):
        if not self._library_can_manage_inventory():
            raise AccessError(
                "Only a librarian or administrator can register books.")
        for values in vals_list:
            values['price'] = 6.0
        return super().create(vals_list)

    def write(self, vals):
        if not self._library_can_manage_inventory():
            raise AccessError(
                "Only a librarian or administrator can update physical books.")
        if 'price' in vals and vals['price'] != 6.0:
            raise ValidationError(
                "The physical book borrowing price is fixed at $6.00 USD.")
        if 'price' in vals:
            vals = {**vals, 'price': 6.0}
        return super().write(vals)

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
