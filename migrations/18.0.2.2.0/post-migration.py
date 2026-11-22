"""Move the library from Flutterwave to Odoo bank transfer (Wire Transfer).

Nothing is deleted. Payments already made keep their original method label;
only requests still waiting for checkout (no transaction yet) switch to bank
transfer.
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
    for table in _TABLES:
        cr.execute("""
            UPDATE %s
               SET payment_method = 'bank'
             WHERE payment_status = 'pending'
               AND payment_transaction_id IS NULL
        """ % table)
        _logger.info("%s: %s pending request(s) set to bank transfer",
                     table, cr.rowcount)
