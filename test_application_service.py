"""Characterization tests for the first application-service slice."""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import banco
import cadastros_v9 as cad9
import fluxo_os
import prestadores_ext as ext
from application.contracts import ServicoIndisponivelError, ValidacaoError
from application.http_service import HttpService
from application.local_service import LocalService
from application.connection import (
    ConnectionMode,
    ConnectionSettings,
    build_service,
    load_settings,
    save_settings,
)


class LocalServiceClientTest(unittest.TestCase):
    def setUp(self):
        os.environ.pop('AUTOSEG_BASE', None)
        self.tmp = tempfile.TemporaryDirectory(prefix='app_service_')
        self.db = Path(self.tmp.name) / 'teste.db'
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        cad9.instalar(self.db)
        self.service = LocalService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def criar(self, **dados):
        base = {
            'tipo_pessoa': 'Jurídica',
            'documento': '',
            'nome': 'Condomínio Alfa',
            'status': 'Ativo',
        }
        base.update(dados)
        return self.service.salvar_cliente(None, base)

    def test_health_reports_local_mode(self):
        info = self.service.health()
        self.assertEqual(info.status, 'ok')
        self.assertEqual(info.mode, 'local')
        self.assertEqual(info.database, str(self.db))
        self.assertIn('clientes.listar', info.capabilities)

    def test_create_list_and_get_client(self):
        criado = self.criar(nome='Alfa', cidade='Porto Alegre')
        self.assertGreater(criado.id, 0)
        self.assertEqual(criado.campos['nome'], 'Alfa')
        self.assertFalse(criado.incompleto)

        lista = self.service.listar_clientes('porto')
        self.assertEqual([item.nome for item in lista], ['Alfa'])
        obtido = self.service.obter_cliente(criado.id)
        self.assertIsNotNone(obtido)
        self.assertEqual(obtido.campos['cidade'], 'Porto Alegre')

    def test_save_increments_version_and_keeps_contract_error(self):
        criado = self.criar()
        atualizado = self.service.salvar_cliente(
            criado.id,
            {'tipo_pessoa': 'Jurídica', 'documento': '',
             'nome': 'Condomínio Beta', 'status': 'Ativo'})
        self.assertEqual(atualizado.versao, 2)
        self.assertEqual(atualizado.campos['nome'], 'Condomínio Beta')

        with self.assertRaises(ValidacaoError) as contexto:
            self.criar(tipo_pessoa='Física', documento='123')
        self.assertEqual(contexto.exception.titulo, 'Documento inválido')

    def test_missing_client_returns_none(self):
        self.assertIsNone(self.service.obter_cliente(99999))

    def test_dashboard_summary_uses_service(self):
        self.criar(nome='Alfa')
        with sqlite3.connect(self.db) as conexao:
            conexao.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                "data_abertura,origem,arquivada) VALUES('OS-1',1,'Aberta',100,'2026-11-01','App',0)")
            conexao.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                "data_abertura,origem,arquivada) VALUES('OS-2',1,'Concluída',200,'2026-11-02','App',0)")
            conexao.execute(
                "INSERT INTO financeiro(os_id,cliente_id,valor,status) "
                "VALUES(2,1,200,'Recebido')")
            conexao.execute(
                "INSERT INTO financeiro(os_id,cliente_id,valor,status) "
                "VALUES(1,1,100,'Aguardando pagamento')")
        resumo = self.service.resumo_inicio()
        self.assertEqual(resumo.clientes_ativos, 1)
        self.assertEqual(resumo.os_abertas, 1)
        self.assertEqual(resumo.financeiro_recebido, 200.0)
        self.assertEqual(resumo.financeiro_a_receber, 100.0)


    def test_active_os_list_uses_contract_dto(self):
        self.criar(nome='Alfa')
        with sqlite3.connect(self.db) as conexao:
            conexao.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                "descricao,forma_pagamento,urgencia,origem,arquivada) "
                "VALUES('OS-A1',1,'Aberta',150,'Reparo','PIX','Normal','App',0)")
            conexao.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                "descricao,forma_pagamento,urgencia,origem,arquivada) "
                "VALUES('OS-A2',1,'Concluída',250,'Encerrada','PIX','Normal','App',0)")
        linhas = self.service.listar_os_ativas()
        self.assertEqual([item.numero_os for item in linhas], ['OS-A1'])
        self.assertEqual(linhas[0].cliente, 'Alfa')
        self.assertEqual(linhas[0].responsavel, 'Não atribuído')
        self.assertFalse(linhas[0].incompleto)
        self.assertEqual(
            [item.numero_os for item in self.service.listar_os_ativas('A1')],
            ['OS-A1'])

    def test_history_slice_uses_contract_dtos(self):
        fluxo_os.instalar(self.db)
        self.criar(nome='Alfa')
        with sqlite3.connect(self.db) as conexao:
            for numero, status, valor in (('OS-H1', 'Concluída', 300),
                                          ('OS-H2', 'Aberta', 100)):
                conexao.execute(
                    "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                    "data_abertura,origem,arquivada) VALUES(?,1,?,?, '2026-11-06','App',0)",
                    (numero, status, valor))
            concluida = conexao.execute(
                "SELECT id FROM ordens_servico WHERE numero_os='OS-H1'").fetchone()[0]
            conexao.execute(
                "INSERT INTO os_documentos(os_id,tipo,versao,caminho,sha256,publicado_em) "
                "VALUES(?,'relatorio_pdf',1,'/tmp/x.pdf','abc','2026-11-06')",
                (concluida,))
        resumo = self.service.resumo_historico()
        self.assertEqual((resumo.total, resumo.abertas, resumo.concluidas), (2, 1, 1))
        self.assertEqual(resumo.valor_concluido, 300.0)
        linhas = self.service.listar_historico('H1')
        self.assertEqual(len(linhas), 1)
        self.assertTrue(linhas[0].pdf_disponivel)

    def test_finance_slice_uses_contract_dtos(self):
        self.criar(nome='Alfa')
        with sqlite3.connect(self.db) as conexao:
            for numero, status, valor in (('OS-F1', 'Aguardando pagamento', 100),
                                          ('OS-F2', 'Recebido', 200)):
                os_id = conexao.execute(
                    "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                    "data_abertura,origem,arquivada) VALUES(?,1,'Concluída',?, '2026-11-06','App',0)",
                    (numero, valor)).lastrowid
                conexao.execute(
                    "INSERT INTO financeiro(os_id,cliente_id,valor,status,forma_pagamento) "
                    "VALUES(?,1,?,?,'PIX')", (os_id, valor, status))
        resumo = self.service.resumo_financeiro()
        self.assertEqual(resumo.a_receber, 100.0)
        self.assertEqual(resumo.recebido, 200.0)
        linhas = self.service.listar_financeiro('F1')
        self.assertEqual([item.numero_os for item in linhas], ['OS-F1'])
        self.service.marcar_recebido(linhas[0].id)
        self.assertEqual(self.service.resumo_financeiro().a_receber, 0.0)
        self.assertEqual(self.service.resumo_financeiro().recebido, 300.0)

    def test_portal_summary_and_rows_use_contract_dtos(self):
        self.criar(nome='Alfa')
        with sqlite3.connect(self.db) as conexao:
            conexao.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                "data_abertura,origem,urgencia,arquivada) "
                "VALUES('OS-P1',1,'Pendente',50,'2026-11-06','Portal','Alta',0)")
        resumo = self.service.resumo_portal()
        self.assertEqual((resumo.total, resumo.andamento, resumo.concluidas),
                         (1, 1, 0))
        linhas = self.service.listar_solicitacoes_portal()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0].numero_os, 'OS-P1')
        self.assertEqual(linhas[0].cliente, 'Alfa')
        self.assertEqual(linhas[0].urgencia, 'Alta')


class ConnectionSettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='connection_')
        self.path = Path(self.tmp.name) / 'connection.json'
        self.env = {
            'AUTOSEG_CONNECTION_MODE': os.environ.pop('AUTOSEG_CONNECTION_MODE', None),
            'AUTOSEG_SERVER_URL': os.environ.pop('AUTOSEG_SERVER_URL', None),
            'AUTOSEG_CONNECTION_FILE': os.environ.pop('AUTOSEG_CONNECTION_FILE', None),
            'AUTOSEG_WEB_ACCESS': os.environ.pop('AUTOSEG_WEB_ACCESS', None),
        }

    def tearDown(self):
        for chave, valor in self.env.items():
            if valor is None:
                os.environ.pop(chave, None)
            else:
                os.environ[chave] = valor
        self.tmp.cleanup()

    def test_save_and_load_remote_settings(self):
        original = ConnectionSettings(
            mode=ConnectionMode.REMOTE,
            server_url='https://example.invalid',
            web_access=False,
            last_user='teste')
        save_settings(original, self.path)
        carregado = load_settings(self.path)
        self.assertEqual(carregado.mode, ConnectionMode.REMOTE)
        self.assertEqual(carregado.server_url, 'https://example.invalid')
        self.assertFalse(carregado.web_access)
        self.assertEqual(carregado.last_user, 'teste')

    def test_local_is_default_and_factory_returns_local_service(self):
        carregado = load_settings(self.path)
        self.assertEqual(carregado.mode, ConnectionMode.LOCAL)
        self.assertFalse(carregado.web_access)
        servico = build_service('/tmp/nao-usado.db', carregado)
        self.assertEqual(servico.mode, 'local')

    def test_explicit_env_can_enable_web_access(self):
        os.environ['AUTOSEG_WEB_ACCESS'] = '1'
        carregado = load_settings(self.path)
        self.assertTrue(carregado.web_access)

    def test_remote_without_url_fails_instead_of_falling_back(self):
        config = ConnectionSettings(mode=ConnectionMode.REMOTE, server_url='')
        with self.assertRaises(ServicoIndisponivelError):
            build_service('/tmp/nao-usado.db', config)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/api/v1/health':
            self.send_response(404)
            self.end_headers()
            return
        corpo = json.dumps({'data': {'status': 'ok', 'version': '9.9.9'}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_args):
        return


class HttpServiceTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), _HealthHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_health_uses_remote_contract(self):
        info = HttpService(self.base).health()
        self.assertEqual(info.status, 'ok')
        self.assertEqual(info.mode, 'remote')
        self.assertEqual(info.version, '9.9.9')

    def test_client_slice_is_not_silently_local(self):
        servico = HttpService(self.base)
        with self.assertRaises(ServicoIndisponivelError):
            servico.listar_clientes('')
        with self.assertRaises(ServicoIndisponivelError):
            servico.salvar_cliente(None, {'nome': 'X'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
