# Library Manager (Odoo 18)

A simple Odoo module to manage books and lending.

## Features
- Add books (title, author, ISBN, category, pages)
- Lend a book to a contact (14-day due date)
- Return a book or mark it as lost
- Overdue highlighting, filters, grouping
- Chatter tracking on every book

## Install
1. Put the `library_manager` folder inside your custom addons folder.
2. Add that folder to `addons_path` in `odoo.conf`.
3. Run:
   ```bash
   ./odoo-bin -c odoo.conf -d librarydb -i library_manager --dev=all
   ```
4. Open http://localhost:8069 and click the **Library** app.

## Update after changes
```bash
./odoo-bin -c odoo.conf -d librarydb -u library_manager --dev=all
```

## Run tests
```bash
./odoo-bin -c odoo.conf -d testdb -i library_manager --test-enable --stop-after-init
```

## Git quick start
```bash
git init
git branch -M main
git add .
git commit -m "chore: initial library_manager module"
git remote add origin https://github.com/<your-username>/library_manager.git
git push -u origin main
```

## Odoo version notes
- Built for Odoo 18 (uses `<list>` views and `view_mode` `list,form`).
- Odoo 17: rename `<list>` to `<tree>` and `view_mode` to `tree,form`, and set the version to `17.0.1.0.0`.
