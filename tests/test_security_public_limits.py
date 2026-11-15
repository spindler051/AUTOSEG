"""Negative security tests for public-request budget and overload handling."""
import unittest
from officina.application.public_limits import PublicBudget


class PublicRequestBudgetTest(unittest.TestCase):
    def test_fake_clock_window_per_origin_and_per_category(self):
        now = [100.]
        budget = PublicBudget(clock=lambda: now[0], limits={'login': 2, 'public': 3}, period=60)
        self.assertEqual(budget.reserve('198.51.100.1', 'login'), 0)
        self.assertEqual(budget.reserve('198.51.100.1', 'login'), 0)
        self.assertGreaterEqual(budget.reserve('198.51.100.1', 'login'), 1)
        self.assertEqual(budget.reserve('198.51.100.2', 'login'), 0)
        self.assertEqual(budget.reserve('198.51.100.1', 'public'), 0)
        now[0] += 61
        self.assertEqual(budget.reserve('198.51.100.1', 'login'), 0)

    def test_concurrent_requests_fail_closed_and_release(self):
        budget = PublicBudget(max_concurrent=1)
        self.assertTrue(budget.enter())
        self.assertFalse(budget.enter())
        budget.leave()
        self.assertTrue(budget.enter())
        budget.leave()

    def test_real_api_returns_429_retry_after_without_parsing_request(self):
        import tempfile
        import urllib.error
        import urllib.request
        from pathlib import Path
        from flavors.autoseg.modules import api_server
        from officina.core import banco
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'api.db')
            banco.criar_banco(path)
            server = api_server.start(path, '127.0.0.1', 0)
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            now = [10.]
            server.public_budget = PublicBudget(clock=lambda: now[0],
                    limits={'read': 1, 'login': 1, 'public': 1})
            url = 'http://127.0.0.1:%s/api/v1/desktop/health' % server.server_address[1]
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(url, timeout=5)
            self.assertEqual(denied.exception.code, 429)
            self.assertTrue(denied.exception.headers.get('Retry-After'))
            now[0] += 61
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 200)

    def test_invalid_ip_cannot_bypass_default_budget(self):
        now=[0.]
        budget=PublicBudget(clock=lambda: now[0], limits={'public': 1})
        self.assertEqual(budget.reserve('', 'public'), 0)
        self.assertGreaterEqual(budget.reserve('', 'public'), 1)


if __name__=='__main__':
    unittest.main()
