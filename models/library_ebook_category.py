from odoo import fields, models


class LibraryEbookCategory(models.Model):
    _name = 'library.ebook.category'
    _description = 'Ebook Category'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True, index=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    ebook_ids = fields.One2many(
        'library.ebook', 'category_id', string='eBooks')
    ebook_count = fields.Integer(compute='_compute_ebook_count')

    def _compute_ebook_count(self):
        for category in self:
            category.ebook_count = len(category.ebook_ids)
