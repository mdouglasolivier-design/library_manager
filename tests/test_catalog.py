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
        cls.private_ebook = cls.env['library.ebook'].create({
            'name': 'Private Website Catalog Test eBook',
            'author': 'Catalog Test Author',
            'isbn': 'TEST-CATALOG-PRIVATE',
        })
        cls.portal_user = cls.env['res.users'].create({
            'name': 'Website Catalog Portal Member',
            'login': 'website-catalog-portal-member',
            'password': 'library-test-password',
            'groups_id': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })

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

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.public_ebook.name, response.text)
        self.assertIn('eBooks in the collection', response.text)

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
                '/my/library/account'):
            with self.subTest(path=path):
                response = self.url_open(path)
                self.assertEqual(response.status_code, 200, path)
