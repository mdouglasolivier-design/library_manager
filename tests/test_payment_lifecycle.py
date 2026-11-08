import uuid

from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from .common import create_test_ebook_file


PASSWORD = 'library-payment-test-password'


def _create_user(env, login, group_xmlids, email=True):
    groups = [env.ref(xmlid).id for xmlid in group_xmlids]
    return env['res.users'].with_context(no_reset_password=True).create({
        'name': login,
        'login': login,
        'password': PASSWORD,
        'email': '%s@example.test' % login if email else False,
        'groups_id': [(6, 0, groups)],
    })


class LibraryPaymentFixtureMixin:
    """Shared helpers: a member, a priced eBook request and a bank transfer."""

    def _setup_payment_fixture(self):
        self.member = _create_user(
            self.env, 'payment-member-%s' % uuid.uuid4().hex[:6],
            ['base.group_portal'])
        self.librarian = _create_user(
            self.env, 'payment-librarian-%s' % uuid.uuid4().hex[:6],
            ['base.group_user', 'library_manager.group_library_librarian'])
        self.ebook = self.env['library.ebook'].create({
            'name': 'Payment Lifecycle eBook',
            'website_published': True,
        })
        create_test_ebook_file(self.env, self.ebook)
        self.provider = self.env.ref('payment.payment_provider_flutterwave')
        self.payment_method = self.env.ref('payment.payment_method_card')

    def _new_request(self, user=None):
        user = user or self.member
        ebook = self.env['library.ebook'].create({
            'name': 'Payment eBook %s' % uuid.uuid4().hex[:6],
            'website_published': True,
        })
        create_test_ebook_file(self.env, ebook)
        return self.env['library.ebook.request'].with_user(user).create({
            'ebook_id': ebook.id,
        }).sudo()

    def _new_transaction(self, request, amount=None):
        transaction = self.env['payment.transaction'].create({
            'provider_id': self.provider.id,
            'payment_method_id': self.payment_method.id,
            'reference': 'LIBTEST-%s' % uuid.uuid4().hex[:10].upper(),
            'amount': (
                request.payment_amount if amount is None else amount),
            'currency_id': request.payment_currency_id.id,
            'partner_id': request.borrower_id.id,
            'operation': 'online_direct',
        })
        return transaction

    def _receipt_mails(self, transaction):
        return self.env['mail.mail'].sudo().search([
            ('email_to', '=', transaction.partner_id.email),
            ('subject', 'ilike', transaction.reference),
        ])


class TestLibraryPaymentLifecycle(
        LibraryPaymentFixtureMixin, TransactionCase):

    def setUp(self):
        super().setUp()
        self._setup_payment_fixture()

    def test_amount_comes_from_configured_price_not_a_constant(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'library_manager.ebook_borrowing_price', '7.25')
        request = self._new_request()

        self.assertEqual(request.payment_amount, 7.25)

    def test_pending_payment_grants_nothing(self):
        request = self._new_request()
        transaction = self._new_transaction(request)
        transaction._library_link_payment_record(request)
        transaction._set_pending()

        self.assertEqual(request.payment_status, 'pending')
        self.assertEqual(request.state, 'pending')
        self.assertFalse(request.loan_id)
        self.assertFalse(self._receipt_mails(transaction))
        with self.assertRaises(UserError):
            request.with_user(self.librarian).action_approve()

    def test_verified_payment_emails_pdf_receipt_once(self):
        request = self._new_request()
        transaction = self._new_transaction(request)
        transaction._library_link_payment_record(request)
        transaction._set_pending()

        transaction._set_done()

        self.assertEqual(request.payment_status, 'confirmed')
        self.assertTrue(transaction.library_receipt_sent)
        mails = self._receipt_mails(transaction)
        self.assertEqual(len(mails), 1)
        self.assertTrue(mails.attachment_ids)
        self.assertTrue(any(
            name.startswith('library-payment-%s' % transaction.reference)
            for name in mails.attachment_ids.mapped('name')))
        self.assertIn(transaction.reference, mails.body_html)
        self.assertIn(request.ebook_id.name, mails.body_html)

    def test_duplicate_notifications_do_not_send_a_second_receipt(self):
        request = self._new_request()
        transaction = self._new_transaction(request)
        transaction._library_link_payment_record(request)
        transaction._set_pending()
        transaction._set_done()

        transaction._set_done()
        transaction._library_send_receipt()
        transaction.write({'state': 'done'})

        self.assertEqual(request.payment_status, 'confirmed')
        self.assertEqual(len(self._receipt_mails(transaction)), 1)

    def test_failed_payment_sends_no_receipt_and_blocks_approval(self):
        request = self._new_request()
        transaction = self._new_transaction(request)
        transaction._library_link_payment_record(request)
        transaction._set_pending()

        transaction._set_error("Provider declined the payment.")

        self.assertEqual(request.payment_status, 'failed')
        self.assertFalse(transaction.library_receipt_sent)
        self.assertFalse(self._receipt_mails(transaction))
        with self.assertRaises(UserError):
            request.with_user(self.librarian).action_approve()

    def test_cancelled_payment_sends_no_receipt(self):
        request = self._new_request()
        transaction = self._new_transaction(request)
        transaction._library_link_payment_record(request)
        transaction._set_pending()

        transaction._set_canceled()

        self.assertEqual(request.payment_status, 'cancelled')
        self.assertFalse(self._receipt_mails(transaction))

    def test_refund_marks_payment_refunded_without_new_receipt(self):
        request = self._new_request()
        transaction = self._new_transaction(request)
        transaction._library_link_payment_record(request)
        transaction._set_pending()
        transaction._set_done()
        refund = self.env['payment.transaction'].create({
            'provider_id': self.provider.id,
            'payment_method_id': self.payment_method.id,
            'reference': 'R-%s' % transaction.reference,
            'amount': -transaction.amount,
            'currency_id': transaction.currency_id.id,
            'partner_id': transaction.partner_id.id,
            'operation': 'refund',
            'source_transaction_id': transaction.id,
        })

        refund._set_pending()
        refund._set_done()

        self.assertEqual(request.payment_status, 'refunded')
        self.assertEqual(len(self._receipt_mails(transaction)), 1)

    def test_member_without_email_is_confirmed_without_error(self):
        member = _create_user(
            self.env, 'payment-no-email-%s' % uuid.uuid4().hex[:6],
            ['base.group_portal'], email=False)
        request = self._new_request(member)
        transaction = self._new_transaction(request)
        transaction._library_link_payment_record(request)
        transaction._set_pending()

        transaction._set_done()

        self.assertEqual(request.payment_status, 'confirmed')
        self.assertFalse(transaction.library_receipt_sent)

    def test_mismatched_amount_cannot_be_linked_to_a_request(self):
        request = self._new_request()
        transaction = self._new_transaction(
            request, amount=request.payment_amount + 1)

        with self.assertRaises(ValidationError):
            transaction._library_link_payment_record(request)

    def test_second_active_transaction_is_rejected(self):
        request = self._new_request()
        first = self._new_transaction(request)
        first._library_link_payment_record(request)
        first._set_pending()
        second = self._new_transaction(request)

        with self.assertRaises(ValidationError):
            second._library_link_payment_record(request)

    def test_approval_after_verified_payment_grants_the_loan(self):
        request = self._new_request()
        transaction = self._new_transaction(request)
        transaction._library_link_payment_record(request)
        transaction._set_pending()
        transaction._set_done()

        request.with_user(self.librarian).action_approve()

        self.assertEqual(request.state, 'approved')
        self.assertTrue(request.loan_id)

    def test_receipt_template_has_no_hardcoded_payment_details(self):
        template = self.env.ref(
            'library_manager.mail_template_library_payment_receipt')

        self.assertEqual(
            template.report_template_ids,
            self.env.ref('library_manager.action_library_payment_receipt'))
        self.assertNotIn('100212701941', template.body_html)


class TestLibraryFlutterwaveFlow(LibraryPaymentFixtureMixin, TransactionCase):

    API = ('odoo.addons.payment_flutterwave.models.payment_provider.'
           'PaymentProvider._flutterwave_make_request')

    def setUp(self):
        super().setUp()
        self._setup_payment_fixture()
        self.request_record = self._new_request()
        self.transaction = self._new_transaction(self.request_record)
        self.transaction._library_link_payment_record(self.request_record)
        self.transaction._set_pending()

    def _verified(self, **overrides):
        data = {
            'id': 987654, 'status': 'successful',
            'tx_ref': self.transaction.reference,
            'amount': self.transaction.amount,
            'currency': self.transaction.currency_id.name,
            'payment_type': 'card', 'card': {'type': 'VISA'},
            'customer': {'email': 'member@example.test'},
        }
        data.update(overrides)
        return {'status': 'success', 'data': data}

    def _notify(self, response):
        with patch(self.API, return_value=response):
            self.env['payment.transaction']._handle_notification_data(
                'flutterwave', {
                    'tx_ref': self.transaction.reference,
                    'status': 'successful'})

    def test_verified_flutterwave_payment_creates_receipt(self):
        self._notify(self._verified())

        self.assertEqual(self.transaction.state, 'done')
        self.assertEqual(self.request_record.payment_status, 'confirmed')
        self.assertEqual(self.request_record.payment_method, 'flutterwave')
        self.assertEqual(self.transaction.provider_reference, '987654')
        self.assertEqual(len(self._receipt_mails(self.transaction)), 1)

    def test_repeated_notification_keeps_a_single_receipt(self):
        self._notify(self._verified())
        self._notify(self._verified())

        self.assertEqual(len(self._receipt_mails(self.transaction)), 1)

    def test_wrong_amount_is_not_accepted(self):
        self._notify(self._verified(amount=self.transaction.amount - 1))

        self.assertEqual(self.transaction.state, 'error')
        self.assertEqual(self.request_record.payment_status, 'failed')
        self.assertFalse(self._receipt_mails(self.transaction))

    def test_wrong_currency_is_not_accepted(self):
        other = 'EUR' if self.transaction.currency_id.name != 'EUR' else 'USD'
        self._notify(self._verified(currency=other))

        self.assertEqual(self.transaction.state, 'error')
        self.assertFalse(self._receipt_mails(self.transaction))

    def test_failed_flutterwave_payment_has_no_receipt(self):
        self._notify(self._verified(status='failed'))

        self.assertEqual(self.request_record.payment_status, 'failed')
        self.assertFalse(self._receipt_mails(self.transaction))

    def test_library_checkout_offers_only_flutterwave(self):
        self.provider.write({
            'state': 'test',
            'flutterwave_public_key': 'FLWPUBK_TEST-x',
            'flutterwave_secret_key': 'FLWSECK_TEST-x',
            'flutterwave_webhook_secret': 'secret-hash',
        })
        other = self.env['payment.provider'].search([
            ('code', '!=', 'flutterwave'),
            ('state', 'in', ('enabled', 'test')),
        ])
        compatible = self.env['payment.provider']._get_compatible_providers(
            self.env.company.id, self.member.partner_id.id, 5.0,
            currency_id=self.request_record.payment_currency_id.id,
            library_checkout=True)
        self.assertEqual(compatible.mapped('code'), ['flutterwave'])
        self.assertFalse(compatible & other)


@tagged('-at_install', 'post_install')
class TestLibraryPaymentReceiptDownload(
        LibraryPaymentFixtureMixin, HttpCase):

    def setUp(self):
        super().setUp()
        self._setup_payment_fixture()
        self.other_member = _create_user(
            self.env, 'payment-other-%s' % uuid.uuid4().hex[:6],
            ['base.group_portal'])
        self.request = self._new_request()
        self.transaction = self._new_transaction(self.request)
        self.transaction._library_link_payment_record(self.request)
        self.transaction._set_pending()
        self.url = '/my/library/payments/%s/receipt' % self.transaction.id

    def test_pending_payment_has_no_downloadable_receipt(self):
        self.authenticate(self.member.login, PASSWORD)

        self.assertEqual(self.url_open(self.url).status_code, 404)

    def test_owner_downloads_receipt_after_verified_payment(self):
        self.transaction._set_done()
        self.authenticate(self.member.login, PASSWORD)

        response = self.url_open(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertIn(
            self.transaction.reference,
            response.headers['Content-Disposition'])

    def test_another_member_cannot_download_the_receipt(self):
        self.transaction._set_done()
        self.authenticate(self.other_member.login, PASSWORD)

        self.assertEqual(self.url_open(self.url).status_code, 404)

    def test_anonymous_visitor_cannot_download_the_receipt(self):
        self.transaction._set_done()

        response = self.url_open(self.url, allow_redirects=False)

        self.assertNotEqual(response.status_code, 200)

    def test_pay_button_with_unpaid_request_goes_to_checkout(self):
        request = self._new_request(self.other_member)
        self.authenticate(self.other_member.login, PASSWORD)
        page = self.url_open(
            '/library/ebooks/%s' % request.ebook_id.id).text

        self.assertIn('library-pay-button', page)
        self.assertIn('/my/library/payment/EREQ/%s' % request.id, page)

    def test_pay_button_with_started_payment_opens_payment_page(self):
        self.authenticate(self.member.login, PASSWORD)
        page = self.url_open(
            '/library/ebooks/%s' % self.request.ebook_id.id).text

        self.assertIn('library-pay-button', page)
        self.assertIn('href="/my/library/payments"', page)

    def test_pay_button_without_request_starts_one(self):
        self.authenticate(self.member.login, PASSWORD)
        page = self.url_open('/library/ebooks/%s' % self.ebook.id).text

        self.assertIn('library-pay-button', page)
        self.assertIn(
            '/my/library/ebooks/%s/request' % self.ebook.id, page)

    def test_pay_button_for_visitor_asks_to_sign_in(self):
        page = self.url_open('/library/ebooks/%s' % self.ebook.id).text

        self.assertIn('library-pay-button', page)
        self.assertIn('/web/login?redirect=/library/ebooks/', page)

    def test_failed_payment_can_be_retried_from_the_pay_button(self):
        self.transaction._set_error("Provider declined the payment.")
        self.assertEqual(self.request.payment_status, 'failed')
        self.authenticate(self.member.login, PASSWORD)
        page = self.url_open(
            '/library/ebooks/%s' % self.request.ebook_id.id).text
        self.assertIn(
            '/my/library/payment/EREQ/%s' % self.request.id, page)

        response = self.url_open(
            '/my/library/payment/EREQ/%s' % self.request.id,
            allow_redirects=False)

        self.assertIn('/payment/pay', response.headers.get('Location', ''))
        self.request.invalidate_recordset()
        self.assertEqual(self.request.payment_status, 'pending')

    def test_book_without_reading_file_shows_a_disabled_pay_button(self):
        ebook = self.env['library.ebook'].create({
            'name': 'No File Yet', 'website_published': True})
        self.authenticate(self.member.login, PASSWORD)
        page = self.url_open('/library/ebooks/%s' % ebook.id).text

        self.assertIn('library-pay-button--disabled', page)
        self.assertNotIn(
            '/my/library/ebooks/%s/request' % ebook.id, page)
