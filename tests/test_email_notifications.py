import base64
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestEbookEmailNotifications(TransactionCase):

    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'eBook Email Member',
            'email': 'ebook-email-member@example.test',
        })
        self.ebook = self.env['library.ebook'].create({
            'name': 'eBook Email Notification Test',
        })
        self.env['library.ebook.asset'].create({
            'ebook_id': self.ebook.id,
            'filename': 'email-test.pdf',
            'file_format': 'pdf',
            'file_data': base64.b64encode(
                b'%PDF-1.7\nEmail fixture').decode('ascii'),
        })

    def test_member_notifications_are_queued_for_email(self):
        notification_model = self.env['library.ebook.notification']
        mail_model = self.env['mail.mail'].sudo()
        mail_domain = [('email_to', '=', self.partner.email)]
        mail_count_before = mail_model.search_count(mail_domain)
        notification_types = [
            'request_submitted',
            'request_approved',
            'request_rejected',
            'reservation_submitted',
            'reservation_fulfilled',
        ]

        notification_ids = []
        for notification_type in notification_types:
            notification_ids.append(notification_model._notify_partner(
                self.partner, notification_type, ebook=self.ebook).id)
        notifications = notification_model.browse(notification_ids)

        self.assertEqual(len(notifications), len(notification_types))
        self.assertTrue(all(notifications.mapped('email_queued')))
        self.assertEqual(
            mail_model.search_count(mail_domain) - mail_count_before,
            len(notification_types))

    def test_missing_member_email_keeps_portal_notification_only(self):
        partner_without_email = self.env['res.partner'].create({
            'name': 'Member Without Email',
        })
        mail_model = self.env['mail.mail'].sudo()
        mail_domain = [
            ('email_to', '=', partner_without_email.email or ''),
        ]
        mail_count_before = mail_model.search_count(mail_domain)

        notification = self.env[
            'library.ebook.notification'
        ]._notify_partner(
            partner_without_email, 'request_submitted', ebook=self.ebook)

        self.assertFalse(notification.email_queued)
        self.assertEqual(
            mail_model.search_count(mail_domain), mail_count_before)

    def test_overdue_reminder_queues_once_each_day_until_return(self):
        today = fields.Date.today()
        loan = self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.partner.id,
            'borrow_date': today - timedelta(days=14),
            'due_date': today - timedelta(days=1),
        })
        loan_model = self.env['library.ebook.loan']
        mail_model = self.env['mail.mail'].sudo()
        mail_domain = [('email_to', '=', self.partner.email)]
        mail_count_before = mail_model.search_count(mail_domain)

        self.assertEqual(loan_model._cron_send_overdue_reminders(), 1)
        self.assertEqual(loan.last_overdue_reminder_date, today)
        self.assertEqual(
            mail_model.search_count(mail_domain) - mail_count_before, 1)
        self.assertEqual(loan_model._cron_send_overdue_reminders(), 0)

        loan.last_overdue_reminder_date = today - timedelta(days=1)
        self.assertEqual(loan_model._cron_send_overdue_reminders(), 1)
        self.assertEqual(
            mail_model.search_count(mail_domain) - mail_count_before, 2)

        loan.action_mark_returned()
        loan.last_overdue_reminder_date = today - timedelta(days=1)
        self.assertEqual(loan_model._cron_send_overdue_reminders(), 0)

    def test_overdue_reminder_is_skipped_when_borrower_has_no_email(self):
        today = fields.Date.today()
        partner_without_email = self.env['res.partner'].create({
            'name': 'Overdue Member Without Email',
        })
        self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': partner_without_email.id,
            'borrow_date': today - timedelta(days=14),
            'due_date': today - timedelta(days=1),
        })
        mail_model = self.env['mail.mail'].sudo()
        mail_domain = [
            ('email_to', '=', partner_without_email.email or ''),
        ]
        mail_count_before = mail_model.search_count(mail_domain)

        self.assertEqual(
            self.env['library.ebook.loan']._cron_send_overdue_reminders(), 0)
        self.assertEqual(
            mail_model.search_count(mail_domain), mail_count_before)
