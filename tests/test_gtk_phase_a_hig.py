"""Headless structural checks for the Phase A GNOME HIG integration."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GtkPhaseAHigTest(unittest.TestCase):
    def _source(self, name):
        return (ROOT / 'flavors/autoseg/modules' / name).read_text(encoding='utf-8')

    def test_shared_tables_have_native_empty_state(self):
        source = self._source('gtk_comum.py')
        self.assertIn('Adw.StatusPage(', source)
        self.assertIn('self._display.set_visible_child_name("empty")', source)
        self.assertIn('"rows" if count else "empty"', source)
        self.assertIn('return self._display', source)

    def test_application_actions_have_keyboard_accelerators(self):
        source = self._source('gtk_app.py')
        syntax = ast.parse(source)
        assigned = {node.args[0].value for node in ast.walk(syntax)
                    if isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Attribute) and
                    node.func.attr == 'set_accels_for_action' and node.args and
                    isinstance(node.args[0], ast.Constant)}
        self.assertTrue({'win.atualizar', 'win.sair', 'win.sobre'} <= assigned)

    def test_financial_and_access_changes_require_confirmation(self):
        tree = ast.parse(self._source('gtk_app.py'))
        methods = {node.name: node for node in ast.walk(tree)
                   if isinstance(node, ast.FunctionDef)}
        for name in ('_marcar_recebido', '_alternar_prestador',
                     '_alternar_componente'):
            with self.subTest(method=name):
                calls = [node for node in ast.walk(methods[name])
                         if isinstance(node, ast.Call)]
                self.assertTrue(any(isinstance(c.func, ast.Attribute)
                                    and c.func.attr == 'alerta' for c in calls))
                self.assertFalse(any(isinstance(c.func, ast.Attribute)
                                     and c.func.attr in ('marcar_recebido',
                                         'alternar_prestador', '_salvar_config_composicao')
                                     for c in calls))

    def test_work_order_cancel_requires_destructive_confirmation(self):
        source = self._source('gtk_dialogos.py')
        tree = ast.parse(source)
        method = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.FunctionDef)
                      and node.name == '_confirmar_situacao')
        text = ast.get_source_segment(source, method)
        self.assertIn('"Confirmar cancelamento"', text)
        self.assertIn('destrutivo=True', text)
        self.assertIn('lambda: self._salvar("Cancelada")', text)

    def test_surface_exceptions_have_specific_reasons(self):
        from flavors.autoseg.modules.autoseg_web_navigation import ITEMS
        exceptions = {item.id: item for item in ITEMS
                      if item.surfaces != ('web', 'gtk')}
        self.assertEqual(len(exceptions), 12)
        self.assertIn('Adwaita', exceptions['settings'].surface_reason)
        self.assertIn('feedback', exceptions['feedback'].surface_reason.lower())
        for name, item in exceptions.items():
            with self.subTest(name=name):
                self.assertTrue(item.surface_reason)
                self.assertNotIn('outside GTK provider phase', item.surface_reason)
                if name.startswith('client-'):
                    self.assertIn('client mode', item.surface_reason)

    def test_page_chrome_uses_libadwaita(self):
        source = self._source('gtk_app.py')
        self.assertIn('Adw.NavigationSplitView()', source)
        self.assertIn('Adw.ToolbarView()', source)
        self.assertIn('Adw.HeaderBar()', source)
        self.assertNotIn('Gtk.HeaderBar(', source)


if __name__ == '__main__':
    unittest.main()
