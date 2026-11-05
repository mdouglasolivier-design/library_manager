from odoo import api, fields, models
from odoo.exceptions import ValidationError


_LIBRARY_PAYMENT_RECORD_MODELS = [
    ('library.ebook.request', 'eBook request'),
    ('library.book.request', 'Physical book request'),
    ('library.ebook.reservation', 'eBook reservation'),
    ('library.ebook.loan', 'eBook loan'),
    ('library.loan', 'Physical book loan'),
]


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    library_payment_record_ref = fields.Reference(
        string='Library Payment',
        selection=_LIBRARY_PAYMENT_RECORD_MODELS,
        copy=False,
        index=True,
        readonly=True,
    )

    @api.constrains(
        'library_payment_record_ref', 'partner_id', 'amount', 'currency_id')
    def _check_library_payment_values(self):
        for transaction in self.filtered('library_payment_record_ref'):
            payment = transaction.library_payment_record_ref
            if (
                    payment.borrower_id != transaction.partner_id
                    or payment.payment_currency_id != transaction.currency_id
                    or transaction.currency_id.compare_amounts(
                        transaction.amount, payment.payment_amount) != 0):
                raise ValidationError(
                    "The transaction partner, amount, and currency must match "
                    "the linked library payment.")

    def write(self, vals):
        result = super().write(vals)
        if 'state' in vals or 'library_payment_record_ref' in vals:
            self._sync_library_payment_status()
        return result

    def _sync_library_payment_status(self):
        for transaction in self:
            payment = transaction.library_payment_record_ref
            if not payment and transaction.source_transaction_id:
                payment = (
                    transaction.source_transaction_id.library_payment_record_ref)
            if not payment:
                continue
            if transaction.operation == 'refund' and transaction.state == 'done':
                status = 'refunded'
            else:
                status = {
                    'pending': 'pending',
                    'authorized': 'authorized',
                    'done': 'confirmed',
                    'error': 'failed',
                    'cancel': 'cancelled',
                }.get(transaction.state)
            if status and payment.payment_status != status:
                payment.sudo().with_context(
                    _library_payment_action=True).write({
                        'payment_status': status,
                    })

    def _library_link_payment_record(self, payment):
        self.ensure_one()
        if payment.payment_transaction_id and (
                payment.payment_transaction_id.state
                not in ('cancel', 'error')):
            raise ValidationError(
                "A payment transaction is already active for this request.")
        if payment.payment_status != 'pending':
            raise ValidationError(
                "Only a pending library payment can start checkout.")
        if (
                payment.borrower_id != self.partner_id
                or payment.payment_currency_id != self.currency_id
                or self.currency_id.compare_amounts(
                    self.amount, payment.payment_amount) != 0):
            raise ValidationError(
                "The payment transaction does not match the library request.")
        self.sudo().write({
            'library_payment_record_ref': '%s,%s' % (payment._name, payment.id),
        })
        payment.sudo().write({
            'payment_transaction_id': self.id,
            'payment_reference': self.reference,
            'payment_method': (
                'bank' if self.provider_code == 'custom' else 'card'),
        })
