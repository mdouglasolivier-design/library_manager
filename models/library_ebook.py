from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LibraryEbook(models.Model):
    _name = 'library.ebook'
    _description = 'Ebook'
    _order = 'name, id'

    name = fields.Char(string='Title', required=True, index=True)
    author = fields.Char()
    publisher = fields.Char()
    isbn = fields.Char(string='ISBN', copy=False, index=True)
    cover_image = fields.Image(
        string='Cover', max_width=1200, max_height=1800)
    category_id = fields.Many2one(
        'library.ebook.category', string='Category',
        ondelete='set null', index=True)
    language = fields.Char()
    file_format = fields.Selection([
        ('pdf', 'PDF'),
        ('epub', 'EPUB'),
        ('other', 'Other'),
    ], string='File Format')
    description = fields.Text()
    publication_date = fields.Date()
    active = fields.Boolean(default=True)
    website_published = fields.Boolean(
        string='Published on Website', default=False, index=True)

    loan_ids = fields.One2many(
        'library.ebook.loan', 'ebook_id', string='Loan History')
    asset_ids = fields.One2many(
        'library.ebook.asset', 'ebook_id', string='Protected File')
    request_ids = fields.One2many(
        'library.ebook.request', 'ebook_id', string='Borrowing Requests')
    reservation_ids = fields.One2many(
        'library.ebook.reservation', 'ebook_id', string='Reservations')
    loan_count = fields.Integer(compute='_compute_loan_count', store=True)
    active_loan_count = fields.Integer(
        compute='_compute_active_loan_count', store=True, index=True)
    file_available = fields.Boolean(
        string='Protected File Available',
        compute='_compute_file_available', store=True, index=True)
    availability_status = fields.Selection([
        ('available', 'Available'),
        ('on_loan', 'On Loan'),
    ], compute='_compute_availability_status',
        search='_search_availability_status')

    _sql_constraints = [
        ('isbn_unique', 'unique(isbn)', 'This ISBN already exists!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        ebooks = super().create(vals_list)
        for ebook in ebooks:
            self.env['library.ebook.audit']._record_event(
                'ebook_created', ebook=ebook)
        return ebooks

    def write(self, vals):
        previous = {
            ebook.id: (ebook.active, ebook.website_published)
            for ebook in self
        }
        result = super().write(vals)
        metadata_fields = {
            'name', 'author', 'publisher', 'isbn', 'cover_image',
            'category_id', 'language', 'file_format', 'description',
            'publication_date',
        }
        for ebook in self:
            was_active, was_published = previous[ebook.id]
            audit = self.env['library.ebook.audit']
            if was_active and not ebook.active:
                event_type = 'ebook_archived'
            elif not was_active and ebook.active:
                event_type = 'ebook_restored'
            elif not was_published and ebook.website_published:
                event_type = 'ebook_published'
            elif was_published and not ebook.website_published:
                event_type = 'ebook_unpublished'
            elif metadata_fields.intersection(vals):
                event_type = 'ebook_updated'
            else:
                continue
            audit._record_event(
                event_type,
                ebook=ebook,
                detail=', '.join(sorted(metadata_fields.intersection(vals)))
                if event_type == 'ebook_updated' else False)
        return result

    @api.depends('loan_ids')
    def _compute_loan_count(self):
        for ebook in self:
            ebook.loan_count = len(ebook.sudo().loan_ids)

    @api.depends('loan_ids.state')
    def _compute_active_loan_count(self):
        for ebook in self:
            ebook.active_loan_count = len(
                ebook.sudo().loan_ids.filtered(
                    lambda loan: loan.state == 'active'))

    @api.depends(
        'asset_ids', 'asset_ids.file_size', 'asset_ids.filename',
        'asset_ids.file_format')
    def _compute_file_available(self):
        for ebook in self:
            ebook.file_available = bool(
                ebook.sudo().asset_ids.filtered(
                    lambda asset: asset.file_size > 0
                    and asset.filename and asset.file_format))

    def _check_file_available(self):
        for ebook in self:
            if not ebook.sudo().file_available:
                raise ValidationError(
                    "A valid protected PDF or EPUB file is required "
                    "before this eBook can be borrowed.")

    @api.depends('active_loan_count')
    def _compute_availability_status(self):
        parameter = self.env['ir.config_parameter'].sudo().get_param(
            'library_manager.ebook_max_concurrent_loans', '0')
        try:
            limit = int(parameter or 0)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                "The maximum concurrent eBook loan setting must be an integer."
            ) from error
        if limit < 0:
            raise ValidationError(
                "The maximum concurrent eBook loan setting cannot be negative.")
        for ebook in self:
            ebook.availability_status = (
                'on_loan' if limit and ebook.active_loan_count >= limit
                else 'available')

    def _search_availability_status(self, operator, value):
        if operator not in ('=', '!='):
            raise NotImplementedError(
                "Availability supports equality filters only.")
        wants_available = value == 'available'
        if operator == '!=':
            wants_available = not wants_available
        parameter = self.env['ir.config_parameter'].sudo().get_param(
            'library_manager.ebook_max_concurrent_loans', '0')
        try:
            limit = int(parameter or 0)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                "The maximum concurrent eBook loan setting must be an integer."
            ) from error
        if limit < 0:
            raise ValidationError(
                "The maximum concurrent eBook loan setting cannot be negative.")
        if wants_available and not limit:
            return [('id', '!=', 0)]
        if not wants_available and not limit:
            return [('id', '=', 0)]

        comparison = '<' if wants_available else '>='
        self.env.cr.execute(
            "SELECT ebook.id FROM library_ebook AS ebook "
            "LEFT JOIN library_ebook_loan AS loan "
            "ON loan.ebook_id = ebook.id AND loan.state = 'active' "
            "GROUP BY ebook.id "
            "HAVING COUNT(loan.id) " + comparison + " %s",
            (limit,))
        ebook_ids = [row[0] for row in self.env.cr.fetchall()]
        return [('id', 'in', ebook_ids)]

    def _is_at_concurrent_capacity(self):
        self.ensure_one()
        parameter = self.env['ir.config_parameter'].sudo().get_param(
            'library_manager.ebook_max_concurrent_loans', '0')
        try:
            limit = int(parameter or 0)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                "The maximum concurrent eBook loan setting must be an integer."
            ) from error
        if limit < 0:
            raise ValidationError(
                "The maximum concurrent eBook loan setting cannot be negative.")
        if not limit:
            return False
        active_count = self.env['library.ebook.loan'].sudo().search_count([
            ('ebook_id', '=', self.id),
            ('state', '=', 'active'),
        ])
        return active_count >= limit

    @api.constrains('publication_date')
    def _check_publication_date(self):
        for ebook in self:
            if ebook.publication_date and ebook.publication_date > fields.Date.today():
                raise ValidationError("The publication date cannot be in the future.")

    def action_view_loans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ebook Loans',
            'res_model': 'library.ebook.loan',
            'view_mode': 'list,form',
            'domain': [('ebook_id', '=', self.id)],
            'context': {'default_ebook_id': self.id},
        }
