# Storage, Backup, and Recovery

Protected eBook files use database-backed binary fields rather than public
attachments or a separate filestore. Include the PostgreSQL database in the
library's normal encrypted, access-controlled backup and restore procedures.
The Odoo filestore may still be needed for other Odoo applications, but it does
not contain these eBook file binaries.

Test a restore into a non-production environment and verify that an entitled
member can read an eBook while a member without an active loan is denied.
Restrict database and backup access because anyone who can read the database
can access the stored file data. File-size uploads are limited to 50 MiB.
