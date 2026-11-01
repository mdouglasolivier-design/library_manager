from odoo import api, fields, models


class LibraryDashboard(models.TransientModel):
    _name = 'library.dashboard'
    _description = 'Library Analytics Dashboard'

    name = fields.Char(default='Library analytics', readonly=True)
    published_ebook_count = fields.Integer(
        string='Published eBooks', compute='_compute_statistics')
    file_unavailable_count = fields.Integer(
        string='Published eBooks without a file', compute='_compute_statistics')
    ready_to_borrow_count = fields.Integer(
        string='Ready to borrow', compute='_compute_statistics')
    active_loan_count = fields.Integer(
        string='Active eBook loans', compute='_compute_statistics')
    overdue_loan_count = fields.Integer(
        string='Overdue eBook loans', compute='_compute_statistics')
    pending_request_count = fields.Integer(
        string='Pending borrowing requests', compute='_compute_statistics')
    pending_reservation_count = fields.Integer(
        string='Pending reservations', compute='_compute_statistics')

    @api.depends()
    def _compute_statistics(self):
        Ebook = self.env['library.ebook'].sudo()
        Loan = self.env['library.ebook.loan'].sudo()
        Request = self.env['library.ebook.request'].sudo()
        Reservation = self.env['library.ebook.reservation'].sudo()
        published_domain = [
            ('active', '=', True),
            ('website_published', '=', True),
        ]
        active_loan_domain = [('state', '=', 'active')]
        today = fields.Date.today()
        for dashboard in self:
            dashboard.published_ebook_count = Ebook.search_count(
                published_domain)
            dashboard.file_unavailable_count = Ebook.search_count(
                published_domain + [('file_available', '=', False)])
            dashboard.ready_to_borrow_count = Ebook.search_count(
                published_domain + [
                    ('file_available', '=', True),
                    ('availability_status', '=', 'available'),
                ])
            dashboard.active_loan_count = Loan.search_count(
                active_loan_domain)
            dashboard.overdue_loan_count = Loan.search_count(
                active_loan_domain + [('due_date', '<', today)])
            dashboard.pending_request_count = Request.search_count([
                ('state', '=', 'pending'),
            ])
            dashboard.pending_reservation_count = Reservation.search_count([
                ('state', '=', 'pending'),
            ])

    @api.model
    def action_open_dashboard(self):
        dashboard = self.create({})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Library analytics',
            'res_model': self._name,
            'view_mode': 'form',
            'view_id': self.env.ref(
                'library_manager.view_library_dashboard_form').id,
            'res_id': dashboard.id,
            'target': 'current',
            'context': {'create': False, 'edit': False, 'delete': False},
        }
