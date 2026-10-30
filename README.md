# Library Manager

![Odoo 18](https://img.shields.io/badge/Odoo-18.0-875A7B) ![License](https://img.shields.io/badge/license-LGPL--3-blue)

A simple, clean Odoo app to manage books, lending, loan history and printable reports.

## Features

- **Book catalogue**: cover-based Kanban, detailed book pages, title/author/ISBN/description search, category and availability filters
- **Lending and returns**: lend a book to any contact, 14-day due date, return or mark as lost
- **Loan history**: one record per borrow, with return date and days late
- **Ebook catalog and loans**: librarians issue date-bounded ebook loans
- **Ebook access eligibility**: only the signed-in member's active, in-date loan grants access
- **Ebook reservations**: readers can request an ebook; librarians manage pending requests
- **Availability at a glance**: clear available, borrowed, overdue, and lost indicators
- **Overdue tracking**: highlighted rows, filters, grouping
- **PDF reports**: loan receipt (with barcode), overdue loans list, member card
- **Saved filters and Excel export templates**
- **Chatter tracking** on every book

## Requirements

- Odoo 18.0 (Community or Enterprise)
- Odoo modules: `base`, `mail`

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
| Browse the catalogue | Library, then Books; switch between cover cards and the list |
| Find a book | Search by title, author, ISBN, or description; narrow results by category and availability |
| Add a book | Library, then Books, then New; add a cover image and book details |
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
- Ebook file delivery, asset management and DRM integrations
- Settings page, overdue email reminders

## License

LGPL-3
