"""6.4: single Chrome, shared root and client modules; no GTK or extra deps."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flavors.autoseg.modules import officina_web, client_web
from officina.web import ShellPage, active_for
from flavors.autoseg.modules.autoseg_web_navigation import navigation_for, canonical_client_path


def _context(kind, role='customer'):
    if kind == 'provider':
        return officina_web.context_for({'nome': 'Test User', 'csrf': 'csrf',
                                         'admin': role == 'admin'})
    return officina_web.context_for(SimpleNamespace(
        identity=SimpleNamespace(kind='client', display_name='Test User'),
        principal=SimpleNamespace(role=role), csrf='csrf'))


class SharedShellContractTest(unittest.TestCase):
    def _html(self, context):
        return officina_web.render_page(ShellPage('Shared title', '<section class="card">Shared content</section>',
                                      context, navigation_for(context)))

    def test_provider_and_client_use_exact_same_renderer_chrome(self):
        for kind in ('provider', 'client'):
            with self.subTest(kind=kind):
                html = self._html(_context(kind))
                self.assertEqual(html.count('<aside class="app-side">'), 1)
                self.assertEqual(html.count('<header>'), 1)
                self.assertEqual(html.count('<footer>'), 1)
                self.assertIn('class="side-nav"', html)
                self.assertIn('class="ui-app"', html)
                self.assertIn('class="side-brand"', html)
                self.assertIn('Shared content', html)

    def test_provider_keeps_legacy_nav_markers(self):
        html = self._html(_context('provider', 'admin'))
        for label in ('Ordens de serviço', 'Clientes', 'Financeiro', 'Prestadores'):
            self.assertIn(label, html)
        self.assertIn('href="/prestadores"', html)

    def test_client_reuses_chrome_but_reduces_links(self):
        html = self._html(_context('client'))
        self.assertIn('Portal do cliente', html)
        self.assertIn('href="/os"', html)
        self.assertIn('href="/documentos"', html)
        self.assertNotIn('href="/financeiro"', html)
        self.assertNotIn('href="/prestadores"', html)
        self.assertNotIn('href="/clientes"', html)

    def test_module_only_for_client(self):
        self.assertIn('/em-rota', [n.href for n in navigation_for(_context('client'))])
        self.assertNotIn('/em-rota', [n.href for n in navigation_for(_context('provider'))])

    def test_permissionless_nav_item_is_removed(self):
        from dataclasses import replace
        ctx = replace(_context('client'), permissions=frozenset())
        links = [item.href for item in navigation_for(ctx)]
        self.assertNotIn('/solicitar', links)
        self.assertNotIn('/documentos', links)

    def test_navigation_active_by_route(self):
        ctx = _context('client')
        self.assertEqual(active_for('/os/12', navigation_for(ctx)), 'client-work')
        self.assertEqual(active_for('/documentos', navigation_for(ctx)), 'client-documents')

    def test_aliases_cover_nested_work_and_call_documents(self):
        for old, new in [('/cliente', '/'), ('/cliente/painel', '/'),
                         ('/cliente/os', '/os'), ('/cliente/os/10', '/os/10'),
                         ('/cliente/os/10/documento/-2', '/os/10/documento/-2'),
                         ('/cliente/chamado/4', '/chamado/4'),
                         ('/cliente/chamado/4/documento/5', '/chamado/4/documento/5'),
                         ('/cliente/solicitar', '/solicitar')]:
            self.assertEqual(canonical_client_path(old), new)

    def test_unknown_alias_is_not_invented(self):
        self.assertIsNone(canonical_client_path('/cliente/admin'))
        self.assertFalse(officina_web.client_path_allowed('/financeiro'))
        self.assertFalse(officina_web.client_path_allowed('/prestadores'))

    def test_login_is_shared_shell_fragment(self):
        class Handler:
            def pagina(self, title, body, session=None, status=200):
                self.title, self.body, self.session = title, body, session
        handler = Handler()
        officina_web.login_page(handler, error='internal secret', identifier='<user>')
        self.assertIn('Officina Web', handler.body)
        self.assertIn('Acesso à plataforma', handler.body)
        self.assertIn('action="/login"', handler.body)
        self.assertNotIn('Usar login antigo', handler.body)
        self.assertNotIn('internal secret', handler.body)
        self.assertNotIn('<user>', handler.body)
        self.assertIn('&lt;user&gt;', handler.body)
        self.assertNotIn('react', handler.body.lower())

    def test_module_fragment_has_no_second_chrome(self):
        class Handler:
            def pagina(self, title, body, session, status=200):
                self.body = body
        handler = Handler()
        item = SimpleNamespace(id=5, number='OS-0005', status='Em rota')
        with patch.object(client_web.client_service, 'list_work_items', return_value=(item,)):
            client_web.en_route(handler, 'db', SimpleNamespace(),)
        self.assertIn('Acompanhamento de atendimentos', handler.body)
        self.assertNotIn('<header>', handler.body)
        self.assertNotIn('<aside', handler.body)

    def test_client_module_does_not_modify_provider_nav(self):
        before = navigation_for(_context('provider'))
        with patch.object(client_web.client_service, 'list_work_items', return_value=()):
            class Handler:
                def pagina(self, *args, **kwargs):
                    pass
            client_web.en_route(Handler(), 'db', SimpleNamespace())
        self.assertEqual(before, navigation_for(_context('provider')))


class SharedShellHttpTest(unittest.TestCase):
    """HTTP assertions use the existing setup without inheriting its tests."""
    def setUp(self):
        from tests.test_officina_web import OfficinaWebHttpTest
        OfficinaWebHttpTest.setUp(self)

    @staticmethod
    def browser(follow=False):
        from tests.test_officina_web import OfficinaWebHttpTest
        return OfficinaWebHttpTest.browser(follow)

    def req(self, *args, **kwargs):
        from tests.test_officina_web import OfficinaWebHttpTest
        return OfficinaWebHttpTest.req(self, *args, **kwargs)

    def login(self, *args, **kwargs):
        from tests.test_officina_web import OfficinaWebHttpTest
        return OfficinaWebHttpTest.login(self, *args, **kwargs)

    def test_provider_and_client_have_identical_chrome_markers(self):
        provider, st, headers, _ = self.login('provider@example.test', self.provider_pass)
        self.assertEqual(303, st)
        self.assertEqual('/', headers['Location'])
        client, st, headers, _ = self.login('customer@example.test', self.client_pass)
        self.assertEqual(303, st)
        self.assertEqual('/', headers['Location'])
        for browser in (provider, client):
            status, _, html = self.req(browser, '/')
            self.assertEqual(200, status)
            for marker in (b'class="app-side"', b'class="side-nav"',
                           b'<header>', b'<footer>', b'Officina Web'):
                self.assertIn(marker, html)
        self.assertIn(b'Portal do cliente', self.req(client, '/')[2])
        self.assertNotIn(b'href="/prestadores"', self.req(client, '/')[2])

    def test_customer_alias_redirect_and_module(self):
        client, _, _, _ = self.login('customer@example.test', self.client_pass)
        for old, target in (('/cliente', '/'), ('/cliente/os', '/os'),
                            ('/cliente/solicitar', '/solicitar')):
            status, headers, _ = self.req(client, old)
            self.assertEqual(303, status)
            self.assertEqual(target, headers['Location'])
        self.assertEqual(200, self.req(client, '/em-rota')[0])
        self.assertEqual(403, self.req(client, '/financeiro')[0])

    def test_provider_cannot_open_client_only_module(self):
        provider, _, _, _ = self.login('provider@example.test', self.provider_pass)
        self.assertNotEqual(200, self.req(provider, '/em-rota')[0])
        self.assertEqual(200, self.req(provider, '/')[0])


class FlavorBoundaryTest(unittest.TestCase):
    """The reusable web package must never depend on AUTOSEG."""

    def test_generic_sources_do_not_reference_flavor(self):
        import ast
        from pathlib import Path
        import officina.web
        package = Path(officina.web.__file__).parent
        for file in package.glob('*.py'):
            source = file.read_text(encoding='utf-8')
            with self.subTest(file=file.name):
                self.assertNotIn('flavors.autoseg', source)
                self.assertNotIn('portal_prestador', source)
                ast.parse(source)

    def test_generic_renderer_is_injected_and_flavor_independent(self):
        from officina.web import ShellPage, render_shell
        ctx = _context('client')
        page = ShellPage('Title', '<p>Module</p>', ctx, ())
        self.assertEqual(render_shell(page, lambda p: p.content), '<p>Module</p>')
        with self.assertRaises(TypeError):
            render_shell(page, None)

    def test_autoseg_items_have_one_source_in_flavor(self):
        from flavors.autoseg.modules import autoseg_web_navigation as registry
        from officina.web.navigation import navigation_for as generic_filter
        for kind in ('provider', 'client'):
            ctx = _context(kind)
            with self.subTest(kind=kind):
                self.assertEqual(registry.navigation_for(ctx),
                                 generic_filter(ctx, registry.ITEMS))
        self.assertIn('/financeiro', [item.href for item in registry.ITEMS])
        self.assertIn('/em-rota', [item.href for item in registry.ITEMS])

    def test_flavor_route_registry_has_only_real_handler_functions(self):
        from flavors.autoseg.modules import autoseg_web_navigation as registry
        routes = registry.client_routes(home=client_web.home,
                                      list_items=client_web.list_items,
                                      documents=client_web.documents,
                                      request_form=client_web.request_form,
                                      en_route=client_web.en_route)
        self.assertEqual({route.path for route in routes},
                         {'/', '/os', '/documentos', '/solicitar', '/em-rota'})
        for route in routes:
            with self.subTest(route=route.path):
                self.assertTrue(callable(route.handler))
                self.assertEqual(route.handler.__module__, client_web.__name__)

class SharedNavigationSingleSourceTest(unittest.TestCase):
    """Topbar and sidebar must use one filtered AUTOSEG item snapshot."""

    def _render(self, context):
        return officina_web.render_page(ShellPage(
            'Navigation', '<section class="card">Body</section>', context,
            navigation_for(context)))

    def test_changed_item_label_is_visible_in_both_navigation_surfaces(self):
        from dataclasses import replace
        from flavors.autoseg.modules import autoseg_web_navigation as source
        original = source.ITEMS
        changed = tuple(replace(item, label='Atendimentos testados')
                        if item.id == 'work' else item for item in original)
        try:
            source.ITEMS = changed
            context = _context('provider', 'admin')
            html = self._render(context)
            self.assertEqual(html.count('>Atendimentos testados</span>'), 1)
            self.assertEqual(html.count('>Atendimentos testados</a>'), 1)
            self.assertNotIn('>Ordens de serviço</a>', html)
        finally:
            source.ITEMS = original

    def test_top_flag_toggle_only_affects_topbar(self):
        from dataclasses import replace
        from flavors.autoseg.modules import autoseg_web_navigation as source
        original = source.ITEMS
        try:
            source.ITEMS = tuple(replace(item, top=False)
                                 if item.id == 'work' else item for item in original)
            html = self._render(_context('provider', 'admin'))
            self.assertIn('>Ordens de serviço</span>', html)
            self.assertNotIn('>Ordens de serviço</a>', html)
        finally:
            source.ITEMS = original

    def test_employee_admin_only_item_absent_in_top_and_sidebar(self):
        html = self._render(_context('provider', 'employee'))
        for title in ('Prestadores', 'Estoque', 'Composição de valores', 'Feedbacks'):
            self.assertNotIn(f'>{title}</a>', html)
            self.assertNotIn(f'>{title}</span>', html)
        self.assertIn('>Ordens de serviço</a>', html)
        self.assertIn('>Ordens de serviço</span>', html)

    def test_client_has_no_provider_items_in_either_surface(self):
        html = self._render(_context('client'))
        for href in ('/clientes', '/financeiro', '/prestadores', '/pj-publicas'):
            self.assertNotIn(f'href="{href}"', html)
        self.assertIn('href="/documentos"', html)
        self.assertIn('href="/solicitar"', html)

    def test_layout_has_no_second_menu_table_or_admin_branch(self):
        import inspect
        from flavors.autoseg.modules import portal_prestador
        code = inspect.getsource(portal_prestador.layout)
        self.assertNotIn('menus=[', code)
        self.assertNotIn('menus =', code)
        self.assertNotIn("usuario.get('admin')", code)
        self.assertIn('top_navigation_for(', code)
        self.assertNotIn("('/clientes'", code)
