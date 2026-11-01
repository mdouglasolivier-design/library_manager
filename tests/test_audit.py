from odoo.tests.common import TransactionCase

from .common import create_test_ebook_file


class TestEbookAudit(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ebook = self.env['library.ebook'].create({
            'name': 'Audit Test eBook',
            'website_published': True,
        })
        self.asset = create_test_ebook_file(self.env, self.ebook)
        self.reader = self.env['res.users'].create({
            'name': 'audit-reader',
            'login': 'audit-reader',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.librarian = self.env['res.users'].create({
            'name': 'audit-librarian',
            'login': 'audit-librarian',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('library_manager.group_library_librarian').id,
            ])],
        })

    def test_request_issue_and_return_are_recorded_with_actor(self):
        borrowing_request = self.env[
            'library.ebook.request'
        ].with_user(self.reader).submit_for_current_user(self.ebook.id)
        submitted_event = self.env['library.ebook.audit'].sudo().search([
            ('event_type', '=', 'request_submitted'),
            ('request_id', '=', borrowing_request.id),
        ], limit=1)
        self.assertTrue(submitted_event)
        self.assertEqual(submitted_event.actor_id, self.reader)
        self.assertEqual(submitted_event.partner_id, self.reader.partner_id)

        borrowing_request.with_user(self.librarian).action_approve()
        loan = borrowing_request.loan_id
        self.assertTrue(self.env['library.ebook.audit'].sudo().search([
            ('event_type', '=', 'request_approved'),
            ('request_id', '=', borrowing_request.id),
            ('loan_id', '=', loan.id),
        ], limit=1))
        self.assertTrue(self.env['library.ebook.audit'].sudo().search([
            ('event_type', '=', 'loan_issued'),
            ('loan_id', '=', loan.id),
        ], limit=1))

        loan.with_user(self.librarian).action_mark_returned()
        returned_event = self.env['library.ebook.audit'].sudo().search([
            ('event_type', '=', 'loan_returned'),
            ('loan_id', '=', loan.id),
        ], limit=1)
        self.assertTrue(returned_event)
        self.assertEqual(returned_event.actor_id, self.librarian)

    def test_asset_upload_is_audited_without_logging_file_contents(self):
        event = self.env['library.ebook.audit'].sudo().search([
            ('event_type', '=', 'asset_uploaded'),
            ('asset_id', '=', self.asset.id),
        ], limit=1)

        self.assertTrue(event)
        self.assertEqual(event.details, self.asset.filename)
        self.assertNotIn(self.asset.file_data.decode('ascii'), event.details)
