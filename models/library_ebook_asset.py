import base64
import binascii

from odoo import api, fields, models
from .library_file_validator import decode_ebook_file


class LibraryEbookAsset(models.Model):
    _name = 'library.ebook.asset'
    _description = 'Protected eBook File'
    _rec_name = 'filename'

    ebook_id = fields.Many2one(
        'library.ebook', required=True, ondelete='cascade', index=True)
    filename = fields.Char(required=True)
    file_format = fields.Selection([
        ('pdf', 'PDF'),
        ('epub', 'EPUB'),
    ], required=True, default='pdf')
    file_data = fields.Binary(
        string='File', required=True, attachment=False, copy=False)
    file_size = fields.Integer(compute='_compute_file_size', store=True)

    _sql_constraints = [
        ('ebook_unique', 'unique(ebook_id)',
         'Each eBook can have only one protected file.'),
    ]

    @api.depends('file_data')
    def _compute_file_size(self):
        for asset in self:
            try:
                asset.file_size = len(base64.b64decode(asset.file_data or ''))
            except (binascii.Error, ValueError):
                asset.file_size = 0

    @api.constrains('filename', 'file_format', 'file_data')
    def _check_file(self):
        for asset in self:
            decode_ebook_file(
                asset.filename, asset.file_format, asset.file_data)

    def _decode_for_delivery(self):
        self.ensure_one()
        self.env['library.ebook.access'].check_access(self.ebook_id.id)
        return decode_ebook_file(
            self.filename, self.file_format, self.file_data)
