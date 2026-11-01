import base64
import sys
import threading
import traceback

from psycopg2.errors import SerializationFailure

from odoo import SUPERUSER_ID, api
from odoo.api import Transaction
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from .common import create_test_ebook_file


class TestEbookLoanLimitsAndCapacity(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ebook = self.env['library.ebook'].create({
            'name': 'Concurrent Capacity eBook',
        })
        create_test_ebook_file(self.env, self.ebook)
        self.first_partner = self.env['res.partner'].create({
            'name': 'Capacity Member One',
        })
        self.second_partner = self.env['res.partner'].create({
            'name': 'Capacity Member Two',
        })
        self.parameters = self.env['ir.config_parameter'].sudo()

    def test_second_active_loan_is_rejected_at_title_capacity(self):
        self.parameters.set_param(
            'library_manager.ebook_max_concurrent_loans', '1')
        self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.first_partner.id,
        })

        with self.assertRaises(ValidationError):
            self.env['library.ebook.loan'].create({
                'ebook_id': self.ebook.id,
                'borrower_id': self.second_partner.id,
            })

        self.assertEqual(self.ebook.availability_status, 'on_loan')

    def test_bulk_issue_cannot_exceed_title_capacity(self):
        self.parameters.set_param(
            'library_manager.ebook_max_concurrent_loans', '1')
        with self.assertRaises(ValidationError):
            self.env['library.ebook.loan'].create([
                {
                    'ebook_id': self.ebook.id,
                    'borrower_id': self.first_partner.id,
                },
                {
                    'ebook_id': self.ebook.id,
                    'borrower_id': self.second_partner.id,
                },
            ])

        self.assertFalse(self.env['library.ebook.loan'].search([
            ('ebook_id', '=', self.ebook.id),
            ('state', '=', 'active'),
        ]))

    def test_member_active_loan_limit_is_enforced_across_titles(self):
        second_ebook = self.env['library.ebook'].create({
            'name': 'Another Capacity eBook',
        })
        create_test_ebook_file(self.env, second_ebook)
        self.parameters.set_param(
            'library_manager.ebook_max_concurrent_loans', '0')
        self.parameters.set_param(
            'library_manager.ebook_max_active_loans', '1')
        self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.first_partner.id,
        })

        with self.assertRaises(ValidationError):
            self.env['library.ebook.loan'].create({
                'ebook_id': second_ebook.id,
                'borrower_id': self.first_partner.id,
            })

    def test_simultaneous_loans_do_not_exceed_title_capacity(self):
        registry = self.env.registry
        parameter_key = 'library_manager.ebook_max_concurrent_loans'
        ebook_id = False
        partner_ids = []
        prior_parameter = False
        parameter_existed = False
        outcomes = []
        barrier = threading.Barrier(2)

        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            params = env['ir.config_parameter'].sudo()
            prior = params.search([('key', '=', parameter_key)], limit=1)
            parameter_existed = bool(prior)
            prior_parameter = prior.value if prior else False
            params.set_param(parameter_key, '1')
            ebook = env['library.ebook'].create({
                'name': 'Parallel Capacity Test eBook',
            })
            ebook_id = ebook.id
            env['library.ebook.asset'].create({
                'ebook_id': ebook.id,
                'filename': 'parallel-test.pdf',
                'file_format': 'pdf',
                'file_data': base64.b64encode(
                    b'%PDF-1.7\nParallel test').decode('ascii'),
            })
            partners = env['res.partner'].create([
                {'name': 'Parallel Borrower One'},
                {'name': 'Parallel Borrower Two'},
            ])
            partner_ids = partners.ids
            cr.commit()

        def issue_loan(partner_id):
            try:
                with registry.cursor() as cr:
                    cr.transaction = Transaction(registry)
                    env = api.Environment(cr, SUPERUSER_ID, {})
                    barrier.wait(timeout=15)
                    env['library.ebook.loan'].create({
                        'ebook_id': ebook_id,
                        'borrower_id': partner_id,
                    })
                    cr.commit()
                    outcomes.append('issued')
            except ValidationError:
                outcomes.append('capacity_rejected')
            except SerializationFailure:
                outcomes.append('capacity_rejected')
            except Exception as error:
                outcomes.append('unexpected_error: %s' % error)

        threads = [
            threading.Thread(target=issue_loan, args=(partner_id,), daemon=True)
            for partner_id in partner_ids
        ]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
            alive_threads = [
                thread for thread in threads if thread.is_alive()]
            if alive_threads:
                frames = sys._current_frames()
                stacks = '\n'.join(
                    '%s:\n%s' % (
                        thread.name,
                        ''.join(traceback.format_stack(
                            frames[thread.ident])))
                    for thread in alive_threads
                    if thread.ident in frames
                )
                self.fail(
                    'Loan workers did not finish. Outcomes: %r\n%s'
                    % (outcomes, stacks))
            self.assertCountEqual(
                outcomes, ['issued', 'capacity_rejected'])
        finally:
            with registry.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                env['library.ebook.audit'].sudo().search([
                    ('ebook_id', '=', ebook_id),
                ]).unlink()
                env['library.ebook.loan'].sudo().search([
                    ('ebook_id', '=', ebook_id),
                ]).unlink()
                env['library.ebook.asset'].sudo().search([
                    ('ebook_id', '=', ebook_id),
                ]).unlink()
                env['library.ebook'].sudo().browse(ebook_id).unlink()
                env['res.partner'].sudo().browse(partner_ids).unlink()
                params = env['ir.config_parameter'].sudo()
                prior = params.search([('key', '=', parameter_key)], limit=1)
                if parameter_existed:
                    prior.value = prior_parameter
                elif prior:
                    prior.unlink()
                cr.commit()
