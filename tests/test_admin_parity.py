"""Admin parity: provider, stock, cash and composition pages on the site."""
import http.cookiejar
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from officina.core.banco import criar_banco
from officina.core import atendimento_os as aten
from officina.core import cadastros_v9 as cad9
from officina.core import catalogo_servicos as catalogo
from officina.core import composicao
from officina.core import empresa_financeiro as empresa
from officina.core import estoque_materiais as estoque
from officina.core import fluxo_os as fluxo
from officina.core import prestadores_ext as ext
from flavors.autoseg.modules.portal_prestador import PortalPrestador


def browser():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(client, base, path, data=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    try:
        with client.open(urllib.request.Request(base + path, body), timeout=15) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def csrf(html):
    found = re.search(r'name="csrf" value="([^"]+)"', html)
    return found.group(1) if found else ''


class AdminParityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='admin_parity_')
        self.old_base = os.environ.get('AUTOSEG_BASE')
        os.environ['AUTOSEG_BASE'] = self.tmp.name
        self.db = str(Path(self.tmp.name) / 'parity.db')
        criar_banco(self.db)
        for module in (ext, fluxo, aten, cad9, estoque, catalogo, empresa):
            module.instalar(self.db)
        composicao.instalar()
        composicao.instalar_banco(self.db)
        self.admin = ext.cadastrar(
            self.db, 'Admin Paridade', 'admin.paridade@example.invalid',
            'senha-admin-123')
        cad9.definir_admin(self.db, self.admin, True)
        self.employee = ext.cadastrar(
            self.db, 'Funcionário Paridade', 'func.paridade@example.invalid',
            'senha-func-123')
        self.server = PortalPrestador(self.db, '127.0.0.1', 0)
        self.server.iniciar()
        self.base = f'http://127.0.0.1:{self.server.servidor.server_port}'
        self.admin_browser = browser()
        self.func_browser = browser()
        status, html = request(self.admin_browser, self.base, '/login', {
            'email': 'admin.paridade@example.invalid',
            'senha': 'senha-admin-123'})
        self.assertEqual(status, 200)
        self.admin_csrf = csrf(html)
        status, html = request(self.func_browser, self.base, '/login', {
            'email': 'func.paridade@example.invalid',
            'senha': 'senha-func-123'})
        self.assertEqual(status, 200)
        self.func_csrf = csrf(html)

    def tearDown(self):
        self.server.parar()
        if self.old_base is None:
            os.environ.pop('AUTOSEG_BASE', None)
        else:
            os.environ['AUTOSEG_BASE'] = self.old_base
        self.tmp.cleanup()

    def test_admin_pages_are_visible_and_employee_is_denied(self):
        for path in ('/prestadores', '/estoque', '/estoque/novo',
                     '/caixa', '/composicao'):
            status, html = request(self.admin_browser, self.base, path)
            self.assertEqual(status, 200, path)
            self.assertNotIn('Falha interna', html)
            status, _html = request(self.func_browser, self.base, path)
            self.assertEqual(status, 403, path)

    def test_admin_creates_provider_stock_cash_and_composition(self):
        status, html = request(self.admin_browser, self.base,
                               '/prestadores/novo', {
                                   'csrf': self.admin_csrf,
                                   'nome': 'Novo Prestador Web',
                                   'email': 'novo.web@example.invalid',
                                   'senha': 'senha-novo-123',
                                   'telefone': '', 'documento': '',
                                   'especialidade': 'Teste'})
        self.assertEqual(status, 200)
        self.assertIn('Novo Prestador Web', html)

        status, html = request(self.admin_browser, self.base,
                               '/estoque/salvar', {
                                   'csrf': self.admin_csrf,
                                   'nome': 'Material Web', 'sku': 'WEB1',
                                   'unidade': 'un', 'custo': '5',
                                   'venda': '10', 'minimo': '1'})
        self.assertEqual(status, 200)
        self.assertIn('Material Web', html)
        with ext.db(self.db) as c:
            produto = c.execute(
                "SELECT id FROM estoque_produtos WHERE nome='Material Web'"
            ).fetchone()['id']
        status, html = request(self.admin_browser, self.base,
                               f'/estoque/{produto}/ajuste', {
                                   'csrf': self.admin_csrf,
                                   'delta': '+2', 'motivo': 'teste'})
        self.assertEqual(status, 200)
        self.assertIn('+2', html)

        status, html = request(self.admin_browser, self.base,
                               '/caixa/movimentos', {
                                   'csrf': self.admin_csrf,
                                   'tipo': 'aporte', 'descricao': 'Aporte Web',
                                   'valor': '100', 'data': '07/11/2026',
                                   'prestador_id': str(self.admin),
                                   'os_id': '', 'categoria': 'Capital',
                                   'finalidade': 'Teste', 'observacao': ''})
        self.assertEqual(status, 200)
        self.assertIn('Aporte Web', html)

        import yaml
        config = composicao.carregar()
        status, html = request(self.admin_browser, self.base,
                               '/composicao/yaml', {
                                   'csrf': self.admin_csrf,
                                   'yaml': yaml.safe_dump(
                                       config, allow_unicode=True,
                                       sort_keys=False)})
        self.assertEqual(status, 200)
        self.assertIn('Composição de valores', html)


if __name__ == '__main__':
    unittest.main(verbosity=2)
