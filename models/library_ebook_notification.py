import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError


_logger = logging.getLogger(__name__)


class LibraryEbookNotification(models.Model):
    _name = 'library.ebook.notification'
    _description = 'eBook Member Notification'
    _order = 'create_date desc, id desc'

    partner_id = fields.Many2one(
        'res.partner', required=True, index=True, ondelete='cascade')
    notification_type = fields.Selection([
        ('request_submitted', 'Request submitted'),
        ('request_approved', 'Request approved'),
        ('request_rejected', 'Request rejected'),
        ('reservation_submitted', 'Reservation submitted'),
        ('reservation_fulfilled', 'Reservation fulfilled'),
    ], required=True, index=True)
    ebook_id = fields.Many2one('library.ebook', ondelete='set null')
    request_id = fields.Many2one(
        'library.ebook.request', ondelete='set null')
    reservation_id = fields.Many2one(
        'library.ebook.reservation', ondelete='set null')
    is_read = fields.Boolean(default=False, index=True)
    email_queued = fields.Boolean(readonly=True, copy=False)

    @api.model
    def _notify_partner(
            self, partner, notification_type, ebook=None,
            borrowing_request=None, reservation=None):
        notification = self.sudo().create({
            'partner_id': partner.id,
            'notification_type': notification_type,
            'ebook_id': ebook.id if ebook else False,
            'request_id': borrowing_request.id if borrowing_request else False,
            'reservation_id': reservation.id if reservation else False,
        })
        email = (partner.email or '').strip()
        if not email:
            _logger.info(
                "eBook notification %s was not emailed because partner %s "
                "has no email address.", notification.id, partner.id)
            return notification

        template = self.env.ref(
            'library_manager.mail_template_library_ebook_notification')
        mail_id = template.sudo().send_mail(
            notification.id,
            force_send=False,
            email_values={'email_to': email},
        )
        if mail_id:
            notification.sudo().write({'email_queued': True})
        else:
            _logger.warning(
                "Email was not queued for eBook notification %s.",
                notification.id)
        return notification

    def write(self, vals):
        can_manage = (
            self.env.su
            or self.env.user.has_group('library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not can_manage and (
                set(vals) != {'is_read'}
                or any(item.partner_id != self.env.user.partner_id
                       for item in self)):
            raise AccessError("You can only mark your own notifications as read.")
        return super().write(vals)

    def action_mark_read(self):
        for notification in self:
            if (notification.partner_id != self.env.user.partner_id
                    and not self.env.su
                    and not self.env.user.has_group(
                        'library_manager.group_library_librarian')
                    and not self.env.user.has_group('base.group_system')):
                raise AccessError("You can only update your own notifications.")
        self.write({'is_read': True})
