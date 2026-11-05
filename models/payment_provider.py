from odoo import models


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    def _get_compatible_providers(
            self, company_id, partner_id, amount, currency_id=None,
            force_tokenization=False, is_express_checkout=False,
            is_validation=False, report=None, **kwargs):
        providers = super()._get_compatible_providers(
            company_id, partner_id, amount,
            currency_id=currency_id,
            force_tokenization=force_tokenization,
            is_express_checkout=is_express_checkout,
            is_validation=is_validation,
            report=report,
            **kwargs)
        if kwargs.get('library_checkout'):
            providers = providers.filtered(
                lambda provider: (
                    provider.code == 'stripe'
                    or (
                        provider.code == 'custom'
                        and provider.custom_mode == 'wire_transfer'
                    )
                ))
        return providers
