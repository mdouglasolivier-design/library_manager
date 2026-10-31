import re

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class LibraryEbookReaderController(http.Controller):

    def _render_reader_page(self, template, values, status=200):
        response = request.render(template, values)
        response.status_code = status
        return response

    @http.route(
        '/my/library/ebooks/<int:ebook_id>/read', type='http',
        auth='user', website=True, sitemap=False)
    def read_ebook(self, ebook_id, **params):
        try:
            asset = request.env[
                'library.ebook.access'
            ].get_readable_asset(ebook_id)
        except AccessError:
            return self._render_reader_page(
                'library_manager.portal_ebook_reader_denied', {}, status=403)
        if not asset:
            return self._render_reader_page(
                'library_manager.portal_ebook_reader_missing', {}, status=404)
        return self._render_reader_page(
            'library_manager.portal_ebook_reader', {
                'ebook': asset.ebook_id,
                'asset': asset,
                'file_url': '/my/library/ebooks/%s/file' % ebook_id,
            })

    @http.route(
        '/my/library/ebooks/<int:ebook_id>/file', type='http',
        auth='user', website=False, sitemap=False)
    def serve_ebook_file(self, ebook_id, **params):
        try:
            asset = request.env[
                'library.ebook.access'
            ].get_readable_asset(ebook_id)
        except AccessError:
            return request.make_response(
                'An active loan is required to access this file.',
                status=403, headers=[
                    ('Content-Type', 'text/plain; charset=utf-8'),
                    ('Cache-Control', 'private, no-store'),
                ])
        if not asset:
            return request.not_found()

        content = asset._decode_for_delivery()
        total_size = len(content)
        start, end = 0, total_size - 1
        status = 200
        range_header = request.httprequest.headers.get('Range')
        if range_header:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header.strip())
            if not match or (not match.group(1) and not match.group(2)):
                return self._range_not_satisfiable(total_size)
            try:
                if match.group(1):
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else end
                else:
                    suffix_size = int(match.group(2))
                    if suffix_size <= 0:
                        return self._range_not_satisfiable(total_size)
                    start = max(total_size - suffix_size, 0)
            except ValueError:
                return self._range_not_satisfiable(total_size)
            if start >= total_size or end < start:
                return self._range_not_satisfiable(total_size)
            end = min(end, total_size - 1)
            status = 206
            content = content[start:end + 1]

        filename = ''.join(
            char for char in asset.filename
            if ord(char) < 128 and (char.isalnum() or char in ' ._-'))
        filename = filename.strip(' .') or (
            'ebook.pdf' if asset.file_format == 'pdf' else 'ebook.epub')
        disposition = 'inline' if asset.file_format == 'pdf' else 'attachment'
        headers = [
            ('Content-Type', 'application/pdf' if asset.file_format == 'pdf'
             else 'application/epub+zip'),
            ('Content-Disposition', '%s; filename="%s"' % (
                disposition, filename.replace('"', ''))),
            ('Content-Length', str(len(content))),
            ('Accept-Ranges', 'bytes'),
            ('Cache-Control', 'private, no-store'),
            ('X-Content-Type-Options', 'nosniff'),
            ('X-Frame-Options', 'SAMEORIGIN'),
        ]
        if status == 206:
            headers.append((
                'Content-Range',
                'bytes %s-%s/%s' % (start, end, total_size)))
        return request.make_response(content, headers=headers, status=status)

    def _range_not_satisfiable(self, total_size):
        return request.make_response(
            b'', status=416, headers=[
                ('Content-Range', 'bytes */%s' % total_size),
                ('Accept-Ranges', 'bytes'),
                ('Cache-Control', 'private, no-store'),
            ])
