from odoo import models, fields, api
from odoo.exceptions import AccessError, ValidationError


class LibraryLoan(models.Model):
    _name = 'library.loan'
    _description = 'Library Loan'
    _inherit = ['library.payment.mixin']
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

    @api.model_create_multi
    def create(self, vals_list):
        manager = (
            self.env.su
            or self.env.user.has_group(
                'library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not manager:
            raise AccessError(
                "Only a librarian or administrator can issue physical books.")
        book_ids = sorted({
            values.get('book_id') for values in vals_list
            if values.get('book_id') and values.get('state', 'borrowed') == 'borrowed'
        })
        if book_ids:
            self.env.cr.execute(
                "SELECT id FROM library_book "
                "WHERE id = ANY(%s) ORDER BY id FOR UPDATE", (book_ids,))
            books = self.env['library.book'].browse(book_ids)
            books.invalidate_recordset([
                'state', 'borrower_id', 'total_copies', 'lost_copies',
                'available_copies', 'borrowed_copies', 'loan_ids',
            ])
            requested_counts = {}
            for values in vals_list:
                if values.get('state', 'borrowed') == 'borrowed':
                    book_id = values.get('book_id')
                    requested_counts[book_id] = (
                        requested_counts.get(book_id, 0) + 1)
            for book in books:
                if requested_counts[book.id] > book.available_copies:
                    raise ValidationError(
                        "There are not enough available copies of %s."
                        % book.display_name)
        for values in vals_list:
            values.setdefault('payment_amount', 6.0)
        loans = super().create(vals_list)
        for book in loans.mapped('book_id'):
            open_loans = book.loan_ids.filtered(
                lambda loan: loan.state == 'borrowed')
            latest = open_loans.sorted(
                lambda loan: (loan.borrow_date, loan.id), reverse=True)[:1]
            remaining = book.total_copies - len(open_loans) - book.lost_copies
            book.with_context(_library_inventory_action=True).write({
                'state': (
                    'borrowed' if remaining <= 0 else
                    'lost' if book.lost_copies >= book.total_copies else
                    'available'),
                'borrower_id': latest.borrower_id.id if latest else False,
                'borrow_date': latest.borrow_date if latest else False,
                'due_date': latest.due_date if latest else False,
            })
        return loans

    def action_mark_returned(self):
        if not (
                self.env.su
                or self.env.user.has_group(
                    'library_manager.group_library_librarian')
                or self.env.user.has_group('base.group_system')):
            raise AccessError(
                "Only a librarian or administrator can return physical books.")
        today = fields.Date.today()
        for loan in self.filtered(lambda l: l.state == 'borrowed'):
            loan.with_context(_library_return_action=True).write({
                'state': 'returned',
                'return_date': today,
            })
            book = loan.book_id
            open_loans = book.loan_ids.filtered(
                lambda item: item.state == 'borrowed')
            remaining = book.total_copies - len(open_loans) - book.lost_copies
            latest = open_loans.sorted(
                lambda item: (item.borrow_date, item.id), reverse=True)[:1]
            book.with_context(_library_inventory_action=True).write({
                'state': (
                    'borrowed' if remaining <= 0 else
                    'lost' if book.lost_copies >= book.total_copies else
                    'available'),
                'borrower_id': latest.borrower_id.id if latest else False,
                'borrow_date': latest.borrow_date if latest else False,
                'due_date': latest.due_date if latest else False,
            })

    def write(self, vals):
        if not (
                self.env.su
                or self.env.user.has_group(
                    'library_manager.group_library_librarian')
                or self.env.user.has_group('base.group_system')):
            raise AccessError(
                "Only a librarian or administrator can update physical loans.")
        if ({'state', 'return_date'} & set(vals)
                and not self.env.context.get('_library_return_action')):
            raise AccessError(
                "Return a physical copy through its loan action.")
        return super().write(vals)