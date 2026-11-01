import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_logger = logging.getLogger(__name__)


class LibraryEbookLoan(models.Model):
    _name = 'library.ebook.loan'
    _description = 'Ebook Loan'
    _order = 'borrow_date desc, id desc'

    ebook_id = fields.Many2one(
        'library.ebook', string='Ebook', required=True,
        ondelete='restrict', index=True)
    borrower_id = fields.Many2one(
        'res.partner', string='Borrower', required=True, index=True)
    borrow_date = fields.Date(
        required=True, default=fields.Date.context_today, index=True)
    due_date = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self) + timedelta(days=14),
        index=True)
    return_date = fields.Date()
    renewal_count = fields.Integer(default=0, readonly=True, copy=False)
    last_overdue_reminder_date = fields.Date(
        readonly=True, copy=False, index=True)
    state = fields.Selection(
        [('active', 'Active'), ('returned', 'Returned')],
        default='active', required=True, index=True)
    is_overdue = fields.Boolean(
        compute='_compute_is_overdue', search='_search_is_overdue')
    days_late = fields.Integer(compute='_compute_days_late')
    access_ids = fields.One2many(
        'library.ebook.access', 'loan_id', string='Access Grants', readonly=True)

    @api.model
    def _policy_integer(self, key, default):
        value = self.env['ir.config_parameter'].sudo().get_param(
            'library_manager.%s' % key, str(default))
        try:
            value = int(value)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                "The eBook lending policy setting %s must be an integer."
                % key) from error
        if value < 0:
            raise ValidationError(
                "The eBook lending policy setting %s cannot be negative."
                % key)
        return value

    @api.model
    def _member_at_loan_limit(self, partner):
        limit = self._policy_integer('ebook_max_active_loans', 0)
        if not limit:
            return False
        active_count = self.sudo().search_count([
            ('borrower_id', '=', partner.id),
            ('state', '=', 'active'),
        ])
        return active_count >= limit

    @api.model
    def _default_due_date(self):
        days = self._policy_integer('ebook_loan_duration_days', 14)
        if not days:
            raise ValidationError(
                "The eBook loan duration must be greater than zero.")
        return fields.Date.context_today(self) + timedelta(days=days)

    @api.model_create_multi
    def create(self, vals_list):
        ebook_ids = sorted({
            values.get('ebook_id') for values in vals_list
            if values.get('ebook_id')
        })
        ebooks = self.env['library.ebook'].sudo().browse(ebook_ids).exists()
        ebooks._check_file_available()
        if ebook_ids:
            self.env.cr.execute(
                "SELECT id FROM library_ebook "
                "WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                (ebook_ids,))
        partner_ids = sorted({
            values.get('borrower_id') for values in vals_list
            if values.get('borrower_id')
        })
        if partner_ids:
            self.env.cr.execute(
                "SELECT id FROM res_partner "
                "WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                (partner_ids,))

        planned_by_ebook = {}
        planned_by_partner = {}
        planned_pairs = set()
        for values in vals_list:
            if values.get('state') not in (False, None, 'active'):
                continue
            ebook_id = values.get('ebook_id')
            partner_id = values.get('borrower_id')
            if not ebook_id or not partner_id:
                continue
            pair = (ebook_id, partner_id)
            if pair in planned_pairs or self.sudo().search_count([
                    ('ebook_id', '=', ebook_id),
                    ('borrower_id', '=', partner_id),
                    ('state', '=', 'active'),
            ]):
                raise ValidationError(
                    "This member already has an active loan for this eBook.")

            ebook = self.env['library.ebook'].sudo().browse(ebook_id).exists()
            if not ebook or not ebook.active:
                raise ValidationError("An archived eBook cannot be loaned.")
            if ebook._is_at_concurrent_capacity():
                raise ValidationError(
                    "The eBook has reached its concurrent loan limit.")
            if self._member_at_loan_limit(
                    self.env['res.partner'].browse(partner_id)):
                raise ValidationError(
                    "The member has reached the active eBook loan limit.")
            planned_pairs.add(pair)
            planned_by_ebook[ebook_id] = (
                planned_by_ebook.get(ebook_id, 0) + 1)
            planned_by_partner[partner_id] = (
                planned_by_partner.get(partner_id, 0) + 1)

        for ebook_id, planned_count in planned_by_ebook.items():
            limit = self._policy_integer('ebook_max_concurrent_loans', 0)
            if limit:
                active_count = self.sudo().search_count([
                    ('ebook_id', '=', ebook_id),
                    ('state', '=', 'active'),
                ])
                if active_count + planned_count > limit:
                    raise ValidationError(
                        "The eBook has reached its concurrent loan limit.")
        member_limit = self._policy_integer('ebook_max_active_loans', 0)
        if member_limit:
            for partner_id, planned_count in planned_by_partner.items():
                active_count = self.sudo().search_count([
                    ('borrower_id', '=', partner_id),
                    ('state', '=', 'active'),
                ])
                if active_count + planned_count > member_limit:
                    raise ValidationError(
                        "The member has reached the active eBook loan limit.")

        for values in vals_list:
            values.setdefault('due_date', self._default_due_date())
        loans = super().create(vals_list)
        self.env['library.ebook.access'].sudo().create([
            {'loan_id': loan.id} for loan in loans
        ])
        for loan in loans:
            self.env['library.ebook.audit']._record_event(
                'loan_issued',
                ebook=loan.ebook_id,
                partner=loan.borrower_id,
                loan=loan)
        return loans

    def write(self, vals):
        previous = {
            loan.id: (loan.state, loan.due_date)
            for loan in self
        }
        result = super().write(vals)
        for loan in self:
            old_state, old_due_date = previous[loan.id]
            if old_state != 'returned' and loan.state == 'returned':
                self.env['library.ebook.audit']._record_event(
                    'loan_returned',
                    ebook=loan.ebook_id,
                    partner=loan.borrower_id,
                    loan=loan)
            elif (old_due_date and loan.due_date
                  and loan.due_date > old_due_date
                  and loan.state == 'active'):
                self.env['library.ebook.audit']._record_event(
                    'loan_renewed',
                    ebook=loan.ebook_id,
                    partner=loan.borrower_id,
                    loan=loan,
                    detail='Due date extended to %s' % loan.due_date)
        return result

    def action_renew(self):
        self.ensure_one()
        is_librarian = (
            self.env.su
            or self.env.user.has_group('library_manager.group_library_librarian')
            or self.env.user.has_group('base.group_system')
        )
        if not is_librarian and self.borrower_id != self.env.user.partner_id:
            raise AccessError("You can only renew your own eBook loan.")
        if self.state != 'active':
            raise UserError("Only an active eBook loan can be renewed.")
        if self.due_date < fields.Date.today():
            raise UserError("An overdue eBook loan cannot be renewed.")
        if self.renewal_count:
            raise UserError("This eBook loan has already been renewed.")
        if self.env['library.ebook.reservation'].sudo().search_count([
                ('ebook_id', '=', self.ebook_id.id),
                ('state', '=', 'pending')]):
            raise UserError(
                "This eBook has a waiting reservation and cannot be renewed.")
        self.ebook_id._check_file_available()
        duration = self._policy_integer('ebook_loan_duration_days', 14)
        if not duration:
            raise ValidationError(
                "The eBook loan duration must be greater than zero.")
        self.sudo().write({
            'due_date': self.due_date + timedelta(days=duration),
            'renewal_count': 1,
        })

    @api.depends('ebook_id.name', 'borrower_id.name')
    def _compute_display_name(self):
        for loan in self:
            loan.display_name = "%s / %s" % (
                loan.ebook_id.name or '', loan.borrower_id.name or '')

    @api.depends('state', 'due_date')
    def _compute_is_overdue(self):
        today = fields.Date.today()
        for loan in self:
            loan.is_overdue = bool(
                loan.state == 'active' and loan.due_date and loan.due_date < today)

    def _search_is_overdue(self, operator, value):
        today = fields.Date.today()
        positive = (operator == '=') == bool(value)
        if positive:
            return [('state', '=', 'active'), ('due_date', '<', today)]
        return ['|', '|',
                ('state', '!=', 'active'),
                ('due_date', '=', False),
                ('due_date', '>=', today)]

    @api.depends('state', 'due_date', 'return_date')
    def _compute_days_late(self):
        today = fields.Date.today()
        for loan in self:
            end_date = loan.return_date if loan.state == 'returned' else today
            if loan.due_date and end_date and end_date > loan.due_date:
                loan.days_late = (end_date - loan.due_date).days
            else:
                loan.days_late = 0

    @api.constrains('borrow_date', 'due_date', 'return_date', 'state')
    def _check_dates(self):
        for loan in self:
            if loan.due_date < loan.borrow_date:
                raise ValidationError(
                    "The due date cannot be before the borrow date.")
            if loan.return_date and loan.return_date < loan.borrow_date:
                raise ValidationError(
                    "The return date cannot be before the borrow date.")
            if loan.state == 'active' and loan.return_date:
                raise ValidationError(
                    "An active ebook loan cannot have a return date.")
            if loan.state == 'returned' and not loan.return_date:
                raise ValidationError(
                    "A returned ebook loan must have a return date.")

    @api.constrains('ebook_id', 'borrower_id', 'state')
    def _check_single_open_loan_per_borrower(self):
        for loan in self.filtered(lambda item: item.state == 'active'):
            other_open_loan = self.search_count([
                ('ebook_id', '=', loan.ebook_id.id),
                ('borrower_id', '=', loan.borrower_id.id),
                ('state', '=', 'active'),
                ('id', '!=', loan.id),
            ])
            if other_open_loan:
                raise ValidationError(
                    "This borrower already has an active loan for this ebook.")

    @api.constrains('ebook_id')
    def _check_ebook_is_active(self):
        for loan in self:
            if not loan.ebook_id.active:
                raise ValidationError("An archived ebook cannot be loaned.")

    def action_mark_returned(self):
        today = fields.Date.today()
        self.filtered(lambda loan: loan.state == 'active').write({
            'state': 'returned',
            'return_date': today,
        })

    @api.model
    def _cron_send_overdue_reminders(self):
        today = fields.Date.today()
        overdue_loans = self.sudo().search([
            ('state', '=', 'active'),
            ('due_date', '<', today),
            '|',
            ('last_overdue_reminder_date', '=', False),
            ('last_overdue_reminder_date', '<', today),
        ], order='id')
        template = self.env.ref(
            'library_manager.mail_template_library_ebook_overdue_reminder')
        queued_count = 0
        for loan in overdue_loans:
            email = (loan.borrower_id.email or '').strip()
            if not email:
                _logger.warning(
                    "Overdue reminder for eBook loan %s was skipped: "
                    "the borrower has no email address.", loan.id)
                continue
            mail_id = template.sudo().send_mail(
                loan.id,
                force_send=False,
                email_values={'email_to': email},
            )
            if not mail_id:
                _logger.warning(
                    "Overdue reminder email was not queued for eBook loan %s.",
                    loan.id)
                continue
            loan.last_overdue_reminder_date = today
            queued_count += 1
        return queued_count
