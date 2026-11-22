"""Bank transfer only: clean up anything Flutterwave left behind.

Safe to run on a database that was on 18.0.2.2.0 or on the short-lived
Flutterwave-plus-bank build (18.0.2.3.0). Payments that were completed keep
their records and receipts.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

_TABLES = (
    'library_ebook_request',
    'library_book_request',
    'library_ebook_reservation',
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cron = env.ref(
        'library_manager.ir_cron_library_flutterwave_reconcile',
        raise_if_not_found=False)
    if cron:
        cron.unlink()
        _logger.info("Removed the Flutterwave reconciliation cron job")
    # Unfinished Flutterwave checkouts can never be completed now.
    stale = env['payment.transaction'].search([
        ('provider_code', '=', 'flutterwave'),
        ('state', 'in', ('draft', 'pending')),
        ('library_payment_record_ref', '!=', False),
    ])
    if stale:
        stale._set_canceled(
            state_message="Flutterwave is no longer used by the library.")
        _logger.info("Cancelled %s unfinished Flutterwave payment(s)",
                     len(stale))
    for table in _TABLES:
        cr.execute("""
            UPDATE %s
               SET payment_method = 'bank'
             WHERE payment_status = 'pending'
               AND payment_transaction_id IS NULL
        """ % table)
