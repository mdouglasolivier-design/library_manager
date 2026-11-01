# Library Manager

![Odoo 18](https://img.shields.io/badge/Odoo-18.0-875A7B) ![License](https://img.shields.io/badge/license-LGPL--3-blue)

A simple, clean Odoo app to manage books, lending, loan history and printable reports.

## Features

- **Book catalogue**: cover-based Kanban, detailed book pages, title/author/ISBN/description search, category and availability filters
- **Lending and returns**: lend a book to any contact, 14-day due date, return or mark as lost
- **Loan history**: one record per borrow, with return date and days late
- **Ebook catalog and loans**: librarians issue date-bounded ebook loans
- **Public eBook catalog**: cover-led discovery, metadata pages, search, filters, and responsive layouts
- **eBook reading access**: approval creates an active loan and a **Read now** link; only the signed-in member's active, in-date loan grants access
- **Borrower portal**: members can submit borrowing requests, reserve titles at capacity, and manage loans, history, reservations, and notifications
- **Protected eBook reader**: PDF browser reading and entitled EPUB downloads; librarian-uploaded files stay private and require an active loan on every request
- **Email notifications**: request and reservation updates are queued for members with an email address
- **Overdue reminders**: overdue eBook loans generate one queued reminder per day until returned
- **Lending policy**: configure approval, loan duration, and optional per-member/title capacity limits
- **Availability at a glance**: clear available, borrowed, overdue, and lost indicators
- **Library Dashboard**: live eBook, borrower, combined loan, request, and reservation metrics with monthly activity and top-loan charts
- **Overdue tracking**: highlighted rows, filters, grouping
- **PDF reports**: loan receipt (with barcode), overdue loans list, member card
- **Saved filters and Excel export templates**
- **Chatter tracking** on every book

The website provides public eBook discovery, details, member requests, reservations, loan history, notifications, account contact updates, and protected reading. The reader embeds PDFs; EPUB files are downloaded for reading in a compatible app.

## Requirements

- Odoo 18.0 (Community or Enterprise)
- Odoo modules: `base`, `mail`, `website`, `portal`, `auth_signup`

## Installation

1. Copy the `library_manager` folder into your custom addons folder.
2. Add that folder to `addons_path` in `odoo.conf`.
3. Restart Odoo and enable developer mode.
4. Go to **Apps**, click **Update Apps List**, search for **Library Manager** and click **Install**.

Command-line install:

```bash
python odoo-bin -c odoo.conf -d <database> -i library_manager
```

## Usage

| Task | How |
|---|---|
| View library activity | Open **Library → Dashboard**; loan counts combine physical-book and eBook loans |
| Browse the catalogue | Library, then Books; switch between cover cards and the list |
| Find a book | Search by title, author, ISBN, or description; narrow results by category and availability |
| Add a book | Library, then Books, then New; add a cover image and book details |
| Publish an eBook to the website | Library, then Ebooks; add its cover and metadata, then enable **Published on Website** |
| Upload the protected eBook file | Open the eBook's **Protected File** tab and upload a PDF or EPUB (maximum 50 MiB) |
| Browse eBooks online | Open `/library` or `/library/ebooks` on the Odoo website |
| Request eBook access | Sign in, open a published title, and choose **Request eBook access** or **Reserve this eBook** |
| Manage eBook activity | Sign in and open **My Library** at `/my/library` |
| Read a borrowed eBook | Open an active loan and choose **Read now**; an active, in-date loan is checked for both the reader and file |
| Receive eBook email updates | Keep the email address on your library contact record current; messages are queued through Odoo's mail system |
| Send overdue reminders | Configure an outgoing Odoo mail server; overdue eBook loans are reminded daily until returned |
| Configure eBook lending | In Settings, set librarian approval, loan duration, and optional loan limits |
| Lend a book | Open the book, choose **Borrowed By**, click **Lend Book** |
| Return a book | Open the book, click **Return Book** |
| Issue an ebook loan | As a librarian, open **Library → Ebook Loans** and create a loan |
| Reserve an ebook | Open **Library → Ebook Reservations** and create a request |
| Process a reservation | As a librarian, open a pending reservation and mark it fulfilled or cancel it |
| Print a receipt | Library, then Loans, open a loan, then Print |
| Overdue report | Library, then Reports, then Overdue Loans Report |
| Member card | Contacts, open a contact, then Print |
| Export to Excel | In a list, select rows, then Actions, then Export |

Assign the **Library Librarian** group to trusted staff in **Settings → Users
& Companies → Users** to let them issue and manage ebook loans.

## Upgrading

```bash
python odoo-bin -c odoo.conf -d <database> -u library_manager
```

## Running the tests

```bash
python odoo-bin -c odoo.conf -d <database> -u library_manager --test-enable --test-tags /library_manager --stop-after-init
```

## Project structure

```
library_manager/
├── __manifest__.py
├── data/          saved filters and export templates
├── models/        physical and ebook catalog, loan, and access models
├── report/        PDF reports and QWeb templates
├── security/      access rights
├── static/        icon and Apps page description
├── tests/         automated tests
├── views/         list, form, search views and menus
└── wizard/        overdue report wizard
```

## Roadmap

- Members, authors and publishers as separate models
- Optional DRM, watermarking, or in-browser EPUB integration

## License

LGPL-3
