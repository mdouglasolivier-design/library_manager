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
    loan_id = fields.Many2one(
        'library.ebook.loan', readonly=True, copy=False, ondelete='set null')
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
                {
                    'ebook_id': values.get('ebook_id'),
                    'borrower_id': partner_id,
                    'state': 'pending',
                }
                for values in vals_list
            ]
        ebook_ids = sorted({
            values.get('ebook_id') for values in vals_list
            if values.get('ebook_id')
        })
        if ebook_ids:
            self.env.cr.execute(
                "SELECT id FROM library_ebook "
                "WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                (ebook_ids,))
        if not can_issue_for_others:
            partner = self.env.user.partner_id
            Loan = self.env['library.ebook.loan'].sudo()
            BorrowingRequest = self.env['library.ebook.request']
            for values in vals_list:
                ebook = self.env['library.ebook'].sudo().browse(
                    values.get('ebook_id')).exists()
                if (not ebook or not ebook.active
                        or not ebook.website_published):
                    raise ValidationError(
                        "Only active eBooks published in the catalog can be reserved.")
                ebook._check_file_available()
                if Loan.search_count([
                        ('ebook_id', '=', ebook.id),
                        ('borrower_id', '=', partner.id),
                        ('state', '=', 'active')]):
                    raise ValidationError(
                        "You already have an active loan for this eBook.")
                if Loan._member_at_loan_limit(partner):
                    raise ValidationError(
                        "Your account has reached its active eBook loan limit.")
                if not ebook._is_at_concurrent_capacity():
                    raise ValidationError(
                        "This eBook is available. Submit a borrowing request instead.")
                if BorrowingRequest.search_count([
                        ('ebook_id', '=', ebook.id),
                        ('borrower_id', '=', partner.id),
                        ('state', '=', 'pending')]):
                    raise ValidationError(
                        "You already have a pending request for this eBook.")
        reservations = super().create(vals_list)
        for reservation in reservations:
            reservation.env['library.ebook.notification']._notify_partner(
                partner=reservation.borrower_id,
                notification_type='reservation_submitted',
                ebook=reservation.ebook_id,
                reservation=reservation)
            reservation.env['library.ebook.audit']._record_event(
                'reservation_submitted',
                ebook=reservation.ebook_id,
                partner=reservation.borrower_id,
                reservation=reservation)
        return reservations

    def write(self, vals):
        can_manage = (
            self.env.su
            or self.env.user.has_group('library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not can_manage:
            if set(vals) != {'state'} or vals.get('state') != 'cancelled':
                raise AccessError(
                    "Members can only cancel their own pending reservations.")
            if any(
                    item.borrower_id != self.env.user.partner_id
                    or item.state != 'pending' for item in self):
                raise AccessError(
                    "Only your own pending reservations can be cancelled.")
        previous_states = {item.id: item.state for item in self}
        result = super().write(vals)
        if vals.get('state') == 'cancelled':
            for reservation in self:
                if previous_states.get(reservation.id) != 'cancelled':
                    self.env['library.ebook.audit']._record_event(
                        'reservation_cancelled',
                        ebook=reservation.ebook_id,
                        partner=reservation.borrower_id,
                        reservation=reservation)
        if vals.get('state') == 'fulfilled':
            for reservation in self:
                if previous_states.get(reservation.id) != 'fulfilled':
                    reservation.env[
                        'library.ebook.notification'
                    ]._notify_partner(
                        partner=reservation.borrower_id,
                        notification_type='reservation_fulfilled',
                        ebook=reservation.ebook_id,
                        reservation=reservation)
                    self.env['library.ebook.audit']._record_event(
                        'reservation_fulfilled',
                        ebook=reservation.ebook_id,
                        partner=reservation.borrower_id,
                        reservation=reservation,
                        loan=reservation.loan_id)
        return result

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
            if (not reservation.ebook_id.sudo().website_published
                    and not self.env.su
                    and not self.env.user.has_group(
                        'library_manager.group_library_librarian')
                    and not self.env.user.has_group('base.group_system')):
                raise ValidationError(
                    "Only eBooks published in the catalog can be reserved.")
            if reservation.reservation_date > fields.Date.today():
                raise ValidationError(
                    "The reservation date cannot be in the future.")

    @api.constrains('state', 'loan_id', 'borrower_id')
    def _check_fulfilled_reservation_loan(self):
        for reservation in self:
            if reservation.state == 'fulfilled' and not reservation.loan_id:
                raise ValidationError(
                    "A fulfilled reservation must be linked to an eBook loan.")
            if (reservation.loan_id
                    and reservation.loan_id.borrower_id
                    != reservation.borrower_id):
                raise ValidationError(
                    "The linked loan must belong to the reservation holder.")

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
        if self.env['library.ebook.loan']._member_at_loan_limit(
                self.borrower_id):
            raise UserError(
                "The member has reached the active eBook loan limit.")
        self.ebook_id._check_file_available()
        loan = self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook_id.id,
            'borrower_id': self.borrower_id.id,
        })
        self.write({'state': 'fulfilled', 'loan_id': loan.id})

    def action_cancel(self):
        self.ensure_one()
        can_manage = (
            self.env.su
            or self.env.user.has_group('library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not can_manage and self.borrower_id != self.env.user.partner_id:
            raise AccessError("You can only cancel your own reservation.")
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
