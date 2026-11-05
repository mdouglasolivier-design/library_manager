import base64
import re
import urllib.parse

from odoo import http
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers.portal import PaymentPortal
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


_CHECKOUT_RECORDS = {
    'EREQ': 'library.ebook.request',
    'BREQ': 'library.book.request',
    'ERES': 'library.ebook.reservation',
}
_PAYMENT_RECORD_MODELS = tuple(_CHECKOUT_RECORDS.values()) + (
    'library.ebook.loan',
    'library.loan',
)


class LibraryPaymentPortal(PaymentPortal):

    def _get_extra_payment_form_values(self, **kwargs):
        values = super()._get_extra_payment_form_values(**kwargs)
        reference_prefix = kwargs.get('reference_prefix', '')
        match = re.fullmatch(
            r'LIBRARY-(EREQ|BREQ|ERES)-([1-9][0-9]*)',
            reference_prefix)
        if not match:
            return values
        model = _CHECKOUT_RECORDS[match.group(1)]
        payment = request.env[model].sudo().search([
            ('id', '=', int(match.group(2))),
            ('borrower_id', '=', request.env.user.partner_id.id),
        ], limit=1)
        if not payment:
            return values
        if model == 'library.book.request':
            title = payment.book_id.name
        else:
            title = payment.ebook_id.name
        values.update({
            'library_checkout_payment': {
                'title': title,
                'borrower': payment.borrower_id,
                'amount': payment.payment_amount,
                'currency': payment.payment_currency_id,
            },
            'library_no_payment_providers': not bool(
                kwargs.get('providers_sudo')),
        })
        return values

    def _create_transaction(
            self, provider_id, payment_method_id, token_id, amount,
            currency_id, partner_id, flow, tokenization_requested,
            landing_route, reference_prefix=None, is_validation=False,
            custom_create_values=None, **kwargs):
        match = re.fullmatch(
            r'LIBRARY-(EREQ|BREQ|ERES)-([1-9][0-9]*)',
            reference_prefix or '')
        if not match:
            return super()._create_transaction(
                provider_id, payment_method_id, token_id, amount,
                currency_id, partner_id, flow, tokenization_requested,
                landing_route, reference_prefix=reference_prefix,
                is_validation=is_validation,
                custom_create_values=custom_create_values, **kwargs)

        model = _CHECKOUT_RECORDS[match.group(1)]
        payment = request.env[model].sudo().browse(
            int(match.group(2))).exists()
        if (
                not payment
                or request.env.user._is_public()
                or payment.borrower_id != request.env.user.partner_id
                or payment.payment_status != 'pending'):
            raise AccessError("This library payment is unavailable.")
        if (
                payment.payment_transaction_id
                and payment.payment_transaction_id.state
                not in ('cancel', 'error')):
            raise ValidationError(
                "A payment transaction is already active for this request.")
        currency = request.env['res.currency'].sudo().browse(
            currency_id).exists()
        if (
                not currency
                or currency != payment.payment_currency_id
                or currency.compare_amounts(
                    amount, payment.payment_amount) != 0
                or partner_id != payment.borrower_id.id):
            raise ValidationError(
                "The checkout amount, currency, or borrower does not match "
                "the library request.")
        provider = request.env['payment.provider'].sudo().browse(
            provider_id).exists()
        if not provider or provider.state not in ('enabled', 'test'):
            raise ValidationError("Select an enabled payment provider.")
        if (
                provider.code == 'custom'
                and provider.custom_mode == 'wire_transfer'):
            method = 'bank'
        elif provider.code == 'stripe':
            method = 'card'
        else:
            raise ValidationError(
                "This provider is not supported by the library checkout.")

        payment_method = request.env['payment.method'].sudo().browse(
            payment_method_id).exists()
        if not payment_method or provider not in payment_method.provider_ids:
            raise ValidationError(
                "The selected payment method is not enabled for this provider.")

        tx = super()._create_transaction(
            provider_id, payment_method_id, token_id, amount,
            currency_id, partner_id, flow, tokenization_requested,
            landing_route, reference_prefix=reference_prefix,
            is_validation=is_validation,
            custom_create_values=custom_create_values, **kwargs)
        tx._library_link_payment_record(payment)
        payment.sudo().write({'payment_method': method})
        return tx

    @staticmethod
    def _update_landing_route(tx_sudo, access_token):
        if tx_sudo.library_payment_record_ref:
            tx_sudo.landing_route = (
                '/my/library/payment-confirmation?tx_id=%s&access_token=%s'
                % (tx_sudo.id, urllib.parse.quote(access_token)))
            return
        PaymentPortal._update_landing_route(tx_sudo, access_token)

    def _owned_payment(self, model, record_id):
        if model not in _PAYMENT_RECORD_MODELS:
            raise AccessError("Unsupported library payment record.")
        return request.env[model].sudo().search([
            ('id', '=', record_id),
            ('borrower_id', '=', request.env.user.partner_id.id),
        ], limit=1)

    @http.route(
        '/my/library/payment/<string:record_key>/<int:record_id>',
        type='http', auth='user', website=True, sitemap=False)
    def library_payment_checkout(self, record_key, record_id, **kwargs):
        model = _CHECKOUT_RECORDS.get(record_key.upper())
        payment = self._owned_payment(model, record_id) if model else False
        if not payment:
            return request.not_found()
        if payment.payment_status != 'pending':
            request.session['library_portal_notice'] = {
                'message': "This payment is no longer pending.",
                'level': 'info',
            }
            return request.redirect('/my/library/payments')
        company = request.env.company
        partner = request.env.user.partner_id
        access_token = payment_utils.generate_access_token(
            partner.id,
            payment.payment_amount,
            payment.payment_currency_id.id)
        params = {
            'reference': 'LIBRARY-%s-%s' % (record_key.upper(), payment.id),
            'amount': payment.payment_amount,
            'currency_id': payment.payment_currency_id.id,
            'partner_id': partner.id,
            'company_id': company.id,
            'access_token': access_token,
            'library_checkout': '1',
        }
        return request.redirect('/payment/pay?%s' % urllib.parse.urlencode(params))

    @http.route(
        '/my/library/payments', type='http', auth='user',
        website=True, sitemap=False)
    def library_payment_history(self, **kwargs):
        partner_id = request.env.user.partner_id.id
        payments = []
        for model in _PAYMENT_RECORD_MODELS:
            records = request.env[model].sudo().search([
                ('borrower_id', '=', partner_id),
                ('payment_transaction_id', '!=', False),
            ], order='create_date desc, id desc', limit=100)
            payments.extend(records)
        payments.sort(
            key=lambda payment: (
                payment.payment_transaction_id.create_date
                or payment.create_date),
            reverse=True)
        return request.render('library_manager.portal_library_payments', {
            'payments': payments[:100],
            'notice': request.session.pop('library_portal_notice', False),
            'is_public': False,
        })

    @http.route(
        '/my/library/payment-confirmation', type='http',
        auth='public', website=True, sitemap=False)
    def library_payment_confirmation(self, tx_id, access_token, **kwargs):
        try:
            tx_id = int(tx_id)
        except (TypeError, ValueError):
            return request.not_found()
        tx = request.env['payment.transaction'].sudo().browse(tx_id).exists()
        if (
                not tx
                or not tx.library_payment_record_ref
                or not payment_utils.check_access_token(
                    access_token, tx.partner_id.id, tx.amount,
                    tx.currency_id.id)):
            return request.not_found()
        return request.render(
            'library_manager.portal_library_payment_confirmation', {
                'tx': tx,
                'payment': tx.library_payment_record_ref,
                'is_public': request.env.user._is_public(),
            })

    @http.route(
        '/my/library/payment/<string:model>/<int:record_id>/evidence',
        type='http', auth='user', website=True, methods=['POST'],
        csrf=True, sitemap=False)
    def upload_bank_evidence(self, model, record_id, **kwargs):
        payment = self._owned_payment(model, record_id)
        if not payment:
            return request.not_found()
        evidence = request.httprequest.files.get('payment_evidence')
        try:
            if not evidence:
                raise ValidationError("Choose a payment evidence file.")
            content = evidence.read(5 * 1024 * 1024 + 1)
            if len(content) > 5 * 1024 * 1024:
                raise ValidationError(
                    "Payment evidence must not exceed 5 MB.")
            payment._library_submit_bank_evidence(
                evidence.filename, base64.b64encode(content))
        except (AccessError, UserError, ValidationError) as error:
            request.session['library_portal_notice'] = {
                'message': str(error), 'level': 'warning',
            }
        else:
            request.session['library_portal_notice'] = {
                'message': (
                    "Your evidence was submitted. A librarian must verify "
                    "the funds before the borrowing request can be approved."),
                'level': 'info',
            }
        return request.redirect('/my/library/payments')

    @http.route(
        '/my/library/payments/<int:tx_id>/receipt', type='http',
        auth='user', website=True, sitemap=False)
    def library_payment_receipt(self, tx_id, **kwargs):
        tx = request.env['payment.transaction'].sudo().search([
            ('id', '=', tx_id),
            ('partner_id', '=', request.env.user.partner_id.id),
            ('library_payment_record_ref', '!=', False),
            ('state', '=', 'done'),
        ], limit=1)
        if not tx:
            return request.not_found()
        pdf, _content_type = request.env.ref(
            'library_manager.action_library_payment_receipt'
        ).sudo()._render_qweb_pdf(
            'library_manager.action_library_payment_receipt',
            res_ids=tx.ids)
        filename = 'library-payment-%s.pdf' % tx.reference
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ('Cache-Control', 'private, no-store'),
            ('X-Content-Type-Options', 'nosniff'),
        ])
