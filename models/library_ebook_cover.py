import posixpath
from io import BytesIO
import logging
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

import pymupdf as fitz
from PIL import Image, ImageOps, UnidentifiedImageError


_logger = logging.getLogger(__name__)
_MAX_COVER_BYTES = 15 * 1024 * 1024
_MAX_XML_BYTES = 2 * 1024 * 1024
_MAX_IMAGE_PIXELS = 40_000_000
_MAX_PREVIEW_SIZE = (1200, 1800)


class CoverExtractionError(Exception):
    """Raised when an uploaded eBook has no usable cover image."""


def _normalize_image(image_data):
    if not image_data or len(image_data) > _MAX_COVER_BYTES:
        raise CoverExtractionError("Cover image is empty or too large.")
    try:
        with Image.open(BytesIO(image_data)) as image:
            width, height = image.size
            if (width <= 0 or height <= 0
                    or width * height > _MAX_IMAGE_PIXELS):
                raise CoverExtractionError(
                    "Cover image dimensions exceed the supported limit.")
            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail(_MAX_PREVIEW_SIZE, Image.Resampling.LANCZOS)
            image = image.convert(
                'RGBA' if 'A' in image.getbands() else 'RGB')
            output = BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()
    except CoverExtractionError:
        raise
    except (OSError, ValueError, UnidentifiedImageError,
            Image.DecompressionBombError) as error:
        raise CoverExtractionError(
            "The extracted cover is not a supported image.") from error


def _local_name(element):
    return element.tag.rsplit('}', 1)[-1]


def _epub_member_path(base_path, href):
    href_path = urllib.parse.urlsplit(href).path
    decoded_path = urllib.parse.unquote(href_path)
    if (not decoded_path or decoded_path.startswith('/')
            or '\\' in decoded_path or '\x00' in decoded_path):
        raise CoverExtractionError("The EPUB cover path is invalid.")
    path = posixpath.normpath(posixpath.join(base_path, decoded_path))
    if path == '..' or path.startswith('../'):
        raise CoverExtractionError("The EPUB cover path is invalid.")
    return path


def _read_epub_member(archive, path, max_size):
    try:
        info = archive.getinfo(path)
    except KeyError as error:
        raise CoverExtractionError(
            "The EPUB cover resource is missing.") from error
    if info.file_size <= 0 or info.file_size > max_size:
        raise CoverExtractionError(
            "The EPUB cover resource exceeds the supported size.")
    try:
        with archive.open(info) as member:
            data = member.read(max_size + 1)
        if len(data) > max_size:
            raise CoverExtractionError(
                "The EPUB cover resource exceeds the supported size.")
        return data
    except (RuntimeError, OSError, EOFError, zipfile.BadZipFile) as error:
        raise CoverExtractionError(
            "The EPUB cover resource could not be read.") from error


def _extract_epub_cover(contents):
    try:
        with zipfile.ZipFile(BytesIO(contents)) as archive:
            container = ET.fromstring(_read_epub_member(
                archive, 'META-INF/container.xml', _MAX_XML_BYTES))
            rootfile = next(
                element for element in container.iter()
                if _local_name(element) == 'rootfile')
            package_path = rootfile.attrib['full-path']
            if (not package_path or package_path.startswith('/')
                    or '\\' in package_path or '\x00' in package_path):
                raise CoverExtractionError(
                    "The EPUB package path is invalid.")
            package_path = posixpath.normpath(package_path)
            if package_path == '..' or package_path.startswith('../'):
                raise CoverExtractionError(
                    "The EPUB package path is invalid.")
            package = ET.fromstring(_read_epub_member(
                archive, package_path, _MAX_XML_BYTES))
            manifest = {
                item.attrib['id']: item
                for item in package.iter()
                if _local_name(item) == 'item' and item.attrib.get('id')
            }
            cover_ids = []
            for item_id, item in manifest.items():
                if 'cover-image' in item.attrib.get('properties', '').split():
                    cover_ids.append(item_id)
            for metadata in package.iter():
                if (_local_name(metadata) == 'meta'
                        and metadata.attrib.get('name') == 'cover'):
                    cover_ids.append(metadata.attrib.get('content', ''))

            base_path = posixpath.dirname(package_path)
            for cover_id in dict.fromkeys(cover_ids):
                item = manifest.get(cover_id)
                if item is None or not item.attrib.get('href'):
                    continue
                cover_path = _epub_member_path(
                    base_path, item.attrib['href'])
                image_data = _read_epub_member(
                    archive, cover_path, _MAX_COVER_BYTES)
                return _normalize_image(image_data)
    except CoverExtractionError:
        raise
    except (ET.ParseError, KeyError, StopIteration, ValueError,
            OSError, RuntimeError, zipfile.BadZipFile) as error:
        raise CoverExtractionError(
            "The EPUB package does not contain a readable designated cover."
        ) from error
    raise CoverExtractionError(
        "The EPUB package does not identify a cover image.")


def _extract_pdf_cover(contents):
    try:
        with fitz.open(stream=contents, filetype='pdf') as document:
            if not document.page_count:
                raise CoverExtractionError("The PDF contains no pages.")
            page = document.load_page(0)
            images = sorted(
                page.get_image_info(xrefs=True),
                key=lambda info: (
                    info.get('width', 0) * info.get('height', 0)),
                reverse=True)
            for info in images:
                xref = info.get('xref')
                width = info.get('width', 0)
                height = info.get('height', 0)
                if (not xref or width <= 0 or height <= 0
                        or width * height > _MAX_IMAGE_PIXELS):
                    continue
                try:
                    extracted = document.extract_image(xref)
                    return _normalize_image(
                        extracted.get('image', b''))
                except (
                        CoverExtractionError, RuntimeError, ValueError,
                        KeyError):
                    continue

            page_width = page.rect.width
            page_height = page.rect.height
            if page_width <= 0 or page_height <= 0:
                raise CoverExtractionError(
                    "The first PDF page has no dimensions.")
            scale = min(
                2.0,
                _MAX_PREVIEW_SIZE[0] / page_width,
                _MAX_PREVIEW_SIZE[1] / page_height)
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale), alpha=False)
            return _normalize_image(pixmap.tobytes('png'))
    except CoverExtractionError:
        raise
    except (RuntimeError, ValueError, TypeError, OSError) as error:
        raise CoverExtractionError(
            "The PDF first page could not be rendered as a cover.") from error


def extract_ebook_cover(file_format, contents):
    """Return a normalized PNG cover from validated PDF or EPUB bytes."""
    if file_format == 'epub':
        return _extract_epub_cover(contents)
    if file_format == 'pdf':
        return _extract_pdf_cover(contents)
    raise CoverExtractionError("Only PDF and EPUB covers are supported.")


def log_cover_extraction_failure(filename, error):
    _logger.warning(
        "Could not extract a cover image from eBook file %r: %s",
        filename, error, exc_info=True)
