"""Phase 3.1: render the real GTK customer page with remote-session stand-ins.

Only GTK widgets are stubbed; _pagina_clientes is compiled unchanged from source.
The test intentionally uses empty permissions for both admin and employee.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'flavors/autoseg/modules/gtk_app.py'


def render_customer_actions(*, admin: bool, web_enabled: bool = True) -> list[str]:
    session = SimpleNamespace(mode='remote', admin=admin,
                              permissions=frozenset())
    source = APP.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=str(APP))
    window = next(node for node in tree.body
                  if isinstance(node, ast.ClassDef) and node.name == 'Janela')
    page = next(node for node in window.body
                if isinstance(node, ast.FunctionDef) and node.name == '_pagina_clientes')

    class Widget:
        def __init__(self, *_args, **_kwargs):
            self.children = []
        def set_hexpand(self, *_value):
            pass
        def connect(self, *_args):
            pass
        def append(self, child):
            self.children.append(child)

    class Ui:
        class Tabela:
            def __init__(self, *_args, **_kwargs):
                self.widget = Widget()
        @staticmethod
        def botao(label, *_args, **_kwargs):
            return {'label': label}
        @staticmethod
        def barra(*controls):
            return list(controls)

    gtk = SimpleNamespace(Box=Widget, SearchEntry=Widget,
                          Orientation=SimpleNamespace(VERTICAL=1))
    namespace = {'Gtk': gtk, 'ui': Ui}
    exec(compile(ast.Module(body=[page], type_ignores=[]), str(APP), 'exec'),
         namespace)
    noop = lambda *_args: None
    window_instance = SimpleNamespace(
        sessao=session, web=SimpleNamespace(enabled=web_enabled),
        carregar_clientes=noop, _importar_cliente_yaml=noop,
        _modelo_cliente_yaml=noop, _atribuir_responsavel=noop,
        novo_cliente=noop, _editar_cliente=noop, _nova_os_cliente=noop,
        _excluir_cliente=noop, _senha_cliente=noop,
        _abrir_portal_navegador=noop,
    )
    page_widget = namespace['_pagina_clientes'](window_instance)
    return [item['label'] for item in page_widget.children[-1]]


class CustomerPasswordGtkAffordanceTest(unittest.TestCase):
    def test_remote_admin_with_empty_permissions_sees_password_control(self):
        labels = render_customer_actions(admin=True)
        self.assertEqual(labels.count('Acesso web / senha'), 1)
        self.assertIn('Abrir Officina Web', labels)

    def test_remote_employee_with_empty_permissions_hides_password_control(self):
        labels = render_customer_actions(admin=False)
        self.assertNotIn('Acesso web / senha', labels)
        self.assertIn('Abrir Officina Web', labels)
        self.assertNotIn('Excluir / desativar', labels)

    def test_remote_admin_still_sees_destructive_customer_control(self):
        labels = render_customer_actions(admin=True)
        self.assertIn('Excluir / desativar', labels)

    def test_password_control_requires_web_access_as_before(self):
        labels = render_customer_actions(admin=True, web_enabled=False)
        self.assertNotIn('Acesso web / senha', labels)
        self.assertNotIn('Abrir Officina Web', labels)


if __name__ == '__main__':
    unittest.main()
