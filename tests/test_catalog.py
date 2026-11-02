import base64

from odoo.tests import HttpCase, tagged


@tagged('-at_install', 'post_install')
class TestLibraryCatalogWebsite(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['library.ebook.category'].create({
            'name': 'Website Catalog Test Category',
        })
        cls.public_ebook = cls.env['library.ebook'].create({
            'name': 'Public Website Catalog Test eBook',
            'author': 'Catalog Test Author',
            'isbn': 'TEST-CATALOG-PUBLIC',
            'publication_date': '2024-06-15',
            'category_id': cls.category.id,
            'website_published': True,
        })
        cls.env['library.ebook.asset'].create({
            'ebook_id': cls.public_ebook.id,
            'filename': 'catalog-test.pdf',
            'file_format': 'pdf',
            'file_data': base64.b64encode(
                b'%PDF-1.7\nCatalog fixture').decode('ascii'),
        })
        cls.private_ebook = cls.env['library.ebook'].create({
            'name': 'Private Website Catalog Test eBook',
            'author': 'Catalog Test Author',
            'isbn': 'TEST-CATALOG-PRIVATE',
        })
        cls.portal_user = cls.env['res.users'].create({
            'name': 'Website Catalog Portal Member',
            'login': 'website-catalog-portal-member',
            'email': 'catalog-member@example.test',
            'password': 'library-test-password',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.portal_user.partner_id.phone = '+15550000000'

    def test_public_catalog_search_and_category_filter(self):
        response = self.url_open(
            '/library/ebooks?q=TEST-CATALOG-PUBLIC'
            '&category=%s&availability=available&year=2024'
            % self.category.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.public_ebook.name, response.text)
        self.assertNotIn(self.private_ebook.name, response.text)

    def test_public_home_displays_catalog_statistics(self):
        response = self.url_open('/library')
        hero_image = self.url_open(
            '/library_manager/static/src/img/library_hero.png')

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.public_ebook.name, response.text)
        self.assertIn(
            '/library_manager/static/src/img/library_hero.png',
            response.text)
        self.assertIn('Odoo Library', response.text)
        self.assertIn(
            '/library_manager/static/description/icon.png', response.text)
        self.assertIn(
            'Your Integrated Digital Library Management Platform.',
            response.text)
        self.assertIn('douglasgroupltd@gmail.com', response.text)
        self.assertIn('+250791393885', response.text)
        self.assertIn('Rwanda, Kigali', response.text)
        self.assertIn('Staff Login', response.text)
        self.assertIn('How Odoo Library works', response.text)
        self.assertEqual(response.text.count('loading="eager"'), 1)
        self.assertEqual(hero_image.status_code, 200)
        self.assertEqual(
            hero_image.headers.get('Content-Type'), 'image/png')
        self.assertIn('eBooks in the collection', response.text)
        self.assertNotIn('id="top"', response.text)
        self.assertNotIn('id="bottom"', response.text)

    def test_public_home_links_to_member_authentication(self):
        response = self.url_open('/library')

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'href="/web/login?redirect=/library"', response.text)
        self.assertIn(
            'href="/web/signup?redirect=/library"', response.text)
        self.assertIn('href="/library/staff"', response.text)

    def test_removed_about_page_is_not_routable(self):
        response = self.url_open('/library/about')

        self.assertEqual(response.status_code, 404)

    def test_login_hides_database_picker_and_signup_is_guided(self):
        login = self.url_open('/web/login')
        signup = self.url_open('/web/signup?token=invalid-test-token')

        self.assertEqual(login.status_code, 200)
        self.assertNotIn('>Database</label>', login.text)
        self.assertNotIn('/web/database/selector', login.text)
        self.assertIn(
            '/library_manager/static/description/icon.png', login.text)
        self.assertEqual(signup.status_code, 200)
        self.assertIn('Library member account', signup.text)
        self.assertIn('1. Your details', signup.text)
        self.assertIn('2. Set a password', signup.text)
        self.assertIn('3. Create account', signup.text)
        self.assertIn('Create member account', signup.text)

    def test_staff_login_redirects_portal_users_to_public_library(self):
        self.authenticate(
            'website-catalog-portal-member', 'library-test-password')

        response = self.url_open('/library/staff')

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            'Staff access is restricted to authorized librarians',
            response.text)

    def test_unpublished_ebook_detail_is_not_public(self):
        response = self.url_open(
            '/library/ebooks/%s' % self.private_ebook.id)

        self.assertEqual(response.status_code, 404)

    def test_published_ebook_detail_uses_cover_fallback(self):
        response = self.url_open(
            '/library/ebooks/%s' % self.public_ebook.id)
        cover_response = self.url_open(
            '/library/ebooks/%s/cover' % self.public_ebook.id)

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.public_ebook.name, response.text)
        self.assertEqual(cover_response.status_code, 200)
        self.assertIn(b'<svg', cover_response.content)
        self.assertIn('>Available</span>', response.text)

    def test_published_title_without_file_is_listed_but_not_borrowable(self):
        ebook = self.env['library.ebook'].create({
            'name': 'Published Without File',
            'website_published': True,
        })
        response = self.url_open('/library/ebooks/%s' % ebook.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Reading file unavailable', response.text)
        self.assertIn('Borrowing and reading are disabled', response.text)

    def test_member_portal_pages_render_after_login(self):
        self.authenticate(
            'website-catalog-portal-member', 'library-test-password')

        for path in (
                '/my/library',
                '/my/library/loans',
                '/my/library/history',
                '/my/library/requests',
                '/my/library/reservations',
                '/my/library/notifications',
            '/my/library/account',
            '/my/home'):
            with self.subTest(path=path):
                response = self.url_open(path)
                self.assertEqual(response.status_code, 200, path)
                if path == '/my/library/account':
                    self.assertIn(
                        'catalog-member@example.test', response.text)
                    self.assertIn('+15550000000', response.text)
                if path == '/my/home':
                    self.assertIn(
                        'douglasgroupltd@gmail.com', response.text)
                    self.assertIn('+250791393885', response.text)
                    self.assertIn('Rwanda, Kigali', response.text)
