from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    library_ebook_approval_required = fields.Boolean(
        string='Require librarian approval',
        default=True,
        config_parameter='library_manager.ebook_approval_required')
    library_ebook_loan_duration_days = fields.Integer(
        string='eBook loan duration (days)',
        default=14,
        config_parameter='library_manager.ebook_loan_duration_days')
    library_ebook_max_active_loans = fields.Integer(
        string='Maximum active eBook loans per member',
        default=0,
        config_parameter='library_manager.ebook_max_active_loans',
        help='Use 0 for no limit.')
    library_ebook_max_concurrent_loans = fields.Integer(
        string='Maximum concurrent loans per eBook',
        default=0,
        config_parameter='library_manager.ebook_max_concurrent_loans',
        help='Use 0 for no limit.')
    library_momo_recipient_name = fields.Char(
        string='MTN MoMo merchant name',
        default='Odoo Library',
        config_parameter='library_manager.momo_recipient_name')
    library_momo_recipient_phone = fields.Char(
        string='MTN MoMo merchant phone',
        default='+250791393885',
        config_parameter='library_manager.momo_recipient_phone')
    library_bank_account_number = fields.Char(
        string='Bank account number',
        default='100212701941',
        config_parameter='library_manager.bank_account_number')
    library_bank_name = fields.Char(
        string='Bank name',
        config_parameter='library_manager.bank_name')
    library_bank_account_holder = fields.Char(
        string='Bank account holder',
        config_parameter='library_manager.bank_account_holder')
    library_external_card_instructions = fields.Char(
        string='External card payment instructions',
        default='Configure a secure payment provider before enabling card payments.',
        config_parameter='library_manager.external_card_instructions')
    library_ebook_borrowing_price = fields.Float(
        string='eBook borrowing price',
        default=5.0,
        digits=(12, 2),
        config_parameter='library_manager.ebook_borrowing_price')
    library_physical_borrowing_price = fields.Float(
        string='Physical book borrowing price',
        default=6.0,
        digits=(12, 2),
        config_parameter='library_manager.physical_borrowing_price')
    library_payment_currency = fields.Char(
        string='Borrowing currency code',
        default='USD',
        config_parameter='library_manager.payment_currency')

    @api.model
    def _library_approval_required(self):
        value = self.env['ir.config_parameter'].sudo().get_param(
            'library_manager.ebook_approval_required', 'True')
        return value.lower() not in ('false', '0', 'no')

    @api.constrains(
        'library_ebook_loan_duration_days',
        'library_ebook_max_active_loans',
        'library_ebook_max_concurrent_loans')
    def _check_ebook_lending_policy(self):
        for settings in self:
            if settings.library_ebook_loan_duration_days < 1:
                raise ValidationError(
                    "The eBook loan duration must be at least one day.")
            if settings.library_ebook_max_active_loans < 0:
                raise ValidationError(
                    "The active eBook loan limit cannot be negative.")
            if settings.library_ebook_max_concurrent_loans < 0:
                raise ValidationError(
                    "The concurrent eBook loan limit cannot be negative.")

    @api.constrains(
        'library_ebook_borrowing_price',
        'library_physical_borrowing_price',
        'library_payment_currency')
    def _check_library_payment_settings(self):
        for settings in self:
            if (
                    settings.library_ebook_borrowing_price <= 0
                    or settings.library_physical_borrowing_price <= 0):
                raise ValidationError(
                    "Library borrowing prices must be greater than zero.")
            currency_code = (settings.library_payment_currency or '').strip().upper()
            if len(currency_code) != 3 or not currency_code.isalpha():
                raise ValidationError(
                    "Enter a valid three-letter currency code.")
            currency = self.env['res.currency'].search([
                ('name', '=', currency_code),
                ('active', '=', True),
            ], limit=1)
            if not currency:
                raise ValidationError(
                    "The library payment currency must be an active Odoo currency.")
