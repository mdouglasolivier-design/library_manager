from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LibraryEbook(models.Model):
    _name = 'library.ebook'
    _description = 'Ebook'
    _order = 'name, id'

    name = fields.Char(string='Title', required=True, index=True)
    author = fields.Char()
    isbn = fields.Char(string='ISBN', copy=False, index=True)
    description = fields.Text()
    publication_date = fields.Date()
    active = fields.Boolean(default=True)

    loan_ids = fields.One2many(
        'library.ebook.loan', 'ebook_id', string='Loan History')
    loan_count = fields.Integer(compute='_compute_loan_count')

    _sql_constraints = [
        ('isbn_unique', 'unique(isbn)', 'This ISBN already exists!'),
    ]

    @api.depends('loan_ids')
    def _compute_loan_count(self):
        for ebook in self:
            ebook.loan_count = len(ebook.loan_ids)

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
