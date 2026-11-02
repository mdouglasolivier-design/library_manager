import re

from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.exceptions import UserError
from odoo.http import request


class LibraryAuthSignupHome(AuthSignupHome):

    def get_auth_signup_qcontext(self):
        context = super().get_auth_signup_qcontext()
        context['phone'] = request.params.get('phone', '')
        return context

    def do_signup(self, qcontext):
        phone = (qcontext.get('phone') or '').strip()
        if not qcontext.get('token') and not re.fullmatch(
                r'[0-9+().\-\s]{7,32}', phone):
            raise UserError("Enter a valid phone number to register.")
        super().do_signup(qcontext)
        if not qcontext.get('token'):
            request.env.user.partner_id.sudo().write({'phone': phone})
