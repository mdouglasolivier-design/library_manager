# Security and DRM Limits

`library.ebook.access.check_access(ebook_id)` checks the signed-in user's
contact against active ebook loans. A loan is eligible from its borrow date
through its due date, inclusive. Returned loans, future or expired loans, and
archived ebooks are denied. Librarians and system administrators can issue
loans; readers can view only their own loans and generated, read-only
access-grant rows. Readers may create reservations only for their own account
and can view only their own requests. Only librarians and system administrators
may process reservation statuses.

This check determines eligibility only. The addon does not currently store,
stream, encrypt, watermark, or apply DRM to ebook files, and it has no reader
endpoint that enforces the check before serving a file. A file-delivery
integration must call this method before returning protected content.
