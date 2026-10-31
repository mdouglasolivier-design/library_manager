import base64
from io import BytesIO
import zipfile

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestEbookAssetValidation(TransactionCase):

    def setUp(self):
        super().setUp()
        self.ebook = self.env['library.ebook'].create({
            'name': 'Protected Asset Validation eBook',
        })
        self.asset_model = self.env['library.ebook.asset']

    def _create_asset(self, filename, file_format, content):
        return self.asset_model.create({
            'ebook_id': self.ebook.id,
            'filename': filename,
            'file_format': file_format,
            'file_data': base64.b64encode(content).decode('ascii'),
        })

    def _epub_fixture(self):
        data = BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr(
                'mimetype', 'application/epub+zip',
                compress_type=zipfile.ZIP_STORED)
            archive.writestr(
                'META-INF/container.xml', '<container/>',
                compress_type=zipfile.ZIP_DEFLATED)
        return data.getvalue()

    def test_valid_pdf_file_is_accepted(self):
        content = b'%PDF-1.7\nPDF fixture'
        asset = self._create_asset('fixture.pdf', 'pdf', content)

        self.assertEqual(asset.file_size, len(content))

    def test_valid_epub_package_is_accepted(self):
        asset = self._create_asset(
            'fixture.epub', 'epub', self._epub_fixture())

        self.assertEqual(asset.file_format, 'epub')

    def test_file_extension_must_match_format(self):
        with self.assertRaises(ValidationError):
            self._create_asset(
                'fixture.pdf', 'epub', self._epub_fixture())

    def test_invalid_file_signature_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_asset('fixture.pdf', 'pdf', b'not a PDF')

    def test_invalid_epub_archive_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_asset('fixture.epub', 'epub', b'PK\x03\x04invalid')

    def test_empty_file_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._create_asset('fixture.pdf', 'pdf', b'')

    def test_second_protected_file_for_title_is_rejected(self):
        self._create_asset('first.pdf', 'pdf', b'%PDF-1.7\nfixture')

        with self.assertRaises(ValidationError):
            self._create_asset('second.pdf', 'pdf', b'%PDF-1.7\nfixture')

    def test_portal_user_cannot_read_private_asset_model(self):
        portal_user = self.env['res.users'].create({
            'name': 'Asset Model Portal Member',
            'login': 'asset-model-portal-member',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

        with self.assertRaises(AccessError):
            self.asset_model.with_user(portal_user).search([])
