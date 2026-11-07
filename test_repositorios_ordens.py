"""Characterization tests for the read-only OS repository."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import fluxo_os
import prestadores_ext as ext
from banco import criar_banco
from repositorios import ordens


class OrdensRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ordens_repo_')
        self.db = Path(self.tmp.name) / 'teste.db'
        criar_banco(self.db)
        ext.instalar(self.db)
        fluxo_os.instalar(self.db)
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO clientes(nome) VALUES('Cliente A')")
            c.execute("INSERT INTO clientes(nome) VALUES('Cliente B')")
            base = [
                ('OS-1', 1, 'Aberta', 100.0, '2026-11-01', 'App', 0),
                ('OS-2', 1, 'Iniciada', 200.0, '2026-11-02', 'App', 0),
                ('OS-3', 2, 'Pendente', 300.0, '2026-11-03', 'App', 0),
                ('OS-4', 2, 'Concluída', 400.0, '2026-11-04', 'App', 0),
                ('OS-5', 1, 'Cancelada', 500.0, '2026-11-05', 'App', 0),
                ('OS-6', 2, 'Concluída', 600.0, '2026-11-06', 'App', 1),
                ('OS-7', 1, 'Aberta', 700.0, '2026-11-07', 'Portal', 0),
            ]
            for numero, cliente, status, valor, data, origem, arquivada in base:
                c.execute(
                    "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                    "data_abertura,origem,arquivada) VALUES(?,?,?,?,?,?,?)",
                    (numero, cliente, status, valor, data, origem, arquivada))
            c.execute("INSERT INTO financeiro(os_id,cliente_id,valor,status) VALUES(4,2,400,'Recebido')")
            c.execute("INSERT INTO financeiro(os_id,cliente_id,valor,status) VALUES(5,1,500,'Recebido')")
            c.execute("INSERT INTO financeiro(os_id,cliente_id,valor,status) VALUES(3,2,300,'Aguardando pagamento')")
            c.execute("INSERT INTO os_documentos(os_id,tipo,versao,caminho,sha256,publicado_em) "
                      "VALUES(4,'relatorio_pdf',2,'/tmp/os4.pdf','abc','2026-11-04')")

    def tearDown(self):
        self.tmp.cleanup()

    def test_resumo_ignora_arquivadas_e_conta_status(self):
        dados = ordens.resumo(self.db)
        self.assertEqual(dados['total'], 6)
        self.assertEqual(dados['abertas'], 2)
        self.assertEqual(dados['iniciadas'], 1)
        self.assertEqual(dados['pendentes'], 1)
        self.assertEqual(dados['concluidas'], 1)

    def test_financeiro_resumo_mantem_aliases(self):
        dados = ordens.financeiro_resumo(self.db)
        self.assertEqual(dados['recebido'], 900.0)
        self.assertEqual(dados['pendente'], 300.0)
        self.assertEqual(dados['a_receber'], 300.0)

    def test_recentes_respeita_limite_e_ordem(self):
        linhas = ordens.recentes(self.db, limite=2)
        self.assertEqual([x['numero_os'] for x in linhas], ['OS-7', 'OS-5'])
        self.assertEqual(linhas[0]['cliente'], 'Cliente A')

    def test_historico_exclui_ativas_e_arquivadas_e_traz_versao(self):
        linhas = ordens.listar_historico(self.db)
        self.assertEqual([x['numero_os'] for x in linhas], ['OS-5', 'OS-4'])
        self.assertEqual(linhas[0]['versao'], None)
        self.assertEqual(linhas[1]['versao'], 2)

    def test_portal_summary_and_rows_preserve_previous_semantics(self):
        dados = ordens.resumo_portal(self.db)
        self.assertEqual(dados['total'], 1)
        self.assertEqual(dados['andamento'], 1)
        self.assertEqual(dados['concluidas'], 0)
        linhas = ordens.listar_solicitacoes_portal(self.db)
        self.assertEqual([x['numero_os'] for x in linhas], ['OS-7'])
        self.assertEqual(linhas[0]['cliente'], 'Cliente A')

    def test_relatorios_e_origem_portal(self):
        relatorios = ordens.listar_relatorios(self.db)
        self.assertEqual(len(relatorios), 6)
        self.assertEqual(relatorios[0]['numero_os'], 'OS-7')
        portal = ordens.listar_origem_portal(self.db)
        self.assertEqual([x['numero_os'] for x in portal], ['OS-7'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
