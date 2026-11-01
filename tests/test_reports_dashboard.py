from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase

from .common import create_test_ebook_file


class TestLibraryDashboardStatistics(TransactionCase):

    def setUp(self):
        super().setUp()
        self.librarian = self.env['res.users'].create({
            'name': 'dashboard-librarian',
            'login': 'dashboard-librarian',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('library_manager.group_library_librarian').id,
            ])],
        })

    def test_dashboard_counts_catalog_and_borrowing_activity(self):
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param(
            'library_manager.ebook_max_concurrent_loans', '0')
        before = self.env['library.dashboard'].sudo().create({})
        baseline = {
            'published': before.published_ebook_count,
            'missing': before.file_unavailable_count,
            'ready': before.ready_to_borrow_count,
            'active': before.active_loan_count,
            'overdue': before.overdue_loan_count,
            'requests': before.pending_request_count,
            'reservations': before.pending_reservation_count,
        }

        ready_ebook = self.env['library.ebook'].create({
            'name': 'Dashboard Ready eBook',
            'website_published': True,
        })
        create_test_ebook_file(self.env, ready_ebook)
        overdue_ebook = self.env['library.ebook'].create({
            'name': 'Dashboard Overdue eBook',
            'website_published': True,
        })
        create_test_ebook_file(self.env, overdue_ebook)
        missing_ebook = self.env['library.ebook'].create({
            'name': 'Dashboard Missing File eBook',
            'website_published': True,
        })

        member = self.env['res.partner'].create({
            'name': 'Dashboard Member',
        })
        today = fields.Date.today()
        self.env['library.ebook.loan'].create({
            'ebook_id': ready_ebook.id,
            'borrower_id': member.id,
        })
        self.env['library.ebook.loan'].create({
            'ebook_id': overdue_ebook.id,
            'borrower_id': member.id,
            'borrow_date': today - timedelta(days=14),
            'due_date': today - timedelta(days=1),
        })
        self.env['library.ebook.request'].create({
            'ebook_id': ready_ebook.id,
            'borrower_id': member.id,
        })
        self.env['library.ebook.reservation'].create({
            'ebook_id': ready_ebook.id,
            'borrower_id': member.id,
        })

        dashboard = self.env['library.dashboard'].with_user(
            self.librarian).create({})
        self.assertEqual(
            dashboard.published_ebook_count, baseline['published'] + 3)
        self.assertEqual(
            dashboard.file_unavailable_count, baseline['missing'] + 1)
        self.assertEqual(
            dashboard.ready_to_borrow_count, baseline['ready'] + 2)
        self.assertEqual(
            dashboard.active_loan_count, baseline['active'] + 2)
        self.assertEqual(
            dashboard.overdue_loan_count, baseline['overdue'] + 1)
        self.assertEqual(
            dashboard.pending_request_count, baseline['requests'] + 1)
        self.assertEqual(
            dashboard.pending_reservation_count, baseline['reservations'] + 1)

    def test_analytics_menu_action_opens_dashboard_form(self):
        result = self.env.ref(
            'library_manager.action_library_dashboard'
        ).with_user(self.librarian).run()

        self.assertEqual(result['res_model'], 'library.dashboard')
        self.assertEqual(result['view_mode'], 'form')
        self.assertTrue(result['res_id'])
