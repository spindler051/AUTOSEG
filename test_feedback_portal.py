"""Feedback do Portal do Prestador: UI, persistência, IA mockada e triagem."""
import base64
import http.cookiejar
import json
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

import cadastros_v9 as cad
import feedback_ai
import feedback_portal as feedback
import portal_prestador
import prestadores_ext as ext
from banco import criar_banco
from portal_prestador import PortalPrestador


def request(opener, url, data=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    pedido = urllib.request.Request(url, body)
    try:
        with opener.open(pedido, timeout=30) as resposta:
            return resposta.status, resposta.headers.get('Content-Type', ''), resposta.read()
    except urllib.error.HTTPError as erro:
        return erro.code, erro.headers.get('Content-Type', ''), erro.read()


def csrf(html):
    achado = re.search(rb'name="csrf" value="([^"]+)"', html)
    assert achado, 'CSRF não encontrado'
    return achado.group(1).decode()


class FeedbackPortalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_feedback_')
        self.db = str(Path(self.tmp.name) / 'teste.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        self.pid = ext.cadastrar(self.db, 'Prestador Feedback',
                                 'feedback@example.org', 'senha-bem-segura-2026')
        self.servidor = PortalPrestador(self.db, host='127.0.0.1', porta=0)
        self.servidor.iniciar()
        self.base = f'http://127.0.0.1:{self.servidor.porta}'
        self.browser = self._browser()
        status, _, html = request(self.browser, self.base + '/login', {
            'email': 'feedback@example.org',
            'senha': 'senha-bem-segura-2026',
        })
        self.assertEqual(status, 200)
        self.assertIn(b'Painel principal', html)
        self.csrf = csrf(html)

    def tearDown(self):
        self.servidor.parar()
        self.tmp.cleanup()

    def _browser(self):
        return urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _enviar(self, mensagem, responder_ia=False, pagina='/clientes'):
        return request(self.browser, self.base + '/feedback', {
            'csrf': self.csrf,
            'mensagem': mensagem,
            'pagina': pagina,
            'responder_ia': '1' if responder_ia else '',
        })

    def _feedback(self, fid):
        return feedback.obter(self.db, fid)

    def test_botao_aparece_no_prestador_e_nao_no_cliente(self):
        _, _, html = request(self.browser, self.base + '/clientes')
        self.assertIn(b'id="abrir-feedback"', html)
        self.assertIn(b'id="dialogo-feedback"', html)
        self.assertIn(b'D\xc3\xaa um feedback', html)
        self.assertIn(b'P\xc3\xa1gina atual', html)
        self.assertIn(b'name="pagina"', html)
        self.assertIn(b'name="responder_ia"', html)
        self.assertIn(b'/static/portal.js', html)
        # O portal do cliente usa o mesmo layout com cliente=True; não deve
        # receber o canal de feedback do prestador.
        cliente = portal_prestador.layout('Teste', 'corpo', None, cliente=True)
        self.assertNotIn('abrir-feedback', cliente)
        self.assertNotIn('dialogo-feedback', cliente)

    def test_feedback_sem_ia_nao_cria_os_nem_financeiro(self):
        status, _, html = self._enviar('O botão de iniciar OS não apareceu para mim.')
        self.assertEqual(status, 200)
        texto = html.decode()
        self.assertIn('Feedback FB-', texto)
        self.assertIn('O botão de iniciar OS não apareceu', texto)
        self.assertIn('Aguardando triagem', texto)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM portal_feedback').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ordens_servico').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM financeiro').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM portal_feedback_aberturas').fetchone()[0], 0)

    def test_ia_opcional_recebe_texto_anonimizado(self):
        mensagem = ('Meu nome é João Silva. CPF 123.456.789-01, e-mail joao@example.com. '
                    'Não encontrei onde alterar o preço do serviço.')
        analise = {
            'status': 'ok',
            'resposta': 'O preço é alterado em Serviços e valores. O relato será revisado.',
            'categoria': 'Dúvida',
            'urgencia': 'Baixa',
            'possivel_melhoria': 'Melhorar o texto de ajuda da tela de serviços.',
            'confianca': 0.82,
        }
        with patch.object(feedback, 'consultar_ia', return_value=analise) as ia:
            status, _, html = self._enviar(mensagem, responder_ia=True, pagina='/servicos')
        self.assertEqual(status, 200)
        texto = html.decode()
        self.assertIn('Resposta da IA', texto)
        self.assertIn('Serviços e valores', texto)
        ia.assert_called_once()
        enviado = ia.call_args.args[0]
        self.assertNotIn('123.456.789-01', enviado)
        self.assertNotIn('joao@example.com', enviado)
        self.assertIn('[CPF]', enviado)
        self.assertIn('[e-mail]', enviado)
        with ext.db(self.db) as c:
            linha = c.execute('SELECT * FROM portal_feedback').fetchone()
        self.assertEqual(linha['ia_status'], 'ok')
        self.assertEqual(linha['categoria'], 'Dúvida')
        self.assertEqual(linha['urgencia'], 'Baixa')
        self.assertIn('Serviços e valores', linha['resposta_ia'])
        self.assertEqual(linha['pagina'], '/servicos')

    def test_abertura_registra_contexto_e_sem_query(self):
        status, _, _ = request(self.browser, self.base + '/feedback/aberto', {
            'csrf': self.csrf,
            'pagina': '/os/25?cliente=segredo',
        })
        self.assertEqual(status, 204)
        with ext.db(self.db) as c:
            abertura = c.execute('SELECT * FROM portal_feedback_aberturas').fetchone()
        self.assertIsNotNone(abertura)
        self.assertEqual(abertura['prestador_id'], self.pid)
        self.assertEqual(abertura['pagina'], '/os/25')
        self.assertTrue(abertura['sessao_hash'])
        self.assertTrue(abertura['navegador'])

    def test_triagem_admin_e_pendencias_anonimizadas(self):
        cad.definir_admin(self.db, self.pid, True)
        status, _, html = self._enviar('CPF 123.456.789-01: o orçamento não aceita material.')
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            fid = c.execute('SELECT id FROM portal_feedback').fetchone()[0]
        status, _, pagina = request(self.browser, self.base + '/feedback/recebidos')
        self.assertEqual(status, 200)
        self.assertIn(b'Aberturas recentes', pagina)
        self.assertIn(f'FB-{fid:04d}'.encode(), pagina)
        status, _, detalhe = request(
            self.browser, self.base + f'/feedback/{fid}/triagem', {
                'csrf': self.csrf,
                'status_dev': 'Pendente na DEV',
                'nota_dev': 'Registrar correção na DEV.',
            })
        self.assertEqual(status, 200)
        self.assertIn('Pendente na DEV', detalhe.decode())
        status, tipo, markdown = request(self.browser, self.base + '/feedback/pendencias.md')
        self.assertEqual(status, 200)
        self.assertIn('text/markdown', tipo)
        texto = markdown.decode()
        self.assertIn('Pendente na DEV', texto)
        self.assertIn('[CPF]', texto)
        self.assertNotIn('123.456.789-01', texto)
        self.assertNotIn('Prestador Feedback', texto)

    def test_exportacao_admin_e_restricao_de_acesso(self):
        cad.definir_admin(self.db, self.pid, True)
        self._enviar('Feedback para exportação.')
        status, tipo, corpo = request(self.browser, self.base + '/feedback/dados/exportar.json')
        self.assertEqual(status, 200)
        self.assertIn('application/json', tipo)
        dados = json.loads(corpo)
        self.assertEqual(len(dados['feedbacks']), 1)
        self.assertTrue(dados['feedbacks'][0]['mensagem'])
        outro_pid = ext.cadastrar(self.db, 'Outro Prestador', 'outro@example.org',
                                  'outra-senha-segura-2026')
        outro = self._browser()
        status, _, _ = request(outro, self.base + '/login', {
            'email': 'outro@example.org', 'senha': 'outra-senha-segura-2026'})
        self.assertEqual(status, 200)
        status, _, _ = request(outro, self.base + '/feedback/recebidos')
        self.assertEqual(status, 403)
        self.assertNotEqual(outro_pid, self.pid)

    def test_telemetria_local_opcional(self):
        with patch.dict(os.environ, {'AUTOSEG_TELEMETRY': 'local'}, clear=False):
            status, _, _ = self._enviar('Quero registrar um evento de telemetria.')
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            eventos = [x['event'] for x in c.execute(
                'SELECT event FROM telemetria_eventos ORDER BY id')]
        self.assertIn('feedback_submit', eventos)

    def test_ia_sem_chave_preserva_feedback(self):
        with patch.dict(os.environ, {
            'AUTOSEG_FEEDBACK_AI_PROVIDER': 'deepseek',
            'DEEPSEEK_API_KEY': '',
            'AUTOSEG_FEEDBACK_AI': '1',
        }):
            status, _, html = self._enviar(
                'Não encontrei a ajuda da tela de orçamento.', responder_ia=True)
        self.assertEqual(status, 200)
        self.assertIn('Resposta automática indisponível', html.decode())
        with ext.db(self.db) as c:
            linha = c.execute('SELECT * FROM portal_feedback').fetchone()
        self.assertEqual(linha['ia_status'], 'sem_chave')
        self.assertEqual(linha['resposta_ia'], '')

    def test_opencode_without_session_keeps_feedback(self):
        with patch.dict(os.environ, {
            'AUTOSEG_FEEDBACK_AI_PROVIDER': 'opencode',
            'AUTOSEG_FEEDBACK_OPENCODE_SESSION': '',
            'AUTOSEG_FEEDBACK_AI': '1',
        }):
            status, _, html = self._enviar(
                'A resposta automática não está configurada.', responder_ia=True)
        self.assertEqual(status, 200)
        self.assertIn('Resposta automática indisponível', html.decode())
        with ext.db(self.db) as c:
            linha = c.execute('SELECT * FROM portal_feedback').fetchone()
        self.assertEqual(linha['ia_status'], 'sem_configuracao')
        self.assertEqual(linha['resposta_ia'], '')

    def test_otlp_nao_finge_exportar_nem_grava_local(self):
        with patch.dict(os.environ, {
            'AUTOSEG_TELEMETRY': 'otlp',
            'AUTOSEG_TELEMETRY_OTLP_ENDPOINT': 'https://collector.example/v1',
        }):
            status, _, _ = self._enviar('Evento que não deve ser gravado localmente.')
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            total = c.execute('SELECT COUNT(*) FROM telemetria_eventos').fetchone()[0]
        self.assertEqual(total, 0)

    def test_mensagem_curta_e_rejeitada(self):
        status, _, html = self._enviar('oi')
        self.assertEqual(status, 400)
        self.assertIn('pelo menos', html.decode())
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM portal_feedback').fetchone()[0], 0)


class AnonimizacaoTest(unittest.TestCase):
    def test_remove_documentos_contatos_e_endereco(self):
        original = ('João Silva, CPF 123.456.789-01, CNPJ 12.345.678/0001-95, '
                    'joao@example.com, (51) 99999-1234, CEP 90000-000, '
                    'Rua das Flores 123, apartamento 203.')
        limpo = feedback.anonimizar(original)
        for proibido in ('123.456.789-01', '12.345.678/0001-95',
                         'joao@example.com', '99999-1234', '90000-000', 'Rua das Flores'):
            self.assertNotIn(proibido, limpo)
        self.assertIn('[CPF]', limpo)
        self.assertIn('[CNPJ]', limpo)
        self.assertIn('[e-mail]', limpo)
        self.assertIn('[telefone]', limpo)
        self.assertIn('[endereço]', limpo)


class ContextoRedeTest(unittest.TestCase):
    def test_ip_do_tunel_so_e_usado_em_conexao_local(self):
        cf = {'CF-Connecting-IP': '203.0.113.45'}
        self.assertEqual(feedback.ip_requisicao('127.0.0.1', cf), '203.0.113.45')
        self.assertEqual(feedback.ip_requisicao('198.51.100.7', cf), '198.51.100.7')
        forwarded = {'X-Forwarded-For': '2001:db8::1, 10.0.0.1'}
        self.assertEqual(feedback.ip_requisicao('::1', forwarded), '2001:db8::1')
        self.assertEqual(feedback.ip_requisicao('127.0.0.1', {}), '127.0.0.1')


class ProvedorIATest(unittest.TestCase):
    def test_opencode_uses_transient_endpoint_and_basic_auth(self):
        captured = {}

        def fake_post(url, headers, body, timeout):
            captured.update(
                url=url, headers=headers, body=body, timeout=timeout)
            return {'data': {'text': json.dumps({
                'resposta': 'O preço fica em Serviços e valores.',
                'categoria': 'Dúvida',
                'urgencia': 'Baixa',
                'possivel_melhoria': None,
                'confianca': 0.75,
            }, ensure_ascii=False)}}

        env = {
            'AUTOSEG_FEEDBACK_AI': '1',
            'AUTOSEG_FEEDBACK_AI_PROVIDER': 'opencode',
            'AUTOSEG_FEEDBACK_OPENCODE_URL': 'http://127.0.0.1:9999',
            'AUTOSEG_FEEDBACK_OPENCODE_SESSION': 'ses_teste',
            'AUTOSEG_FEEDBACK_OPENCODE_PASSWORD': 'segredo-local',
            'AUTOSEG_FEEDBACK_OPENCODE_TIMEOUT': '10',
        }
        with patch.dict(os.environ, env, clear=False), \
                patch.object(feedback_ai, '_post_json', side_effect=fake_post):
            resultado = feedback_ai.consult(
                'Não encontrei o preço [CPF].', 'PROMPT SISTEMA')

        self.assertEqual(resultado['status'], 'ok')
        self.assertEqual(resultado['categoria'], 'Dúvida')
        self.assertEqual(resultado['urgencia'], 'Baixa')
        self.assertEqual(resultado['possivel_melhoria'], '')
        self.assertEqual(
            captured['url'],
            'http://127.0.0.1:9999/api/session/ses_teste/generate')
        esperado = 'Basic ' + base64.b64encode(
            b'opencode:segredo-local').decode('ascii')
        self.assertEqual(captured['headers']['Authorization'], esperado)
        prompt = captured['body']['prompt']
        self.assertIn('PROMPT SISTEMA', prompt)
        self.assertIn('Não encontrei o preço [CPF].', prompt)
        self.assertEqual(captured['timeout'], 10.0)

    def test_opencode_plain_text_becomes_reply(self):
        with patch.dict(os.environ, {
            'AUTOSEG_FEEDBACK_AI': '1',
            'AUTOSEG_FEEDBACK_AI_PROVIDER': 'opencode',
            'AUTOSEG_FEEDBACK_OPENCODE_SESSION': 'ses_teste',
            'AUTOSEG_FEEDBACK_OPENCODE_PASSWORD': 'segredo-local',
        }, clear=False), patch.object(
                feedback_ai, '_post_json',
                return_value={'data': {'text': 'A tela fica em Serviços e valores.'}}):
            resultado = feedback_ai.consult('texto', 'PROMPT')

        self.assertEqual(resultado['status'], 'ok')
        self.assertIn('Serviços e valores', resultado['resposta'])
        self.assertEqual(resultado['categoria'], 'Não classificada')

    def test_deepseek_remains_selectable_by_environment(self):
        captured = {}

        def fake_post(url, headers, body, timeout):
            captured.update(url=url, headers=headers, body=body, timeout=timeout)
            return {'choices': [{'message': {'content': json.dumps({
                'resposta': 'Resposta alternativa.',
                'categoria': 'Melhoria',
                'urgencia': 'Média',
                'possivel_melhoria': 'Ajustar o texto de ajuda.',
                'confianca': 0.9,
            })}}]}

        with patch.dict(os.environ, {
            'AUTOSEG_FEEDBACK_AI': '1',
            'AUTOSEG_FEEDBACK_AI_PROVIDER': 'deepseek',
            'DEEPSEEK_API_KEY': 'chave-teste',
            'DEEPSEEK_API_URL': 'https://exemplo.invalid/v1/chat/completions',
            'DEEPSEEK_MODEL': 'modelo-teste',
        }, clear=False), patch.object(
                feedback_ai, '_post_json', side_effect=fake_post):
            resultado = feedback_ai.consult('texto', 'PROMPT')

        self.assertEqual(resultado['status'], 'ok')
        self.assertEqual(captured['url'], 'https://exemplo.invalid/v1/chat/completions')
        self.assertEqual(captured['headers']['Authorization'], 'Bearer chave-teste')
        self.assertEqual(captured['body']['model'], 'modelo-teste')
        self.assertIn('PROMPT', captured['body']['messages'][0]['content'])

    def test_unknown_provider_keeps_feedback_record(self):
        with patch.dict(os.environ, {
            'AUTOSEG_FEEDBACK_AI': '1',
            'AUTOSEG_FEEDBACK_AI_PROVIDER': 'provedor-inexistente',
        }, clear=False):
            resultado = feedback_ai.consult('texto', 'PROMPT')
        self.assertEqual(resultado['status'], 'configuracao_invalida')
        self.assertEqual(resultado['resposta'], '')

    def test_disabled_ai_does_not_call_provider(self):
        with patch.dict(os.environ, {
            'AUTOSEG_FEEDBACK_AI': '0',
            'AUTOSEG_FEEDBACK_AI_PROVIDER': 'opencode',
        }, clear=False), patch.object(feedback_ai, '_post_json') as post:
            resultado = feedback_ai.consult('texto', 'PROMPT')
        self.assertEqual(resultado['status'], 'desativada')
        post.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
