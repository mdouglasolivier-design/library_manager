from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class LibraryEbookAccess(models.Model):
    _name = 'library.ebook.access'
    _description = 'Ebook Access Grant'
    _rec_name = 'ebook_id'
    _order = 'valid_from desc, id desc'

    loan_id = fields.Many2one(
        'library.ebook.loan', required=True, ondelete='cascade',
        index=True, readonly=True)
    ebook_id = fields.Many2one(
        related='loan_id.ebook_id', store=True, index=True, readonly=True)
    borrower_id = fields.Many2one(
        related='loan_id.borrower_id', store=True, index=True, readonly=True)
    valid_from = fields.Date(
        related='loan_id.borrow_date', store=True, index=True, readonly=True)
    valid_until = fields.Date(
        related='loan_id.due_date', store=True, index=True, readonly=True)
    is_active = fields.Boolean(compute='_compute_is_active')

    _sql_constraints = [
        ('loan_unique', 'unique(loan_id)',
         'Each ebook loan can only have one access grant.'),
    ]

    @api.depends(
        'loan_id.state', 'loan_id.borrow_date', 'loan_id.due_date',
        'loan_id.ebook_id.active')
    def _compute_is_active(self):
        today = fields.Date.today()
        for grant in self:
            grant.is_active = bool(
                grant.loan_id.state == 'active'
                and grant.loan_id.ebook_id.active
                and grant.valid_from
                and grant.valid_until
                and grant.valid_from <= today <= grant.valid_until
            )

    @api.model
    def check_ebook_access(self, ebook_id):
        if type(ebook_id) is not int or ebook_id <= 0:
            raise ValidationError("A valid ebook ID is required.")

        ebook = self.env['library.ebook'].sudo().browse(ebook_id).exists()
        if not ebook or not ebook.active:
            raise AccessError("This ebook is not available.")

        partner = self.env.user.partner_id
        if not partner:
            raise AccessError("Your user account has no library member contact.")

        today = fields.Date.today()
        grant = self.sudo().search([
            ('ebook_id', '=', ebook.id),
            ('borrower_id', '=', partner.id),
            ('loan_id.state', '=', 'active'),
            ('valid_from', '<=', today),
            ('valid_until', '>=', today),
        ], limit=1)
        if not grant:
            raise AccessError("You need an active ebook loan to access this ebook.")
        return True

    @api.model
    def get_readable_asset(self, ebook_id):
        self.check_ebook_access(ebook_id)
        return self.env['library.ebook.asset'].sudo().search([
            ('ebook_id', '=', ebook_id),
        ], limit=1)
