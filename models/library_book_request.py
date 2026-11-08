import re
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class LibraryBookRequest(models.Model):
    _name = 'library.book.request'
    _description = 'Physical Book Borrowing Request'
    _inherit = ['library.payment.mixin']
    _order = 'request_date desc, id desc'

    book_id = fields.Many2one(
        'library.book', required=True, ondelete='restrict', index=True)
    borrower_id = fields.Many2one(
        'res.partner', required=True, index=True,
        default=lambda self: self.env.user.partner_id)
    borrower_name = fields.Char(required=True, readonly=True)
    borrower_phone = fields.Char(required=True)
    request_date = fields.Datetime(
        required=True, default=fields.Datetime.now, index=True)
    borrow_date = fields.Date(
        required=True, default=fields.Date.context_today, index=True)
    due_date = fields.Date(required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, index=True)
    loan_id = fields.Many2one(
        'library.loan', readonly=True, copy=False, ondelete='set null')
    decision_date = fields.Datetime(readonly=True)

    @api.model
    def _library_is_manager(self):
        return (
            self.env.su
            or self.env.user.has_group(
                'library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )

    @api.model
    def submit_for_current_user(
            self, book_id, borrow_date=None, due_date=None,
            borrower_phone=None, payment_method='flutterwave', momo_phone=None,
            payment_reference=None):
        user = self.env.user
        if user._is_public() or not user.partner_id:
            raise AccessError(
                "Sign in with a library account to request a physical book.")
        book = self.env['library.book'].sudo().search([
            ('id', '=', book_id),
            ('active', '=', True),
            ('website_published', '=', True),
        ], limit=1)
        if not book:
            raise UserError("This book is not available in the public catalog.")
        if payment_method != 'flutterwave':
            raise ValidationError("Select a supported payment method.")
        contact_phone = (borrower_phone or '').strip()
        if not contact_phone:
            contact_phone = (user.partner_id.phone or '').strip()
        if not re.fullmatch(r'[0-9+().\-\s]{7,32}', contact_phone):
            raise ValidationError(
                "Enter a valid borrower contact phone number.")
        borrow_date = fields.Date.to_date(
            borrow_date or fields.Date.context_today(self))
        due_date = fields.Date.to_date(
            due_date or borrow_date + timedelta(days=14))
        if due_date < borrow_date:
            raise ValidationError(
                "The expected return date cannot be before the borrowing date.")
        return self.create({
            'book_id': book.id,
            'borrow_date': borrow_date,
            'due_date': due_date,
            'payment_method': payment_method,
            'payment_reference': (payment_reference or '').strip()[:128],
            'borrower_phone': contact_phone,
        })

    @api.model_create_multi
    def create(self, vals_list):
        manager = self._library_is_manager()
        for values in vals_list:
            if not manager:
                partner = self.env.user.partner_id
                if not partner or self.env.user._is_public():
                    raise AccessError(
                        "Sign in to submit a physical book request.")
                values.update({
                    'borrower_id': partner.id,
                    'borrower_name': partner.name,
                    'state': 'pending',
                    'loan_id': False,
                    'payment_status': 'pending',
                    'payment_amount': 6.0,
                })
            book = self.env['library.book'].sudo().browse(
                values.get('book_id')).exists()
            if not book or not book.active:
                raise ValidationError(
                    "Select an active book from the library catalog.")
            if not manager and not book.website_published:
                raise AccessError(
                    "Only books published in the public catalog can be requested.")
            if not values.get('borrower_phone'):
                raise ValidationError(
                    "A borrower phone number is required.")
            if not re.fullmatch(
                    r'[0-9+().\-\s]{7,32}', values['borrower_phone']):
                raise ValidationError(
                    "Enter a valid borrower phone number.")
            values.setdefault('borrower_name', values.get(
                'borrower_id') and self.env[
                    'res.partner'].browse(
                        values['borrower_id']).name)
            values.setdefault('payment_amount', 6.0)
            values.setdefault('due_date', fields.Date.to_date(
                values.get('borrow_date') or fields.Date.context_today(self))
                + timedelta(days=14))
        requests = super().create(vals_list)
        for borrowing_request in requests:
            borrowing_request._check_duplicate_pending()
        return requests

    def _check_duplicate_pending(self):
        for borrowing_request in self.filtered(
                lambda item: item.state == 'pending'):
            if self.search_count([
                    ('book_id', '=', borrowing_request.book_id.id),
                    ('borrower_id', '=', borrowing_request.borrower_id.id),
                    ('state', '=', 'pending'),
                    ('id', '!=', borrowing_request.id),
            ]):
                raise ValidationError(
                    "You already have a pending request for this book.")

    def write(self, vals):
        manager = self._library_is_manager()
        if not manager:
            if set(vals) != {'state'} or vals.get('state') != 'cancelled':
                raise AccessError(
                    "Borrowers can only cancel their own pending requests.")
            if any(
                    item.borrower_id != self.env.user.partner_id
                    or item.state != 'pending' for item in self):
                raise AccessError(
                    "You can only cancel your own pending request.")
        return super().write(vals)

    def action_confirm_payment(self):
        return super().action_confirm_payment()

    def action_reject_payment(self):
        return super().action_reject_payment()

    def action_approve(self):
        if not self._library_is_manager():
            raise AccessError(
                "Only a librarian or administrator can approve requests.")
        for borrowing_request in self:
            if borrowing_request.state != 'pending':
                raise UserError("Only a pending request can be approved.")
            if borrowing_request.payment_status != 'confirmed':
                raise UserError(
                    "Confirm the payment before approving this request.")
            book = borrowing_request.book_id
            self.env.cr.execute(
                "SELECT id FROM library_book WHERE id = %s FOR UPDATE",
                (book.id,))
            book.invalidate_recordset([
                'total_copies', 'lost_copies', 'available_copies',
                'borrowed_copies', 'loan_ids', 'state',
            ])
            if not book.available_copies:
                raise UserError(
                    "No physical copies are available. The request cannot be approved.")
            loan = self.env['library.loan'].create({
                'book_id': book.id,
                'borrower_id': borrowing_request.borrower_id.id,
                'borrow_date': borrowing_request.borrow_date,
                'due_date': borrowing_request.due_date,
                'payment_method': borrowing_request.payment_method,
                'payment_status': 'confirmed',
                'payment_amount': 6.0,
                'payment_reference': borrowing_request.payment_reference,
                'momo_phone': borrowing_request.momo_phone,
            })
            borrowing_request.write({
                'state': 'approved',
                'loan_id': loan.id,
                'decision_date': fields.Datetime.now(),
            })

    def action_reject(self):
        if not self._library_is_manager():
            raise AccessError(
                "Only a librarian or administrator can reject requests.")
        for borrowing_request in self:
            if borrowing_request.state != 'pending':
                raise UserError("Only a pending request can be rejected.")
            borrowing_request.write({
                'state': 'rejected',
                'decision_date': fields.Datetime.now(),
            })
