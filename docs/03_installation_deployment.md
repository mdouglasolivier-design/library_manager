# Installation and Deployment

Install this addon through the standard Odoo Apps workflow after placing the
addon directory on the configured addons path.

Configure an outgoing mail server in Odoo for email delivery. Member status
notifications are queued when the member contact has an email address. A
daily scheduled action queues overdue eBook reminders; the first reminder is
queued on the day after the loan due date and repeats daily until the loan is
returned. Odoo's outgoing mail queue handles delivery and retries.
