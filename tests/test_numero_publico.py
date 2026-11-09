"""Public OS number: resolver, alias and canonical URL."""
import http.cookiejar
import re
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from officina.core.banco import criar_banco
from officina.core import cadastros_v9 as cad9
from officina.core import fluxo_os
from flavors.autoseg.modules.portal_prestador import PortalPrestador
from officina.core import prestadores_ext as ext
from officina.repositories import ordens


def pedido(browser, base, url, dados=None):
    body = urllib.parse.urlencode(dados).encode() if dados is not None else None
    req = urllib.request.Request(base + url, body)
    with browser.open(req, timeout=12) as resposta:
        return resposta.status, resposta.geturl(), resposta.read().decode('utf-8', 'replace')


def token(html):
    achado = re.search(r'name="csrf" value="([^"]+)"', html)
    if not achado:
        raise AssertionError('CSRF não disponível')
    return achado.group(1)


class NumeroPublicoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='numero_publico_')
        self.db = str(Path(self.tmp.name) / 'teste.db')
        criar_banco(self.db)
        for modulo in (ext, fluxo_os, cad9):
            modulo.instalar(self.db)
        self.pid = ext.cadastrar(
            self.db, 'Prestador Número', 'numero@exemplo.com', 'senha-numero-2026!')
        with ext.db(self.db) as c:
            c.execute(
                "CREATE TABLE IF NOT EXISTS os_numero_alias("
                "alias TEXT PRIMARY KEY, os_id INTEGER NOT NULL, "
                "criado_em TEXT NOT NULL, origem TEXT NOT NULL)")
            self.cid = c.execute(
                "INSERT INTO clientes(nome,status) VALUES('Cliente Número','Ativo')"
            ).lastrowid
            self.oid = c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao,"
                "data_abertura,criado_em) VALUES('261107001',?,'Aberta','Teste',?,?)",
                (self.cid, '2026-11-07 10:00:00', '2026-11-07 10:00:00')).lastrowid
            c.execute(
                "INSERT INTO os_numero_alias(alias,os_id,criado_em,origem) "
                "VALUES('OS-0001',?,?, 'teste')",
                (self.oid, '2026-11-07 10:00:00'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_resolver_and_canonical_url(self):
        self.assertEqual(ordens.obter_por_token(self.db, '261107001')['id'], self.oid)
        self.assertEqual(ordens.obter_por_token(self.db, 'OS-0001')['id'], self.oid)
        self.assertEqual(ordens.obter_por_token(self.db, str(self.oid))['id'], self.oid)
        self.assertEqual(ordens.url_os(self.db, '261107001'), '/os/261107001')
        self.assertEqual(ordens.url_os(self.db, 'OS-0001'), '/os/261107001')
        self.assertEqual(ordens.url_os(self.db, self.oid), '/os/261107001')

    def test_site_redirects_alias_and_id_to_number(self):
        servidor = PortalPrestador(self.db, host='127.0.0.1', porta=0)
        try:
            servidor.iniciar()
            base = f'http://127.0.0.1:{servidor.porta}'
            browser = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            _, _, html = pedido(browser, base, '/login', {
                'email': 'numero@exemplo.com', 'senha': 'senha-numero-2026!'})
            self.assertIn('Visão geral', html)
            status, url, html = pedido(browser, base, '/os/261107001')
            self.assertEqual(status, 200)
            self.assertIn('261107001', html)
            status, url, html = pedido(browser, base, '/os/OS-0001')
            self.assertEqual(status, 200)
            self.assertTrue(url.endswith('/os/261107001'))
            status, url, html = pedido(browser, base, f'/os/{self.oid}')
            self.assertEqual(status, 200)
            self.assertTrue(url.endswith('/os/261107001'))
        finally:
            servidor.parar()

    def test_workflow_actions_persist_form_client(self):
        from officina.core import atendimento_os as aten
        from officina.core import produtividade_os as prod
        aten.instalar(self.db)
        prod.instalar(self.db)
        with ext.db(self.db) as c:
            provisorio = c.execute(
                "INSERT INTO clientes(nome,status) VALUES('Cliente a definir','A definir')"
            ).lastrowid
            escolhido = c.execute(
                "INSERT INTO clientes(nome,status) VALUES('Cliente Escolhido','Ativo')"
            ).lastrowid
        servidor = PortalPrestador(self.db, host='127.0.0.1', porta=0)
        try:
            servidor.iniciar()
            base = f'http://127.0.0.1:{servidor.porta}'
            browser = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            _, _, html = pedido(browser, base, '/login', {
                'email': 'numero@exemplo.com', 'senha': 'senha-numero-2026!'})
            self.assertIn('Visão geral', html)
            _, _, html = pedido(browser, base, f'/os/{self.oid}')
            csrf = token(html)
            for indice, acao in enumerate(('abrir', 'em-rota', 'iniciar')):
                numero = f'2611070{10 + indice}'
                with ext.db(self.db) as c:
                    oid = c.execute(
                        "INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao,"
                        "data_abertura,criado_em) VALUES(?,?,'Aberta','Teste',?,?)",
                        (numero, provisorio, '2026-11-07 10:00:00',
                         '2026-11-07 10:00:00')).lastrowid
                if acao == 'em-rota':
                    ext.assumir(self.db, oid, self.pid)
                status, url, html = pedido(browser, base, f'/os/{numero}/{acao}', {
                    'csrf': csrf,
                    'cliente_id': str(escolhido),
                    'cliente_busca': 'Cliente Escolhido',
                })
                self.assertEqual(status, 200, (acao, html[:500]))
                with ext.db(self.db) as c:
                    salvo = c.execute(
                        'SELECT cliente_id FROM ordens_servico WHERE id=?',
                        (oid,)).fetchone()['cliente_id']
                self.assertEqual(salvo, escolhido, acao)
        finally:
            servidor.parar()

    def test_pending_os_groups_workflow_before_preview(self):
        with ext.db(self.db) as c:
            c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?",
                      (self.oid,))
        ext.assumir(self.db, self.oid, self.pid)
        url = ordens.url_os(self.db, self.oid)
        servidor = PortalPrestador(self.db, host='127.0.0.1', porta=0)
        try:
            servidor.iniciar()
            base = f'http://127.0.0.1:{servidor.porta}'
            browser = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            _, _, html = pedido(browser, base, '/login', {
                'email': 'numero@exemplo.com', 'senha': 'senha-numero-2026!'})
            self.assertIn('Visão geral', html)
            _, _, html = pedido(browser, base, url)
            csrf = token(html)
            self.assertIn('>Em rota</button>', html)
            self.assertIn('>Iniciada</button>', html)
            self.assertIn(f'formaction="{url}/em-rota"', html)
            self.assertIn(f'formaction="{url}/iniciar"', html)
            self.assertIn('Baixar preview do PDF', html)
            self.assertLess(html.find(f'formaction="{url}/em-rota"'),
                            html.find('Baixar preview do PDF'))
            self.assertEqual(html.count(f'formaction="{url}/em-rota"'), 1)
            status, _, _ = pedido(browser, base, f'{url}/em-rota', {
                'csrf': csrf,
                'cliente_id': str(self.cid),
                'cliente_busca': 'Cliente Número',
            })
            self.assertEqual(status, 200)
            _, _, html = pedido(browser, base, url)
            self.assertIn(f'formaction="{url}/cancelar-rota"', html)
            self.assertNotIn(f'formaction="{url}/em-rota"', html)
        finally:
            servidor.parar()

    def test_draft_materials_restore_on_os_form(self):
        ext.salvar_rascunho_web(self.db, self.oid, self.pid, {
            'material_item[]': ['Material do rascunho'],
            'material_qtd[]': ['2'],
            'material_unidade[]': ['un'],
            'material_unit[]': ['10,00'],
            'materiais_presentes': '1',
        })
        servidor = PortalPrestador(self.db, host='127.0.0.1', porta=0)
        try:
            servidor.iniciar()
            base = f'http://127.0.0.1:{servidor.porta}'
            browser = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            _, _, html = pedido(browser, base, '/login', {
                'email': 'numero@exemplo.com', 'senha': 'senha-numero-2026!'})
            self.assertIn('Visão geral', html)
            status, url, html = pedido(browser, base, f'/os/{self.oid}')
            self.assertEqual(status, 200)
            self.assertIn('Material do rascunho', html)
            self.assertIn('name="material_item[]"', html)
        finally:
            servidor.parar()


if __name__ == '__main__':
    unittest.main(verbosity=2)
