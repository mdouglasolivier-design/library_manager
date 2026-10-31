from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class LibraryEbookRequest(models.Model):
    _name = 'library.ebook.request'
    _description = 'eBook Borrowing Request'
    _order = 'request_date desc, id desc'

    ebook_id = fields.Many2one(
        'library.ebook', required=True, ondelete='restrict', index=True)
    borrower_id = fields.Many2one(
        'res.partner', required=True, index=True,
        default=lambda self: self.env.user.partner_id)
    request_date = fields.Datetime(
        required=True, default=fields.Datetime.now, index=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, index=True)
    loan_id = fields.Many2one(
        'library.ebook.loan', readonly=True, copy=False, ondelete='set null')
    decision_date = fields.Datetime(readonly=True)

    @api.model
    def submit_for_current_user(self, ebook_id):
        user = self.env.user
        if user._is_public() or not user.partner_id:
            raise AccessError("Sign in with a library account to request an eBook.")

        ebook = self.env['library.ebook'].sudo().search([
            ('id', '=', ebook_id),
            ('active', '=', True),
            ('website_published', '=', True),
        ], limit=1)
        if not ebook:
            raise UserError("This eBook is not available in the public catalog.")

        self.env.cr.execute(
            "SELECT id FROM library_ebook WHERE id = %s FOR UPDATE",
            (ebook.id,))
        Loan = self.env['library.ebook.loan'].sudo()
        if Loan.search_count([
                ('ebook_id', '=', ebook.id),
                ('borrower_id', '=', user.partner_id.id),
                ('state', '=', 'active')]):
            raise UserError("You already have an active loan for this eBook.")
        if self.search_count([
                ('ebook_id', '=', ebook.id),
                ('borrower_id', '=', user.partner_id.id),
                ('state', '=', 'pending')]):
            raise UserError("You already have a pending request for this eBook.")
        if self.env['library.ebook.loan']._member_at_loan_limit(
                user.partner_id):
            raise UserError("Your account has reached its active eBook loan limit.")

        if ebook._is_at_concurrent_capacity():
            reservation = self.env['library.ebook.reservation'].create({
                'ebook_id': ebook.id,
            })
            return reservation

        borrowing_request = self.create({'ebook_id': ebook.id})
        if not self.env['res.config.settings']._library_approval_required():
            borrowing_request._approve(auto_approval=True)
        return borrowing_request

    @api.model_create_multi
    def create(self, vals_list):
        can_manage = (
            self.env.su
            or self.env.user.has_group('library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not can_manage:
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
        if not can_manage:
            partner = self.env.user.partner_id
            Loan = self.env['library.ebook.loan'].sudo()
            Reservation = self.env['library.ebook.reservation']
            for values in vals_list:
                ebook = self.env['library.ebook'].sudo().browse(
                    values.get('ebook_id')).exists()
                if (not ebook or not ebook.active
                        or not ebook.website_published):
                    raise ValidationError(
                        "Only active eBooks published in the catalog can be requested.")
                if Loan.search_count([
                        ('ebook_id', '=', ebook.id),
                        ('borrower_id', '=', partner.id),
                        ('state', '=', 'active')]):
                    raise ValidationError(
                        "You already have an active loan for this eBook.")
                if Loan._member_at_loan_limit(partner):
                    raise ValidationError(
                        "Your account has reached its active eBook loan limit.")
                if ebook._is_at_concurrent_capacity():
                    raise ValidationError(
                        "This eBook is at capacity. Submit a reservation instead.")
                if Reservation.search_count([
                        ('ebook_id', '=', ebook.id),
                        ('borrower_id', '=', partner.id),
                        ('state', '=', 'pending')]):
                    raise ValidationError(
                        "You already have a pending reservation for this eBook.")
        requests = super().create(vals_list)
        for borrowing_request in requests:
            borrowing_request._notify(
                'request_submitted', borrowing_request.borrower_id)
        return requests

    def write(self, vals):
        can_manage = (
            self.env.su
            or self.env.user.has_group('library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not can_manage:
            if set(vals) != {'state'} or vals.get('state') != 'cancelled':
                raise AccessError(
                    "Members can only cancel their own pending requests.")
            if any(
                    item.borrower_id != self.env.user.partner_id
                    or item.state != 'pending' for item in self):
                raise AccessError(
                    "Only your own pending requests can be cancelled.")
        previous_states = {item.id: item.state for item in self}
        result = super().write(vals)
        if vals.get('state') in ('approved', 'rejected'):
            notification_type = (
                'request_approved' if vals['state'] == 'approved'
                else 'request_rejected')
            for borrowing_request in self:
                if previous_states.get(borrowing_request.id) != vals['state']:
                    borrowing_request._notify(
                        notification_type, borrowing_request.borrower_id)
        return result

    @api.constrains('ebook_id', 'borrower_id', 'state')
    def _check_request_integrity(self):
        for borrowing_request in self:
            if not borrowing_request.ebook_id.active:
                raise ValidationError("An archived eBook cannot be requested.")
            if (not borrowing_request.ebook_id.sudo().website_published
                    and not self.env.su):
                raise ValidationError(
                    "Only eBooks published in the catalog can be requested.")
            if (borrowing_request.state == 'pending'
                    and self.search_count([
                        ('ebook_id', '=', borrowing_request.ebook_id.id),
                        ('borrower_id', '=', borrowing_request.borrower_id.id),
                        ('state', '=', 'pending'),
                        ('id', '!=', borrowing_request.id),
                    ])):
                raise ValidationError(
                    "You already have a pending request for this eBook.")
            if (borrowing_request.loan_id
                    and borrowing_request.loan_id.borrower_id
                    != borrowing_request.borrower_id):
                raise ValidationError(
                    "The linked loan must belong to the requesting member.")
            if (borrowing_request.state == 'approved'
                    and not borrowing_request.loan_id):
                raise ValidationError(
                    "An approved request must be linked to an active loan.")

    def _notify(self, notification_type, partner):
        self.ensure_one()
        self.env['library.ebook.notification']._notify_partner(
            partner=partner,
            notification_type=notification_type,
            ebook=self.ebook_id,
            borrowing_request=self)

    def _approve(self, auto_approval=False):
        self.ensure_one()
        is_librarian = (
            self.env.su
            or self.env.user.has_group('library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not is_librarian and not (
                auto_approval
                and not self.env['res.config.settings']._library_approval_required()):
            raise AccessError("Only a librarian can approve an eBook request.")
        if self.state != 'pending':
            raise UserError("Only a pending request can be approved.")

        ebook = self.ebook_id
        self.env.cr.execute(
            "SELECT id FROM library_ebook WHERE id = %s FOR UPDATE",
            (ebook.id,))
        if ebook._is_at_concurrent_capacity():
            raise UserError(
                "The eBook has reached its concurrent loan limit. "
                "Reserve it instead.")
        if self.env['library.ebook.loan']._member_at_loan_limit(
                self.borrower_id):
            raise UserError("The member has reached the active eBook loan limit.")

        loan = self.env['library.ebook.loan'].sudo().create({
            'ebook_id': ebook.id,
            'borrower_id': self.borrower_id.id,
        })
        self.sudo().write({
            'state': 'approved',
            'loan_id': loan.id,
            'decision_date': fields.Datetime.now(),
        })

    def action_approve(self):
        for borrowing_request in self:
            borrowing_request._approve()

    def action_reject(self):
        self.ensure_one()
        if (not self.env.su
                and not self.env.user.has_group(
                    'library_manager.group_library_librarian')
                and not self.env.user.has_group('base.group_system')):
            raise AccessError("Only a librarian can reject an eBook request.")
        if self.state != 'pending':
            raise UserError("Only a pending request can be rejected.")
        self.write({
            'state': 'rejected',
            'decision_date': fields.Datetime.now(),
        })

    def action_cancel(self):
        self.ensure_one()
        can_manage = (
            self.env.su
            or self.env.user.has_group('library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not can_manage and self.borrower_id != self.env.user.partner_id:
            raise AccessError("You can only cancel your own request.")
        if self.state != 'pending':
            raise UserError("Only a pending request can be cancelled.")
        self.write({'state': 'cancelled'})

    @api.depends('ebook_id.name', 'borrower_id.name')
    def _compute_display_name(self):
        for borrowing_request in self:
            borrowing_request.display_name = "%s / %s" % (
                borrowing_request.ebook_id.name or '',
                borrowing_request.borrower_id.name or '',
            )
