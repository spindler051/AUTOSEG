"""Due date for receivables and overdue highlight in the provider portal."""
import http.cookiejar
import re
import sqlite3
import tempfile
import unittest
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from banco import criar_banco
import fluxo_os
import portal_negocios as neg
from portal_prestador import PortalPrestador
import prestadores_ext as ext


def pedido(browser, base, url, dados=None):
    body = urllib.parse.urlencode(dados).encode() if dados is not None else None
    req = urllib.request.Request(base + url, body)
    with browser.open(req, timeout=12) as resposta:
        return resposta.read().decode('utf-8', 'replace')


def csrf(html):
    achado = re.search(r'name="csrf" value="([^"]+)"', html)
    if not achado:
        raise AssertionError('CSRF não disponível')
    return achado.group(1)


class FinanceiroVencimentoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_venc_')
        self.db = str(Path(self.tmp.name) / 'teste.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        fluxo_os.instalar(self.db)
        self.a = ext.cadastrar(
            self.db, 'Técnico A', 'a@example.org', 'senha-teste-a!')
        self.b = ext.cadastrar(
            self.db, 'Técnico B', 'b@example.org', 'senha-teste-b!')
        with ext.db(self.db) as c:
            cliente = c.execute(
                "INSERT INTO clientes(nome,status) VALUES('Cliente Teste','Ativo')"
            ).lastrowid
            self.os_id = c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total) "
                "VALUES('OS-VENC-1',?,'Concluída',100)", (cliente,)).lastrowid
            self.fid = c.execute(
                "INSERT INTO financeiro(os_id,cliente_id,descricao,valor,status) "
                "VALUES(?,?,'OS-VENC-1',100,'Aguardando pagamento')",
                (self.os_id, cliente)).lastrowid
            c.execute(
                "INSERT INTO os_encerramentos(os_id,situacao,ator,prestador_id,encerrado_em) "
                "VALUES(?,'Concluída','Teste',?,?)",
                (self.os_id, self.a, ext.agora()))

    def tearDown(self):
        self.tmp.cleanup()

    def test_define_e_remove_vencimento(self):
        self.assertEqual(
            neg.financeiro_definir_vencimento(
                self.db, self.fid, self.a, '2026-11-30'),
            '2026-11-30')
        with ext.db(self.db) as c:
            self.assertEqual(
                c.execute('SELECT vencimento FROM financeiro WHERE id=?',
                          (self.fid,)).fetchone()[0],
                '2026-11-30')
        self.assertEqual(
            neg.financeiro_definir_vencimento(self.db, self.fid, self.a, ''),
            '')
        with ext.db(self.db) as c:
            self.assertIsNone(
                c.execute('SELECT vencimento FROM financeiro WHERE id=?',
                          (self.fid,)).fetchone()[0])

    def test_rejeita_data_invalida(self):
        with self.assertRaises(ValueError):
            neg.financeiro_definir_vencimento(
                self.db, self.fid, self.a, '30/11/2026')

    def test_rejeita_outro_prestador_e_recebido(self):
        with self.assertRaises(PermissionError):
            neg.financeiro_definir_vencimento(
                self.db, self.fid, self.b, '2026-11-30')
        with ext.db(self.db) as c:
            c.execute("UPDATE financeiro SET status='Recebido' WHERE id=?",
                      (self.fid,))
        with self.assertRaises(ValueError):
            neg.financeiro_definir_vencimento(
                self.db, self.fid, self.a, '2026-11-30')

    def test_portal_shows_overdue_and_accepts_new_date(self):
        ontem = (date.today() - timedelta(days=1)).isoformat()
        amanha = (date.today() + timedelta(days=1)).isoformat()
        with ext.db(self.db) as c:
            c.execute("UPDATE financeiro SET vencimento=? WHERE id=?",
                      (ontem, self.fid))
        servidor = PortalPrestador(self.db, host='127.0.0.1', porta=0)
        try:
            servidor.iniciar()
            base = f'http://127.0.0.1:{servidor.porta}'
            browser = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            html = pedido(browser, base, '/login', {
                'email': 'a@example.org', 'senha': 'senha-teste-a!'})
            self.assertIn('Visão geral', html)
            html = pedido(browser, base, '/financeiro')
            self.assertIn('Atrasado', html)
            self.assertIn('name="vencimento"', html)
            html = pedido(browser, base, f'/financeiro/{self.fid}/vencimento', {
                'csrf': csrf(html), 'vencimento': amanha})
            self.assertNotIn('Atrasado', html)
            with sqlite3.connect(self.db) as conexao:
                self.assertEqual(conexao.execute(
                    'SELECT vencimento FROM financeiro WHERE id=?',
                    (self.fid,)).fetchone()[0], amanha)
        finally:
            servidor.parar()


if __name__ == '__main__':
    unittest.main(verbosity=2)
