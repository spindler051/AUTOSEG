"""Explicit transport consent prevents accidental credential disclosure."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from officina.application.http_service import (HttpService, validate_server_transport,
                                                persist_cgnat_http_consent)


class TransportSecurityTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.settings = str(Path(tmp.name) / 'settings.json')
        self.env = patch.dict('os.environ', {'AUTOSEG_CONNECTION_FILE': self.settings})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_supported_tls_and_loopback(self):
        for url, kind in (('https://example.org:8767', 'https'),
                          ('http://localhost:8767', 'loopback'),
                          ('http://127.0.0.1:8767', 'loopback'),
                          ('http://[::1]:8767', 'loopback')):
            with self.subTest(url=url):
                self.assertEqual(validate_server_transport(url), kind)
                self.assertIsInstance(HttpService(url), HttpService)

    def test_cgnat_requires_explicit_persisted_consent_per_host(self):
        url = 'http://100.66.88.127:8767'
        with self.assertRaises(ValueError):
            HttpService(url)
        persist_cgnat_http_consent(url, confirmed=True)
        self.assertEqual(validate_server_transport(url), 'tailscale-cgnat')
        self.assertIsInstance(HttpService(url), HttpService)
        for other in ('http://100.66.88.127:8768', 'http://100.66.88.128:8767'):
            with self.assertRaises(ValueError):
                HttpService(other)

    def test_malformed_urls_and_plain_http_rejected(self):
        for url in ('http://192.168.1.5:8767', 'http://example.org',
                    'http://127.0.0.1.evil.test', 'http://100.128.0.1',
                    'https://user:pass@example.org', 'https://user@example.org',
                    'https://example.org:bad', 'https://', 'https://example.org?token=secret',
                    'http://localhost@evil.test', 'ftp://localhost',
                    'http://localHOST.evil', 'http://[::1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                HttpService(url)

    def test_mutating_base_url_is_not_a_transport_bypass(self):
        service = HttpService('http://127.0.0.1:8767', token='sensitive')
        service.base_url = 'http://example.org'
        with self.assertRaises(ValueError):
            service._request('POST', '/login', {'senha': 'sensitive'})
