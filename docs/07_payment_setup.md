# Payment setup (Flutterwave)

The library takes every payment through **Flutterwave** (bank cards and mobile
money). Members pay on Flutterwave's secure page; card numbers and mobile money
PINs are never typed into, or stored by, the library website. Nobody uploads
proof of payment: when Flutterwave confirms a payment, Odoo marks it paid,
creates the receipt, shows it on the member's **Payments** page and emails the
PDF.

## 1. Flutterwave account

1. Create a Flutterwave merchant account and stay in **test mode** first.
2. In the Flutterwave dashboard: Settings -> API keys. Copy the **public key**
   and **secret key**.
3. Settings -> Webhooks. Set the URL to
   `https://YOUR-SITE/payment/flutterwave/webhook` and choose a **secret hash**
   (any long random text). Keep it for the next step.

Flutterwave must be able to reach your site over the internet for webhooks.
Without that (for example on a home computer) payments are still confirmed when
the member returns to the site, but not if they close the page early.

## 2. Odoo

1. Open **Flutterwave** under Payment Providers. Without the Invoicing app, use
   `http://localhost:8069/odoo/action-payment.action_payment_provider`.
2. On the Credentials tab paste the public key, secret key and the webhook
   secret hash.
3. Payment methods: keep **Card** and **MTN Mobile Money (Rwanda)** ticked. Untick
   any you do not want (for example M-Pesa).
4. Set the state to **Test Mode**, save, and try a payment with Flutterwave's
   test cards. When ready for real money use live keys and set **Enabled**.

## 3. Library settings

In **Settings -> Library** set the eBook and physical book prices and the
currency code. The currency must be active in Odoo and supported by
Flutterwave (for example RWF or USD). Rwandan francs have no decimals.

## 4. What members see

- **Checkout** shows only Flutterwave.
- **My Library -> Payments** lists each payment. As soon as one is confirmed the
  **Receipt (PDF)** and **View** buttons appear. The PDF is also emailed once.
- A receipt is only ever created for a payment Flutterwave has verified. Odoo
  re-checks every payment with Flutterwave's API before accepting it.

The member needs an email address on their account and Odoo needs an outgoing
mail server (Settings -> Technical -> Outgoing Mail Servers) for the email.
