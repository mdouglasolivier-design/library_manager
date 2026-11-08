"""Move the library to Flutterwave-only payments.

Nothing is deleted. Payments already made keep their original method label;
only requests that are still waiting for checkout (no transaction yet) switch
to Flutterwave, and the old manual bank / MoMo settings are removed.
"""
import logging

_logger = logging.getLogger(__name__)

_TABLES = (
    'library_ebook_request',
    'library_book_request',
    'library_ebook_reservation',
)
_OLD_SETTINGS = (
    'library_manager.momo_recipient_name',
    'library_manager.momo_recipient_phone',
    'library_manager.bank_account_number',
    'library_manager.bank_name',
    'library_manager.bank_account_holder',
    'library_manager.external_card_instructions',
)


def migrate(cr, version):
    for table in _TABLES:
        cr.execute("""
            UPDATE %s
               SET payment_method = 'flutterwave'
             WHERE payment_status = 'pending'
               AND payment_transaction_id IS NULL
        """ % table)
        _logger.info("%s: %s pending request(s) set to Flutterwave",
                     table, cr.rowcount)
    cr.execute(
        "DELETE FROM ir_config_parameter WHERE key = ANY(%s)",
        (list(_OLD_SETTINGS),))
