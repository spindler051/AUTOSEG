"""Characterization tests for the first application-service slice."""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import api_server
import atendimento_os
import banco
import cadastros_v9 as cad9
import catalogo_servicos
import composicao
import empresa_financeiro
import estoque_materiais
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
            'AUTOSEG_DEV': os.environ.pop('AUTOSEG_DEV', None),
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

    def test_dev_defaults_to_remote_server_without_local_fallback(self):
        os.environ['AUTOSEG_DEV'] = '1'
        carregado = load_settings(self.path)
        self.assertEqual(carregado.mode, ConnectionMode.REMOTE)
        self.assertEqual(carregado.server_url, 'http://127.0.0.1:8766')
        servico = build_service('/tmp/nao-usado.db', carregado)
        self.assertEqual(servico.mode, 'remote')

    def test_explicit_env_can_enable_web_access(self):
        os.environ['AUTOSEG_WEB_ACCESS'] = '1'
        carregado = load_settings(self.path)
        self.assertTrue(carregado.web_access)

    def test_remote_without_url_returns_unavailable_service(self):
        config = ConnectionSettings(mode=ConnectionMode.REMOTE, server_url='')
        servico = build_service('/tmp/nao-usado.db', config)
        self.assertEqual(servico.mode, 'remote')
        self.assertEqual(servico.health().status, 'unavailable')


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ('/api/v1/health','/api/v1/desktop/health'):
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

    def test_reads_degrade_but_writes_do_not_fall_back_to_local(self):
        servico = HttpService('http://127.0.0.1:1', timeout=0.2)
        self.assertEqual(servico.listar_clientes(''), [])
        self.assertIsNone(servico.obter_cliente(1))
        self.assertTrue(servico.health().status != 'ok')
        with self.assertRaises(ServicoIndisponivelError):
            servico.salvar_cliente(None, {'nome': 'X'})


class DesktopApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='desktop_api_')
        self.db = str(Path(self.tmp.name) / 'api.db')
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        fluxo_os.instalar(self.db)
        atendimento_os.instalar(self.db)
        cad9.instalar(self.db)
        estoque_materiais.instalar(self.db)
        catalogo_servicos.instalar(self.db)
        empresa_financeiro.instalar(self.db)
        composicao.instalar()
        composicao.instalar_banco(self.db)
        investidor = self.service_prestador()
        self.server = api_server.start(self.db, '127.0.0.1', 0)
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.service = HttpService(self.base)
        self.service.login(investidor['email'], investidor['senha'])

    def service_prestador(self):
        email = 'api-admin@example.invalid'
        senha = 'senha-api-123456'
        pid = ext.cadastrar(self.db, 'Admin API', email, senha)
        cad9.definir_admin(self.db, pid, True)
        return {'id': pid, 'email': email, 'senha': senha}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_health_and_client_roundtrip(self):
        info = self.service.health()
        self.assertEqual(info.status, 'ok')
        self.assertEqual(info.mode, 'remote')
        criado = self.service.salvar_cliente(
            None, {'tipo_pessoa': 'Jurídica', 'documento': '',
                   'nome': 'Condomínio API', 'status': 'Ativo'})
        self.assertGreater(criado.id, 0)
        lista = self.service.listar_clientes('API')
        self.assertEqual([item.nome for item in lista], ['Condomínio API'])
        self.assertEqual(self.service.contar_clientes_ativos(), 1)
        self.assertEqual(self.service.obter_cliente(criado.id).campos['nome'],
                         'Condomínio API')
        self.assertIsNone(self.service.obter_cliente(99999))

    def test_login_is_required_and_logout_revokes_session(self):
        sem_token = HttpService(self.base)
        with self.assertRaises(Exception):
            sem_token.listar_clientes()
        self.assertEqual(self.service.me()['email'],
                         'api-admin@example.invalid')
        self.service.logout()
        with self.assertRaises(Exception):
            self.service.me()
        self.service.login('api-admin@example.invalid', 'senha-api-123456')
        self.assertEqual(self.service.me()['email'],
                         'api-admin@example.invalid')

    def test_catalog_stock_company_and_composition_roundtrip(self):
        servico_id = self.service.catalogo_salvar({
            'nome': 'Serviço API', 'descricao': 'Teste',
            'preco_servico': '100', 'materiais': '',
            'relatorio_padrao': ''})
        self.assertEqual(self.service.catalogo_obter(servico_id)['nome'],
                         'Serviço API')
        produto_id = self.service.estoque_cadastrar({
            'nome': 'Material API', 'sku': 'API1', 'unidade': 'un',
            'custo': '5', 'venda': '10', 'minimo': '1'})
        self.assertEqual(self.service.estoque_obter(produto_id)['nome'],
                         'Material API')
        self.service.estoque_ajuste(produto_id, '+3', 'teste')
        self.assertEqual(len(self.service.estoque_movimentos(produto_id)), 1)
        investidor = self.service.criar_prestador({
            'nome': 'Investidor API', 'email': 'investidor@example.invalid',
            'senha': 'senha-ficticia-123'})
        self.service.empresa_registrar({
            'tipo': 'aporte', 'descricao': 'Aporte API', 'valor': '100',
            'data': '', 'prestador_id': investidor, 'os_id': None,
            'categoria': 'Capital', 'finalidade': 'Teste', 'observacao': ''})
        self.assertEqual(self.service.empresa_resumo()['aportes_centavos'],
                         10000)
        self.assertIn('componentes', self.service.composicao_config())

    def test_provider_and_os_actions_roundtrip(self):
        prestador = self.service.criar_prestador({
            'nome': 'Técnico API', 'email': 'tecnico-api@example.invalid',
            'senha': 'senha-ficticia-12345', 'telefone': '',
            'documento': '', 'especialidade': 'Teste'})
        self.assertGreater(prestador, 0)
        self.assertIn('Técnico API',
                      [p.nome for p in self.service.listar_prestadores()])
        self.service.definir_admin(prestador, True)
        self.assertTrue(self.service.prestador_admin(prestador))
        cliente = self.service.salvar_cliente(
            None, {'tipo_pessoa': 'Jurídica', 'documento': '',
                   'nome': 'Condomínio Ações', 'status': 'Ativo'})
        from application.contracts import OSInput
        resultado = self.service.salvar_os(OSInput(
            os_id=None, cliente_id=cliente.id, tecnico='',
            descricao='Ações via API', valor_mao_obra=0,
            valor_materiais=0, custo_materiais=0, valor_total=0,
            forma_pagamento='PIX', urgencia='Normal', observacoes='',
            texto_adicional='', dados_incompletos=0, tempo_horas=0,
            composicao_json='', base_percentuais='total', materiais=(),
            acao='', relato='', motivo='', imagens=()))
        self.assertTrue(self.service.atribuir_os(resultado.os_id, prestador))
        self.service.iniciar_os(resultado.os_id)
        contexto = self.service.contexto_atribuicao(resultado.os_id)
        self.assertEqual(contexto['atual_id'], prestador)
        self.assertEqual(
            self.service.obter_cliente_ativo(cliente.id).nome,
            'Condomínio Ações')
        self.service.desativar_cliente(cliente.id)
        self.assertIsNone(self.service.obter_cliente_ativo(cliente.id))

    def test_os_create_and_context(self):
        cliente = self.service.salvar_cliente(
            None, {'tipo_pessoa': 'Jurídica', 'documento': '',
                   'nome': 'Condomínio OS', 'status': 'Ativo'})
        from application.contracts import OSInput
        entrada = OSInput(
            os_id=None, cliente_id=cliente.id, tecnico='',
            descricao='Teste via API', valor_mao_obra=0,
            valor_materiais=0, custo_materiais=0, valor_total=0,
            forma_pagamento='PIX', urgencia='Normal', observacoes='',
            texto_adicional='', dados_incompletos=0, tempo_horas=0,
            composicao_json='', base_percentuais='total', materiais=(),
            acao='', relato='', motivo='', imagens=())
        resultado = self.service.salvar_os(entrada)
        self.assertEqual(resultado.os_id, 1)
        self.assertEqual(len(self.service.listar_os_ativas()), 1)
        contexto = self.service.contexto_os(resultado.os_id)
        self.assertEqual(contexto['dados']['descricao'], 'Teste via API')
        self.assertEqual(self.service.resumo_inicio().os_abertas, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
