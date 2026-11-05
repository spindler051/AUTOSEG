"""Read-only finance API: auth, isolation, cents, pagination and repasses."""
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import api_financeiro as api
import fluxo_os
import prestadores_ext as ext
import produtividade_os as prod
from banco import criar_banco
from portal_prestador import PortalPrestador


def get(base, path, token=None, method='GET', headers=None):
    pedido = urllib.request.Request(base + path, method=method)
    if token:
        pedido.add_header('Authorization', 'Bearer ' + token)
    for chave, valor in (headers or {}).items():
        pedido.add_header(chave, valor)
    try:
        with urllib.request.urlopen(pedido, timeout=15) as resposta:
            return resposta.status, dict(resposta.headers), resposta.read()
    except urllib.error.HTTPError as erro:
        return erro.code, dict(erro.headers), erro.read()


class ApiFinanceiroTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_api_')
        self.db = str(Path(self.tmp.name) / 'teste.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        fluxo_os.instalar(self.db)
        prod.instalar(self.db)
        api.instalar(self.db)
        self.a = ext.cadastrar(
            self.db, 'Técnico A', 'a@example.org', 'senha-segura-api-1')
        self.b = ext.cadastrar(
            self.db, 'Técnico B', 'b@example.org', 'senha-segura-api-2')
        with ext.db(self.db) as c:
            cliente = c.execute(
                "INSERT INTO clientes(nome,status,criado_em) VALUES(?,?,?)",
                ('Cliente API', 'Ativo', ext.agora())).lastrowid
            self.os_id = c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                "data_abertura,criado_em) VALUES(?,?,?,?,?,?)",
                ('OS-API-1', cliente, 'Concluída', 1000.0,
                 '2026-11-01', ext.agora())).lastrowid
            self.cliente_id = cliente
            c.execute(
                "INSERT INTO os_encerramentos(os_id,situacao,ator,prestador_id,encerrado_em) "
                "VALUES(?,?,?,?,?)",
                (self.os_id, 'Concluída', 'Teste', self.a, '2026-11-01'))
            self.financeiro_id = c.execute(
                "INSERT INTO financeiro(os_id,cliente_id,descricao,valor,status,"
                "data_lancamento,forma_pagamento) VALUES(?,?,?,?,?,?,?)",
                (self.os_id, cliente, 'OS-API-1', 1000.0,
                 'Aguardando pagamento', '2026-11-01', 'PIX')).lastrowid
            c.execute(
                "INSERT INTO produtividade_rateios"
                "(os_id,tecnico_id,valor_centavos,definidor_id,registrado_em) "
                "VALUES(?,?,?,?,?)",
                (self.os_id, self.b, 30000, self.a, '2026-11-01'))
            c.execute(
                "INSERT INTO produtividade_repasses"
                "(os_id,tecnico_id,pago_centavos,enviado_centavos,atualizado_em) "
                "VALUES(?,?,0,0,?)",
                (self.os_id, self.b, '2026-11-01'))
        _, self.token_a = api.criar_token(self.db, self.a, 'Sistema A')
        _, self.token_b = api.criar_token(self.db, self.b, 'Sistema B')
        self.servidor = PortalPrestador(self.db, host='127.0.0.1', porta=0)
        self.servidor.iniciar()
        self.base = f'http://127.0.0.1:{self.servidor.porta}'

    def tearDown(self):
        self.servidor.parar()
        self.tmp.cleanup()

    def _json(self, path, token=None, method='GET', headers=None):
        status, cabecalhos, corpo = get(
            self.base, path, token, method=method, headers=headers)
        try:
            dados = json.loads(corpo)
        except ValueError:
            dados = None
        return status, cabecalhos, dados

    def test_health_and_openapi_are_public(self):
        status, _, dados = self._json('/api/v1/health')
        self.assertEqual(status, 200)
        self.assertEqual(dados['data']['status'], 'ok')
        status, _, spec = self._json('/api/v1/openapi.json')
        self.assertEqual(status, 200)
        self.assertEqual(spec['openapi'], '3.1.0')
        self.assertIn('/financeiro/lancamentos', spec['paths'])
        self.assertIn('BearerAuth', spec['components']['securitySchemes'])

    def test_requires_bearer_token_and_revocation(self):
        status, cabecalhos, dados = self._json('/api/v1/me')
        self.assertEqual(status, 401)
        self.assertIn('WWW-Authenticate', cabecalhos)
        self.assertEqual(dados['error']['code'], 'unauthorized')
        status, _, _ = self._json('/api/v1/me', 'token-invalido')
        self.assertEqual(status, 401)
        status, _, dados = self._json('/api/v1/me', self.token_a)
        self.assertEqual(status, 200)
        self.assertEqual(dados['data']['id'], self.a)
        self.assertEqual(dados['data']['nome'], 'Técnico A')
        with ext.db(self.db) as c:
            linha = c.execute(
                'SELECT token_hash FROM api_tokens WHERE prestador_id=?',
                (self.a,)).fetchone()
        self.assertNotEqual(linha['token_hash'], self.token_a)
        api.revogar_token(self.db, 1)
        status, _, _ = self._json('/api/v1/me', self.token_a)
        self.assertEqual(status, 401)

    def test_provider_isolation_and_own_lancamentos(self):
        status, _, dados = self._json(
            '/api/v1/financeiro/lancamentos', self.token_a)
        self.assertEqual(status, 200)
        self.assertEqual(len(dados['data']), 1)
        item = dados['data'][0]
        self.assertEqual(item['id'], self.financeiro_id)
        self.assertEqual(item['valor_centavos'], 100000)
        self.assertEqual(item['rateios_centavos'], 30000)
        self.assertEqual(item['minha_parcela_centavos'], 70000)
        self.assertEqual(item['os']['numero'], 'OS-API-1')
        status, _, dados = self._json(
            '/api/v1/financeiro/lancamentos', self.token_b)
        self.assertEqual(status, 200)
        self.assertEqual(dados['data'], [])

    def test_rateios_repasses_and_receiver_confirmation(self):
        status, _, dados = self._json('/api/v1/financeiro/rateios', self.token_b)
        self.assertEqual(status, 200)
        self.assertEqual(len(dados['data']), 1)
        item = dados['data'][0]
        self.assertEqual(item['valor_centavos'], 30000)
        self.assertEqual(item['pago_centavos'], 0)
        self.assertEqual(item['status'], 'a_receber')
        status, _, dados = self._json('/api/v1/financeiro/repasses', self.token_a)
        self.assertEqual(status, 200)
        self.assertEqual(dados['data'][0]['a_enviar_centavos'], 30000)

        prod.confirmar_repasse(self.db, self.os_id, self.a, self.b, None)
        _, _, dados = self._json('/api/v1/financeiro/rateios', self.token_b)
        self.assertEqual(dados['data'][0]['enviado_centavos'], 30000)
        self.assertEqual(dados['data'][0]['pago_centavos'], 0)
        self.assertEqual(dados['data'][0]['status'], 'aguardando_confirmacao')
        _, _, dados = self._json('/api/v1/financeiro/repasses', self.token_a)
        self.assertEqual(dados['data'][0]['a_enviar_centavos'], 0)
        self.assertEqual(dados['data'][0]['status'], 'aguardando_confirmacao')
        _, _, resumo_b = self._json('/api/v1/financeiro/resumo', self.token_b)
        self.assertEqual(resumo_b['data']['repasses_recebidos_centavos'], 0)
        self.assertEqual(resumo_b['data']['repasses_a_receber_centavos'], 30000)

        prod.confirmar_recebimento_repasse(self.db, self.os_id, self.b, None)
        _, _, dados = self._json('/api/v1/financeiro/rateios', self.token_b)
        self.assertEqual(dados['data'][0]['pago_centavos'], 30000)
        self.assertEqual(dados['data'][0]['restante_centavos'], 0)
        self.assertEqual(dados['data'][0]['status'], 'recebido')
        _, _, resumo_b = self._json('/api/v1/financeiro/resumo', self.token_b)
        self.assertEqual(resumo_b['data']['repasses_recebidos_centavos'], 30000)

    def test_resumo_values(self):
        status, _, dados = self._json('/api/v1/financeiro/resumo', self.token_a)
        self.assertEqual(status, 200)
        resumo = dados['data']
        self.assertEqual(resumo['moeda'], 'BRL')
        self.assertEqual(resumo['os_a_receber_centavos'], 70000)
        self.assertEqual(resumo['os_recebido_centavos'], 0)
        self.assertEqual(resumo['repasses_a_pagar_centavos'], 30000)
        self.assertEqual(resumo['total_a_receber_centavos'], 70000)
        status, _, dados = self._json('/api/v1/financeiro/resumo', self.token_b)
        resumo = dados['data']
        self.assertEqual(resumo['repasses_a_receber_centavos'], 30000)
        self.assertEqual(resumo['total_recebido_centavos'], 0)

    def test_cursor_pagination_has_no_duplicates(self):
        with ext.db(self.db) as c:
            for indice in range(2, 5):
                oid = c.execute(
                    "INSERT INTO ordens_servico(numero_os,cliente_id,status,valor_total,"
                    "data_abertura,criado_em) VALUES(?,?,?,?,?,?)",
                    (f'OS-API-{indice}', self.cliente_id, 'Concluída', 100.0,
                     f'2026-11-0{indice}', ext.agora())).lastrowid
                c.execute(
                    "INSERT INTO os_encerramentos(os_id,situacao,ator,prestador_id,"
                    "encerrado_em) VALUES(?,?,?,?,?)",
                    (oid, 'Concluída', 'Teste', self.a, '2026-11-01'))
                c.execute(
                    "INSERT INTO financeiro(os_id,cliente_id,valor,status,data_lancamento) "
                    "VALUES(?,?,?,?,?)",
                    (oid, self.cliente_id, 100.0, 'Recebido', f'2026-11-0{indice}'))
        vistos = []
        cursor = None
        for _ in range(5):
            caminho = '/api/v1/financeiro/lancamentos?limit=1'
            if cursor:
                caminho += '&cursor=' + cursor
            status, _, dados = self._json(caminho, self.token_a)
            self.assertEqual(status, 200)
            vistos.extend(x['id'] for x in dados['data'])
            cursor = dados['meta']['next_cursor']
            if not cursor:
                break
        self.assertEqual(len(vistos), len(set(vistos)))
        self.assertEqual(len(vistos), 4)
        status, _, dados = self._json(
            '/api/v1/financeiro/lancamentos?status=Recebido', self.token_a)
        self.assertEqual(status, 200)
        self.assertEqual(len(dados['data']), 3)

    def test_inactive_provider_and_read_only_post(self):
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET ativo=0 WHERE id=?', (self.b,))
        status, _, _ = self._json('/api/v1/me', self.token_b)
        self.assertEqual(status, 401)
        status, _, dados = self._json('/api/v1/me', self.token_a, method='POST')
        self.assertEqual(status, 405)
        self.assertEqual(dados['error']['code'], 'method_not_allowed')

    def test_cors_preflight_only_for_configured_origin(self):
        with patch.dict(os.environ, {'AUTOSEG_API_ORIGINS': 'https://app.example'}):
            status, cabecalhos, _ = get(
                self.base, '/api/v1/me', method='OPTIONS',
                headers={'Origin': 'https://app.example'})
            self.assertEqual(status, 204)
            self.assertEqual(cabecalhos.get('Access-Control-Allow-Origin'),
                             'https://app.example')
            status, cabecalhos, _ = get(
                self.base, '/api/v1/me', method='OPTIONS',
                headers={'Origin': 'https://evil.example'})
            self.assertEqual(status, 204)
            self.assertNotIn('Access-Control-Allow-Origin', cabecalhos)


if __name__ == '__main__':
    unittest.main(verbosity=2)
