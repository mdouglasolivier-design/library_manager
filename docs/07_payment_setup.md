# Payment setup

The library offers two ways to pay, for eBooks and physical books alike.

## Card / mobile money (Flutterwave) - automatic
1. Payment Providers > Flutterwave: add your public key, secret key and secret hash, set state to Test or Enabled.
2. When the member pays, Odoo verifies the payment with Flutterwave, marks it paid, and the receipt can be downloaded at once. A 5-minute cron and the payment pages also re-check unfinished payments, so it works even when the webhook cannot reach a local server.
3. Webhooks need a public address; on localhost the return-page check does the job.

## Bank transfer (Wire Transfer) - librarian confirms
1. Payment Providers > Wire Transfer: enable it and put your bank details in the Pending Message.
2. The payment stays Pending until a librarian clicks Confirm Payment. Odoo cannot see your bank account, so this can never be automatic.

Payments made earlier keep their records and receipts.
