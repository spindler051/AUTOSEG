"""P0: one origin, closed migration allowlist and scoped client modules."""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

# Importing servidor_backend configures the data directory at module import.
# Keep the test process off the system/production path before that import.
_TEST_DATA = tempfile.TemporaryDirectory(prefix="autoseg_p0_test_")
os.environ.setdefault("AUTOSEG_SERVER_DATA", _TEST_DATA.name)

from flavors.autoseg.modules import autoseg_web_navigation as navigation
from flavors.autoseg.modules import links_publicos, servidor_backend
from flavors.autoseg.modules.web_access import WebAccessManager
from scripts.autoseg import cli


class OneOriginContract(unittest.TestCase):
    def test_backend_owns_one_provider_server(self):
        servers = []
        class FakeSite:
            host = '127.0.0.1'
            porta = 0
            def __init__(self, *args, **kwargs):
                servers.append(self)
            def iniciar(self):
                return 'http://127.0.0.1:0'
            def parar(self):
                self.stopped = True
        config = SimpleNamespace(host='127.0.0.1', port=0)
        with (patch.object(servidor_backend, 'BANCO', 'temporary-test-only'),
              patch.object(servidor_backend, '_instalar_base'),
              patch.object(servidor_backend, '_esperar'),
              patch.object(servidor_backend.runtime_config, 'provider_server', return_value=config),
              patch('flavors.autoseg.modules.portal_prestador.PortalPrestador', FakeSite)):
            servidor_backend.run_site()
        self.assertEqual(len(servers), 1)
        self.assertTrue(servers[0].stopped)

    def test_single_port_is_explicit_in_cli_and_links(self):
        self.assertEqual(cli.ports('dev', 'site'), (8866,))
        self.assertEqual(cli.ports('main', 'site'), (8766,))
        self.assertEqual(links_publicos.PORTAS, (links_publicos.PORTA_SITE,))
        self.assertEqual(len(links_publicos.PORTAS), 1)
        with patch.object(links_publicos, 'estado_com_manuais', return_value={}):
            html = links_publicos.quadro_html()
        self.assertIn('Officina Web', html)
        self.assertNotIn('Portal do Cliente', html)

    def test_legacy_server_has_been_deleted(self):
        base = Path(__file__).resolve().parents[1]
        self.assertFalse((base/'flavors/autoseg/modules/servidor_web.py').exists())
        self.assertFalse((base/'flavors/autoseg/modules/portal_cliente_v94.py').exists())
        sources = (base/'flavors/autoseg/modules/servidor_backend.py',
                   base/'flavors/autoseg/modules/web_access.py')
        for source in sources:
            tree = ast.parse(source.read_text())
            imports = [x for x in ast.walk(tree) if isinstance(x, (ast.Import, ast.ImportFrom))]
            self.assertNotIn('servidor_web', str([(getattr(x, 'module', None),
                [a.name for a in x.names]) for x in imports]))

    def test_only_approved_redirects_and_retired_flows(self):
        for old, new in navigation.ALIASES.items():
            self.assertEqual(navigation.canonical_client_path(old), new)
        self.assertEqual(navigation.canonical_client_path('/cliente/os/34'), '/os/34')
        self.assertEqual(navigation.canonical_client_path('/cliente/chamado/12'), '/chamado/12')
        for route in ('/cliente/falso', '/cliente/os/12/documento/9', '/cliente/pj',
                      '/cliente/nota/12', '/cliente/cadastro-pj'):
            self.assertIsNone(navigation.canonical_client_path(route))
        for route in ('/legado', '/legado/entrar', '/legado/os/x/pdf',
                      '/pj-rapido', '/pj-rapido/enviar', '/cliente/pj-rapido',
                      '/cliente/cadastro', '/cliente/cadastrar', '/cliente/cadastro-pj'):
            self.assertTrue(navigation.retired_client_path(route), route)

    def test_gtk_contract_has_no_second_port(self):
        base = Path(__file__).resolve().parents[1] / 'flavors/autoseg/modules'
        for name in ('gtk_app.py', 'portal_v9.py', 'web_access.py', 'links_publicos.py'):
            self.assertNotIn('PORTAS[1]', (base/name).read_text(), name)
        for name in ('client_info', 'start_client', 'stop_client', '_criar_cliente'):
            self.assertFalse(hasattr(WebAccessManager, name))


class MigratedClientHttp(unittest.TestCase):
    def setUp(self):
        from tests.test_officina_web import OfficinaWebHttpTest
        OfficinaWebHttpTest.setUp(self)

    def browser(self, follow=False):
        from tests.test_officina_web import OfficinaWebHttpTest
        return OfficinaWebHttpTest.browser(follow)

    def req(self, *args, **kwargs):
        from tests.test_officina_web import OfficinaWebHttpTest
        return OfficinaWebHttpTest.req(self, *args, **kwargs)

    def login(self, *args, **kwargs):
        from tests.test_officina_web import OfficinaWebHttpTest
        return OfficinaWebHttpTest.login(self, *args, **kwargs)

    def test_public_assets_and_diagnostics_share_the_origin(self):
        browser = self.browser()
        for path in ('/api/versao', '/api/health', '/api/info',
                     '/manifest.webmanifest', '/static/portal.js',
                     '/static/cliente_whatsapp.js', '/icone.png',
                     '/favicon.ico', '/logo.png'):
            code, _, content = self.req(browser, path)
            self.assertEqual(code, 200, path)
            self.assertTrue(content, path)

    def test_aliases_are_308_without_new_cookie(self):
        browser = self.browser()
        for old, new in (('/cliente', '/'), ('/cliente/entrar-pf', '/login'),
                         ('/cliente/nova', '/solicitar'), ('/cliente/os/5', '/os/5'),
                         ('/cliente/chamado/6', '/chamado/6')):
            code, headers, _ = self.req(browser, old)
            self.assertEqual(code, 308, old)
            self.assertEqual(headers['Location'], new)
            self.assertFalse(headers.get_all('Set-Cookie'), old)

    def test_retired_flows_return_410_without_login_or_write(self):
        browser = self.browser()
        for path in ('/legado', '/legado/entrar', '/pj-rapido',
                     '/cliente/pj-rapido/enviar', '/cliente/cadastrar'):
            code, _, body = self.req(browser, path)
            self.assertEqual(code, 410, path)
            self.assertIn(b'indispon', body.lower())
        for path in ('/legado/entrar', '/pj-rapido/enviar', '/cliente/cadastrar'):
            self.assertEqual(self.req(browser, path, {'cpf':'00000000000'})[0], 410)

    def test_authenticated_client_sees_migrated_modules_in_one_shell(self):
        browser, code, headers, _ = self.login('customer@example.test', self.client_pass)
        self.assertEqual(code, 303)
        self.assertEqual(headers['Location'], '/')
        for route, label in (('/cliente/perfil', b'perfil PF'),
                             ('/cliente/senha', b'Seguran'),
                             ('/cliente/organizacoes', b'condom'),
                             ('/cliente/orcamento', b'Or'),
                             ('/cliente/os/nova', b'OS particular')):
            status, _, body = self.req(browser, route)
            self.assertEqual(status, 200, (route,body[:100]))
            self.assertIn(label, body, route)
            self.assertEqual(body.count(b'class="app-side"'), 1, route)
        for path in ('/clientes','/financeiro','/prestadores','/estoque',
                     '/composicao','/caixa'):
            self.assertIn(self.req(browser,path)[0],(403,404), path)

    def test_password_or_profile_forms_do_not_skip_csrf(self):
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        for route in ('/cliente/perfil', '/cliente/senha', '/cliente/orcamento/pdf',
                      '/cliente/nova-organizacao', '/cliente/chamado/novo'):
            status, _, _ = self.req(browser, route, {'nome':'Bad', 'nova_senha':'BadPassword2026'})
            self.assertEqual(status, 403, route)

    def test_unknown_client_path_is_404_not_403(self):
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        self.assertEqual(self.req(browser, '/cliente/falso')[0], 404)
        self.assertEqual(self.req(browser, '/cliente/os/12/documento/9')[0], 404)

    def test_document_access_denies_other_customer(self):
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        other_work_id = self._create_owned_work(self.other_id, 'Serviço exclusivo do outro cliente')
        for route in (f'/cliente/os/{other_work_id}/pdf',
                      f'/cliente/nota/{other_work_id}',
                      f'/os/{other_work_id}'):
            self.assertEqual(self.req(browser, route)[0], 404, route)

    def _csrf(self, browser, path='/cliente/perfil'):
        import re
        status, _, body = self.req(browser, path)
        self.assertEqual(status, 200)
        match = re.search(rb'name="csrf" value="([^"]+)"', body)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def test_profile_updates_only_authenticated_customer(self):
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        form = {'csrf':self._csrf(browser), 'nome':'Customer Example',
                'telefone':'51999999999', 'email':'customer@example.test',
                'endereco':'Rua Exemplo', 'numero':'12', 'bairro':'Centro',
                'cidade':'Cidade Fictícia', 'uf':'RS', 'cep':'90000000'}
        status, headers, _ = self.req(browser, '/cliente/perfil', form)
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/cliente/perfil')
        from officina.core import prestadores_ext as ext
        with ext.db(self.db) as c:
            row=c.execute('SELECT numero FROM v9_usuarios WHERE id=?',(self.client_id,)).fetchone()
            other=c.execute('SELECT numero FROM v9_usuarios WHERE id=?',(self.other_id,)).fetchone()
        self.assertEqual(row['numero'], '12')
        self.assertEqual(other['numero'], '10')

    def test_password_updates_account_and_revokes_session(self):
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        csrf = self._csrf(browser, '/cliente/senha')
        new_password = 'NewStrongPassword2026'
        status, headers, _ = self.req(browser, '/cliente/senha', {
            'csrf':csrf, 'senha_atual':self.client_pass,
            'nova_senha':new_password, 'confirmar_senha':new_password})
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/login')
        self.assertNotEqual(self.req(browser,'/cliente/perfil')[0],200)
        old_browser, old_code, _, _ = self.login('customer@example.test',self.client_pass)
        self.assertNotEqual(old_code,303)
        new_browser, new_code, _, _ = self.login('customer@example.test',new_password)
        self.assertEqual(new_code,303)
        self.assertEqual(self.req(new_browser,'/cliente/perfil')[0],200)

    def test_quote_pdf_generated_for_authenticated_customer(self):
        from officina.core import catalogo_servicos as catalogo
        catalogo.instalar(self.db)
        service_id=catalogo.salvar(self.db,{'nome':'Vistoria técnica',
             'descricao':'Vistoria de testes', 'preco_servico':'180,00'})
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        self.assertIn(b'Vistoria t',self.req(browser,'/cliente/orcamento')[2])
        csrf = self._csrf(browser,'/cliente/orcamento')
        status, headers, payload = self.req(browser,'/cliente/orcamento/pdf',{
            'csrf':csrf,'servico_id':str(service_id),'quantidade':'1'})
        self.assertEqual(status,200)
        self.assertIn('application/pdf',headers['Content-Type'])
        self.assertTrue(payload.startswith(b'%PDF-'))

    def test_organization_creation_and_call_are_authenticated(self):
        from officina.core import prestadores_ext as ext
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        csrf = self._csrf(browser, '/cliente/nova-organizacao')
        form = {'csrf':csrf, 'tipo':'Condomínio', 'nome':'Condomínio Exemplo P0',
                'endereco':'Rua de Teste 100', 'cidade':'Cidade Fictícia',
                'telefone':'51999999999', 'papel':'Morador',
                'unidade':'Sala 203', 'solicitante_nome':'Customer Example',
                'solicitante_telefone':'51999999999','urgencia':'Normal',
                'descricao':'Problema de interfone da unidade teste'}
        status, headers, _ = self.req(browser,'/cliente/nova-organizacao',form)
        self.assertEqual(status,303)
        self.assertTrue(headers['Location'].startswith('/chamado/'))
        self.assertEqual(self.req(browser,headers['Location'])[0],200)
        other_browser, _, _, _ = self.login('other@example.test',self.client_pass)
        self.assertEqual(self.req(other_browser,headers['Location'])[0],404)
        with ext.db(self.db) as c:
            result=c.execute('SELECT COUNT(*) FROM v9_chamados WHERE usuario_id=?',
                             (self.client_id,)).fetchone()[0]
        self.assertEqual(result,1)

    def _create_owned_work(self, uid, description):
        from tests.test_officina_web import OfficinaWebHttpTest
        return OfficinaWebHttpTest._create_owned_work(self, uid, description)


if __name__ == '__main__':
    unittest.main()
