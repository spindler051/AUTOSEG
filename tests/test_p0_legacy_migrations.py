"""Active behavior formerly exercised through the removed client server.

Unlike the retired script smoke tests, these use converted accounts, the
single HTTP origin, a disposable database, and positive/negative assertions.
"""
from __future__ import annotations

import html.parser
import re
import unittest
from urllib.parse import urljoin, urlsplit

from tests import test_officina_web as _fixture
from officina.core import cadastros_v9 as cad, prestadores_ext as ext
from flavors.autoseg.modules import accounts


class _LinkParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        key = 'href' if tag == 'a' else 'action' if tag == 'form' else None
        if key and attributes.get(key):
            self.urls.append(attributes[key])


class LegacyBehaviorsOnOneOrigin(unittest.TestCase):
    def setUp(self):
        _fixture.OfficinaWebHttpTest.setUp(self)

    def browser(self):
        return _fixture.OfficinaWebHttpTest.browser()

    def req(self, *args, **kwargs):
        return _fixture.OfficinaWebHttpTest.req(self, *args, **kwargs)

    def login(self, *args, **kwargs):
        return _fixture.OfficinaWebHttpTest.login(self, *args, **kwargs)

    def owned_work(self, uid, description):
        return _fixture.OfficinaWebHttpTest._create_owned_work(self, uid, description)

    def csrf(self, browser, route):
        status, _, body = self.req(browser, route)
        self.assertEqual(status, 200, route)
        found = re.search(rb'name="csrf" value="([^"]+)"', body)
        self.assertIsNotNone(found, route)
        return found.group(1).decode()

    def organization(self, name='Condomínio da revisão'):
        with ext.db(self.db) as c:
            return c.execute("INSERT INTO v9_organizacoes(nome,tipo,criado_em) "
                             "VALUES(?,'Condomínio',?)", (name, ext.agora())).lastrowid

    def test_retired_signup_and_public_intake_never_create_accounts_or_calls(self):
        visitor = self.browser()
        with ext.db(self.db) as c:
            initial = tuple(c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                            for table in ('v9_usuarios', 'v9_chamados', 'accounts'))
        for route in ('/cliente/cadastro', '/cliente/cadastro-pj',
                      '/cliente/cadastrar', '/pj-rapido', '/pj-rapido/enviar',
                      '/cliente/pj-rapido/enviar'):
            self.assertEqual(self.req(visitor, route)[0], 410, route)
            self.assertEqual(self.req(visitor, route, {'cpf':'52998224725'})[0], 410, route)
        with ext.db(self.db) as c:
            final = tuple(c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                          for table in ('v9_usuarios', 'v9_chamados', 'accounts'))
        self.assertEqual(initial, final)

    def test_one_origin_login_and_no_cross_site_links(self):
        visitor = self.browser()
        status, _, login_html = self.req(visitor, '/login')
        self.assertEqual(status, 200)
        self.assertIn(b'Officina Web', login_html)
        self.assertIn(b'name="identificador"', login_html)
        browser, code, headers, _ = self.login('customer@example.test', self.client_pass)
        self.assertEqual(code, 303)
        self.assertEqual(headers['Location'], '/')
        for route in ('/', '/cliente/perfil', '/cliente/organizacoes', '/cliente/orcamento'):
            status, _, body = self.req(browser, route)
            self.assertEqual(status, 200, route)
            links = _LinkParser()
            links.feed(body.decode('utf-8'))
            for link in links.urls:
                if link.startswith(('http:', 'https:')):
                    self.assertEqual(urlsplit(link).netloc, urlsplit(self.base).netloc)
                else:
                    self.assertFalse(link.startswith('//'), (route,link))
                    self.assertEqual(urlsplit(urljoin(self.base, link)).netloc,
                                     urlsplit(self.base).netloc)
        self.assertEqual(self.req(visitor, '/cliente/entrar-pf')[0], 308)

    def test_profile_completion_and_private_request_are_owner_scoped(self):
        customer, code, _, _ = self.login('customer@example.test', self.client_pass)
        self.assertEqual(code, 303)
        status, _, profile = self.req(customer, '/cliente/perfil')
        self.assertEqual(status, 200)
        self.assertIn(b'Complete o perfil PF', profile)
        oid = self.owned_work(self.client_id, 'Portão particular da revisão')
        self.assertEqual(self.req(customer, f'/os/{oid}')[0], 200)
        self.assertIn(b'Port', self.req(customer, '/os')[2])
        other, _, _, _ = self.login('other@example.test', self.client_pass)
        self.assertEqual(self.req(other, f'/os/{oid}')[0], 404)

    def test_condominium_request_requires_contact_and_preserves_pending_status(self):
        org = self.organization()
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        csrf = self.csrf(browser, f'/cliente/chamado/novo?org={org}')
        post = {'csrf':csrf,'org_id':str(org),'papel':'Morador',
                'unidade':'Apto 303','urgencia':'Normal','solicitante_nome':'Cliente Teste',
                'descricao':'Portão do condomínio não abre corretamente.'}
        status, _, body = self.req(browser, '/cliente/chamado/novo', post)
        self.assertEqual(status, 409)
        self.assertIn(b'telefone', body.lower())
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM v9_chamados').fetchone()[0], 0)
        post['solicitante_telefone'] = '51999998888'
        status, headers, _ = self.req(browser, '/cliente/chamado/novo', post)
        self.assertEqual(status, 303)
        self.assertTrue(headers['Location'].startswith('/chamado/'))
        with ext.db(self.db) as c:
            call = c.execute('SELECT * FROM v9_chamados ORDER BY id DESC LIMIT 1').fetchone()
            self.assertEqual(call['status'], 'Aguardando AUTOSEG')
            self.assertEqual(call['unidade'], 'Apto 303')
            self.assertEqual(call['solicitante_telefone'], '51999998888')
            self.assertIsNotNone(call['os_id'])
        other, _, _, _ = self.login('other@example.test', self.client_pass)
        self.assertEqual(self.req(other, headers['Location'])[0], 404)

    def test_org_search_and_unapproved_administration_never_grants_role(self):
        org = self.organization('Condomínio Árvore Azul')
        client, _, _, _ = self.login('customer@example.test', self.client_pass)
        code, _, result = self.req(client, '/cliente/organizacoes?q=%C3%81rvore')
        self.assertEqual(code, 200)
        self.assertIn('Condomínio Árvore Azul'.encode(), result)
        route = f'/cliente/vinculo/novo?org={org}'
        token = self.csrf(client, route)
        code, _, body = self.req(client, '/cliente/vinculo/novo', {
            'csrf':token, 'org_id':str(org),'funcao':'Síndico','cnpj':''})
        self.assertIn(code, (303,409))
        self.assertEqual(accounts.account_link(self.db,
            accounts.find_account_by_identifier(self.db,'email',
                'customer@example.test').id).client_role,'customer')
        self.assertEqual(self.req(client, f'/cliente/sindico?org={org}')[0],404)

    def test_provider_sees_operational_os_and_form_without_client_portal(self):
        oid = self.owned_work(self.client_id,'OS PF do controle operacional')
        provider, code, _, _ = self.login('provider@example.test',self.provider_pass)
        self.assertEqual(code, 303)
        for route in ('/', '/os', '/os/rapida'):
            status, _, page = self.req(provider, route)
            self.assertEqual(status, 200, route)
            self.assertIn(b'Officina Web', page)
        code, headers, detail = self.req(provider, f'/os/{oid}')
        if code == 303:
            code, _, detail = self.req(provider, headers['Location'])
        self.assertIn(code, (200,403,404))
        self.assertNotIn(b'action="/cliente/cadastrar"', detail)
        self.assertEqual(self.req(provider, '/cliente/orcamento')[0], 404)

    def test_client_quote_pdf_and_whatsapp_asset_on_shared_origin(self):
        from officina.core import catalogo_servicos as catalogo
        catalogo.instalar(self.db)
        sid = catalogo.salvar(self.db, {'nome':'Vistoria de portão',
                                       'descricao':'Inspeção', 'preco_servico':'120,00'})
        browser, _, _, _ = self.login('customer@example.test', self.client_pass)
        token = self.csrf(browser,'/cliente/orcamento')
        code, headers, pdf = self.req(browser,'/cliente/orcamento/pdf',{
            'csrf':token,'servico_id':str(sid),'quantidade':'1'})
        self.assertEqual(code,200)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn('application/pdf',headers['Content-Type'])
        self.assertEqual(self.req(browser,'/static/cliente_whatsapp.js')[0],200)
        self.assertEqual(self.req(browser,'/pj-rapido')[0],410)


if __name__ == '__main__':
    unittest.main()
