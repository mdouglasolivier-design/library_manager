import re
import uuid

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


LIBRARY_PAYMENT_RECORD_MODELS = (
    'library.ebook.request',
    'library.book.request',
    'library.ebook.reservation',
    'library.ebook.loan',
    'library.loan',
)


class LibraryPaymentMixin(models.AbstractModel):
    _name = 'library.payment.mixin'
    _description = 'Library Payment'

    payment_method = fields.Selection([
        ('momo', 'MTN Mobile Money'),
        ('bank', 'Bank transfer'),
        ('card', 'Bank card'),
        ('external_card', 'External card provider'),
    ], string='Payment Method', default='momo', required=True, index=True)
    payment_status = fields.Selection([
        ('pending', 'Pending'),
        ('authorized', 'Authorized'),
        ('confirmed', 'Successful'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('rejected', 'Rejected'),
    ], string='Payment Status', default='pending', required=True, index=True)
    payment_amount = fields.Monetary(
        string='Amount', currency_field='payment_currency_id',
        digits=(12, 2), readonly=True)
    payment_currency_id = fields.Many2one(
        'res.currency', string='Payment Currency', readonly=True,
        default=lambda self: self._library_payment_currency())
    payment_reference = fields.Char(
        string='Payment Reference', copy=False,
        help='Reference or transaction ID only. Never enter card numbers or PINs.')
    payment_transaction_id = fields.Many2one(
        'payment.transaction', string='Online Transaction',
        readonly=True, copy=False, ondelete='set null', index=True)
    payment_evidence = fields.Binary(
        string='Bank Transfer Evidence', attachment=True, copy=False,
        groups='library_manager.group_library_librarian,base.group_system')
    payment_evidence_filename = fields.Char(
        string='Evidence Filename', copy=False,
        groups='library_manager.group_library_librarian,base.group_system')
    momo_phone = fields.Char(
        string='MTN MoMo Phone', copy=False,
        help='The borrower phone number used for a MoMo payment.')

    @api.model
    def _library_payment_currency(self):
        code = self.env['ir.config_parameter'].sudo().get_param(
            'library_manager.payment_currency', 'USD')
        currency = self.env['res.currency'].sudo().search([
            ('name', '=', code),
            ('active', '=', True),
        ], limit=1)
        if not currency:
            raise ValidationError(
                "The configured library payment currency is not active.")
        return currency.id

    @api.model
    def _library_service_price(self, service):
        setting_by_service = {
            'ebook': 'library_manager.ebook_borrowing_price',
            'physical': 'library_manager.physical_borrowing_price',
        }
        try:
            parameter = setting_by_service[service]
        except KeyError as error:
            raise ValidationError("Unsupported library payment service.") from error
        raw_amount = self.env['ir.config_parameter'].sudo().get_param(
            parameter, '5.00' if service == 'ebook' else '6.00')
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                "The configured library borrowing price is invalid.") from error
        if amount <= 0:
            raise ValidationError(
                "The configured library borrowing price must be greater than zero.")
        currency = self.env['res.currency'].sudo().browse(
            self._library_payment_currency())
        return currency.round(amount)

    @api.model_create_multi
    def create(self, vals_list):
        service_by_model = {
            'library.ebook.request': 'ebook',
            'library.ebook.reservation': 'ebook',
            'library.ebook.loan': 'ebook',
            'library.book.request': 'physical',
            'library.loan': 'physical',
        }
        service = service_by_model.get(self._name)
        if service:
            currency_id = self._library_payment_currency()
            amount = self._library_service_price(service)
            for vals in vals_list:
                vals['payment_currency_id'] = currency_id
                vals['payment_amount'] = amount
        return super().create(vals_list)

    def write(self, vals):
        if 'payment_status' in vals and not self.env.context.get(
                '_library_payment_action'):
            if not self._library_can_verify_payment():
                raise AccessError(
                    "Only a librarian or administrator can verify payments.")
        if {'payment_transaction_id', 'payment_amount',
                'payment_currency_id'} & vals.keys():
            if not (
                    self.env.su
                    or self.env.user.has_group(
                        'library_manager.group_library_librarian')
                    or self.env.user.has_group('base.group_system')):
                raise AccessError(
                    "Only authorized staff can change transaction details.")
        return super().write(vals)

    def _library_can_verify_payment(self):
        return (
            self.env.su
            or self.env.user.has_group(
                'library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )

    def action_confirm_payment(self):
        for record in self:
            if not record._library_can_verify_payment():
                raise AccessError(
                    "Only a librarian or administrator can confirm payment.")
            if record.payment_status != 'pending':
                raise UserError("Only a pending payment can be confirmed.")
            transaction = record.payment_transaction_id
            if transaction:
                if (
                        record.payment_method != 'bank'
                        or transaction.provider_code != 'custom'
                        or transaction.state != 'pending'):
                    raise UserError(
                        "Online payment can only be confirmed by its verified provider.")
                if not record.payment_evidence:
                    raise UserError(
                        "Attach bank-transfer evidence before reconciliation.")
                if (
                        transaction.partner_id != record.borrower_id
                        or transaction.currency_id != record.payment_currency_id
                        or transaction.currency_id.compare_amounts(
                            transaction.amount, record.payment_amount) != 0):
                    raise ValidationError(
                        "The bank transaction does not match this library payment.")
                transaction._set_done(
                    state_message="Bank transfer verified by authorized library staff.")
                return
            record.with_context(_library_payment_action=True).write({
                'payment_status': 'confirmed',
            })

    def action_reject_payment(self):
        for record in self:
            if not record._library_can_verify_payment():
                raise AccessError(
                    "Only a librarian or administrator can reject payment.")
            if record.payment_status != 'pending':
                raise UserError("Only a pending payment can be rejected.")
            transaction = record.payment_transaction_id
            if transaction and transaction.state in ('draft', 'pending', 'authorized'):
                transaction._set_canceled(
                    state_message="Library staff rejected the bank transfer.")
            record.with_context(_library_payment_action=True).write({
                'payment_status': 'rejected',
            })

    def _library_submit_bank_evidence(self, filename, content):
        self.ensure_one()
        if self.borrower_id != self.env.user.partner_id:
            raise AccessError("You can only submit evidence for your own payment.")
        if self.payment_method != 'bank':
            raise UserError("Payment evidence is only accepted for bank transfers.")
        if self.payment_status != 'pending':
            raise UserError("Evidence can only be submitted for a pending payment.")
        if not self.payment_transaction_id or (
                self.payment_transaction_id.provider_code != 'custom'
                or self.payment_transaction_id.state != 'pending'):
            raise UserError(
                "Start a bank-transfer checkout before uploading payment evidence.")
        if not filename or len(filename) > 255:
            raise ValidationError("Choose a valid evidence filename.")
        extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if extension not in ('pdf', 'png', 'jpg', 'jpeg'):
            raise ValidationError(
                "Payment evidence must be a PDF, PNG, or JPEG file.")
        if not content or len(content) > 5 * 1024 * 1024:
            raise ValidationError(
                "Payment evidence must be between 1 byte and 5 MB.")
        self.sudo().write({
            'payment_evidence': content,
            'payment_evidence_filename': filename,
        })

    def _library_checkout_reference(self):
        self.ensure_one()
        return "LIB-%s-%s-%s" % (
            self._name.replace('.', '-').upper(),
            self.id,
            uuid.uuid4().hex[:8].upper(),
        )

    def _library_get_payment_record(self, model, record_id):
        if model not in LIBRARY_PAYMENT_RECORD_MODELS:
            raise ValidationError("Unsupported library payment record.")
        record = self.env[model].sudo().browse(record_id).exists()
        if not record or record.borrower_id != self.env.user.partner_id:
            raise AccessError("You can only access your own library payments.")
        return record
