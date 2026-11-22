# Payment setup (bank transfer)

The library takes every payment by **bank transfer** through Odoo's built-in
**Wire Transfer** payment provider. Members never type card numbers or PINs on
the website and nobody uploads proof of payment. After a member requests a
book, the website shows your bank details and a payment reference. When you
see the money in your bank account, a librarian confirms it in Odoo and the
receipt is created and emailed automatically.

## 1. Enable Wire Transfer

1. Open **Apps**, search for **Payment Provider: Custom Payment Modes**
   (`payment_custom`). It is installed automatically with the library module.
2. Open **Settings -> Technical -> Payment Providers** (turn on developer mode
   if you do not see Technical) and open **Wire Transfer**. Without the
   Invoicing app, use that path; with it, use Invoicing -> Configuration ->
   Payment Providers.
3. Set the state to **Enabled**.
4. On the **Messages** tab, edit the **Pending Message**. This text is shown to
   the member after they request a book, so put your real bank details in it:
   bank name, account name, account number, and an instruction to quote the
   payment reference on the transfer.
5. Save.

## 2. Currency and price

In **Settings -> Library** set the eBook and physical book prices and the
payment currency (for example RWF or USD). Rwandan francs have no decimals.

## 3. Confirming a payment

1. Check your bank statement for the transfer and its payment reference.
2. Open **Odoo Library -> Payment Review** and choose the matching list
   (eBook or Physical Book Payment Requests), then open the request.
3. Click **Confirm Payment**. Odoo marks the transaction done, shows the
   receipt on the member's **Payments** page and emails the PDF receipt.
4. Click **Reject Payment** if the money never arrived.
5. For a physical book, click **Approve** afterwards to create the loan.

## Notes

- Bank transfers cannot be confirmed automatically: Odoo does not see your
  bank account, so a librarian must confirm each transfer.
- A receipt is only ever created for a payment a librarian confirmed.
- Payments made earlier with Flutterwave keep their records and receipts.
