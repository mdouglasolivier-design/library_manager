import base64
import binascii

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
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
        self.env['library.ebook.access'].check_ebook_access(
            self.ebook_id.id)
        return decode_ebook_file(
            self.filename, self.file_format, self.file_data)

    @api.model_create_multi
    def create(self, vals_list):
        ebook_ids = []
        for values in vals_list:
            decode_ebook_file(
                values.get('filename'),
                values.get('file_format', 'pdf'),
                values.get('file_data'))
            ebook_id = values.get('ebook_id')
            if ebook_id:
                ebook_ids.append(ebook_id)

        if (len(ebook_ids) != len(set(ebook_ids))
                or self.sudo().search_count([
                ('ebook_id', 'in', ebook_ids),
        ])):
            raise ValidationError(
                "Each eBook can have only one protected file.")

        try:
            with self.env.cr.savepoint():
                assets = super().create(vals_list)
        except IntegrityError as error:
            if error.diag.constraint_name != (
                    'library_ebook_asset_ebook_unique'):
                raise
            raise ValidationError(
                "Each eBook can have only one protected file.") from error
        for asset in assets:
            asset.env['library.ebook.audit']._record_event(
                'asset_uploaded',
                ebook=asset.ebook_id,
                asset=asset,
                detail=asset.filename)
        return assets

    def write(self, vals):
        result = super().write(vals)
        if {'filename', 'file_format', 'file_data', 'ebook_id'} & vals.keys():
            for asset in self:
                asset.env['library.ebook.audit']._record_event(
                    'asset_updated',
                    ebook=asset.ebook_id,
                    asset=asset,
                    detail=asset.filename)
        return result

    def unlink(self):
        if not self.env.su and not (
                self.env.user.has_group(
                    'library_manager.group_library_librarian')
                or self.env.user.has_group('base.group_system')):
            raise AccessError("Only librarians can remove protected eBook files.")
        for asset in self:
            asset.env['library.ebook.audit']._record_event(
                'asset_removed',
                ebook=asset.ebook_id,
                asset=asset,
                detail=asset.filename)
        return super().unlink()
