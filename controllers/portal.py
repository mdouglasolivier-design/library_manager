import base64
from datetime import date
from urllib.parse import urlencode

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class LibraryCatalogController(http.Controller):

    @http.route(
        '/library', type='http', auth='public', website=True, sitemap=True)
    def library_home(self, **params):
        Ebook = request.env['library.ebook'].sudo()
        domain = [
            ('active', '=', True),
            ('website_published', '=', True),
        ]
        featured = Ebook.search(
            domain, order='loan_count desc, id desc', limit=8)
        recent = Ebook.search(
            domain, order='create_date desc, id desc', limit=8)
        categories = request.env['library.ebook.category'].sudo().search([
            ('active', '=', True),
            ('ebook_ids', 'any', [
                ('active', '=', True),
                ('website_published', '=', True),
            ]),
        ], order='sequence, name', limit=12)
        category_domain = [
            ('active', '=', True),
            ('ebook_ids', 'any', [
                ('active', '=', True),
                ('website_published', '=', True),
            ]),
        ]
        return request.render('library_manager.portal_library_home', {
            'featured_ebooks': featured,
            'recent_ebooks': recent,
            'categories': categories,
            'category_count': request.env[
                'library.ebook.category'
            ].sudo().search_count(category_domain),
            'available_count': Ebook.search_count(domain + [
                ('availability_status', '=', 'available'),
                ('file_available', '=', True),
            ]),
            'ebook_count': Ebook.search_count(domain),
            'is_public': request.env.user._is_public(),
        })

    @http.route(
        '/library/ebooks', type='http', auth='public', website=True,
        sitemap=True)
    def library_catalog(self, q=None, category=None, availability=None,
                        year=None, sort='newest', page=1, **params):
        Ebook = request.env['library.ebook'].sudo()
        domain = [
            ('active', '=', True),
            ('website_published', '=', True),
        ]
        query = (q or '').strip()[:100]
        if query:
            domain += [
                '|', '|', '|',
                ('name', 'ilike', query),
                ('author', 'ilike', query),
                ('isbn', 'ilike', query),
                ('publisher', 'ilike', query),
            ]
        category_id = False
        if category:
            try:
                category_id = int(category)
            except (TypeError, ValueError):
                category_id = False
            if category_id:
                domain.append(('category_id', '=', category_id))
        if availability in ('available', 'on_loan'):
            domain.append(('availability_status', '=', availability))
            domain.append(('file_available', '=', True))
        elif availability == 'file_unavailable':
            domain.append(('file_available', '=', False))
        publication_year = False
        if year:
            try:
                candidate_year = int(year)
            except (TypeError, ValueError):
                candidate_year = 0
            if 1000 <= candidate_year <= date.today().year:
                publication_year = candidate_year
                domain.extend([
                    ('publication_date', '>=', date(candidate_year, 1, 1)),
                    ('publication_date', '<=', date(candidate_year, 12, 31)),
                ])

        sort_orders = {
            'newest': 'create_date desc, id desc',
            'title': 'name, id',
            'popular': 'loan_count desc, name, id',
        }
        sort = sort if sort in sort_orders else 'newest'
        page_size = 20
        total = Ebook.search_count(domain)
        try:
            page_number = max(int(page), 1)
        except (TypeError, ValueError):
            page_number = 1
        page_count = max((total + page_size - 1) // page_size, 1)
        page_number = min(page_number, page_count)
        ebooks = Ebook.search(
            domain, order=sort_orders[sort],
            limit=page_size, offset=(page_number - 1) * page_size)
        categories = request.env['library.ebook.category'].sudo().search([
            ('active', '=', True),
            ('ebook_ids', 'any', [
                ('active', '=', True),
                ('website_published', '=', True),
            ]),
        ], order='sequence, name')

        query_values = {
            key: value for key, value in {
                'q': query,
                'category': category_id,
                'availability': availability,
                'year': publication_year,
                'sort': sort,
            }.items() if value
        }
        previous_url = False
        next_url = False
        if page_number > 1:
            previous_url = '/library/ebooks?' + urlencode({
                **query_values, 'page': page_number - 1})
        if page_number < page_count:
            next_url = '/library/ebooks?' + urlencode({
                **query_values, 'page': page_number + 1})
        return request.render('library_manager.portal_library_catalog', {
            'ebooks': ebooks,
            'categories': categories,
            'query': query,
            'selected_category': category_id,
            'availability': availability or '',
            'year': publication_year or '',
            'sort': sort,
            'total': total,
            'page_number': page_number,
            'page_count': page_count,
            'previous_url': previous_url,
            'next_url': next_url,
            'is_public': request.env.user._is_public(),
        })

    @http.route(
        '/library/ebooks/<int:ebook_id>', type='http',
        auth='public', website=True, sitemap=False)
    def library_ebook_detail(self, ebook_id, **params):
        ebook = request.env['library.ebook'].sudo().search([
            ('id', '=', ebook_id),
            ('active', '=', True),
            ('website_published', '=', True),
        ], limit=1)
        if not ebook:
            return request.not_found()
        related_domain = [
            ('id', '!=', ebook.id),
            ('active', '=', True),
            ('website_published', '=', True),
        ]
        if ebook.category_id:
            related_domain.append(('category_id', '=', ebook.category_id.id))
        related = request.env['library.ebook'].sudo().search(
            related_domain, limit=4, order='name, id')
        is_public = request.env.user._is_public()
        active_loan = False
        pending_request = False
        pending_reservation = False
        reader_asset = False
        if not is_public:
            partner = request.env.user.partner_id
            active_loan = request.env['library.ebook.loan'].search([
                ('ebook_id', '=', ebook.id),
                ('borrower_id', '=', partner.id),
                ('state', '=', 'active'),
            ], limit=1)
            pending_request = request.env['library.ebook.request'].search([
                ('ebook_id', '=', ebook.id),
                ('borrower_id', '=', partner.id),
                ('state', '=', 'pending'),
            ], limit=1)
            if active_loan:
                try:
                    reader_asset = request.env[
                        'library.ebook.access'
                    ].get_readable_asset(ebook.id)
                except AccessError:
                    reader_asset = False
            pending_reservation = request.env[
                'library.ebook.reservation'
            ].search([
                ('ebook_id', '=', ebook.id),
                ('borrower_id', '=', partner.id),
                ('state', '=', 'pending'),
            ], limit=1)
        return request.render('library_manager.portal_library_ebook_detail', {
            'ebook': ebook,
            'related_ebooks': related,
            'is_public': is_public,
            'at_capacity': ebook._is_at_concurrent_capacity(),
            'active_loan': active_loan,
            'reader_asset': reader_asset,
            'pending_request': pending_request,
            'pending_reservation': pending_reservation,
            'notice': request.session.pop('library_portal_notice', False),
        })

    @http.route(
        '/library/ebooks/<int:ebook_id>/cover', type='http',
        auth='public', website=True, sitemap=False)
    def library_ebook_cover(self, ebook_id, **params):
        ebook = request.env['library.ebook'].sudo().search([
            ('id', '=', ebook_id),
            ('active', '=', True),
            ('website_published', '=', True),
        ], limit=1)
        if not ebook:
            return request.not_found()
        if not ebook.cover_image:
            return request.redirect(
                '/library_manager/static/src/img/default_book_cover.svg')
        image = base64.b64decode(ebook.cover_image)
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
