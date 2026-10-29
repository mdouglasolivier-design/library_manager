# Library Manager

![Odoo 18](https://img.shields.io/badge/Odoo-18.0-875A7B) ![License](https://img.shields.io/badge/license-LGPL--3-blue)

A simple, clean Odoo app to manage books, lending, loan history and printable reports.

## Features

- **Book catalogue**: title, author, unique ISBN, category, pages, description
- **Lending and returns**: lend a book to any contact, 14-day due date, return or mark as lost
- **Loan history**: one record per borrow, with return date and days late
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
| Add a book | Library, then Books, then New |
| Lend a book | Open the book, choose **Borrowed By**, click **Lend Book** |
| Return a book | Open the book, click **Return Book** |
| Print a receipt | Library, then Loans, open a loan, then Print |
| Overdue report | Library, then Reports, then Overdue Loans Report |
| Member card | Contacts, open a contact, then Print |
| Export to Excel | In a list, select rows, then Actions, then Export |

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
├── models/        library.book, library.loan
├── report/        PDF reports and QWeb templates
├── security/      access rights
├── static/        icon and Apps page description
├── tests/         automated tests
├── views/         list, form, search views and menus
└── wizard/        overdue report wizard
```

## Roadmap

- Members, authors and publishers as separate models
- Security groups (Reader, Librarian, Manager)
- Settings page, overdue email reminders, kanban view with covers

## License

LGPL-3
