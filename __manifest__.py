{
    'name': 'Library Manager',
    'version': '18.0.1.0.0',
    'summary': 'Manage books and lending in a simple library',
    'category': 'Services',
    'author': 'Douglas',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/library_book_views.xml',
        'views/library_menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
