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
