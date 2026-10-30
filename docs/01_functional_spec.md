# Functional Specification

The addon implements physical books and loans, plus ebook catalogue records,
date-bounded ebook loans, and an access eligibility check.

Librarians and system administrators issue ebook loans. An active loan grants
access to its borrower from the borrow date through the due date, inclusive.
Returning the loan or archiving the ebook revokes eligibility. A borrower may
have only one active loan for a particular ebook; the same ebook may be loaned
to different borrowers concurrently.

The access check is exposed as `library.ebook.access.check_access(ebook_id)`
and is tied to the currently signed-in user's contact. It returns `True` when
access is allowed and raises an access error otherwise. Ebook file storage,
delivery, DRM, and detailed reader-session tracking are not implemented by
this feature.

Readers can create one pending reservation per ebook for their own account.
They can see only their own reservation records and cannot alter reservation
status. Librarians can review all requests and mark a pending reservation
fulfilled or cancelled. A cancelled request can be submitted again.
