from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class LibraryEbookReservation(models.Model):
    _name = 'library.ebook.reservation'
    _description = 'Ebook Reservation'
    _order = 'reservation_date, id'

    ebook_id = fields.Many2one(
        'library.ebook', string='Ebook', required=True,
        ondelete='restrict', index=True)
    borrower_id = fields.Many2one(
        'res.partner', string='Reader', required=True,
        default=lambda self: self.env.user.partner_id, index=True)
    reservation_date = fields.Date(
        string='Requested On', required=True,
        default=fields.Date.context_today, index=True)
    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('fulfilled', 'Fulfilled'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending', required=True, index=True)
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        can_issue_for_others = (
            self.env.su
            or self.env.user.has_group('library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not can_issue_for_others:
            partner_id = self.env.user.partner_id.id
            vals_list = [
                {**values, 'borrower_id': partner_id, 'state': 'pending'}
                for values in vals_list
            ]
        return super().create(vals_list)

    @api.constrains('ebook_id', 'borrower_id', 'state')
    def _check_single_pending_reservation(self):
        for reservation in self.filtered(
                lambda item: item.state == 'pending'):
            duplicate = self.search_count([
                ('ebook_id', '=', reservation.ebook_id.id),
                ('borrower_id', '=', reservation.borrower_id.id),
                ('state', '=', 'pending'),
                ('id', '!=', reservation.id),
            ])
            if duplicate:
                raise ValidationError(
                    "You already have a pending reservation for this ebook.")

    @api.constrains('ebook_id', 'borrower_id')
    def _check_reservation_owner(self):
        if (self.env.su
                or self.env.user.has_group(
                    'library_manager.group_library_librarian')
                or self.env.user.has_group('base.group_system')):
            return
        partner = self.env.user.partner_id
        if any(reservation.borrower_id != partner for reservation in self):
            raise ValidationError(
                "You can only reserve an ebook for your own library account.")

    @api.constrains('ebook_id', 'reservation_date')
    def _check_ebook_is_active(self):
        for reservation in self:
            if not reservation.ebook_id.active:
                raise ValidationError(
                    "An archived ebook cannot be reserved.")
            if reservation.reservation_date > fields.Date.today():
                raise ValidationError(
                    "The reservation date cannot be in the future.")

    def _check_can_manage(self):
        if (not self.env.su
                and not self.env.user.has_group(
                    'library_manager.group_library_librarian')
                and not self.env.user.has_group('base.group_system')):
            raise AccessError(
                "Only librarians can update ebook reservation statuses.")

    def action_mark_fulfilled(self):
        self.ensure_one()
        self._check_can_manage()
        if self.state != 'pending':
            raise UserError(
                "Only a pending reservation can be marked as fulfilled.")
        self.write({'state': 'fulfilled'})

    def action_cancel(self):
        self.ensure_one()
        self._check_can_manage()
        if self.state != 'pending':
            raise UserError("Only a pending reservation can be cancelled.")
        self.write({'state': 'cancelled'})

    @api.depends('ebook_id.name', 'borrower_id.name')
    def _compute_display_name(self):
        for reservation in self:
            reservation.display_name = "%s / %s" % (
                reservation.ebook_id.name or '',
                reservation.borrower_id.name or '',
            )
