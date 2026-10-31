# Security and DRM Limits

`library.ebook.access.check_access(ebook_id)` checks the signed-in user's
contact against active ebook loans. A loan is eligible from its borrow date
through its due date, inclusive. Returned loans, future or expired loans, and
archived ebooks are denied. Librarians and system administrators can issue
loans; readers can view only their own loans and generated, read-only
access-grant rows. Readers may create reservations only for their own account
and can view only their own requests. Only librarians and system administrators
may process reservation statuses.

Librarians can upload one PDF or EPUB file per title. Files are stored as
private database-backed binary fields (not public `ir.attachment` URLs), with
extension/signature checks and a 50 MiB size limit. Each reader page and file
request requires an authenticated user and calls the entitlement check before
retrieving the file. The file route supports single byte ranges for browser PDF
viewers, returns private no-store responses, and does not expose a reusable
public token.

The browser reader embeds PDFs. EPUBs can be downloaded after entitlement
verification for use in a member's preferred reading application; an in-browser
EPUB renderer is not included. Once a user has received file bytes, the addon
cannot prevent copying, screenshots, or redistribution. It provides no
encryption at rest beyond the database's own controls, watermarking, DRM, or
usage analytics. Database access and backups must therefore be protected by the
library's normal operational controls.

Member request/reservation email notifications and daily overdue reminders are
queued through Odoo's mail subsystem. Reminder delivery requires a configured
outgoing mail server and a borrower contact email address.
