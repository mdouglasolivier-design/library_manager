import base64
import binascii
from io import BytesIO
import os
import zipfile

from odoo.exceptions import ValidationError


MAX_EBOOK_FILE_SIZE = 50 * 1024 * 1024
FILE_SIGNATURES = {
    'pdf': b'%PDF-',
    'epub': b'PK',
}


def decode_ebook_file(filename, file_format, file_data):
    """Validate uploaded eBook bytes and return their decoded content."""
    if file_format not in FILE_SIGNATURES:
        raise ValidationError("Only PDF and EPUB files are supported.")
    if not filename or os.path.splitext(filename.strip())[1].lower() != (
            f'.{file_format}'):
        raise ValidationError(
            "The filename extension must match the selected file format.")
    if not file_data:
        raise ValidationError("Select an eBook file to upload.")
    try:
        contents = base64.b64decode(file_data, validate=True)
    except (binascii.Error, ValueError, TypeError) as error:
        raise ValidationError("The uploaded file is not valid.") from error
    if not contents or len(contents) > MAX_EBOOK_FILE_SIZE:
        raise ValidationError(
            "The file must be non-empty and no larger than 50 MiB.")
    if not contents.startswith(FILE_SIGNATURES[file_format]):
        raise ValidationError(
            f"The selected file does not have a valid {file_format.upper()} signature.")
    if file_format == 'epub':
        try:
            with zipfile.ZipFile(BytesIO(contents)) as archive:
                names = archive.namelist()
                valid_epub = (
                    bool(names)
                    and names[0] == 'mimetype'
                    and archive.getinfo('mimetype').compress_type
                    == zipfile.ZIP_STORED
                    and archive.read('mimetype') == b'application/epub+zip'
                    and 'META-INF/container.xml' in names
                )
        except (
                zipfile.BadZipFile, KeyError, RuntimeError, OSError,
                EOFError) as error:
            raise ValidationError(
                "The uploaded file is not a valid EPUB package.") from error
        if not valid_epub:
            raise ValidationError(
                "The uploaded file is not a valid EPUB package.")
    return contents
