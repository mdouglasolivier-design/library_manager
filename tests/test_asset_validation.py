import base64
from io import BytesIO
import zipfile

import pymupdf
from PIL import Image

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

    def _cover_image(self, color=(30, 120, 60)):
        image = Image.new('RGB', (80, 120), color)
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()

    def _epub_fixture(
            self, cover_image=None, designated=True, epub3=False):
        data = BytesIO()
        cover_metadata = (
            '' if epub3 else
            '<meta name="cover" content="cover-image"/>')
        cover_properties = (
            ' properties="cover-image"' if epub3 else '')
        package = (
            '<package><metadata>{}</metadata><manifest>'
            '<item id="cover-image" href="images/cover.png" '
            'media-type="image/png"{}/></manifest></package>'
        ).format(cover_metadata, cover_properties)
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr(
                'mimetype', 'application/epub+zip',
                compress_type=zipfile.ZIP_STORED)
            archive.writestr(
                'META-INF/container.xml',
                '<container><rootfiles><rootfile '
                'full-path="OPS/package.opf"/></rootfiles></container>',
                compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr('OPS/package.opf', package)
            if designated and cover_image:
                archive.writestr('OPS/images/cover.png', cover_image)
        return data.getvalue()

    def _pdf_fixture(self, cover_image=None):
        document = pymupdf.open()
        page = document.new_page()
        if cover_image:
            page.insert_image(page.rect, stream=cover_image)
        else:
            page.insert_text((72, 72), 'First page cover')
        content = document.tobytes()
        document.close()
        return content

    def test_valid_pdf_file_is_accepted(self):
        content = b'%PDF-1.7\nPDF fixture'
        asset = self._create_asset('fixture.pdf', 'pdf', content)

        self.assertEqual(asset.file_size, len(content))

    def test_valid_epub_package_is_accepted(self):
        asset = self._create_asset(
            'fixture.epub', 'epub', self._epub_fixture())

        self.assertEqual(asset.file_format, 'epub')

    def test_epub_designated_cover_is_previewed_and_saved(self):
        epub = self._epub_fixture(cover_image=self._cover_image())

        asset = self._create_asset('cover.epub', 'epub', epub)

        self.assertTrue(asset.cover_preview)
        self.assertTrue(self.ebook.cover_image)
        self.assertEqual(
            base64.b64decode(asset.file_data), epub)
        self.assertEqual(
            base64.b64decode(asset.cover_preview),
            base64.b64decode(self.ebook.cover_image))

    def test_epub3_cover_image_property_is_extracted(self):
        asset = self._create_asset(
            'cover.epub', 'epub',
            self._epub_fixture(
                cover_image=self._cover_image(), epub3=True))

        self.assertTrue(asset.cover_preview)
        self.assertTrue(self.ebook.cover_image)

    def test_pdf_embedded_cover_image_is_extracted(self):
        pdf = self._pdf_fixture(cover_image=self._cover_image())

        asset = self._create_asset('cover.pdf', 'pdf', pdf)

        self.assertTrue(asset.cover_preview)
        self.assertTrue(self.ebook.cover_image)
        self.assertEqual(base64.b64decode(asset.file_data), pdf)

    def test_pdf_first_page_is_rendered_when_no_cover_image_is_embedded(self):
        asset = self._create_asset(
            'first-page.pdf', 'pdf', self._pdf_fixture())

        preview = Image.open(BytesIO(base64.b64decode(asset.cover_preview)))
        self.assertGreater(preview.width, 0)
        self.assertGreater(preview.height, 0)
        self.assertTrue(self.ebook.cover_image)

    def test_existing_manual_cover_is_not_overwritten(self):
        manual_cover = self._cover_image((180, 30, 30))
        self.ebook.cover_image = base64.b64encode(manual_cover)

        self._create_asset(
            'cover.epub', 'epub',
            self._epub_fixture(cover_image=self._cover_image()))

        self.assertEqual(
            base64.b64decode(self.ebook.cover_image), manual_cover)

    def test_extraction_failure_keeps_valid_original_file(self):
        content = b'%PDF-1.7\nPDF fixture'

        asset = self._create_asset('fixture.pdf', 'pdf', content)

        self.assertEqual(base64.b64decode(asset.file_data), content)
        self.assertFalse(self.ebook.cover_image)

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
