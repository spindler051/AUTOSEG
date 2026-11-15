"""Web and GTK share section registry, order and server-granted permissions."""
import unittest
from dataclasses import replace

from flavors.autoseg.modules import autoseg_web_navigation as source
from officina.application.session import Sessao, navigation_for_session
from officina.application.policy import load_policy
from types import SimpleNamespace


class SharedSectionSecurityTest(unittest.TestCase):
    @staticmethod
    def session(role):
        return Sessao('remote', 7, role, '', role == 'admin', role=role,
                      permissions=load_policy().roles[role])

    def test_generic_session_has_no_dependency_on_autoseg_flavor(self):
        import ast
        from pathlib import Path
        module = Path(__file__).resolve().parents[1] / 'officina/application/session.py'
        syntax = ast.parse(module.read_text(encoding='utf-8'))
        flavor_imports = [node.module for node in ast.walk(syntax)
                          if isinstance(node, ast.ImportFrom)
                          and (node.module or '').startswith('flavors.')]
        self.assertEqual(flavor_imports, [])

    def test_all_sections_map_to_declared_surface_and_have_reason_for_exceptions(self):
        for item in source.ITEMS:
            with self.subTest(section=item.id):
                self.assertTrue(item.surfaces)
                if item.surfaces != ('web', 'gtk'):
                    self.assertTrue(item.surface_reason)
                if 'gtk' in item.surfaces:
                    self.assertTrue(item.gtk_page)
                if 'web' in item.surfaces:
                    self.assertTrue(item.href)

    def test_provider_gtk_and_web_share_order_permission_and_name(self):
        for role in ('admin', 'employee'):
            with self.subTest(role=role):
                session = self.session(role)
                context = SimpleNamespace(kind='provider',permissions=session.permissions)
                web = source.navigation_for(context)
                gtk = navigation_for_session(source.gtk_navigation_for(context), session)
                from_web = [(item.gtk_page, item.label) for item in web
                            if 'gtk' in item.surfaces]
                self.assertEqual([(item[0], item[1]) for item in gtk
                                  if item[0] not in ('conexao','portal')], from_web)
                visible = {item[0] for item in gtk}
                self.assertIn('estoque',visible)
                if role == 'employee':
                    self.assertNotIn('prestadores',visible)
                    self.assertNotIn('composicao',visible)
                    self.assertNotIn('conexao',visible)

    def test_registry_permission_change_applies_to_both_without_gtk_policy_map(self):
        original = source.ITEMS
        try:
            source.ITEMS = tuple(replace(item, permission='provider.manage.all')
                                  if item.id == 'work' else item for item in original)
            context = SimpleNamespace(kind='provider',permissions=self.session('employee').permissions)
            self.assertNotIn('work', [item.id for item in source.navigation_for(context)])
            self.assertNotIn('os', [item[0] for item in navigation_for_session(source.gtk_navigation_for(context),self.session('employee'))])
        finally:
            source.ITEMS = original

    def test_stale_server_ids_do_not_grant_local_permissions(self):
        session = replace(self.session('employee'), navigation_ids=frozenset({'providers','stock'}))
        context = SimpleNamespace(kind='provider',permissions=session.permissions)
        pages = {row[0] for row in navigation_for_session(source.gtk_navigation_for(context), session)}
        self.assertNotIn('prestadores', pages)
        self.assertIn('estoque', pages)

    def test_navigation_from_server_is_pre_filtered(self):
        from flavors.autoseg.modules.api_desktop import _context_api
        context = SimpleNamespace(role='employee', context_label='Portal',
                                  permissions=self.session('employee').permissions,
                                  account_id=None, identity_kind='provider',identity_id=7,
                                  display_name='Example',provider_org_id='autoseg',provider_id=7,
                                  client_id=None,client_org_ids=frozenset())
        payload = _context_api(context)
        self.assertIn('navigation', payload)
        self.assertFalse(any(row['id'] == 'providers' for row in payload['navigation']))
        self.assertTrue(any(row['id'] == 'stock' for row in payload['navigation']))

if __name__ == '__main__':
    unittest.main()
