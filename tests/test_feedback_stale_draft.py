"""Regression guard for stale web drafts overriding a newer OS row."""
import unittest

from flavors.autoseg.modules.portal_prestador import _rascunho_web_compativel


class StaleDraftTest(unittest.TestCase):
    def test_only_matching_revision_is_merged(self):
        current = '2026-11-18 08:45:57'
        self.assertTrue(_rascunho_web_compativel(
            {'_versao_os': current, 'descricao': 'draft'}, current))
        self.assertFalse(_rascunho_web_compativel(
            {'_versao_os': '2026-11-18 08:08:42', 'descricao': 'old'}, current))
        self.assertFalse(_rascunho_web_compativel(
            {'descricao': 'legacy without version'}, current))
        self.assertTrue(_rascunho_web_compativel(
            {'_versao_os': 'anything'}, ''))
        self.assertFalse(_rascunho_web_compativel(None, current))
