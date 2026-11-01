from odoo import api, fields, models
from odoo.exceptions import AccessError


class LibraryEbookAudit(models.Model):
    _name = 'library.ebook.audit'
    _description = 'eBook Activity Audit'
    _order = 'event_date desc, id desc'

    event_date = fields.Datetime(
        required=True, default=fields.Datetime.now, readonly=True, index=True)
    actor_id = fields.Many2one(
        'res.users', readonly=True, ondelete='set null', index=True)
    partner_id = fields.Many2one(
        'res.partner', readonly=True, ondelete='set null', index=True)
    event_type = fields.Selection([
        ('ebook_created', 'eBook created'),
        ('ebook_updated', 'eBook updated'),
        ('ebook_published', 'eBook published'),
        ('ebook_unpublished', 'eBook unpublished'),
        ('ebook_archived', 'eBook archived'),
        ('ebook_restored', 'eBook restored'),
        ('loan_issued', 'Loan issued'),
        ('loan_returned', 'Loan returned'),
        ('loan_renewed', 'Loan renewed'),
        ('request_submitted', 'Request submitted'),
        ('request_approved', 'Request approved'),
        ('request_rejected', 'Request rejected'),
        ('request_cancelled', 'Request cancelled'),
        ('reservation_submitted', 'Reservation submitted'),
        ('reservation_fulfilled', 'Reservation fulfilled'),
        ('reservation_cancelled', 'Reservation cancelled'),
        ('asset_uploaded', 'Protected file uploaded'),
        ('asset_updated', 'Protected file updated'),
        ('asset_removed', 'Protected file removed'),
    ], required=True, readonly=True, index=True)
    ebook_id = fields.Many2one(
        'library.ebook', readonly=True, ondelete='set null', index=True)
    loan_id = fields.Many2one(
        'library.ebook.loan', readonly=True, ondelete='set null', index=True)
    request_id = fields.Many2one(
        'library.ebook.request', readonly=True, ondelete='set null', index=True)
    reservation_id = fields.Many2one(
        'library.ebook.reservation', readonly=True, ondelete='set null',
        index=True)
    asset_id = fields.Many2one(
        'library.ebook.asset', readonly=True, ondelete='set null', index=True)
    details = fields.Char(readonly=True)

    @api.model
    def _record_event(
            self, event_type, ebook=None, partner=None, loan=None,
            borrowing_request=None, reservation=None, asset=None,
            detail=None):
        return self.sudo().create({
            'actor_id': self.env.user.id,
            'partner_id': partner.id if partner else False,
            'event_type': event_type,
            'ebook_id': ebook.id if ebook else False,
            'loan_id': loan.id if loan else False,
            'request_id': borrowing_request.id if borrowing_request else False,
            'reservation_id': reservation.id if reservation else False,
            'asset_id': asset.id if asset else False,
            'details': detail or False,
        })

    def write(self, vals):
        if not self.env.su:
            raise AccessError("eBook audit events cannot be modified.")
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError("eBook audit events cannot be deleted.")
        return super().unlink()
