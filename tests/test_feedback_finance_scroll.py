"""Regression guard for the finance scroll-position fix (MAIN 158/162)."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FinanceScrollRegressionTest(unittest.TestCase):
    def test_finance_scroll_is_saved_and_restored(self):
        source = (ROOT / 'flavors/autoseg/web/portal.js').read_text(
            encoding='utf-8')
        for marker in (
            "const FIN_SCROLL_KEY = 'autoseg:fin-scroll'",
            'const salvarScrollFin',
            'const restaurarScrollFin',
            "history.scrollRestoration = 'manual'",
            "window.addEventListener('pagehide', salvarScrollFin)",
            "window.addEventListener('beforeunload', salvarScrollFin)",
            'restaurarScrollFin();',
            'const scrollAntes = window.scrollY;',
            'requestAnimationFrame(() => window.scrollTo(0, scrollAntes));',
        ):
            self.assertIn(marker, source)
