from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase

from .common import create_test_ebook_file


class TestEbookReservation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ebook = self.env['library.ebook'].create({
            'name': 'Reservation Test Ebook',
            'website_published': True,
        })
        create_test_ebook_file(self.env, self.ebook)
        self.reader = self._create_user(
            'ebook-reservation-reader',
            [self.env.ref('base.group_user')],
        )
        self.other_reader = self._create_user(
            'ebook-reservation-other-reader',
            [self.env.ref('base.group_user')],
        )
        self.occupant = self._create_user(
            'ebook-reservation-occupant',
            [self.env.ref('base.group_user')],
        )
        self.librarian = self._create_user(
            'ebook-reservation-librarian',
            [
                self.env.ref('base.group_user'),
                self.env.ref('library_manager.group_library_librarian'),
            ],
        )

    def _create_user(self, login, groups):
        return self.env['res.users'].create({
            'name': login,
            'login': login,
            'groups_id': [(6, 0, [group.id for group in groups])],
        })

    def _reserve(self, user, **values):
        parameters = self.env['ir.config_parameter'].sudo()
        parameters.set_param(
            'library_manager.ebook_max_concurrent_loans', '1')
        active_loans = self.env['library.ebook.loan'].sudo().search([
            ('ebook_id', '=', self.ebook.id),
            ('state', '=', 'active'),
        ])
        if not active_loans:
            self.env['library.ebook.loan'].create({
                'ebook_id': self.ebook.id,
                'borrower_id': self.occupant.partner_id.id,
            })
        return self.env['library.ebook.reservation'].with_user(user).create({
            'ebook_id': self.ebook.id,
            **values,
        })

    def test_reader_can_create_own_pending_reservation(self):
        reservation = self._reserve(
            self.reader,
            borrower_id=self.other_reader.partner_id.id,
            state='fulfilled',
        )

        self.assertEqual(reservation.borrower_id, self.reader.partner_id)
        self.assertEqual(reservation.state, 'pending')
        self.assertEqual(reservation.reservation_date, fields.Date.today())

    def test_reader_cannot_reserve_an_available_ebook(self):
        with self.assertRaises(ValidationError):
            self.env['library.ebook.reservation'].with_user(
                self.reader).create({'ebook_id': self.ebook.id})

    def test_member_cannot_reserve_ebook_without_protected_file(self):
        ebook_without_file = self.env['library.ebook'].create({
                'name': 'Reservation Without File',
                'website_published': True,
        })
        with self.assertRaises(ValidationError):
                self.env['library.ebook.reservation'].with_user(
                    self.reader).create({'ebook_id': ebook_without_file.id})

    def test_reader_can_only_see_own_reservations(self):
        own_reservation = self._reserve(self.reader)
        other_reservation = self._reserve(self.other_reader)

        reader_reservations = self.env[
            'library.ebook.reservation'
        ].with_user(self.reader).search([])
        self.assertEqual(reader_reservations.ids, own_reservation.ids)
        self.assertNotIn(other_reservation, reader_reservations)

    def test_reader_cannot_change_reservation_state(self):
        reservation = self._reserve(self.reader)

        with self.assertRaises(AccessError):
            reservation.with_user(self.reader).write({'state': 'fulfilled'})

    def test_only_one_pending_reservation_per_reader_and_ebook(self):
        reservation = self._reserve(self.reader)

        with self.assertRaises(ValidationError):
            self._reserve(self.reader)

        reservation.with_user(self.librarian).write({'state': 'cancelled'})
        replacement = self._reserve(self.reader)
        self.assertEqual(replacement.state, 'pending')

    def test_librarian_can_update_reservation_status(self):
        reservation = self._reserve(self.reader)
        blocking_loan = self.env['library.ebook.loan'].sudo().search([
            ('ebook_id', '=', self.ebook.id),
            ('state', '=', 'active'),
        ], limit=1)
        blocking_loan.action_mark_returned()

        reservation.with_user(self.librarian).action_mark_fulfilled()

        self.assertEqual(reservation.state, 'fulfilled')

    def test_reader_can_cancel_own_pending_reservation(self):
        reservation = self._reserve(self.reader)

        reservation.with_user(self.reader).action_cancel()

        self.assertEqual(reservation.state, 'cancelled')

    def test_reader_cannot_cancel_another_members_reservation(self):
        reservation = self._reserve(self.reader)

        with self.assertRaises(AccessError):
            reservation.with_user(self.other_reader).action_cancel()

    def test_archived_ebook_cannot_be_reserved(self):
        self.env['library.ebook.loan'].create({
            'ebook_id': self.ebook.id,
            'borrower_id': self.occupant.partner_id.id,
        })
        self.ebook.active = False

        with self.assertRaises(ValidationError):
            self._reserve(self.reader)
