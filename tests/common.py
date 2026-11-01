import base64


def create_test_ebook_file(env, ebook):
    return env['library.ebook.asset'].create({
        'ebook_id': ebook.id,
        'filename': 'test-book.pdf',
        'file_format': 'pdf',
        'file_data': base64.b64encode(
            b'%PDF-1.7\nOdoo test fixture').decode('ascii'),
    })
