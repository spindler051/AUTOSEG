"""Cookie serialization and CSRF contract tests for the unified login."""
import io
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flavors.autoseg.modules import web_cookie


class WebCookieTest(unittest.TestCase):
    def setUp(self):
        self.token = 'A' * 48
        self.session = SimpleNamespace(csrf='csrf-<"&>')

    def test_cookie_attributes(self):
        cookie = web_cookie.set_cookie(self.token)
        for attribute in ('autosseg_unified=', 'HttpOnly', 'SameSite=Strict',
                          'Path=/', 'Max-Age=28800'):
            self.assertIn(attribute, cookie)

    def test_secure_conditional(self):
        self.assertIn('; Secure', web_cookie.set_cookie(self.token, secure=True))
        self.assertNotIn('; Secure', web_cookie.set_cookie(self.token, secure=False))

    def test_clear_cookie(self):
        self.assertIn('Max-Age=0', web_cookie.clear_cookie())
        self.assertIn('HttpOnly', web_cookie.clear_cookie())
        self.assertIn('; Secure', web_cookie.clear_cookie(True))

    def test_read_cookie_among_others(self):
        self.assertEqual(self.token, web_cookie.token_from_headers(
            {'Cookie': f'first=1; autosseg_unified={self.token}; last=2'}))

    def test_missing_malformed_or_injected_cookie(self):
        for headers in ({}, {'Cookie': 'foo=bar'},
                        {'Cookie': 'autosseg_unified=!' },
                        {'Cookie': 'autosseg_unified=a%0d%0a'},
                        {'Cookie': 'autosseg_unified=short'}):
            with self.subTest(headers=headers):
                self.assertIsNone(web_cookie.token_from_headers(headers))
        with self.assertRaises(ValueError):
            web_cookie.set_cookie('bad; token')

    def test_secure_request_proxy_hints(self):
        self.assertTrue(web_cookie.secure_request({'CF-Ray': 'one'}))
        self.assertTrue(web_cookie.secure_request({'X-Forwarded-Proto': 'HTTPS'}))
        self.assertFalse(web_cookie.secure_request({}))
        self.assertFalse(web_cookie.secure_request({'X-Forwarded-Proto': 'http'}))

    def test_csrf_html_escaped(self):
        self.assertIn('value="csrf-&lt;&quot;&amp;&gt;"', web_cookie.csrf_input(self.session))
        self.assertNotIn('<"&>', web_cookie.csrf_input(self.session))

    def test_csrf_validation(self):
        self.assertTrue(web_cookie.csrf_valid(self.session, self.session.csrf))
        self.assertFalse(web_cookie.csrf_valid(self.session, 'different'))
        self.assertFalse(web_cookie.csrf_valid(self.session, ''))
        self.assertFalse(web_cookie.csrf_valid(None, self.session.csrf))

    def test_csrf_uses_constant_time_compare(self):
        with patch.object(web_cookie.secrets, 'compare_digest', return_value=True) as comparator:
            self.assertTrue(web_cookie.csrf_valid(self.session, 'test'))
            comparator.assert_called_once_with(self.session.csrf, 'test')

    def test_no_sensitive_repr_or_logging(self):
        output = io.StringIO()
        h = logging.StreamHandler(output)
        log = logging.getLogger('flavors.autoseg.modules.web_cookie')
        log.addHandler(h)
        try:
            web_cookie.set_cookie(self.token)
            web_cookie.csrf_input(self.session)
            self.assertNotIn(self.token, repr(web_cookie))
            self.assertNotIn(self.token, output.getvalue())
            self.assertNotIn(self.session.csrf, output.getvalue())
        finally:
            log.removeHandler(h)


if __name__ == '__main__':
    unittest.main()
