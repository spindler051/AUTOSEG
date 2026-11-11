"""Unit characterization of the generic shell; not an HTTP integration test."""
from unittest.mock import patch
import unittest
from types import SimpleNamespace

from officina.web import Brand, NavItem, PageContext
from flavors.autoseg.modules import officina_web


class ShellTest(unittest.TestCase):
    def test_client_page_escapes_context_and_uses_portal_layout(self):
        session = SimpleNamespace(identity=SimpleNamespace(kind='client', display_name='<script>'),
                                  principal=SimpleNamespace(role='customer'), csrf='session-csrf')
        class Handler:
            sent = None
            def pagina(self, title, body, legacy, status=200, cliente=False):
                self.sent = (title, body, legacy, status, cliente)
        handler = Handler()
        officina_web.page(handler, 'Customer', '<p>Trusted body</p>', session)
        self.assertTrue(handler.sent[4])
        self.assertIn('Officina Web', handler.sent[1])
        self.assertIn('&lt;script&gt;', handler.sent[1])
        self.assertNotIn('<script>', handler.sent[1])
        self.assertNotIn('href="/financeiro"', handler.sent[1])

    def test_login_uses_portal_layout_and_generic_error(self):
        class Handler:
            sent = None
            def pagina(self, title, body, legacy, status=200):
                self.sent = (title, body)
        h = Handler()
        officina_web.login_page(h, error='private information', identifier='" onfocus="bad')
        self.assertNotIn('private information', h.sent[1])
        self.assertIn('Credenciais inválidas', h.sent[1])
        self.assertIn('&quot;', h.sent[1])

    def test_client_navigation_excludes_provider_links(self):
        session = SimpleNamespace(identity=SimpleNamespace(kind='client',display_name='Test'),
                                  principal=SimpleNamespace(role='customer'),csrf='csrf')
        ctx = officina_web.context_for(session)
        links = [n.href for n in ctx.navigation]
        self.assertIn('/cliente/os', links)
        for forbidden in ('/financeiro','/clientes','/estoque','/prestadores'):
            self.assertNotIn(forbidden, links)

    def test_provider_navigation_preserved(self):
        ctx = officina_web.context_for({'nome': 'Test', 'admin': True, 'csrf':'demo'})
        self.assertEqual(ctx.kind, 'provider')
        self.assertIn('/financeiro', [n.href for n in ctx.navigation])

    def test_handler_sends_exactly_once(self):
        class Handler:
            calls = []
            def pagina(self, title, body, session, status=200):
                self.calls.append((title, body, status))
        h = Handler()
        officina_web.page(h, 'Title', '<p>Hello</p>', status=201)
        self.assertEqual(len(h.calls), 1)
        self.assertEqual(h.calls[0][2], 201)




class OfficinaWebHttpTest(unittest.TestCase):
    """Real HTTP regression tests against the actual provider portal on a test DB."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from flavors.autoseg.modules import accounts, web_session
        from flavors.autoseg.modules import cliente_fluxo_v94 as fluxo_pf
        from flavors.autoseg.modules.portal_prestador import PortalPrestador
        from officina.core.banco import criar_banco
        from officina.core import cadastros_v9 as cad, prestadores_ext as ext
        from officina.core import atendimento_os as aten
        self.tmp = tempfile.TemporaryDirectory(prefix='officina_web_http_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'test.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        aten.instalar(self.db)
        accounts.install(self.db)
        self.provider_pass = 'ProviderPassword123'
        self.client_pass = 'ClientPassword123'
        self.provider_id = ext.cadastrar(self.db, 'Provider Example',
                                        'provider@example.test', self.provider_pass)
        self.client_id = cad.cadastrar_usuario(self.db, 'Customer Example',
                        '52998224725', '51999999999', self.client_pass,
                        'customer@example.test')
        self.other_id = cad.cadastrar_usuario(self.db, 'Other Example',
                        '11144477735', '51999999998', self.client_pass,
                        'other@example.test')
        for uid, label in ((self.client_id, 'Customer'), (self.other_id, 'Other')):
            fluxo_pf.atualizar_perfil(self.db, uid, {
                'nome': label + ' Example', 'telefone': '51999999999',
                'email': label.lower() + '@example.test',
                'endereco': 'Rua Exemplo', 'numero': '10', 'bairro': 'Centro',
                'cidade': 'Cidade Fictícia', 'uf': 'RS', 'cep': '90000000'})
        # Import while neither client has a PF link. First-request coverage
        # checks that this does not require a bulk migration.
        accounts.migrate_legacy(self.db, dry_run=False)
        web_session.clear()
        self.addCleanup(web_session.clear)
        self.patch_env = patch.dict('os.environ', {'AUTOSEG_UNIFIED_LOGIN': '1'})
        self.patch_env.start()
        self.addCleanup(self.patch_env.stop)
        self.portal = PortalPrestador(self.db, '127.0.0.1', 0)
        self.portal.iniciar()
        self.addCleanup(self.portal.parar)
        self.base = 'http://127.0.0.1:' + str(self.portal.porta)

    @staticmethod
    def browser(follow=False):
        import http.cookiejar
        import urllib.request
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        processors = [urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
        if not follow:
            processors.insert(0, NoRedirect())
        return urllib.request.build_opener(*processors)

    def req(self, browser, route, data=None, headers=None):
        import urllib.parse, urllib.request, urllib.error
        payload = urllib.parse.urlencode(data).encode() if data is not None else None
        request = urllib.request.Request(self.base + route, payload, headers or {})
        try:
            with browser.open(request, timeout=15) as response:
                try:
                    content = response.read()
                except (ConnectionError, OSError):
                    if response.status not in (301, 302, 303, 307, 308):
                        raise
                    content = b''
                return response.status, response.headers, content
        except urllib.error.HTTPError as response:
            try:
                content = response.read()
            except (ConnectionError, OSError):
                content = b''
            return response.code, response.headers, content

    def login(self, identifier, password):
        browser = self.browser()
        status, headers, body = self.req(browser, '/entrar',
                 {'identificador': identifier, 'senha': password})
        return browser, status, headers, body

    def _create_owned_work(self, uid, description):
        from flavors.autoseg.modules import accounts
        from flavors.autoseg.modules import cliente_fluxo_v94 as fluxo_pf
        from officina.core import prestadores_ext as ext
        fluxo_pf.garantir_perfil_pf(self.db, uid)
        with ext.db(self.db) as c:
            account_id = c.execute("SELECT account_id FROM account_links WHERE client_user_id=?",
                                   (uid,)).fetchone()[0]
        accounts.sync_client_pf_link(self.db, account_id, uid)
        return fluxo_pf.registrar_os_pf(self.db, uid, description)

    def test_provider_keeps_existing_dashboard_markers(self):
        browser, status, headers, _ = self.login('provider@example.test', self.provider_pass)
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/')
        status, _, body = self.req(browser, '/')
        self.assertEqual(status, 200)
        self.assertIn(b'Vis\xc3\xa3o geral', body)
        self.assertIn(b'Ordens de servi\xc3\xa7o', body)
        self.assertIn(b'Officina Web', body)

    def test_customer_gets_own_home_same_origin_cookie(self):
        browser, status, headers, _ = self.login('customer@example.test', self.client_pass)
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/cliente')
        cookie = headers.get_all('Set-Cookie') or ()
        self.assertTrue(any('autosseg_unified=' in c and 'SameSite=Strict' in c for c in cookie))
        status, _, page = self.req(browser, '/cliente')
        self.assertEqual(status, 200)
        self.assertIn(b'Portal do cliente', page)
        self.assertNotIn(b'href="/financeiro"', page)
        self.assertNotIn(b'href="/prestadores"', page)
        self.assertNotIn(b'href="/estoque"', page)

    def test_customer_denied_provider_dashboard_and_workitem_alias(self):
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        for route in ('/financeiro', '/clientes', '/os/1', '/prestadores'):
            status, _, body = self.req(browser, route)
            self.assertEqual(status, 403, route)
            self.assertNotIn(b'Vis\xc3\xa3o geral', body)

    def test_provider_denied_client_routes(self):
        browser, _, _, _ = self.login('provider@example.test', self.provider_pass)
        status, headers, _ = self.req(browser, '/cliente/os')
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/')

    def test_customer_can_request_work_and_see_it(self):
        import re
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        status, _, form = self.req(browser, '/cliente/solicitar')
        self.assertEqual(status, 200)
        csrf = re.search(rb'name="csrf" value="([^"]+)"', form)
        self.assertIsNotNone(csrf)
        status, headers, _ = self.req(browser, '/cliente/solicitar', {
            'csrf': csrf.group(1).decode(), 'descricao': 'Teste de atendimento particular',
            'urgencia': 'Normal'})
        self.assertEqual(status, 303)
        self.assertTrue(headers['Location'].startswith('/cliente/os/'))
        status, _, body = self.req(browser, '/cliente/os')
        self.assertEqual(status, 200)
        self.assertIn(b'/cliente/os/', body)

    def test_cross_customer_item_is_not_visible(self):
        from flavors.autoseg.modules import cliente_fluxo_v94 as fluxo_pf
        work = self._create_owned_work(self.client_id, 'Teste de cliente A')
        other, _, _, _ = self.login('other@example.test', self.client_pass)
        status, _, body = self.req(other, f'/cliente/os/{work}')
        self.assertIn(status, (403, 404))
        self.assertNotIn(b'Teste de cliente A', body)

    def test_csrf_is_required_for_customer_post(self):
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        status, _, body = self.req(browser, '/cliente/solicitar', {
            'csrf': 'wrong', 'descricao': 'Teste de pedido de servico valido',
            'urgencia': 'Normal'})
        self.assertEqual(status, 403)
        self.assertNotIn(b'Teste de pedido', body)

    def test_flag_off_ignores_customer_cookie(self):
        from unittest.mock import patch
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        with patch.dict('os.environ', {'AUTOSEG_UNIFIED_LOGIN': '0'}):
            status, headers, _ = self.req(browser, '/entrar')
            self.assertEqual(status, 303)
            self.assertEqual(headers['Location'], '/login')
            denied, _, _ = self.req(browser, '/cliente')
            self.assertNotEqual(denied, 200)

    def test_legacy_provider_login_still_works(self):
        browser = self.browser()
        status, headers, _ = self.req(browser, '/login', {
            'email': 'provider@example.test', 'senha': self.provider_pass})
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/')
        status, _, body = self.req(browser, '/')
        self.assertEqual(status, 200)
        self.assertIn(b'Vis\xc3\xa3o geral', body)

    def test_customer_logout_revokes_cookie(self):
        import re
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        status, _, html = self.req(browser, '/cliente')
        csrf = re.search(rb'name="csrf" value="([^"]+)"', html)
        self.assertIsNotNone(csrf)
        status, headers, _ = self.req(browser, '/cliente/sair',
                                      {'csrf': csrf.group(1).decode()})
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/login')
        self.assertTrue(any('Max-Age=0' in x for x in headers.get_all('Set-Cookie') or ()))
        status, _, _ = self.req(browser, '/cliente')
        self.assertEqual(status, 303)
    def _make_published_report(self):
        import hashlib
        from pathlib import Path
        from unittest.mock import patch
        from flavors.autoseg.modules import cliente_fluxo_v94 as fluxo_pf
        from officina.core import fluxo_os as fluxo, prestadores_ext as ext
        work_id = self._create_owned_work(self.client_id,
                      'Teste de relatório exclusivo do cliente')
        root = Path(self.tmp.name) / 'reports'
        published = root / 'publicados'
        published.mkdir(parents=True, exist_ok=True)
        file_path = published / 'published.pdf'
        content = b'%PDF-1.4\n' + b'0' * 128 + b'\n%%EOF'
        file_path.write_bytes(content)
        replacement = patch.object(ext, 'RELATORIOS', root)
        replacement.start()
        self.addCleanup(replacement.stop)
        with ext.db(self.db) as connection:
            connection.execute("UPDATE ordens_servico SET status='Concluída' WHERE id=?", (work_id,))
            created = connection.execute(
                'INSERT INTO os_documentos(os_id,tipo,versao,caminho,sha256,publicado_em) '
                'VALUES(?,?,?,?,?,?)',
                (work_id, 'relatorio_pdf', 1, str(file_path),
                 hashlib.sha256(content).hexdigest(), ext.agora()))
            document_id = created.lastrowid
        return work_id, document_id

    def test_authorized_report_download_and_cross_customer_denial(self):
        work, document = self._make_published_report()
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        other, _, _, _ = self.login('other@example.test', self.client_pass)
        route = f'/cliente/os/{work}/documento/{-document}'
        status, headers, content = self.req(browser, route)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), 'application/pdf')
        self.assertTrue(content.startswith(b'%PDF-'))
        status, _, body = self.req(other, route)
        self.assertIn(status, (403, 404))
        self.assertNotIn(b'%PDF-', body)
        self.assertNotIn(b'published.pdf', body)

    def test_document_list_only_links_own_published_report(self):
        work, document = self._make_published_report()
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        other, _, _, _ = self.login('other@example.test', self.client_pass)
        status, _, body = self.req(browser, '/cliente/documentos')
        self.assertEqual(status, 200)
        self.assertIn(f'/cliente/os/{work}/documento/{-document}'.encode(), body)
        status, _, body = self.req(other, '/cliente/documentos')
        self.assertEqual(status, 200)
        self.assertNotIn(f'/cliente/os/{work}/documento/'.encode(), body)

    def test_invoice_download_and_cross_customer_denial(self):
        import hashlib
        from pathlib import Path
        from unittest.mock import patch
        from officina.core import prestadores_ext as ext
        work, _report_id = self._make_published_report()
        root = Path(self.tmp.name) / 'invoices'
        root.mkdir(parents=True, exist_ok=True)
        path = root / 'invoice.pdf'
        payload = b'%PDF-1.4\n' + b'0' * 128 + b'\n%%EOF'
        path.write_bytes(payload)
        replacement = patch.object(ext, 'NOTAS', root)
        replacement.start()
        self.addCleanup(replacement.stop)
        with ext.db(self.db) as connection:
            invoice = connection.execute(
                'INSERT INTO os_notas_fiscais(os_id,prestador_id,nome_original,caminho,sha256,criado_em) '
                'VALUES(?,?,?,?,?,?)',
                (work, self.provider_id, 'invoice.pdf', str(path),
                 hashlib.sha256(payload).hexdigest(), ext.agora())).lastrowid
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        other, _, _, _ = self.login('other@example.test', self.client_pass)
        route = f'/cliente/os/{work}/documento/{invoice}'
        status, headers, content = self.req(browser, route)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), 'application/pdf')
        self.assertTrue(content.startswith(b'%PDF-'))
        status, _, body = self.req(other, route)
        self.assertIn(status, (403, 404))
        self.assertNotIn(b'%PDF-', body)
        self.assertNotIn(str(path).encode(), body)



    def test_associated_call_document_is_owner_scoped(self):
        from officina.core import prestadores_ext as ext
        work, document = self._make_published_report()
        with ext.db(self.db) as c:
            org = c.execute("INSERT INTO v9_organizacoes(nome,tipo,criado_em) VALUES('Docs org','Empresa',?)",
                            (ext.agora(),)).lastrowid
            call_id = c.execute("""INSERT INTO v9_chamados
                (organizacao_id,usuario_id,descricao,urgencia,criado_em,os_id)
                VALUES(?,?,?,?,?,?)""", (org,self.client_id,'Owner call', 'Normal',ext.agora(),work)).lastrowid
        route = f'/cliente/chamado/{call_id}/documento/{-document}'
        owner, _, _, _ = self.login('customer@example.test', self.client_pass)
        outsider, _, _, _ = self.login('other@example.test', self.client_pass)
        status, _, data = self.req(owner, route)
        self.assertEqual(status, 200)
        self.assertTrue(data.startswith(b'%PDF-'))
        status, _, data = self.req(outsider, route)
        self.assertIn(status, (403, 404))
        self.assertNotIn(b'%PDF-', data)
        self.assertNotIn(b'published.pdf', data)

    def test_first_request_syncs_link_rotates_cookie_and_preserves_next_login(self):
        from flavors.autoseg.modules import accounts
        from officina.core import prestadores_ext as ext
        import re
        with ext.db(self.db) as c:
            account_id = c.execute("SELECT account_id FROM account_links WHERE client_user_id=?",
                                   (self.client_id,)).fetchone()[0]
            self.assertIsNone(c.execute("SELECT client_id FROM account_links WHERE account_id=?",
                                        (account_id,)).fetchone()[0])
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        status, _, form = self.req(browser, '/cliente/solicitar')
        self.assertEqual(200, status)
        csrf = re.search(rb'name="csrf" value="([^"]+)"', form).group(1).decode()
        status, headers, _ = self.req(browser, '/cliente/solicitar', {
            'csrf': csrf, 'descricao': 'Primeira solicitação com vínculo PF novo', 'urgencia': 'Normal'})
        self.assertEqual(303, status)
        self.assertTrue(any('autosseg_unified=' in v for v in headers.get_all('Set-Cookie') or ()))
        with ext.db(self.db) as c:
            link = c.execute("SELECT client_id FROM account_links WHERE account_id=?", (account_id,)).fetchone()
            self.assertIsNotNone(link[0])
            self.assertEqual(link[0], c.execute("SELECT cliente_pf_id FROM v9_usuarios WHERE id=?",
                                                 (self.client_id,)).fetchone()[0])
        status, _, page = self.req(browser, '/cliente/os')
        self.assertEqual(200, status)
        work_path = headers['Location']
        self.assertTrue(work_path.startswith('/cliente/os/'))
        self.assertIn(work_path.encode(), page)
        status, _, detail = self.req(browser, work_path)
        self.assertEqual(200, status)
        self.assertIn(b'Primeira solicita', detail)
        fresh, st, hd, _ = self.login('customer@example.test', self.client_pass)
        self.assertEqual(303, st)
        self.assertEqual(200, self.req(fresh, '/cliente')[0])
        other, _, _, _ = self.login('other@example.test', self.client_pass)
        self.assertNotIn(b'Primeira solicita', self.req(other, '/cliente/os')[2])
        self.assertEqual(link[0], accounts.sync_client_pf_link(self.db, account_id, self.client_id))

    def test_unconverted_client_login_is_explicitly_denied(self):
        from flavors.autoseg.modules import auth
        with patch.object(auth, 'accounts', None):
            browser, status, headers, body = self.login('customer@example.test',self.client_pass)
            self.assertEqual(200,status)
            self.assertIn(b'Credenciais inv',body)
            self.assertFalse(any('autosseg_unified=' in c for c in
                                 headers.get_all('Set-Cookie') or ()))
            status,_,_=self.req(browser,'/cliente/solicitar')
            self.assertEqual(303,status)

    def test_account_sync_then_os_failure_rotates_session(self):
        import re
        from unittest.mock import patch
        from flavors.autoseg.modules import cliente_fluxo_v94 as fluxo_pf
        from officina.core import prestadores_ext as ext
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        _, _, form = self.req(browser, '/cliente/solicitar')
        csrf = re.search(rb'name="csrf" value="([^"]+)"', form).group(1).decode()
        with patch.object(fluxo_pf, 'registrar_os_pf', side_effect=ValueError('fake write failure')):
            status, headers, _ = self.req(browser, '/cliente/solicitar', {
                'csrf': csrf, 'descricao': 'Pedido que deve falhar depois do vínculo',
                'urgencia': 'Normal'})
        self.assertEqual(303, status)
        self.assertEqual('/cliente/solicitar?erro=1', headers['Location'])
        self.assertTrue(any('autosseg_unified=' in c for c in
                            headers.get_all('Set-Cookie') or ()))
        status, _, page = self.req(browser, '/cliente/os')
        self.assertEqual(200, status)
        self.assertNotIn(b'Pedido que deve falhar', page)
        with ext.db(self.db) as c:
            pf = c.execute('SELECT cliente_pf_id FROM v9_usuarios WHERE id=?',
                           (self.client_id,)).fetchone()[0]
            linked = c.execute('SELECT client_id FROM account_links WHERE client_user_id=?',
                               (self.client_id,)).fetchone()[0]
        self.assertEqual(pf, linked)
        self.assertIsNotNone(pf)

    def test_unconverted_client_cannot_write_os_even_when_legacy_auth_exists(self):
        from flavors.autoseg.modules import auth, cliente_fluxo_v94 as fluxo_pf
        with (patch.object(auth,'accounts',None),
              patch.object(fluxo_pf,'registrar_os_pf') as write):
            browser,status,headers,body=self.login('customer@example.test',self.client_pass)
            self.assertEqual(200,status)
            self.assertIn(b'Credenciais inv',body)
            self.assertEqual(303,self.req(browser,'/cliente/solicitar')[0])
            write.assert_not_called()

    def test_own_organizational_call_visible_associated_work_and_cross_client_denied(self):
        from officina.core import prestadores_ext as ext
        work = self._create_owned_work(self.client_id, 'Associated work for own call')
        with ext.db(self.db) as c:
            org = c.execute("INSERT INTO v9_organizacoes(nome,tipo,criado_em) VALUES('Example org','Condomínio',?)",
                            (ext.agora(),)).lastrowid
            own = c.execute("INSERT INTO v9_chamados(organizacao_id,usuario_id,descricao,urgencia,criado_em,os_id) VALUES(?,?,?,?,?,?)",
                            (org,self.client_id,'Own organizational call','Normal',ext.agora(),work)).lastrowid
            other_call = c.execute("INSERT INTO v9_chamados(organizacao_id,usuario_id,descricao,urgencia,criado_em) VALUES(?,?,?,?,?)",
                            (org,self.other_id,'Foreign call details','Normal',ext.agora())).lastrowid
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        status, _, page = self.req(browser, '/cliente/os')
        self.assertEqual(200, status)
        self.assertIn(f'/cliente/chamado/{own}'.encode(), page)
        status, _, page = self.req(browser, f'/cliente/chamado/{own}')
        self.assertEqual(200, status)
        self.assertIn(b'OS vinculada', page)
        status, _, page = self.req(browser, f'/cliente/chamado/{other_call}')
        self.assertIn(status, (403,404))
        self.assertNotIn(b'Foreign call details', page)
        other, _, _, _ = self.login('other@example.test', self.client_pass)
        status, _, page = self.req(other, f'/cliente/chamado/{own}')
        self.assertIn(status, (403,404))
        self.assertNotIn(b'Own organizational call', page)




class UnifiedClientLoginContractTest(unittest.TestCase):
    def test_provider_and_client_have_one_session_constructor(self):
        from unittest.mock import patch
        from flavors.autoseg.modules import auth, login_web
        for kind in ('provider', 'client'):
            principal = SimpleNamespace(active=True)
            result = SimpleNamespace(
                identity=SimpleNamespace(kind=kind), membership=object(),
                principal=principal, account_id=None, source='legacy')
            expected = ('token', object())
            with (patch.object(auth, 'authenticate', return_value=result),
                  patch.object(login_web.web_session, 'current_credential', return_value='stored-hash'),
                  patch.object(login_web.web_session, 'create', return_value=expected) as creator):
                self.assertEqual(login_web.authenticate_and_create('db', 'id', 'pw'), expected)
                self.assertEqual(creator.call_args.args[6], 'legacy')

    def test_customer_does_not_map_to_provider_session(self):
        from unittest.mock import patch
        from flavors.autoseg.modules import login_web
        session = SimpleNamespace(identity=SimpleNamespace(kind='client'),
                                  principal=SimpleNamespace(active=True, role='customer'))
        with patch.object(login_web, 'unified_session', return_value=session):
            self.assertIsNone(login_web.provider_session(SimpleNamespace(headers={}), 'db'))
            self.assertIs(login_web.client_session(SimpleNamespace(headers={}), 'db'), session)

    def test_flag_off_blocks_customer_session_resolution(self):
        from unittest.mock import patch
        from flavors.autoseg.modules import login_web
        with (patch.object(login_web.login_flags, 'unified_login_enabled', return_value=False),
              patch.object(login_web.web_session, 'resolve') as resolve):
            self.assertIsNone(login_web.client_session(SimpleNamespace(headers={}), 'db'))
            resolve.assert_not_called()

if __name__ == '__main__':
    unittest.main()
