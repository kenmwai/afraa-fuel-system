from django.test import SimpleTestCase
from django.urls import reverse, resolve


class RegisterURLTests(SimpleTestCase):
    def test_register_url_resolves_to_procurement_register_view(self):
        """Ensure the 'register' URL name resolves to procurement.register_view.register.

        This checks both the URL name and the target view's module and function name
        without importing the view directly (fails fast if the URLconf is wrong).
        """
        # Resolve by name to ensure URL patterns are loaded correctly
        url = reverse('register')
        resolver = resolve(url)

        # The URL name should be 'register'
        self.assertEqual(resolver.view_name, 'register')

        # The view should be defined in procurement.register_view and be called 'register'
        self.assertEqual(resolver.func.__module__, 'procurement.register_view')
        self.assertEqual(resolver.func.__name__, 'register')
