from odoo import fields, models
from odoo.exceptions import AccessError, UserError


class LibraryPaymentMixin(models.AbstractModel):
    _name = 'library.payment.mixin'
    _description = 'Library Manual Payment Tracking'

    payment_method = fields.Selection([
        ('momo', 'MTN Mobile Money'),
        ('bank', 'Bank transfer'),
        ('external_card', 'External card provider'),
    ], string='Payment Method', default='momo', required=True, index=True)
    payment_status = fields.Selection([
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('rejected', 'Rejected'),
    ], string='Payment Status', default='pending', required=True, index=True)
    payment_amount = fields.Float(
        string='Amount (USD)', digits=(12, 2), readonly=True)
    payment_reference = fields.Char(
        string='Payment Reference', copy=False,
        help='Reference or transaction ID only. Never enter card numbers or PINs.')
    momo_phone = fields.Char(
        string='MTN MoMo Phone', copy=False,
        help='The borrower phone number used for a MoMo payment.')

    def write(self, vals):
        if 'payment_status' in vals and not self.env.context.get(
                '_library_payment_action'):
            if not self._library_can_verify_payment():
                raise AccessError(
                    "Only a librarian or administrator can verify payments.")
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
            record.with_context(_library_payment_action=True).write({
                'payment_status': 'rejected',
            })
