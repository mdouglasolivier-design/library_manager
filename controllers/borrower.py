import base64
import re
from datetime import timedelta

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request


class LibraryBorrowerController(http.Controller):

    def _member_partner(self):
        return request.env.user.partner_id

    def _consume_notice(self):
        return request.session.pop('library_portal_notice', False)

    def _set_notice(self, message, level='info'):
        request.session['library_portal_notice'] = {
            'message': message,
            'level': level,
        }

    def _member_context(self):
        return {
            'is_public': False,
            'partner': self._member_partner(),
            'notice': self._consume_notice(),
        }

    @http.route(
        '/my/library', type='http', auth='user', website=True, sitemap=False)
    def member_dashboard(self, **params):
        partner = self._member_partner()
        Loan = request.env['library.ebook.loan']
        Request = request.env['library.ebook.request']
        Reservation = request.env['library.ebook.reservation']
        Notification = request.env['library.ebook.notification']
        today = fields.Date.today()
        active_domain = [
            ('borrower_id', '=', partner.id),
            ('state', '=', 'active'),
        ]
        loans = Loan.search(
            active_domain, order='due_date, id', limit=8)
        context = self._member_context()
        context.update({
            'active_count': Loan.search_count(active_domain),
            'pending_request_count': Request.search_count([
                ('borrower_id', '=', partner.id),
                ('state', '=', 'pending'),
            ]),
            'pending_reservation_count': Reservation.search_count([
                ('borrower_id', '=', partner.id),
                ('state', '=', 'pending'),
            ]),
            'overdue_count': Loan.search_count(active_domain + [
                ('due_date', '<', today),
            ]),
            'due_soon_loans': Loan.search(active_domain + [
                ('due_date', '>=', today),
                ('due_date', '<=', today + timedelta(days=3)),
            ], order='due_date, id', limit=5),
            'recent_loans': loans[:4],
            'unread_notification_count': Notification.search_count([
                ('partner_id', '=', partner.id),
                ('is_read', '=', False),
            ]),
        })
        return request.render(
            'library_manager.portal_library_dashboard', context)

    @http.route(
        '/my/library/ebooks/<int:ebook_id>/request', type='http',
        auth='user', website=True, methods=['POST'], csrf=True)
    def submit_ebook_request(self, ebook_id, **post):
        try:
            result = request.env[
                'library.ebook.request'
            ].submit_for_current_user(ebook_id)
        except (AccessError, UserError, ValidationError) as error:
            self._set_notice(str(error), 'warning')
            return request.redirect('/library/ebooks/%s' % ebook_id)
        if result._name == 'library.ebook.reservation':
            self._set_notice("Your eBook reservation has been submitted.")
            return request.redirect('/my/library/reservations')
        self._set_notice(
            "Your request was approved and the eBook is now in your library."
            if result.state == 'approved'
            else "Your borrowing request has been submitted.")
        return request.redirect('/my/library/requests')

    @http.route(
        '/my/library/loans', type='http', auth='user',
        website=True, sitemap=False)
    def member_loans(self, status='active', **params):
        partner = self._member_partner()
        today = fields.Date.today()
        domain = [('borrower_id', '=', partner.id)]
        if status == 'active':
            domain.append(('state', '=', 'active'))
        elif status == 'returned':
            domain.append(('state', '=', 'returned'))
        elif status == 'overdue':
            domain.extend([
                ('state', '=', 'active'),
                ('due_date', '<', today),
            ])
        elif status == 'due_soon':
            domain.extend([
                ('state', '=', 'active'),
                ('due_date', '>=', today),
                ('due_date', '<=', today + timedelta(days=3)),
            ])
        else:
            status = 'all'
        loans = request.env['library.ebook.loan'].search(
            domain, order='borrow_date desc, id desc')
        reader_assets = {}
        for loan in loans.filtered(lambda item: item.state == 'active'):
            try:
                asset = request.env[
                    'library.ebook.access'
                ].get_readable_asset(loan.ebook_id.id)
            except AccessError:
                continue
            if asset:
                reader_assets[loan.id] = asset
        context = self._member_context()
        context.update({
            'loans': loans,
            'reader_assets': reader_assets,
            'status': status,
        })
        return request.render(
            'library_manager.portal_library_loans', context)

    @http.route(
        '/my/library/history', type='http', auth='user',
        website=True, sitemap=False)
    def member_history(self, q=None, **params):
        query = (q or '').strip()[:100]
        domain = [
            ('borrower_id', '=', self._member_partner().id),
            ('state', '=', 'returned'),
        ]
        if query:
            domain += [
                '|', '|',
                ('ebook_id.name', 'ilike', query),
                ('ebook_id.author', 'ilike', query),
                ('ebook_id.isbn', 'ilike', query),
            ]
        loans = request.env['library.ebook.loan'].search(
            domain, order='return_date desc, id desc')
        context = self._member_context()
        context['loans'] = loans
        context['query'] = query
        return request.render(
            'library_manager.portal_library_history', context)

    @http.route(
        '/my/library/requests', type='http', auth='user',
        website=True, sitemap=False)
    def member_requests(self, **params):
        requests = request.env['library.ebook.request'].search(
            [('borrower_id', '=', self._member_partner().id)],
            order='request_date desc, id desc')
        context = self._member_context()
        context['borrowing_requests'] = requests
        return request.render(
            'library_manager.portal_library_requests', context)

    @http.route(
        '/my/library/requests/<int:request_id>/cancel', type='http',
        auth='user', website=True, methods=['POST'], csrf=True)
    def cancel_request(self, request_id, **post):
        borrowing_request = request.env[
            'library.ebook.request'
        ].browse(request_id).exists()
        if not borrowing_request:
            return request.not_found()
        try:
            borrowing_request.action_cancel()
        except (AccessError, UserError) as error:
            self._set_notice(str(error), 'warning')
        return request.redirect('/my/library/requests')

    @http.route(
        '/my/library/reservations', type='http', auth='user',
        website=True, sitemap=False)
    def member_reservations(self, **params):
        reservations = request.env['library.ebook.reservation'].search(
            [('borrower_id', '=', self._member_partner().id)],
            order='reservation_date desc, id desc')
        context = self._member_context()
        context['reservations'] = reservations
        return request.render(
            'library_manager.portal_library_reservations', context)

    @http.route(
        '/my/library/reservations/<int:reservation_id>/cancel', type='http',
        auth='user', website=True, methods=['POST'], csrf=True)
    def cancel_reservation(self, reservation_id, **post):
        reservation = request.env[
            'library.ebook.reservation'
        ].browse(reservation_id).exists()
        if not reservation:
            return request.not_found()
        try:
            reservation.action_cancel()
        except (AccessError, UserError) as error:
            self._set_notice(str(error), 'warning')
        return request.redirect('/my/library/reservations')

    @http.route(
        '/my/library/notifications', type='http', auth='user',
        website=True, sitemap=False)
    def member_notifications(self, **params):
        notifications = request.env['library.ebook.notification'].search(
            [('partner_id', '=', self._member_partner().id)],
            order='create_date desc, id desc', limit=100)
        context = self._member_context()
        context['notifications'] = notifications
        return request.render(
            'library_manager.portal_library_notifications', context)

    @http.route(
        '/my/library/notifications/<int:notification_id>/read', type='http',
        auth='user', website=True, methods=['POST'], csrf=True)
    def mark_notification_read(self, notification_id, **post):
        notification = request.env[
            'library.ebook.notification'
        ].browse(notification_id).exists()
        if not notification:
            return request.not_found()
        try:
            notification.action_mark_read()
        except AccessError as error:
            self._set_notice(str(error), 'warning')
        return request.redirect('/my/library/notifications')

    @http.route(
        '/my/library/account', type='http', auth='user',
        website=True, sitemap=False)
    def member_account(self, **params):
        context = self._member_context()
        context['membership_status'] = (
            'Active' if request.env.user.active else 'Inactive')
        return request.render(
            'library_manager.portal_library_account', context)

    @http.route(
        '/my/library/account/update', type='http', auth='user',
        website=True, methods=['POST'], csrf=True)
    def update_member_account(self, phone=None, **post):
        phone = (phone or '').strip()
        if len(phone) > 32 or not re.fullmatch(r'[0-9+().\-\s]*', phone):
            self._set_notice(
                "Enter a valid phone number using digits and standard phone punctuation.",
                'warning')
        else:
            request.env.user.partner_id.sudo().write({
                'phone': phone or False,
            })
            self._set_notice("Your contact details have been updated.")
        return request.redirect('/my/library/account')

    @http.route(
        '/my/library/ebooks/<int:ebook_id>/cover', type='http',
        auth='user', website=True, sitemap=False)
    def member_ebook_cover(self, ebook_id, **params):
        loan = request.env['library.ebook.loan'].search([
            ('ebook_id', '=', ebook_id),
            ('borrower_id', '=', self._member_partner().id),
        ], limit=1)
        if not loan:
            return request.not_found()
        ebook = loan.ebook_id.sudo()
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
            ('Cache-Control', 'private, max-age=3600'),
            ('X-Content-Type-Options', 'nosniff'),
        ])
