import logging

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


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
    library_receipt_sent = fields.Boolean(
        string='Library Receipt Emailed',
        copy=False,
        readonly=True,
        help='Set once the PDF receipt email has been queued, so duplicate '
             'provider notifications never send a second receipt.',
    )
    library_receipt_item = fields.Char(
        string='Library Item',
        compute='_compute_library_receipt_item',
    )

    @api.depends('library_payment_record_ref')
    def _compute_library_receipt_item(self):
        for transaction in self:
            record = transaction.library_payment_record_ref
            item = False
            if record:
                record = record.sudo()
                if 'ebook_id' in record._fields and record.ebook_id:
                    item = record.ebook_id.name
                elif 'book_id' in record._fields and record.book_id:
                    item = record.book_id.name
            transaction.library_receipt_item = item

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
            if status == 'confirmed':
                transaction._library_send_receipt()

    def _library_send_receipt(self):
        """Queue the PDF receipt email once per verified library payment."""
        template = self.env.ref(
            'library_manager.mail_template_library_payment_receipt',
            raise_if_not_found=False)
        if not template:
            return
        for transaction in self:
            if (
                    transaction.library_receipt_sent
                    or transaction.state != 'done'
                    or transaction.operation == 'refund'
                    or not transaction.library_payment_record_ref):
                continue
            email = (transaction.partner_id.email or '').strip()
            if not email:
                _logger.info(
                    "Receipt for transaction %s was not emailed because "
                    "partner %s has no email address.",
                    transaction.reference, transaction.partner_id.id)
                continue
            mail_id = template.sudo().send_mail(
                transaction.id,
                force_send=False,
                email_values={'email_to': email},
            )
            if mail_id:
                transaction.sudo().write({'library_receipt_sent': True})
            else:
                _logger.warning(
                    "Receipt email was not queued for transaction %s.",
                    transaction.reference)

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
