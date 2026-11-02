import base64
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


class PhysicalLibraryController(http.Controller):

    def _payment_instructions(self):
        parameters = request.env['ir.config_parameter'].sudo()
        return {
            'momo_name': parameters.get_param(
                'library_manager.momo_recipient_name', 'Odoo Library'),
            'momo_phone': parameters.get_param(
                'library_manager.momo_recipient_phone', '+250791393885'),
            'bank_account': parameters.get_param(
                'library_manager.bank_account_number', '100212701941'),
            'bank_name': parameters.get_param(
                'library_manager.bank_name', ''),
            'bank_holder': parameters.get_param(
                'library_manager.bank_account_holder', ''),
            'card_instructions': parameters.get_param(
                'library_manager.external_card_instructions',
                'Configure a secure payment provider before enabling card payments.'),
        }

    @http.route(
        '/library/books', type='http', auth='public', website=True,
        sitemap=True)
    def physical_catalog(self, q=None, **params):
        query = (q or '').strip()[:100]
        domain = [('active', '=', True), ('website_published', '=', True)]
        if query:
            domain += [
                '|', '|', '|',
                ('name', 'ilike', query),
                ('author', 'ilike', query),
                ('isbn', 'ilike', query),
                ('publisher', 'ilike', query),
            ]
        books = request.env['library.book'].sudo().search(
            domain, order='name, id', limit=60)
        return request.render(
            'library_manager.portal_physical_catalog', {
                'books': books,
                'query': query,
                'is_public': request.env.user._is_public(),
            })

    @http.route(
        '/library/books/<int:book_id>', type='http', auth='public',
        website=True, sitemap=False)
    def physical_book_detail(self, book_id, **params):
        book = request.env['library.book'].sudo().search([
            ('id', '=', book_id),
            ('active', '=', True),
            ('website_published', '=', True),
        ], limit=1)
        if not book:
            return request.not_found()
        return request.render(
            'library_manager.portal_physical_book_detail', {
                'book': book,
                'is_public': request.env.user._is_public(),
                'partner': request.env.user.partner_id,
                'today': fields.Date.today(),
                'expected_return': fields.Date.today() + timedelta(days=14),
                'notice': request.session.pop(
                    'library_portal_notice', False),
                **self._payment_instructions(),
            })

    @http.route(
        '/library/books/<int:book_id>/cover', type='http',
        auth='public', website=True, sitemap=False)
    def physical_book_cover(self, book_id, **params):
        book = request.env['library.book'].sudo().search([
            ('id', '=', book_id),
            ('active', '=', True),
            ('website_published', '=', True),
        ], limit=1)
        if not book:
            return request.not_found()
        if not book.cover_image:
            return request.redirect(
                '/library_manager/static/src/img/default_book_cover.svg')
        image = base64.b64decode(book.cover_image)
        if image.startswith(b'\x89PNG\r\n\x1a\n'):
            content_type = 'image/png'
        elif image.startswith(b'RIFF') and image[8:12] == b'WEBP':
            content_type = 'image/webp'
        else:
            content_type = 'image/jpeg'
        return request.make_response(image, headers=[
            ('Content-Type', content_type),
            ('Cache-Control', 'public, max-age=3600'),
            ('X-Content-Type-Options', 'nosniff'),
        ])

    @http.route(
        '/my/library/books/<int:book_id>/request', type='http',
        auth='user', website=True, methods=['POST'], csrf=True)
    def submit_physical_request(self, book_id, **post):
        try:
            result = request.env[
                'library.book.request'
            ].submit_for_current_user(
                book_id,
                borrow_date=post.get('borrow_date'),
                due_date=post.get('due_date'),
                borrower_phone=post.get('borrower_phone'),
                payment_method=post.get('payment_method', 'momo'),
                momo_phone=post.get('momo_phone'),
                payment_reference=post.get('payment_reference'))
        except (AccessError, UserError, ValidationError, ValueError) as error:
            request.session['library_portal_notice'] = {
                'message': str(error), 'level': 'warning'}
            return request.redirect('/library/books/%s' % book_id)
        request.session['library_portal_notice'] = {
            'message': (
                'Your request was submitted. Payment must be verified by a librarian before approval.'),
            'level': 'info',
        }
        return request.redirect('/my/library/requests')

    @http.route(
        '/my/library/book-requests/<int:request_id>/cancel',
        type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def cancel_physical_request(self, request_id, **post):
        borrowing_request = request.env[
            'library.book.request'
        ].search([
            ('id', '=', request_id),
            ('borrower_id', '=', request.env.user.partner_id.id),
        ], limit=1)
        if not borrowing_request:
            return request.not_found()
        try:
            borrowing_request.write({'state': 'cancelled'})
        except (AccessError, UserError) as error:
            request.session['library_portal_notice'] = {
                'message': str(error), 'level': 'warning'}
        return request.redirect('/my/library/requests')
