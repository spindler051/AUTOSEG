"""Regressões dos feedbacks abertos no DEV: fluxo, fotos e abertura rápida."""
import io
import os
import re
import tempfile
import unittest
from pathlib import Path

import requests
from PIL import Image

import cadastros_v9 as cad9
import estoque_materiais as estoque
import prestadores_ext as ext
from banco import criar_banco
from portal_prestador import PortalPrestador


def csrf(html):
    achado = re.search(r'name="csrf" value="([^"]+)"', html)
    return achado.group(1) if achado else ''


class FeedbackDevTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='feedback_dev_')
        self.old_base = os.environ.get('AUTOSEG_BASE')
        os.environ['AUTOSEG_BASE'] = self.tmp.name
        self.db = str(Path(self.tmp.name) / 'dev.db')
        criar_banco(self.db)
        self.server = PortalPrestador(self.db, '127.0.0.1', 0)
        self.server.iniciar()
        self.base = f'http://127.0.0.1:{self.server.servidor.server_port}'
        self.admin = ext.cadastrar(
            self.db, 'Admin Feedback', 'admin.feedback@example.invalid',
            'senha-admin-123')
        cad9.definir_admin(self.db, self.admin, True)
        self.employee = ext.cadastrar(
            self.db, 'Funcionário Feedback', 'func.feedback@example.invalid',
            'senha-func-123')
        with ext.db(self.db) as c:
            c.execute('''INSERT INTO clientes
                (tipo_pessoa,documento,nome,status,criado_em)
                VALUES('Física','','Cliente Feedback','Ativo',?)''',
                      (ext.agora(),))
            self.cliente = int(c.execute(
                'SELECT MAX(id) FROM clientes').fetchone()[0])
        self.http = requests.Session()
        pagina = self.http.post(self.base + '/login', data={
            'email': 'admin.feedback@example.invalid',
            'senha': 'senha-admin-123'}, timeout=10)
        self.assertEqual(pagina.status_code, 200)
        self.token = csrf(pagina.text)

    def tearDown(self):
        self.server.parar()
        if self.old_base is None:
            os.environ.pop('AUTOSEG_BASE', None)
        else:
            os.environ['AUTOSEG_BASE'] = self.old_base
        self.tmp.cleanup()

    def _criar_os(self, cliente=True, descricao='Atendimento de teste'):
        dados = {
            'csrf': self.token,
            'descricao': descricao,
            'forma_pagamento': 'PIX',
            'urgencia': 'Normal',
        }
        if cliente:
            dados['cliente_id'] = str(self.cliente)
        resposta = self.http.post(self.base + '/os/rapida/salvar',
                                  data=dados, timeout=10)
        self.assertEqual(resposta.status_code, 200)
        with ext.db(self.db) as c:
            os_id = int(c.execute(
                'SELECT MAX(id) FROM ordens_servico').fetchone()[0])
        pagina = self.http.get(self.base + f'/os/{os_id}', timeout=10)
        self.assertEqual(pagina.status_code, 200)
        return os_id, pagina.text

    def _numero(self, os_id):
        with ext.db(self.db) as c:
            return c.execute('SELECT numero_os FROM ordens_servico WHERE id=?',
                             (os_id,)).fetchone()['numero_os']

    def _form_base(self, os_id):
        return {
            'csrf': self.token,
            'cliente_id': str(self.cliente),
            'descricao': 'Atendimento de teste',
            'forma_pagamento': 'PIX',
            'urgencia': 'Normal',
            'valor_mao_obra': '0',
            'valor_materiais_manual': '0',
            'materiais_presentes': '1',
            'confirmar_numero_os': self._numero(os_id),
        }

    def test_cancelar_nao_exige_relatorio_tecnico(self):
        os_id, _html = self._criar_os()
        resposta = self.http.post(self.base + f'/os/{os_id}/cancelar', data={
            'csrf': self.token,
            'motivo_encerramento': 'Cliente desistiu do serviço.',
            'confirmar_numero_os': self._numero(os_id)}, timeout=10)
        self.assertEqual(resposta.status_code, 200, resposta.text[:300])
        with ext.db(self.db) as c:
            os_ = c.execute('SELECT status FROM ordens_servico WHERE id=?',
                            (os_id,)).fetchone()
            fim = c.execute('SELECT relatorio,motivo FROM os_encerramentos '
                            'WHERE os_id=?', (os_id,)).fetchone()
        self.assertEqual(os_['status'], 'Cancelada')
        self.assertEqual(fim['motivo'], 'Cliente desistiu do serviço.')
        self.assertEqual(fim['relatorio'], '')

    def test_pendente_nao_pede_email_e_volta_de_iniciada(self):
        os_id, _html = self._criar_os()
        resposta = self.http.post(self.base + f'/os/{os_id}/iniciar', data={
            'csrf': self.token}, timeout=10)
        self.assertEqual(resposta.status_code, 200, resposta.text[:800])
        with ext.db(self.db) as c:
            inicio = c.execute('SELECT iniciado_em FROM os_atendimentos '
                               'WHERE os_id=?', (os_id,)).fetchone()
        self.assertTrue(inicio['iniciado_em'])
        dados = self._form_base(os_id)
        dados['acao_status'] = 'Pendente'
        resposta = self.http.post(self.base + f'/os/{os_id}/salvar',
                                  data=dados, timeout=10)
        self.assertEqual(resposta.status_code, 200)
        with ext.db(self.db) as c:
            os_ = c.execute('SELECT status FROM ordens_servico WHERE id=?',
                            (os_id,)).fetchone()
            inicio = c.execute('SELECT iniciado_em FROM os_atendimentos '
                               'WHERE os_id=?', (os_id,)).fetchone()
            envios = c.execute('SELECT COUNT(*) FROM produtividade_email '
                               'WHERE os_id=?', (os_id,)).fetchone()[0]
        self.assertEqual(os_['status'], 'Pendente')
        self.assertIsNone(inicio['iniciado_em'])
        self.assertEqual(envios, 0)

    def test_situacao_fica_em_dialogo_e_os_pode_ser_reaberta(self):
        os_id, pagina = self._criar_os()
        self.assertIn('id="dialogo-situacao-os"', pagina)
        self.assertIn('id="abrir-situacao-os"', pagina)
        self.assertIn('name="situacao_popup"', pagina)
        self.assertNotIn('name="situacao_popup" value="Cancelada"', pagina)
        self.assertIn('id="prestador-destino"', pagina)
        self.http.post(self.base + f'/os/{os_id}/iniciar', data={
            'csrf': self.token}, timeout=10)
        resposta = self.http.post(self.base + f'/os/{os_id}/abrir', data={
            'csrf': self.token}, timeout=10)
        self.assertEqual(resposta.status_code, 200)
        with ext.db(self.db) as c:
            os_ = c.execute('SELECT status FROM ordens_servico WHERE id=?',
                            (os_id,)).fetchone()
            inicio = c.execute('SELECT iniciado_em FROM os_atendimentos '
                               'WHERE os_id=?', (os_id,)).fetchone()
        self.assertEqual(os_['status'], 'Aberta')
        self.assertIsNone(inicio['iniciado_em'])

    def test_status_iniciada_exige_cliente_definido(self):
        os_id, _pagina = self._criar_os(cliente=False,
                                        descricao='OS sem cliente para iniciar')
        resposta = self.http.post(self.base + f'/os/{os_id}/iniciar', data={
            'csrf': self.token}, timeout=10)
        self.assertEqual(resposta.status_code, 400)

    def test_abrir_os_sem_cliente_e_associar_depois(self):
        os_id, pagina = self._criar_os(cliente=False,
                                       descricao='OS sem cliente definido')
        self.assertIn('Cliente a definir', pagina)
        with ext.db(self.db) as c:
            linha = c.execute('''SELECT c.status FROM ordens_servico o
                JOIN clientes c ON c.id=o.cliente_id WHERE o.id=?''',
                              (os_id,)).fetchone()
        self.assertEqual(linha['status'], 'A definir')

    def test_aviso_de_duplicidade_e_confirmacao(self):
        os_id, _html = self._criar_os(descricao='Primeira OS')
        dados = {'csrf': self.token, 'cliente_id': str(self.cliente),
                 'descricao': 'Segunda OS', 'forma_pagamento': 'PIX',
                 'urgencia': 'Normal'}
        resposta = self.http.post(self.base + '/os/rapida/salvar',
                                  data=dados, timeout=10)
        self.assertIn('Já existe uma OS recente', resposta.text)
        with ext.db(self.db) as c:
            total = c.execute('SELECT COUNT(*) FROM ordens_servico').fetchone()[0]
        self.assertEqual(total, 1)
        dados['confirmar_duplicidade'] = '1'
        resposta = self.http.post(self.base + '/os/rapida/salvar',
                                  data=dados, timeout=10)
        self.assertIn('OS aberta com sucesso', resposta.text)
        with ext.db(self.db) as c:
            total = c.execute('SELECT COUNT(*) FROM ordens_servico').fetchone()[0]
        self.assertEqual(total, 2)

    def test_fotos_salvam_sem_botao(self):
        os_id, pagina = self._criar_os()
        self.assertIn('Fotos e legendas salvas automaticamente', pagina)
        self.assertNotIn('Salvar fotos e legendas', pagina)
        self.assertNotIn('Adicionar mais fotos', pagina)
        imagem = io.BytesIO()
        Image.new('RGB', (8, 8), (200, 180, 80)).save(imagem, format='PNG')
        resposta = self.http.post(
            self.base + f'/os/{os_id}/fotos',
            data={'csrf': self.token, 'comprimir_fotos_pdf_presente': '1',
                  'comprimir_fotos_pdf': '1'},
            files={'imagens_encerramento[]': ('foto.png', imagem.getvalue(),
                                               'image/png')},
            headers={'X-Requested-With': 'XMLHttpRequest',
                     'Accept': 'application/json'},
            timeout=10)
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json().get('ok'))
        with ext.db(self.db) as c:
            foto = c.execute('SELECT id FROM os_anexos WHERE os_id=?',
                             (os_id,)).fetchone()
        self.assertIsNotNone(foto)
        removida = self.http.post(
            self.base + f'/os/{os_id}/anexo/{foto["id"]}/remover',
            data={'csrf': self.token}, timeout=10)
        self.assertEqual(removida.status_code, 200)
        with ext.db(self.db) as c:
            total = c.execute('SELECT COUNT(*) FROM os_anexos WHERE os_id=?',
                              (os_id,)).fetchone()[0]
        self.assertEqual(total, 0)

    def test_composicao_tem_editor_estruturado(self):
        pagina = self.http.get(self.base + '/composicao', timeout=10)
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('Novo componente', pagina.text)
        self.assertIn('Componentes', pagina.text)
        self.assertIn('YAML avançado', pagina.text)
        editor = self.http.get(self.base + '/composicao/novo', timeout=10)
        self.assertEqual(editor.status_code, 200)
        self.assertIn('Modo de cálculo', editor.text)
        criado = self.http.post(self.base + '/composicao/salvar', data={
            'csrf': self.token, 'nome': 'Componente Feedback',
            'id_novo': 'componente_feedback', 'descricao': 'Teste',
            'modo': 'fixo', 'valor': '50,00', 'formula': '',
            'horas_padrao': '0', 'minimo': '0', 'aplicavel_a': '',
            'ordem': '', 'ativo': '1'}, timeout=15)
        self.assertEqual(criado.status_code, 200)
        lista = self.http.get(self.base + '/composicao', timeout=10)
        self.assertIn('Componente Feedback', lista.text)
        alternado = self.http.post(
            self.base + '/composicao/componente_feedback/alternar',
            data={'csrf': self.token}, timeout=15)
        self.assertEqual(alternado.status_code, 200)
        with open(Path(self.tmp.name) / 'composicao.yaml', encoding='utf-8') as arq:
            import yaml
            config = yaml.safe_load(arq)
        alvo = next(c for c in config['componentes']
                    if c['id'] == 'componente_feedback')
        self.assertFalse(alvo['ativo'])

    def test_material_pesquisa_estoque_no_proprio_campo(self):
        estoque.cadastrar(self.db, nome='Cabo Feedback', sku='FB-1',
                          unidade='m', custo='5', venda='10', minimo='1')
        _os_id, pagina = self._criar_os()
        self.assertIn('list="materiais-estoque-lista"', pagina)
        self.assertIn('Cabo Feedback', pagina)
        self.assertNotIn('Adicionar do estoque', pagina)
        self.assertNotIn('material-estoque-selecionar', pagina)

    def test_exportar_yaml_completo_e_importar_de_volta(self):
        os_id, pagina = self._criar_os(descricao='Serviço para YAML completo')
        cad9.salvar_detalhes(self.db, os_id, 'Diagnóstico exportado',
                             'Execução exportada', 'Resultado exportado')
        self.assertIn('Importar relatório YAML', pagina)
        exportado = self.http.get(
            self.base + f'/os/{os_id}/relatorio.yaml', timeout=10)
        self.assertEqual(exportado.status_code, 200)
        texto = exportado.text
        self.assertIn('instrucoes:', texto)
        self.assertIn('modelo:', texto)
        self.assertIn('numero:', texto)
        self.assertIn('Serviço para YAML completo', texto)
        importado = self.http.post(
            self.base + f'/os/{os_id}/yaml',
            data={'csrf': self.token},
            files={'yaml': ('relatorio_os.yaml', exportado.content,
                            'application/x-yaml')},
            timeout=10)
        self.assertEqual(importado.status_code, 200)
        self.assertIn('Prévia importada', importado.text)

    def test_login_segue_tema_do_sistema_sem_botoes(self):
        pagina = requests.get(self.base + '/login', timeout=10)
        self.assertEqual(pagina.status_code, 200)
        self.assertNotIn('data-login-tema', pagina.text)
        self.assertIn('/static/portal.js', pagina.text)

    def test_os_rapida_cria_cliente_incompleto_sem_pagamento(self):
        resposta = self.http.post(self.base + '/os/rapida/salvar', data={
            'csrf': self.token,
            'cliente_nome': 'Cliente Criado na Rápida',
            'descricao': 'Abertura rápida sem forma de pagamento',
            'urgencia': 'Normal'}, timeout=10)
        self.assertEqual(resposta.status_code, 200)
        with ext.db(self.db) as c:
            cliente = c.execute("SELECT id,dados_incompletos FROM clientes "
                                "WHERE nome='Cliente Criado na Rápida'").fetchone()
            os_ = c.execute('SELECT cliente_id,forma_pagamento FROM ordens_servico '
                            'ORDER BY id DESC LIMIT 1').fetchone()
        self.assertIsNotNone(cliente)
        self.assertTrue(cliente['dados_incompletos'])
        self.assertEqual(int(os_['cliente_id']), int(cliente['id']))
        self.assertEqual(os_['forma_pagamento'], '')

    def test_composicoes_de_valores_sao_editaveis_no_admin(self):
        pagina = self.http.get(self.base + '/composicao', timeout=10)
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('Composições de valores', pagina.text)
        resposta = self.http.post(self.base + '/composicao/bases/salvar', data={
            'csrf': self.token,
            'base_chave[]': ['total', 'visita'],
            'base_nome[]': ['Total da OS', 'Visita mínima'],
            'base_cobertura[]': ['separado', 'incluido'],
            'base_componente[]': ['', 'visita'],
            'base_campo[]': ['', ''],
            'base_padrao': 'total'}, timeout=15)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn('Composição de valores', resposta.text)

    def test_configuracoes_salvam_tema_e_acento_na_conta(self):
        pagina = self.http.get(self.base + '/configuracoes', timeout=10)
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('Aparência do site', pagina.text)
        self.assertIn('name="tema"', pagina.text)
        self.assertIn('name="acento"', pagina.text)
        salvo = self.http.post(self.base + '/configuracoes', data={
            'csrf': self.token, 'tema': 'claro', 'acento': 'azul'}, timeout=10)
        self.assertEqual(salvo.status_code, 200)
        self.assertIn('data-preferencia-tema="claro"', salvo.text)
        self.assertIn('data-acento="azul"', salvo.text)
        import prestador_auth
        prefs = prestador_auth.obter_preferencias(self.db, self.admin)
        self.assertEqual(prefs, {'tema': 'claro', 'acento': 'azul'})

    def test_admin_mescla_clientes_duplicados(self):
        os_id, _pagina = self._criar_os(descricao='OS do cliente duplicado')
        with ext.db(self.db) as c:
            c.execute("""INSERT INTO clientes(tipo_pessoa,documento,nome,status,criado_em)
                         VALUES('Física','','Cliente Destino','Ativo',?)""",
                      (ext.agora(),))
            destino = int(c.execute('SELECT MAX(id) FROM clientes').fetchone()[0])
        resposta = self.http.post(
            self.base + f'/clientes/{self.cliente}/mesclar',
            data={'csrf': self.token, 'destino_id': str(destino)}, timeout=10)
        self.assertEqual(resposta.status_code, 200)
        with ext.db(self.db) as c:
            os_ = c.execute('SELECT cliente_id FROM ordens_servico WHERE id=?',
                            (os_id,)).fetchone()
            origem = c.execute('SELECT status FROM clientes WHERE id=?',
                               (self.cliente,)).fetchone()
        self.assertEqual(int(os_['cliente_id']), destino)
        self.assertEqual(origem['status'], 'Inativo')

    def test_admin_transfere_os_para_outro_prestador(self):
        os_id, _html = self._criar_os()
        resposta = self.http.post(self.base + f'/os/{os_id}/atribuir', data={
            'csrf': self.token, 'prestador_destino': str(self.employee)},
            timeout=10)
        self.assertEqual(resposta.status_code, 200)
        with ext.db(self.db) as c:
            atual = c.execute('SELECT prestador_id FROM os_responsaveis '
                              'WHERE os_id=?', (os_id,)).fetchone()
        self.assertEqual(int(atual['prestador_id']), int(self.employee))


if __name__ == '__main__':
    unittest.main(verbosity=2)
