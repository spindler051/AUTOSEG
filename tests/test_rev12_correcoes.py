"""Correções pós-REV12: OS rápida, PDFs, CNPJ de prestador, exclusões e e-mails.

Usa exclusivamente banco e pastas temporárias; nenhum e-mail real é enviado.
"""
import http.cookiejar
import io
import json
import re
import tempfile
import unittest
from unittest import mock
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

from officina.core import atendimento_os as aten
from officina.core import cadastros_v9 as cad
from officina.core import catalogo_servicos as cat
from officina.core import completude
from officina.core import composicao
from officina.core import estoque_materiais as estoque
from officina.core import fluxo_os as fluxo
from flavors.autoseg.modules import gmail_service
from flavors.autoseg.modules import importacao_yaml
from flavors.autoseg.modules import pdf_cliente_v9
from officina.core import portal_negocios as neg
from officina.core import prestadores_ext as ext
from officina.core import produtividade_os as prod
from officina.core.banco import criar_banco
from flavors.autoseg.modules.portal_prestador import PortalPrestador
from pypdf import PdfReader

# Nenhum envio real de e-mail em segundo plano durante os testes.
import os
os.environ['AUTOSEG_GMAIL_DESATIVADO'] = '1'


def browser():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def req(client, base, path, data=None):
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    pedido = urllib.request.Request(base + path, body)
    try:
        with client.open(pedido, timeout=20) as resposta:
            return resposta.status, resposta.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read().decode('utf-8', 'replace')


def multipart(client, base, path, campos, arquivos):
    fronteira = '----autosegcorr' + uuid.uuid4().hex
    partes = []
    for nome, valor in campos:
        partes.append(f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{valor}\r\n'.encode())
    for nome, nome_arquivo, conteudo, mime in arquivos:
        partes.append((f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"; '
                       f'filename="{nome_arquivo}"\r\nContent-Type: {mime}\r\n\r\n').encode()
                      + conteudo + b'\r\n')
    partes.append(f'--{fronteira}--\r\n'.encode())
    pedido = urllib.request.Request(base + path, b''.join(partes),
                                    {'Content-Type': f'multipart/form-data; boundary={fronteira}'})
    try:
        with client.open(pedido, timeout=30) as resposta:
            return resposta.status, resposta.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read().decode('utf-8', 'replace')


PDF_MINIMO = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n'


def texto_pdf(arquivo):
    return '\n'.join(pagina.extract_text() or '' for pagina in PdfReader(arquivo).pages)


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class CorrecoesRev12(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_correcoes_')
        self.dir = Path(self.tmp.name)
        self.db = str(self.dir / 'teste.db')
        criar_banco(self.db)
        for modulo in (ext, fluxo, aten, cad, cat, prod, estoque):
            modulo.instalar(self.db)
        ext.ANEXOS = self.dir / 'anexos'
        ext.RELATORIOS = self.dir / 'relatorios'
        ext.RASCUNHOS = self.dir / 'rascunhos'
        ext.NOTAS = self.dir / 'notas_fiscais'
        for pasta in (ext.ANEXOS, ext.RELATORIOS, ext.RASCUNHOS, ext.NOTAS):
            pasta.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _prestador(self, nome='Prestador Teste', email=None, documento=''):
        return ext.cadastrar(self.db, nome, email or f'{nome.lower().replace(" ", ".")}@exemplo.com.br',
                             'senha-bem-segura-2026', documento=documento)

    def _numero(self, oid):
        with ext.db(self.db) as c:
            return c.execute('SELECT numero_os FROM ordens_servico WHERE id=?',
                             (oid,)).fetchone()[0]

    def _cliente(self, pid, nome='Condomínio Alfa', **extras):
        dados = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados.update(nome=nome, tipo_pessoa='Jurídica', status='Ativo')
        dados.update(extras)
        return neg.cliente_salvar(self.db, dados, pid)

    def _os_concluida(self, pid, cid):
        dados = {'cliente_id': str(cid), 'descricao': 'Manutenção preventiva',
                 'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '540',
                 'valor_materiais_manual': '100', 'material_item[]': ['Cabo'],
                 'material_qtd[]': ['1'], 'material_unit[]': ['100'],
                 'materiais_presentes': '1', 'relatorio_tecnico': 'Serviço concluído',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        conclusao = dict(dados)
        conclusao.update(acao_status='Concluída', v9_execucao='exec')
        neg.os_salvar(self.db, conclusao, pid, oid)
        return oid

    def _servidor(self):
        servidor = PortalPrestador(self.db, '127.0.0.1', 0)
        servidor.iniciar()
        self.addCleanup(servidor.parar)
        return servidor, f'http://127.0.0.1:{servidor.servidor.server_port}'

    def _login(self, base, email='prestador.teste@exemplo.com.br'):
        cliente = browser()
        req(cliente, base, '/login', {'email': email, 'senha': 'senha-bem-segura-2026'})
        return cliente

    def _csrf(self, base, cliente, oid):
        _, html = req(cliente, base, f'/os/{oid}')
        return re.search(r'name="csrf" value="([^"]+)"', html).group(1)

    # ---------------------------------------------------------------- 1
    def test_os_rapida_busca_cartoes_e_criacao_aberta(self):
        pid = self._prestador()
        alfa = self._cliente(pid, 'Condomínio Alfa', cidade='Porto Alegre')
        self._cliente(pid, 'Empresa Beta', cidade='Canoas')
        servidor = PortalPrestador(self.db, '127.0.0.1', 0)
        servidor.iniciar()
        self.addCleanup(servidor.parar)
        base = f'http://127.0.0.1:{servidor.servidor.server_port}'
        cliente = browser()

        status, html = req(cliente, base, '/login',
                           {'email': 'prestador.teste@exemplo.com.br',
                            'senha': 'senha-bem-segura-2026'})
        self.assertEqual(status, 200)
        status, html = req(cliente, base, '/os/rapida')
        self.assertEqual(status, 200)
        self.assertIn('id="cliente-rapida-nome"', html)
        self.assertIn('list="clientes-rapida-lista"', html)
        self.assertIn('Condomínio Alfa', html)
        self.assertIn('Empresa Beta', html)
        self.assertNotIn('name="forma_pagamento"', html)
        self.assertNotIn('Atribuir prestador', html)

        status, html = req(cliente, base, f'/os/rapida?cliente={alfa}')
        self.assertEqual(status, 200)
        self.assertIn('name="cliente_id"', html)
        self.assertIn('name="descricao"', html)
        self.assertIn('name="urgencia"', html)
        self.assertIn('<option value="Alta"', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        status, html = req(cliente, base, '/os/rapida/salvar',
                           {'csrf': token, 'cliente_id': str(alfa),
                            'descricao': 'Portão da garagem não abre.',
                            'urgencia': 'Alta'})
        self.assertEqual(status, 200)
        self.assertIn('OS aberta com sucesso', html)
        self.assertIn('Abrir OS', html)
        self.assertNotIn('SALVAR RASCUNHO', html)
        with ext.db(self.db) as c:
            ordem = c.execute('SELECT cliente_id,status,descricao,urgencia FROM ordens_servico '
                              'ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(ordem['cliente_id'], alfa)
        self.assertEqual(ordem['status'], 'Aberta')
        self.assertEqual(ordem['urgencia'], 'Alta')
        self.assertIn('Portão da garagem', ordem['descricao'])

    def test_urgencia_da_os_completa_e_preservada_na_edicao(self):
        pid = self._prestador('Técnico Urgência', email='urgencia.os@exemplo.com.br')
        cid = self._cliente(pid, 'Condomínio Urgência')
        dados = {'cliente_id': str(cid), 'descricao': 'Ajustar portão',
                 'tecnico': 'T', 'forma_pagamento': 'PIX', 'urgencia': 'Alta',
                 'valor_mao_obra': '100', 'valor_materiais_manual': '0',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT urgencia FROM ordens_servico WHERE id=?',
                                       (oid,)).fetchone()['urgencia'], 'Alta')
        # Edição sem o campo (integrações antigas) não pode rebaixar para Normal.
        edicao = dict(dados)
        edicao.pop('urgencia')
        edicao['descricao'] = 'Ajustar portão e fechadura'
        neg.os_salvar(self.db, edicao, pid, oid)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT urgencia FROM ordens_servico WHERE id=?',
                                       (oid,)).fetchone()['urgencia'], 'Alta')

    def test_layout_padrao_autosave_e_sem_toggle(self):
        pid = self._prestador('Técnico Padrão', email='padrao@exemplo.com.br')
        cid = self._cliente(pid, 'Condomínio Padrão')
        dados = {'cliente_id': str(cid), 'descricao': 'Ajustar portão',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'valor_materiais_manual': '0',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        _, base = self._servidor()
        _, login = req(browser(), base, '/login')
        self.assertIn('Portal do prestador', login)
        self.assertNotIn('Ativar app', login)
        self.assertNotIn('Desativar app', login)
        cliente = self._login(base, 'padrao@exemplo.com.br')
        _, html = req(cliente, base, '/')
        self.assertIn('Visão geral', html)
        self.assertIn('Ordens recentes', html)
        self.assertIn('A receber', html)
        self.assertIn('href="/os/rapida"', html)
        self.assertIn('+ Nova OS', html)
        self.assertIn('class="ui-app', html)
        self.assertIn('class="app-side"', html)
        self.assertNotIn('Meu Auto Financeiro', html)
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertIn('name="urgencia"', html)
        self.assertIn('os-form-app', html)
        self.assertIn('data-auto-save="1"', html)
        self.assertIn('rascunho-auto-status', html)
        self.assertNotIn(f'formaction="/os/{self._numero(oid)}/rascunho/salvar"', html)
        self.assertIn('os-summary', html)
        self.assertIn('os-ticket', html)
        self.assertIn('os-workflow', html)
        self.assertIn('os-rail', html)
        self.assertIn('Ficha da OS', html)
        self.assertIn('Situação do atendimento', html)
        self.assertIn('Baixar preview do PDF', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        status, _ = req(cliente, base, f'/os/{oid}/rascunho/auto',
                        {'csrf': token, 'v9_diagnostico': 'Rascunho automático'})
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            rascunho = ext.obter_rascunho_web(self.db, oid, pid)
        self.assertEqual(rascunho['v9_diagnostico'], 'Rascunho automático')
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertIn('Rascunho automático', html)
        self.assertNotIn('Ativar app', html)
        self.assertNotIn('Desativar app', html)

    def test_material_unidade_livre_quantidade_opcional_e_composicao(self):
        pid = self._prestador('Técnico Unidades', email='unidades@exemplo.com.br')
        cid = self._cliente(pid, 'Condomínio Unidades')
        dados = {
            'cliente_id': str(cid), 'descricao': 'Ajuste com materiais',
            'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '100',
            'materiais_presentes': '1', 'acao_status': 'salvar',
            'aplicar_composicao': '1',
            'material_item[]': ['Cola silicone', 'Cabo 20A'],
            'material_qtd[]': ['', '20'],
            'material_unidade[]': ['googleplexes', 'm'],
            'material_unit[]': ['25,00', '1,25'],
        }
        oid = neg.os_salvar(self.db, dados, pid)
        with ext.db(self.db) as c:
            os_ = c.execute('SELECT valor_mao_obra,valor_total,composicao_json '
                            'FROM ordens_servico WHERE id=?', (oid,)).fetchone()
            mats = c.execute('SELECT item,quantidade,unidade,valor_total FROM materiais_os '
                             'WHERE os_id=? ORDER BY id', (oid,)).fetchall()
        self.assertIsNone(mats[0]['quantidade'])
        self.assertEqual(mats[0]['unidade'], 'googleplexes')
        self.assertAlmostEqual(float(mats[0]['valor_total']), 25.0, places=2)
        self.assertAlmostEqual(float(mats[1]['quantidade']), 20.0)
        self.assertEqual(mats[1]['unidade'], 'm')
        self.assertAlmostEqual(float(mats[1]['valor_total']), 25.0, places=2)
        comp = json.loads(os_['composicao_json'])
        esperado = composicao.calcular_os(
            materiais_centavos=5000, mao_obra_centavos=10000)
        self.assertAlmostEqual(float(os_['valor_total']),
                               esperado['total_centavos'] / 100, places=2)
        hora = next(x for x in comp['componentes'] if x['modo'] == 'hora')
        self.assertAlmostEqual(float(os_['valor_mao_obra']),
                               hora['valor_centavos'] / 100, places=2)
        self.assertEqual(sum(x['valor_centavos'] for x in comp['componentes']),
                         comp['total_centavos'])
        fixos = [x for x in comp['componentes'] if x['modo'] == 'fixo']
        if fixos:
            self.assertTrue(any(x['valor_centavos'] > 0 for x in fixos))

    def test_composicao_total_450_base_visita(self):
        pid = self._prestador('Técnico Total 450', email='total450@exemplo.com.br')
        cid = self._cliente(pid, 'Condomínio Total 450')
        dados = {
            'cliente_id': str(cid), 'descricao': 'Serviço fechado em 450',
            'tecnico': 'T', 'forma_pagamento': 'PIX',
            'valor_mao_obra': '100', 'valor_materiais_manual': '65',
            'valor_total_override': '450', 'materiais_presentes': '1',
            'aplicar_composicao': '1', 'base_percentuais': 'visita',
            'acao_status': 'salvar',
        }
        # A config efetiva do MAIN não tem deslocamento e usa risco de 10%.
        with mock.patch.dict(os.environ, {'AUTOSEG_BASE': str(self.dir)}):
            composicao.instalar()
            config = composicao.carregar()
            config['componentes'] = [
                c for c in config['componentes'] if c['id'] != 'deslocamento']
            for componente in config['componentes']:
                if componente['id'] == 'risco':
                    componente['valor'] = 10
                if componente['id'] == 'hora_tecnica':
                    componente['minimo_centavos'] = 10000
            composicao.salvar(config)
            oid = neg.os_salvar(self.db, dados, pid)
            with ext.db(self.db) as c:
                os_ = c.execute('SELECT valor_materiais,valor_mao_obra,valor_total,base_percentuais,composicao_json '
                                'FROM ordens_servico WHERE id=?', (oid,)).fetchone()
        self.assertAlmostEqual(float(os_['valor_materiais']), 65.0, places=2)
        self.assertAlmostEqual(float(os_['valor_mao_obra']), 135.0, places=2)
        self.assertAlmostEqual(float(os_['valor_total']), 450.0, places=2)
        self.assertEqual(os_['base_percentuais'], 'visita')
        comp = json.loads(os_['composicao_json'])
        valores = {x['nome']: x['valor_centavos'] for x in comp['componentes']}
        self.assertEqual(comp['total_centavos'], 45000)
        self.assertEqual(comp['base_percentuais'], 'visita')
        self.assertEqual(valores['Materiais'], 6500)
        self.assertEqual(valores['Mão de obra / hora técnica'], 13500)
        self.assertEqual(valores['Taxa mínima de visita'], 25000)
        self.assertNotIn('Custos administrativos', valores)
        visita = next(x for x in comp['componentes'] if x['id'] == 'visita')
        filhos = {x['nome']: x['valor_centavos'] for x in visita['filhos']}
        self.assertEqual(filhos['Custos administrativos'], 2500)
        self.assertEqual(filhos['Custos operacionais e tecnológicos'], 2500)
        self.assertEqual(filhos['Margem de risco e contingência'], 2500)
        self.assertEqual(sum(valores.values()), 45000)

    def test_encerramento_preserva_composicao_modular(self):
        pid = self._prestador('Técnico Encerramento', email='encerramento@exemplo.com.br')
        cid = self._cliente(pid, 'Condomínio Encerramento')
        dados = {
            'cliente_id': str(cid), 'descricao': 'Serviço modular concluído',
            'tecnico': 'T', 'forma_pagamento': 'PIX',
            'valor_mao_obra': '100', 'valor_materiais_manual': '65',
            'valor_total_override': '450', 'materiais_presentes': '1',
            'aplicar_composicao': '1', 'base_percentuais': 'visita',
            'relatorio_tecnico': 'Serviço concluído no teste.',
            'v9_execucao': 'exec', 'acao_status': 'Concluída',
        }
        with mock.patch.dict(os.environ, {'AUTOSEG_BASE': str(self.dir)}):
            composicao.instalar()
            config = composicao.carregar()
            config['componentes'] = [
                c for c in config['componentes'] if c['id'] != 'deslocamento']
            for componente in config['componentes']:
                if componente['id'] == 'risco':
                    componente['valor'] = 10
                if componente['id'] == 'hora_tecnica':
                    componente['minimo_centavos'] = 10000
            composicao.salvar(config)
            oid = neg.os_salvar(self.db, dados, pid)
            with ext.db(self.db) as c:
                os_ = c.execute(
                    'SELECT status,valor_materiais,valor_mao_obra,valor_total,'
                    'base_percentuais,composicao_json FROM ordens_servico WHERE id=?',
                    (oid,)).fetchone()
        self.assertEqual(os_['status'], 'Concluída')
        self.assertAlmostEqual(float(os_['valor_materiais']), 65.0, places=2)
        self.assertAlmostEqual(float(os_['valor_mao_obra']), 135.0, places=2)
        self.assertAlmostEqual(float(os_['valor_total']), 450.0, places=2)
        comp = json.loads(os_['composicao_json'])
        self.assertEqual(comp['base_percentuais'], 'visita')
        valores = {x['nome']: x['valor_centavos'] for x in comp['componentes']}
        self.assertEqual(valores['Mão de obra / hora técnica'], 13500)
        visita = next(x for x in comp['componentes'] if x['id'] == 'visita')
        self.assertEqual(len(visita['filhos']), 3)
        self.assertEqual(sum(valores.values()), 45000)

    def test_cancelamento_exige_numero_da_os(self):
        pid = self._prestador('Técnico Cancelamento', email='cancelamento@exemplo.com.br')
        cid = self._cliente(pid, 'Condomínio Cancelamento')
        dados = {
            'cliente_id': str(cid), 'descricao': 'Serviço a cancelar',
            'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '100',
            'materiais_presentes': '1', 'acao_status': 'salvar',
        }
        oid = neg.os_salvar(self.db, dados, pid)
        with ext.db(self.db) as c:
            numero = c.execute('SELECT numero_os FROM ordens_servico WHERE id=?',
                               (oid,)).fetchone()['numero_os']
        cancelamento = dict(dados)
        cancelamento.update({
            'cancelar_os': '1', 'motivo_encerramento': 'Cliente desistiu.',
            'relatorio_tecnico': 'Cancelamento solicitado pelo cliente.',
            'confirmar_numero_os': 'OS-ERRADA',
        })
        with self.assertRaises(ValueError):
            neg.os_salvar(self.db, cancelamento, pid, oid)
        with ext.db(self.db) as c:
            self.assertEqual(
                c.execute('SELECT status FROM ordens_servico WHERE id=?',
                          (oid,)).fetchone()['status'], 'Aberta')
        cancelamento['confirmar_numero_os'] = numero
        neg.os_salvar(self.db, cancelamento, pid, oid)
        with ext.db(self.db) as c:
            os_ = c.execute('SELECT status FROM ordens_servico WHERE id=?',
                            (oid,)).fetchone()
        self.assertEqual(os_['status'], 'Cancelada')

    def test_pdf_nao_abre_pagina_de_erro_em_os_ativa(self):
        pid = self._prestador()
        cid = self._cliente(pid)
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço em andamento',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'valor_materiais_manual': '0',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        with ext.db(self.db) as c:
            c.execute(
                "INSERT INTO os_documentos(os_id,tipo,versao,caminho,sha256,publicado_em) "
                "VALUES(?,?,?,?,?,?)",
                (oid, 'relatorio_pdf', 1, '/tmp/relatorio-antigo.pdf', 'x', ext.agora()))
        _, base = self._servidor()
        cliente = self._login(base)
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertIn('Documento anterior', html)
        self.assertNotIn(f'href="/os/{self._numero(oid)}/pdf"', html)
        self.assertNotIn('Baixar PDF publicado', html)

    def test_preview_pdf_os_ativa_sem_publicar(self):
        a = self._prestador('Técnico Preview A', email='preview.a@exemplo.com.br')
        b = self._prestador('Técnico Preview B', email='preview.b@exemplo.com.br')
        cid = self._cliente(a, 'Condomínio Preview')
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço em andamento',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'valor_materiais_manual': '0',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, a)
        ext.atribuir(self.db, oid, a)
        _, base = self._servidor()
        cliente_b = self._login(base, 'preview.b@exemplo.com.br')
        _, html = req(cliente_b, base, f'/os/{oid}')
        self.assertIn(f'/os/{self._numero(oid)}/pdf-preview', html)
        self.assertIn('Baixar preview do PDF', html)
        pedido = urllib.request.Request(base + f'/os/{oid}/pdf-preview')
        with cliente_b.open(pedido, timeout=30) as resposta:
            self.assertEqual(resposta.status, 200)
            self.assertEqual(resposta.headers.get_content_type(), 'application/pdf')
            self.assertTrue(resposta.read().startswith(b'%PDF'))
        with ext.db(self.db) as c:
            self.assertEqual(c.execute(
                'SELECT COUNT(*) FROM os_documentos WHERE os_id=?', (oid,)).fetchone()[0], 0)
            self.assertEqual(c.execute(
                'SELECT status FROM ordens_servico WHERE id=?', (oid,)).fetchone()[0],
                'Aberta')

    def test_admin_adiciona_fotos_em_os_de_outro(self):
        a = self._prestador('Técnico Foto A', email='foto.a@exemplo.com.br')
        b = self._prestador('Técnico Foto B', email='foto.b@exemplo.com.br')
        c = self._prestador('Técnico Foto C', email='foto.c@exemplo.com.br')
        cad.definir_admin(self.db, b, True)
        cid = self._cliente(a, 'Condomínio Foto')
        dados = {'cliente_id': str(cid), 'descricao': 'Ajustar portão',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'valor_materiais_manual': '0',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, a)
        ext.atribuir(self.db, oid, a)
        _, base = self._servidor()
        cliente_b = self._login(base, 'foto.b@exemplo.com.br')
        _, html = req(cliente_b, base, f'/os/{oid}')
        self.assertIn('Fotos e legendas salvas automaticamente', html)
        self.assertNotIn('Salvar fotos e legendas', html)
        self.assertNotIn('Adicionar fotos e legendas sem assumir a OS', html)
        self.assertNotIn('sem assumir', html)
        self.assertNotIn(f'formaction="/os/{self._numero(oid)}/rascunho/salvar"', html)
        self.assertIn('id="abrir-situacao-os"', html)
        self.assertIn('Responsável (admin)', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        buffer = io.BytesIO()
        Image.new('RGB', (4, 4), 'red').save(buffer, 'PNG')
        status, _ = multipart(
            cliente_b, base, f'/os/{oid}/fotos',
            [('csrf', token), ('foto_legenda[]', 'Foto do portão'),
             ('foto_chave[]', 'chave-teste'), ('foto_visivel[]', '1')],
            [('imagens_encerramento[]', 'portao.png', buffer.getvalue(), 'image/png')])
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            foto = c.execute('SELECT id,prestador_id FROM os_anexos WHERE os_id=?',
                             (oid,)).fetchone()
            legenda = c.execute('SELECT legenda FROM v9_anexos_visiveis v '
                                'JOIN os_anexos a ON a.id=v.anexo_id WHERE a.os_id=?',
                                (oid,)).fetchone()
            responsavel = c.execute('SELECT prestador_id FROM os_responsaveis '
                                    'WHERE os_id=?', (oid,)).fetchone()
        self.assertEqual(foto['prestador_id'], b)
        self.assertEqual(legenda['legenda'], 'Foto do portão')
        self.assertEqual(responsavel['prestador_id'], a)

        _, html = req(cliente_b, base, f'/os/{oid}')
        self.assertIn('name="anexo_incluir[]"', html)
        self.assertIn(f'data-mover="/os/{self._numero(oid)}/anexo/{foto["id"]}/mover"', html)
        with cliente_b.open(urllib.request.Request(
                base + f'/arquivos/anexo/{foto["id"]}/thumb'), timeout=30) as resposta:
            self.assertEqual(resposta.status, 200)
            self.assertEqual(resposta.headers.get_content_type(), 'image/jpeg')
            self.assertGreater(len(resposta.read()), 0)

        # O mesmo técnico não responsável pode alterar a legenda depois.
        status, _ = req(cliente_b, base, f'/os/{oid}/fotos', {
            'csrf': token,
            'anexo_id[]': [str(foto['id'])],
            'anexo_legenda[]': ['Legenda alterada pelo colaborador'],
            'anexo_incluir_modo': '1',
            'comprimir_fotos_pdf_presente': '1',
        })
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            alterada = c.execute(
                'SELECT legenda,visivel FROM v9_anexos_visiveis WHERE anexo_id=?',
                (foto['id'],)).fetchone()
            compressao = c.execute(
                'SELECT comprimir_fotos_pdf FROM ordens_servico WHERE id=?',
                (oid,)).fetchone()
        self.assertEqual(alterada['legenda'], 'Legenda alterada pelo colaborador')
        self.assertEqual(alterada['visivel'], 0)
        self.assertEqual(compressao['comprimir_fotos_pdf'], 0)

        # Erro de validação nesse formulário deve voltar como JSON/toast, sem
        # navegar para uma página de erro.
        corpo = urllib.parse.urlencode({'csrf': token}).encode()
        pedido = urllib.request.Request(
            base + f'/os/{oid}/fotos', corpo,
            headers={'X-Requested-With': 'XMLHttpRequest',
                     'Accept': 'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as falha:
            cliente_b.open(pedido, timeout=30)
        self.assertEqual(falha.exception.code, 400)
        dados = json.loads(falha.exception.read())
        self.assertIn('Selecione uma foto ou altere uma legenda', dados['error'])

        # Tentar concluir sem ser o responsável deve explicar o motivo em JSON,
        # sem navegar para uma página de erro.
        cliente_c = self._login(base, 'foto.c@exemplo.com.br')
        _, html_c = req(cliente_c, base, f'/os/{oid}')
        token_c = re.search(r'name="csrf" value="([^"]+)"', html_c).group(1)
        corpo = urllib.parse.urlencode({
            'csrf': token_c, 'modo_envio': 'encerrar', 'acao_status': 'Concluída',
            'v9_execucao': 'Serviço executado', 'sem_nota_fiscal': '1',
        }).encode()
        pedido = urllib.request.Request(
            base + f'/os/{oid}/salvar', corpo,
            headers={'X-Requested-With': 'XMLHttpRequest',
                     'Accept': 'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as falha:
            cliente_c.open(pedido, timeout=30)
        self.assertEqual(falha.exception.code, 403)
        dados = json.loads(falha.exception.read())
        self.assertTrue(dados.get('error'))

    # ---------------------------------------------------------------- 2 e 3
    def test_relatorio_pdf_cnpj_prestador_ou_padrao(self):
        outro = self._prestador('Prestador Outro', documento='11222333000181')
        igual = self._prestador('Prestador Principal', documento='23864393000187')
        sem_doc = self._prestador('Prestador Sem Documento')
        cid_outro = self._cliente(outro, 'Cliente Outro', documento='12345678000195')
        cid_igual = self._cliente(igual, 'Cliente Principal')
        cid_sem = self._cliente(sem_doc, 'Cliente Sem Documento')

        # Prestador com CNPJ próprio: mostra o CNPJ dele e o documento do cliente.
        texto = texto_pdf(pdf_cliente_v9.gerar(
            self.db, self._os_concluida(outro, cid_outro)))
        self.assertNotIn('<b>', texto.lower())
        self.assertIn('TOTAL', texto)
        self.assertIn('11.222.333/0001-81', texto)
        self.assertIn('12.345.678/0001-95', texto)

        # Prestador com o CNPJ principal: mostra o principal.
        texto = texto_pdf(pdf_cliente_v9.gerar(
            self.db, self._os_concluida(igual, cid_igual)))
        self.assertNotIn('<b>', texto.lower())
        self.assertIn('23.864.393/0001-87', texto)

        # Prestador sem CNPJ: usa o CNPJ padrão da AUTOSEG.
        texto = texto_pdf(pdf_cliente_v9.gerar(
            self.db, self._os_concluida(sem_doc, cid_sem)))
        self.assertIn('23.864.393/0001-87', texto)

        # Documento é CPF, mas o CNPJ está nos dados bancários/cadastrais.
        cpf_com_cnpj = self._prestador('Prestador CPF com CNPJ',
                                       documento='87820030097')
        cid_cpf = self._cliente(cpf_com_cnpj, 'Cliente CPF com CNPJ')
        ext.salvar_config_prestador(self.db, cpf_com_cnpj, {
            'dados_bancarios_texto': 'Dados da conta\nCNPJ: 52.204.907/0001-76\nPIX: chave-teste'})
        texto = texto_pdf(pdf_cliente_v9.gerar(
            self.db, self._os_concluida(cpf_com_cnpj, cid_cpf)))
        self.assertIn('52.204.907/0001-76', texto)
        self.assertNotIn('23.864.393/0001-87', texto)

        # CNPJ explícito no cadastro do prestador prevalece sobre o texto.
        cnpj_explicito = self._prestador('Prestador CNPJ Explícito',
                                         documento='11222333000181')
        cid_explicito = self._cliente(cnpj_explicito, 'Cliente CNPJ Explícito')
        ext.salvar_config_prestador(self.db, cnpj_explicito, {
            'dados_bancarios_texto': 'CNPJ: 52.204.907/0001-76'})
        texto = texto_pdf(pdf_cliente_v9.gerar(
            self.db, self._os_concluida(cnpj_explicito, cid_explicito)))
        self.assertIn('11.222.333/0001-81', texto)
        self.assertNotIn('52.204.907/0001-76', texto)

    def test_prestadores_podem_repetir_cnpj(self):
        primeiro = self._prestador('Prestador A')
        segundo = self._prestador('Prestador B')
        doc = ext.definir_documento_prestador(self.db, primeiro, '11222333000181')
        self.assertEqual(doc, '11222333000181')
        ext.definir_documento_prestador(self.db, segundo, '11222333000181')
        with ext.db(self.db) as c:
            registros = c.execute(
                'SELECT documento FROM prestadores WHERE id IN (?,?) ORDER BY id',
                (primeiro, segundo)).fetchall()
        self.assertEqual([x['documento'] for x in registros],
                         ['11222333000181', '11222333000181'])

    def test_orcamento_pdf_faixa_preta_e_cnpj_principal(self):
        servico = cat.salvar(self.db, {'nome': 'Instalação de câmeras',
                                       'descricao': 'Serviço completo',
                                       'preco_servico': '540'})
        bruto = cat.pdf_orcamento(self.db, servico, 1, 'Cliente Exemplo')
        leitor = PdfReader(io.BytesIO(bruto))
        texto = '\n'.join(p.extract_text() or '' for p in leitor.pages)
        self.assertIn('23.864.393/0001-87', texto)
        self.assertNotIn('<b>', texto.lower())
        self.assertGreaterEqual(len(leitor.pages[0].images), 1)
        # Faixa preta (#171717) atrás do logo, para contraste das partes brancas.
        self.assertIn(b'.090196 .090196 .090196 rg',
                      leitor.pages[0].get_contents().get_data())

    def test_relatorio_100_por_cento_materiais_no_pdf(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Cliente 100% materiais')
        dados = {'cliente_id': str(cid), 'descricao': 'Instalação de cabo',
                 'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '0',
                 'valor_materiais_manual': '0', 'material_item[]': ['Cabo'],
                 'material_qtd[]': ['1'], 'material_unit[]': ['21,50'],
                 'materiais_presentes': '1', 'relatorio_tecnico': 'ok',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        conclusao = dict(dados)
        conclusao.update(acao_status='Concluída', v9_execucao='exec')
        neg.os_salvar(self.db, conclusao, pid, oid)
        texto = texto_pdf(pdf_cliente_v9.gerar(self.db, oid))
        self.assertIn('Materiais', texto)
        self.assertIn('100,00%', texto)
        self.assertIn('21,50', texto)
        for ruim in ('13,72', '63,77', '19,12', '13,71', '2,95', '4,11'):
            self.assertNotIn(ruim, texto)

    def test_orcamento_100_por_cento_materiais_no_pdf(self):
        servico = cat.salvar(self.db, {'nome': 'Só materiais',
                                       'descricao': 'Sem mão de obra',
                                       'preco_servico': '0',
                                       'materiais': 'Cabo | 1 | 21,50'})
        bruto = cat.pdf_orcamento(self.db, servico, 1, 'Cliente Exemplo')
        texto = '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(bruto)).pages)
        self.assertIn('Materiais', texto)
        self.assertIn('100,00%', texto)
        self.assertIn('21,50', texto)
        for ruim in ('13,72', '63,77', '19,12'):
            self.assertNotIn(ruim, texto)

    # ---------------------------------------------------------------- 4
    def test_excluir_material_sem_uso_remove_e_com_historico_arquiva(self):
        sem_uso = estoque.cadastrar(self.db, 'Conector RJ45', venda='2,50')
        self.assertEqual(estoque.excluir(self.db, sem_uso), 'excluido')
        self.assertFalse(any(x['id'] == sem_uso for x in estoque.listar(self.db)))

        com_uso = estoque.cadastrar(self.db, 'Câmera IP', venda='180,00')
        estoque.ajuste(self.db, com_uso, '3', 'Entrada inicial')
        self.assertEqual(estoque.excluir(self.db, com_uso), 'arquivado')
        registro = next(x for x in estoque.listar(self.db) if x['id'] == com_uso)
        self.assertEqual(registro['ativo'], 0)
        self.assertEqual(len(estoque.movimentos(self.db, com_uso)), 1)

    def test_excluir_servico_do_catalogo(self):
        servico = cat.salvar(self.db, {'nome': 'Serviço temporário',
                                       'descricao': 'Teste',
                                       'preco_servico': '100'})
        cat.excluir(self.db, servico)
        self.assertIsNone(cat.obter(self.db, servico))
        self.assertFalse(any(x['id'] == servico for x in cat.listar(self.db)))

    def test_portal_servicos_exclui_com_botao_e_confirmacao(self):
        self._prestador()
        servico = cat.salvar(self.db, {'nome': 'Serviço do portal',
                                       'descricao': 'Teste',
                                       'preco_servico': '100'})
        servidor = PortalPrestador(self.db, '127.0.0.1', 0)
        servidor.iniciar()
        self.addCleanup(servidor.parar)
        base = f'http://127.0.0.1:{servidor.servidor.server_port}'
        cliente = browser()
        req(cliente, base, '/login', {'email': 'prestador.teste@exemplo.com.br',
                                      'senha': 'senha-bem-segura-2026'})
        status, html = req(cliente, base, '/servicos')
        self.assertEqual(status, 200)
        self.assertIn(f'action="/servicos/{servico}/excluir"', html)
        self.assertIn('data-confirm=', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        status, html = req(cliente, base, f'/servicos/{servico}/excluir',
                           {'csrf': token})
        self.assertEqual(status, 200)
        self.assertIsNone(cat.obter(self.db, servico))

    # ---------------------------------------------------------------- 5
    def test_emails_adicionais_entram_na_lista_final(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Multi',
                            email='cliente@exemplo.com.br',
                            sindico_email='sindico@exemplo.com.br',
                            administradora_email='adm@exemplo.com.br')
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço multi', 'tecnico': 'T',
                 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        lista = prod.destinatarios_para_os(
            self.db, oid, ['administradora'], 'extra@exemplo.com.br, cliente@exemplo.com.br')
        self.assertEqual(lista, ['adm@exemplo.com.br', 'extra@exemplo.com.br',
                                 'cliente@exemplo.com.br'])

    def test_gmail_bloqueia_dominios_de_teste_antes_da_rede(self):
        for endereco in ('34567890175@example.org', 'teste@example.com',
                         'x@algo.invalid', 'y@servidor.test'):
            with self.assertRaises(RuntimeError) as contexto:
                gmail_service.enviar_email_gmail(endereco, 'Teste', '<p>Teste</p>')
            self.assertIn('bloqueado', str(contexto.exception))
            self.assertIn(endereco, str(contexto.exception))

    # ---------------------------------------------------------------- 6
    def test_rascunho_restaura_destinatarios_e_email_adicional(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Multi', email='cliente@exemplo.com.br',
                            sindico_email='sindico@exemplo.com.br',
                            administradora_email='adm@exemplo.com.br')
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço', 'tecnico': 'T',
                 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        servidor, base = self._servidor()
        cliente = self._login(base)
        token = self._csrf(base, cliente, oid)
        rasc = {'csrf': token, 'cliente_id': str(cid), 'descricao': 'Serviço',
                'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                'materiais_presentes': '1', 'v9_execucao': 'exec',
                'destinatario_sel[]': ['cliente', 'sindico', 'administradora'],
                'emails_adicionais': 'extra@exemplo.com.br'}
        status, html = req(cliente, base, f'/os/{oid}/rascunho/salvar', rasc)
        self.assertEqual(status, 200)
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertIn('value="extra@exemplo.com.br"', html)
        self.assertIn('value="administradora" checked', html)
        self.assertIn('value="cliente" checked', html)

    def test_conclusao_envia_todos_os_destinatarios_selecionados(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Multi', email='cliente@exemplo.com.br',
                            sindico_email='sindico@exemplo.com.br',
                            administradora_email='adm@exemplo.com.br')
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço', 'tecnico': 'T',
                 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        servidor, base = self._servidor()
        cliente = self._login(base)
        token = self._csrf(base, cliente, oid)
        status, html = req(cliente, base, f'/os/{oid}/salvar',
                           {'csrf': token, 'cliente_id': str(cid), 'descricao': 'Serviço',
                            'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                            'materiais_presentes': '1', 'v9_execucao': 'exec',
                            'relatorio_tecnico': 'rel', 'acao_status': 'Concluída',
                            'modo_envio': 'encerrar', 'sem_nota_fiscal': '1',
                            'destinatario_sel[]': ['cliente', 'sindico', 'administradora'],
                            'emails_adicionais': 'extra@exemplo.com.br'})
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            reg = c.execute('SELECT destinatarios_json FROM produtividade_email WHERE os_id=?',
                            (oid,)).fetchone()
        self.assertEqual(sorted(json.loads(reg['destinatarios_json'])),
                         sorted(['cliente@exemplo.com.br', 'sindico@exemplo.com.br',
                                 'adm@exemplo.com.br', 'extra@exemplo.com.br']))

    def test_anexar_nota_fiscal_preserva_rascunho(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Multi', email='cliente@exemplo.com.br')
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço', 'tecnico': 'T',
                 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        servidor, base = self._servidor()
        cliente = self._login(base)
        token = self._csrf(base, cliente, oid)
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertIn('data-auto-upload-nf', html)
        self.assertIn(f'data-upload-url="/os/{self._numero(oid)}/nota-fiscal"', html)
        campos = [('csrf', token), ('cliente_id', str(cid)), ('descricao', 'Serviço'),
                  ('tecnico', 'T'), ('forma_pagamento', 'PIX'), ('valor_mao_obra', '10'),
                  ('materiais_presentes', '1'), ('v9_execucao', 'Execução preservada'),
                  ('relatorio_tecnico', 'Relato preservado')]
        status, html = multipart(cliente, base, f'/os/{oid}/nota-fiscal', campos,
                                 [('nota_fiscal', 'nf.pdf', PDF_MINIMO, 'application/pdf')])
        self.assertEqual(status, 200)
        self.assertIsNotNone(ext.ultima_nota_fiscal(self.db, oid))
        rasc = ext.obter_rascunho_web(self.db, oid, pid)
        self.assertEqual(rasc.get('v9_execucao'), 'Execução preservada')
        self.assertEqual(rasc.get('relatorio_tecnico'), 'Relato preservado')
        with ext.db(self.db) as c:
            nota = c.execute('SELECT id,caminho FROM os_notas_fiscais WHERE os_id=? '
                             'ORDER BY id DESC LIMIT 1', (oid,)).fetchone()
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertIn('PDF anexado', html)
        self.assertIn(f'/os/{self._numero(oid)}/nota-fiscal/{nota["id"]}/preview', html)
        self.assertIn(f'/os/{self._numero(oid)}/nota-fiscal/{nota["id"]}/remover', html)
        with cliente.open(base + f'/os/{oid}/nota-fiscal/{nota["id"]}/preview',
                          timeout=20) as resposta:
            self.assertEqual(resposta.status, 200)
            self.assertEqual(resposta.headers.get_content_type(), 'application/pdf')
            self.assertIn('inline', resposta.headers.get('Content-Disposition', ''))
        status, _ = req(cliente, base, f'/os/{oid}/nota-fiscal/{nota["id"]}/remover',
                        {'csrf': token})
        self.assertEqual(status, 200)
        self.assertIsNone(ext.ultima_nota_fiscal(self.db, oid))
        self.assertFalse(Path(nota['caminho']).exists())

    def test_rascunho_salva_nota_fiscal_anexada(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Multi', email='cliente@exemplo.com.br')
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço', 'tecnico': 'T',
                 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        servidor, base = self._servidor()
        cliente = self._login(base)
        token = self._csrf(base, cliente, oid)
        campos = [('csrf', token), ('cliente_id', str(cid)), ('descricao', 'Serviço'),
                  ('tecnico', 'T'), ('forma_pagamento', 'PIX'), ('valor_mao_obra', '10'),
                  ('materiais_presentes', '1'), ('v9_execucao', 'exec')]
        status, html = multipart(cliente, base, f'/os/{oid}/rascunho/salvar', campos,
                                 [('nota_fiscal', 'nf.pdf', PDF_MINIMO, 'application/pdf')])
        self.assertEqual(status, 200)
        self.assertIsNotNone(ext.ultima_nota_fiscal(self.db, oid))
        rasc = ext.obter_rascunho_web(self.db, oid, pid)
        self.assertEqual(rasc.get('v9_execucao'), 'exec')

    def test_reenvio_inclui_nota_fiscal_apos_conclusao(self):
        import time
        import os
        from flavors.autoseg.modules import gmail_service
        os.environ.pop('AUTOSEG_GMAIL_DESATIVADO', None)
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Multi', email='cliente@exemplo.com.br')
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço', 'tecnico': 'T',
                 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        conclusao = dict(dados)
        conclusao.update(acao_status='Concluída', v9_execucao='exec',
                         relatorio_tecnico='Relatório técnico final.')
        neg.os_salvar(self.db, conclusao, pid, oid)
        servidor, base = self._servidor()
        cliente = self._login(base)
        token = self._csrf(base, cliente, oid)
        # Anexa a NF DEPOIS da conclusão (a OS já está encerrada).
        status, html = multipart(cliente, base, f'/os/{oid}/nota-fiscal',
                                 [('csrf', token)],
                                 [('nota_fiscal', 'nf.pdf', PDF_MINIMO, 'application/pdf')])
        self.assertEqual(status, 200)
        self.assertIsNotNone(ext.ultima_nota_fiscal(self.db, oid))
        # Reenvia e verifica que a NF é anexada ao e-mail.
        capturado = {}
        def fake(destinatario, assunto, corpo, cc=None, caminho_pdf_relatorio=None,
                 caminho_pdf_nf=None, **kw):
            capturado['nf'] = caminho_pdf_nf
            return 'msg-ok'
        original = gmail_service.enviar_email_gmail
        gmail_service.enviar_email_gmail = fake
        try:
            status, html = req(cliente, base, f'/os/{oid}/reenviar-email', {'csrf': token})
            self.assertEqual(status, 200)
            for _ in range(50):
                with ext.db(self.db) as c:
                    r = c.execute('SELECT status FROM produtividade_email WHERE os_id=?',
                                  (oid,)).fetchone()
                if r and r['status'] in ('enviado', 'falhou'):
                    break
                time.sleep(0.05)
            self.assertTrue(str(capturado.get('nf', '')).endswith('.pdf'))
        finally:
            gmail_service.enviar_email_gmail = original

    def test_conclusao_exige_nota_fiscal_ou_nao_precisa(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Multi', email='cliente@exemplo.com.br')
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço', 'tecnico': 'T',
                 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        servidor, base = self._servidor()
        cliente = self._login(base)
        token = self._csrf(base, cliente, oid)
        base_form = {'csrf': token, 'cliente_id': str(cid), 'descricao': 'Serviço',
                     'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '10',
                     'materiais_presentes': '1', 'v9_execucao': 'exec',
                     'relatorio_tecnico': 'rel', 'acao_status': 'Concluída',
                     'modo_envio': 'encerrar'}
        # Sem NF e sem "não precisa" → bloqueado.
        status, html = req(cliente, base, f'/os/{oid}/salvar', dict(base_form))
        self.assertEqual(status, 400)
        self.assertIn('nota fiscal', html.lower())
        # Com "não precisa de nota fiscal" → permitido.
        status, html = req(cliente, base, f'/os/{oid}/salvar',
                           dict(base_form, sem_nota_fiscal='1'))
        self.assertEqual(status, 200)

    def test_pendente_publica_pdf_e_envia_email(self):
        import time
        import os
        from flavors.autoseg.modules import gmail_service
        os.environ.pop('AUTOSEG_GMAIL_DESATIVADO', None)
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Pendente', email='cliente@exemplo.com.br')
        dados = {'cliente_id': str(cid), 'descricao': 'Atendimento pendente', 'tecnico': 'T',
                 'forma_pagamento': 'PIX', 'valor_mao_obra': '100',
                 'materiais_presentes': '1', 'relatorio_tecnico': 'Aguardando peça.',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        servidor, base = self._servidor()
        cliente = self._login(base)
        token = self._csrf(base, cliente, oid)
        capt = {}
        def fake(destinatario, assunto, corpo, **kw):
            capt['assunto'] = assunto
            capt['corpo'] = corpo
            return 'msg-pend'
        original = gmail_service.enviar_email_gmail
        gmail_service.enviar_email_gmail = fake
        try:
            status, html = req(cliente, base, f'/os/{oid}/salvar',
                               {'csrf': token, 'cliente_id': str(cid),
                                'descricao': 'Atendimento pendente', 'tecnico': 'T',
                                'forma_pagamento': 'PIX', 'valor_mao_obra': '100',
                                'materiais_presentes': '1', 'v9_execucao': 'Parcial',
                                'relatorio_tecnico': 'Aguardando peça.',
                                'acao_status': 'Pendente', 'modo_envio': 'encerrar',
                                'sem_nota_fiscal': '1', 'destinatario_sel[]': ['cliente']})
            self.assertEqual(status, 200)
            doc = reg = None
            for _ in range(50):
                with ext.db(self.db) as c:
                    doc = c.execute("SELECT COUNT(*) FROM os_documentos WHERE os_id=? AND tipo='relatorio_pdf'",
                                    (oid,)).fetchone()[0]
                    reg = c.execute('SELECT status FROM produtividade_email WHERE os_id=?',
                                    (oid,)).fetchone()
                if doc and reg and reg['status'] in ('enviado', 'falhou'):
                    break
                time.sleep(0.05)
            self.assertGreaterEqual(doc, 1)
            self.assertIsNone(reg)
            with ext.db(self.db) as c:
                self.assertEqual(c.execute('SELECT status FROM ordens_servico WHERE id=?',
                                           (oid,)).fetchone()['status'], 'Pendente')
        finally:
            gmail_service.enviar_email_gmail = original

    def test_formulario_nao_tem_pagamento_nem_situacao_padrao(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Sem Padrão')
        dados = {'cliente_id': str(cid), 'descricao': 'Teste de seleção',
                 'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '0',
                 'materiais_presentes': '1', 'relatorio_tecnico': 'Teste',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        _, base = self._servidor()
        cliente = self._login(base)
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertRegex(html, r'<select id="c_forma_pagamento" name="forma_pagamento"[^>]*>\s*'
                               r'<option value=""[^>]*>Selecione a forma de pagamento</option>')
        self.assertIn('id="acao-status-os"', html)
        self.assertIn('name="situacao_popup"', html)
        self.assertIn('Confirmar situação da OS', html)
        self.assertIn('name="custo_materiais"', html)
        self.assertIn('Custo real dos materiais', html)
        vazio = dict(dados, forma_pagamento='', acao_status='salvar')
        with self.assertRaisesRegex(ValueError, 'Selecione a forma de pagamento'):
            neg.os_salvar(self.db, vazio, pid)

    def test_pdf_publicado_usa_o_numero_da_os_no_nome(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Numeração', email='cliente@exemplo.com.br')
        oid = self._os_concluida(pid, cid)
        with ext.db(self.db) as c:
            c.execute("UPDATE ordens_servico SET numero_os='OS-0099' WHERE id=?", (oid,))
        caminho = Path(fluxo.publicar_relatorio(self.db, oid))
        self.assertEqual(caminho.name, 'OS-0099_relatorio_v1.pdf')
        self.assertNotIn(f'OS_{oid}_', caminho.name)
        email = Path(ext.criar_email_rascunho(self.db, oid, str(caminho), pid))
        self.assertTrue(email.name.startswith('email_OS-0099_'))
        self.assertNotIn(f'email_os_{oid}', email.name)
        nota = Path(ext.criar_rascunho_fiscal(self.db, oid))
        self.assertEqual(nota.name, 'nota_fiscal_rascunho_OS-0099.json')

    def test_rateio_manual_apos_conclusao(self):
        a = self._prestador('Finalizador Manual', email='finalizador.manual@exemplo.com.br')
        b = self._prestador('Secundário Manual', email='secundario.manual@exemplo.com.br')
        cid = self._cliente(a, 'Condomínio Rateio Manual')
        oid = self._os_concluida(a, cid)
        with ext.db(self.db) as c:
            fid = c.execute('SELECT id FROM financeiro WHERE os_id=?', (oid,)).fetchone()['id']
        self.assertEqual(prod.definir_rateio_manual(self.db, oid, a, b, '300,00'), 30000)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT valor_centavos FROM produtividade_rateios '
                                       'WHERE os_id=? AND tecnico_id=?', (oid, b)).fetchone()[0], 30000)
        _, base = self._servidor()
        cliente = self._login(base, 'finalizador.manual@exemplo.com.br')
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertIn('Rateio e repasses', html)
        self.assertIn(f'formaction="/os/{self._numero(oid)}/rateio"', html)
        self.assertIn('R$ 300,00', html)
        self.assertEqual(prod.definir_rateio_manual(self.db, oid, a, b, '400,00'), 40000)
        with self.assertRaisesRegex(ValueError, 'ultrapassa'):
            prod.definir_rateio_manual(self.db, oid, a, b, '700,00')
        neg.financeiro_receber(self.db, fid, a)
        prod.confirmar_repasse(self.db, oid, a, b, '400,00')
        with self.assertRaisesRegex(ValueError, 'já enviado'):
            prod.definir_rateio_manual(self.db, oid, a, b, '0')

    def test_cancelar_pagamento_remove_do_financeiro(self):
        a = self._prestador('Finalizador Cancelar', email='finalizador.cancelar@exemplo.com.br')
        b = self._prestador('Secundário Cancelar', email='secundario.cancelar@exemplo.com.br')
        cid = self._cliente(a, 'Condomínio Pagamento Cancelado')
        oid = self._os_concluida(a, cid)
        with ext.db(self.db) as c:
            fid = c.execute('SELECT id FROM financeiro WHERE os_id=?', (oid,)).fetchone()['id']
        prod.definir_rateio_manual(self.db, oid, a, b, '300,00')
        neg.financeiro_cancelar(self.db, fid, a, 'Cliente não pagará o serviço.')
        with ext.db(self.db) as c:
            status = c.execute('SELECT status FROM financeiro WHERE id=?', (fid,)).fetchone()['status']
            rateio = c.execute('SELECT COUNT(*) FROM produtividade_rateios WHERE os_id=?',
                               (oid,)).fetchone()[0]
            repasse = c.execute('SELECT COUNT(*) FROM produtividade_repasses WHERE os_id=?',
                                (oid,)).fetchone()[0]
        self.assertEqual(status, 'Cancelado')
        self.assertEqual(rateio, 0)
        self.assertEqual(repasse, 0)
        pessoal = prod.financeiro_pessoal(self.db, a)
        self.assertFalse(any(x['os_id'] == oid for x in pessoal['brutos_proprios']))
        _, base = self._servidor()
        cliente = self._login(base, 'finalizador.cancelar@exemplo.com.br')
        _, html = req(cliente, base, '/financeiro')
        self.assertNotIn(f'href="/os/{self._numero(oid)}"', html)

    def test_admin_assume_os_de_outro(self):
        a = self._prestador('Responsável Original', email='original.assume@exemplo.com.br')
        b = self._prestador('Admin Assume', email='admin.assume@exemplo.com.br')
        cad.definir_admin(self.db, b, True)
        cid = self._cliente(a, 'Condomínio Assumir')
        dados = {'cliente_id': str(cid), 'descricao': 'Ajustar portão',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'materiais_presentes': '1',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, a)
        ext.atribuir(self.db, oid, a)
        _, base = self._servidor()
        cliente = self._login(base, 'admin.assume@exemplo.com.br')
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertIn('Responsável (admin)', html)
        self.assertIn(f'data-atribuir-url="/os/{self._numero(oid)}/atribuir"', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        status, _ = req(cliente, base, f'/os/{oid}/atribuir',
                        {'csrf': token, 'prestador_destino': str(b)})
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            self.assertEqual(ext.responsavel_atual(c, oid), b)

    def test_repasse_so_libera_apos_recebimento_do_cliente(self):
        a = self._prestador('Finalizador Repasse', email='finalizador.repasse@exemplo.com.br')
        b = self._prestador('Secundário Repasse', email='secundario.repasse@exemplo.com.br')
        cid = self._cliente(a, 'Condomínio Repasse')
        base_dados = {'cliente_id': str(cid), 'descricao': 'Serviço com repasse',
                      'tecnico': 'T', 'forma_pagamento': 'PIX',
                      'valor_mao_obra': '1000', 'materiais_presentes': '1',
                      'relatorio_tecnico': 'Serviço concluído',
                      'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, base_dados, a)
        ext.atribuir(self.db, oid, a)
        conclusao = dict(base_dados)
        conclusao.update(acao_status='Concluída', sem_nota_fiscal='1')
        conclusao['rateio_tecnico[]'] = [str(b)]
        conclusao['rateio_valor[]'] = ['300,00']
        neg.os_salvar(self.db, conclusao, a, oid)
        with ext.db(self.db) as c:
            fid = c.execute('SELECT id FROM financeiro WHERE os_id=?', (oid,)).fetchone()['id']
        with self.assertRaisesRegex(ValueError, 'Confirme o recebimento do cliente'):
            prod.confirmar_repasse(self.db, oid, a, b, '300,00')
        _, base = self._servidor()
        cliente_a = self._login(base, 'finalizador.repasse@exemplo.com.br')
        _, html_a = req(cliente_a, base, '/financeiro')
        self.assertNotIn('Registrar envio de R$ 300,00', html_a)
        self.assertIn('depois que você confirma o recebimento do cliente', html_a)
        cliente_b = self._login(base, 'secundario.repasse@exemplo.com.br')
        _, html_b = req(cliente_b, base, '/financeiro')
        self.assertIn('Aguardando cliente', html_b)
        self.assertNotIn('action="/financeiro/repasse/confirmar"', html_b)
        neg.financeiro_receber(self.db, fid, a)
        _, html_a = req(cliente_a, base, '/financeiro')
        self.assertIn('Registrar envio de R$ 300,00', html_a)
        self.assertIn(f'href="/os/{self._numero(oid)}"', html_a)
        _, html_b = req(cliente_b, base, '/financeiro')
        self.assertIn('Aguardando envio', html_b)
        self.assertNotIn('action="/financeiro/repasse/confirmar"', html_b)
        prod.confirmar_repasse(self.db, oid, a, b, '300,00')
        _, html_b = req(cliente_b, base, '/financeiro')
        self.assertIn('action="/financeiro/repasse/confirmar"', html_b)

    def test_financeiro_mostra_apenas_a_producao_do_prestador(self):
        a = self._prestador('Técnico A', email='tecnico.a@exemplo.com.br')
        b = self._prestador('Técnico B', email='tecnico.b@exemplo.com.br')
        cid = self._cliente(a, 'Condomínio Financeiro')
        base_dados = {'cliente_id': str(cid), 'descricao': 'Serviço com rateio',
                      'tecnico': 'T', 'forma_pagamento': 'PIX',
                      'valor_mao_obra': '1000', 'materiais_presentes': '1',
                      'relatorio_tecnico': 'Serviço concluído',
                      'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, base_dados, a)
        ext.atribuir(self.db, oid, a)
        conclusao = dict(base_dados)
        conclusao.update(acao_status='Concluída', sem_nota_fiscal='1')
        conclusao['rateio_tecnico[]'] = [str(b)]
        conclusao['rateio_valor[]'] = ['300,00']
        neg.os_salvar(self.db, conclusao, a, oid)
        with ext.db(self.db) as c:
            fid = c.execute('SELECT id FROM financeiro WHERE os_id=?', (oid,)).fetchone()['id']
        _, base = self._servidor()

        cliente_a = self._login(base, 'tecnico.a@exemplo.com.br')
        status, html = req(cliente_a, base, '/financeiro')
        self.assertEqual(status, 200)
        self.assertIn('<span>A receber</span><strong>R$ 700,00</strong>', html)
        self.assertIn('<span>Recebido</span><strong>R$ 0,00</strong>', html)
        self.assertIn('Dados bancários', html)
        self.assertIn('Lançamentos das OS em que participo', html)
        self.assertIn('A receber / Confirmar recebimento', html)
        self.assertIn('Recebidos', html)
        self.assertIn('finance-columns', html)
        self.assertIn('Minha parcela', html)
        self.assertLess(html.index('Dados bancários'), html.index('Lançamentos das OS em que participo'))
        self.assertIn(f'action="/financeiro/{fid}/receber"', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        req(cliente_a, base, f'/financeiro/{fid}/receber', {'csrf': token})
        _, html = req(cliente_a, base, '/financeiro')
        self.assertIn('<span>A receber</span><strong>R$ 0,00</strong>', html)
        self.assertIn('<span>Recebido</span><strong>R$ 700,00</strong>', html)
        self.assertNotIn(f'action="/financeiro/{fid}/receber"', html)

        cliente_b = self._login(base, 'tecnico.b@exemplo.com.br')
        status, html = req(cliente_b, base, '/financeiro')
        self.assertEqual(status, 200)
        self.assertIn('<span>A receber</span><strong>R$ 300,00</strong>', html)
        self.assertIn('Lançamentos das OS em que participo', html)
        self.assertIn('Aguardando envio', html)
        self.assertNotIn('action="/financeiro/repasse/confirmar"', html)

        prod.confirmar_repasse(self.db, oid, a, b, '300,00')
        _, html = req(cliente_b, base, '/financeiro')
        self.assertIn('<span>A receber</span><strong>R$ 300,00</strong>', html)
        self.assertIn('<span>Recebido</span><strong>R$ 0,00</strong>', html)
        self.assertIn('action="/financeiro/repasse/confirmar"', html)
        prod.confirmar_recebimento_repasse(self.db, oid, b)
        _, html = req(cliente_b, base, '/financeiro')
        self.assertIn('<span>A receber</span><strong>R$ 0,00</strong>', html)
        self.assertIn('<span>Recebido</span><strong>R$ 300,00</strong>', html)
        self.assertNotIn('action="/financeiro/repasse/confirmar"', html)

    def test_nao_admin_nao_edita_fotos_de_outro(self):
        a = self._prestador('Técnico Foto Responsável', email='foto.resp@exemplo.com.br')
        b = self._prestador('Técnico Foto Comum', email='foto.comum@exemplo.com.br')
        cid = self._cliente(a, 'Condomínio Foto Comum')
        dados = {'cliente_id': str(cid), 'descricao': 'Ajustar portão',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'valor_materiais_manual': '0',
                 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, a)
        ext.atribuir(self.db, oid, a)
        _, base = self._servidor()
        cliente_b = self._login(base, 'foto.comum@exemplo.com.br')
        _, html = req(cliente_b, base, f'/os/{oid}')
        self.assertNotIn('Salvar fotos e legendas', html)
        self.assertNotIn(f'formaction="/os/{self._numero(oid)}/rascunho/salvar"', html)
        self.assertIn('Somente o responsável ou administrador', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        buffer = io.BytesIO()
        Image.new('RGB', (4, 4), 'blue').save(buffer, 'PNG')
        status, _ = multipart(
            cliente_b, base, f'/os/{oid}/fotos',
            [('csrf', token)], [('imagens_encerramento[]', 'foto.png',
                                 buffer.getvalue(), 'image/png')])
        self.assertEqual(status, 403)

    def test_reordenar_fotos_atualiza_ordem(self):
        pid = self._prestador('Técnico Ordem', email='ordem@exemplo.com.br')
        cid = self._cliente(pid, 'Condomínio Ordem')
        dados = {'cliente_id': str(cid), 'descricao': 'Fotos ordenadas',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'materiais_presentes': '1',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        ext.atribuir(self.db, oid, pid)
        with ext.db(self.db) as c:
            for indice, cor in enumerate(((40, 0, 0), (0, 80, 0)), start=1):
                buffer = io.BytesIO()
                Image.new('RGB', (4, 4), cor).save(buffer, 'PNG')
                ext.registrar_imagem_transacao(
                    c, oid, pid, f'foto-{indice}.png', buffer.getvalue(),
                    permitir_colaboracao=True)
            ids = [r['id'] for r in c.execute(
                'SELECT id FROM os_anexos WHERE os_id=? ORDER BY ordem,id', (oid,))]
        self.assertEqual(len(ids), 2)
        ext.mover_anexo(self.db, oid, ids[1], 'up', pid)
        with ext.db(self.db) as c:
            ordem = [r['id'] for r in c.execute(
                'SELECT id FROM os_anexos WHERE os_id=? ORDER BY ordem,id', (oid,))]
        self.assertEqual(ordem, [ids[1], ids[0]])

    def test_admin_arquiva_os_sem_apagar_historico(self):
        a = self._prestador('Técnico Arquivar A', email='arquivar.a@exemplo.com.br')
        b = self._prestador('Técnico Arquivar B', email='arquivar.b@exemplo.com.br')
        cad.definir_admin(self.db, b, True)
        cid = self._cliente(a, 'Condomínio Arquivar')
        dados = {'cliente_id': str(cid), 'descricao': 'OS criada errada',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'materiais_presentes': '1',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, a)
        with self.assertRaises(PermissionError):
            ext.arquivar_os(self.db, oid, a)
        self.assertTrue(ext.arquivar_os(self.db, oid, b, ator='Admin teste',
                                        motivo='OS criada errada'))
        with ext.db(self.db) as c:
            row = c.execute('SELECT status,arquivada FROM ordens_servico WHERE id=?',
                            (oid,)).fetchone()
            evento = c.execute("SELECT acao FROM os_eventos WHERE os_id=? "
                               "AND acao='OS arquivada'", (oid,)).fetchone()
        self.assertEqual(row['status'], 'Aberta')
        self.assertEqual(row['arquivada'], 1)
        self.assertIsNotNone(evento)
        ids = [x['id'] for x in ext.listar_os_compartilhadas(self.db, 'status')]
        self.assertNotIn(oid, ids)
        with self.assertRaises(ValueError):
            neg.os_salvar(self.db, dados, a, oid)
        _, base = self._servidor()
        cliente_b = self._login(base, 'arquivar.b@exemplo.com.br')
        _, html = req(cliente_b, base, f'/os/{oid}')
        self.assertIn('OS arquivada', html)
        self.assertNotIn(f'formaction="/os/{self._numero(oid)}/rascunho/salvar"', html)

    def test_admin_arquiva_os_concluida(self):
        a = self._prestador('Técnico Arquivar Concluída', email='arquivar.concluida@exemplo.com.br')
        b = self._prestador('Admin Arquivar Concluída', email='arquivar.admin@exemplo.com.br')
        cad.definir_admin(self.db, b, True)
        cid = self._cliente(a, 'Condomínio Arquivar Concluída')
        dados = {'cliente_id': str(cid), 'descricao': 'OS concluída errada',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'materiais_presentes': '1',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, a)
        with ext.db(self.db) as c:
            c.execute("UPDATE ordens_servico SET status='Concluída' WHERE id=?", (oid,))
        self.assertTrue(ext.arquivar_os(self.db, oid, b, ator='Admin teste',
                                        motivo='OS concluída errada'))
        with ext.db(self.db) as c:
            row = c.execute('SELECT status,arquivada FROM ordens_servico WHERE id=?',
                            (oid,)).fetchone()
        self.assertEqual(row['status'], 'Concluída')
        self.assertEqual(row['arquivada'], 1)

    def test_importar_yaml_na_criacao_e_exportar_relatorio(self):
        pid = self._prestador('Técnico YAML OS', email='yaml.os@exemplo.com.br')
        cid = self._cliente(pid, 'Condomínio YAML OS')
        dados = {'cliente_id': str(cid), 'descricao': 'OS para exportar',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'materiais_presentes': '1',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, pid)
        cad.salvar_detalhes(self.db, oid, 'Diagnóstico exportado',
                            'Execução exportada', 'Resultado exportado')
        _, base = self._servidor()
        cliente = self._login(base, 'yaml.os@exemplo.com.br')
        _, html = req(cliente, base, '/os/nova')
        self.assertIn('Importar OS em YAML', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        yaml_os = (b'versao: 1\nos:\n  diagnostico: Diagnostico importado\n'
                   b'  execucao: Execucao importada\n  relatorio_tecnico: Relato importado\n')
        status, body = multipart(
            cliente, base, '/os/yaml',
            [('csrf', token)],
            [('yaml', 'relatorio.yaml', yaml_os, 'application/x-yaml')])
        self.assertEqual(status, 200)
        self.assertIn('Diagnostico importado', body)
        self.assertIn('Execucao importada', body)
        _, html = req(cliente, base, f'/os/{oid}')
        self.assertNotIn('Importar OS em YAML', html)
        status, texto = req(cliente, base, f'/os/{oid}/relatorio.yaml')
        self.assertEqual(status, 200)
        self.assertIn('versao: 1', texto)
        self.assertIn('Diagnóstico exportado', texto)

    def test_admin_cancela_os_de_outro(self):
        a = self._prestador('Técnico Cancelar A', email='cancelar.a@exemplo.com.br')
        b = self._prestador('Admin Cancelar B', email='cancelar.b@exemplo.com.br')
        cad.definir_admin(self.db, b, True)
        cid = self._cliente(a, 'Condomínio Cancelar Admin')
        dados = {'cliente_id': str(cid), 'descricao': 'Serviço a cancelar pelo admin',
                 'tecnico': 'T', 'forma_pagamento': 'PIX',
                 'valor_mao_obra': '100', 'materiais_presentes': '1',
                 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, dados, a)
        with ext.db(self.db) as c:
            numero = c.execute('SELECT numero_os FROM ordens_servico WHERE id=?',
                               (oid,)).fetchone()['numero_os']
        cancelamento = dict(dados)
        cancelamento.update({
            'cancelar_os': '1', 'confirmar_numero_os': numero,
            'motivo_encerramento': 'Cancelamento administrativo.',
            'relatorio_tecnico': 'OS cancelada pelo administrador.',
        })
        neg.os_salvar(self.db, cancelamento, b, oid)
        with ext.db(self.db) as c:
            status = c.execute('SELECT status FROM ordens_servico WHERE id=?',
                               (oid,)).fetchone()['status']
        self.assertEqual(status, 'Cancelada')

    def test_dados_bancarios_site_gtk_e_email_usam_o_mesmo_campo(self):
        pid = self._prestador('Técnico Banco Único', email='banco.unico@exemplo.com.br')
        cid = self._cliente(pid, 'Condomínio Banco Único',
                            email='cliente.banco@exemplo.com.br')
        oid = self._os_concluida(pid, cid)
        _, base = self._servidor()
        cliente = self._login(base, 'banco.unico@exemplo.com.br')
        _, html = req(cliente, base, '/financeiro')
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        texto = 'PIX: banco-unico@exemplo.com\nAgência 0001\nConta 12345-6'
        status, _ = req(cliente, base, '/financeiro/banco/salvar',
                         {'csrf': token, 'dados_bancarios': texto})
        self.assertEqual(status, 200)
        config = ext.obter_config_prestador(self.db, pid)
        self.assertEqual(config['dados_bancarios_texto'], texto)
        with ext.db(self.db) as c:
            legado = c.execute('SELECT dados_texto FROM produtividade_bancos WHERE prestador_id=?',
                               (pid,)).fetchone()
        self.assertIsNone(legado)
        corpo_html = gmail_service._dados_pagamento_html(self.db, oid)
        self.assertIn('banco-unico@exemplo.com', corpo_html)
        self.assertIn('Conta 12345-6', corpo_html)
        import email
        pdf = Path(self.tmp.name) / 'relatorio.pdf'
        pdf.write_bytes(PDF_MINIMO)
        arq = Path(ext.criar_email_rascunho(self.db, oid, str(pdf), pid))
        msg = email.message_from_bytes(arq.read_bytes(), policy=email.policy.default)
        corpo_eml = msg.get_body(preferencelist=('plain',)).get_content()
        self.assertIn('banco-unico@exemplo.com', corpo_eml)
        self.assertIn('Conta 12345-6', corpo_eml)

    def test_migracao_do_texto_bancario_antigo_do_portal(self):
        pid = self._prestador('Técnico Legado', email='legado.banco@exemplo.com.br')
        ext.salvar_config_prestador(self.db, pid,
                                    {'dados_bancarios_texto': 'Conta antiga do GTK'})
        with ext.db(self.db) as c:
            c.execute("UPDATE prestadores_config SET atualizado_em=? WHERE prestador_id=?",
                      ('2026-01-01 10:00:00', pid))
            c.execute('''INSERT INTO produtividade_bancos(prestador_id,dados_texto,atualizado_em)
                         VALUES(?,?,?)''',
                      (pid, 'Conta nova do site', '2026-01-02 10:00:00'))
        config = ext.obter_config_prestador(self.db, pid)
        self.assertEqual(config['dados_bancarios_texto'], 'Conta nova do site')
        with ext.db(self.db) as c:
            oficial = c.execute('SELECT dados_bancarios_texto FROM prestadores_config '
                                'WHERE prestador_id=?', (pid,)).fetchone()
        self.assertEqual(oficial['dados_bancarios_texto'], 'Conta nova do site')
        with ext.db(self.db) as c:
            c.execute('''UPDATE prestadores_config SET dados_bancarios_texto=?,
                         atualizado_em=? WHERE prestador_id=?''',
                      ('Conta GTK mais nova', '2026-02-01 10:00:00', pid))
            c.execute("UPDATE produtividade_bancos SET dados_texto=?,atualizado_em=? "
                      "WHERE prestador_id=?",
                      ('Conta site antiga', '2026-01-02 10:00:00', pid))
        self.assertEqual(ext.obter_config_prestador(self.db, pid)['dados_bancarios_texto'],
                         'Conta GTK mais nova')

    def test_garantia_mao_obra_zero_material_cobrado(self):
        """Garantia: mão de obra 0,00 + material cobrado deve concluir e cobrar só o material."""
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Garantia')
        dados = {'cliente_id': str(cid), 'descricao': 'Reparo em garantia',
                 'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '0',
                 'materiais_presentes': '1', 'material_item[]': ['Cabo de 4 vias'],
                 'material_qtd[]': ['2.5'], 'material_unit[]': ['30,20'],
                 'relatorio_tecnico': 'Serviço em garantia; material cobrado.',
                 'acao_status': 'Concluída'}
        oid = neg.os_salvar(self.db, dados, pid)
        with ext.db(self.db) as c:
            os_ = c.execute('SELECT status,valor_mao_obra,valor_materiais,valor_total '
                            'FROM ordens_servico WHERE id=?', (oid,)).fetchone()
            fin = c.execute('SELECT valor,status FROM financeiro WHERE os_id=?',
                            (oid,)).fetchone()
        self.assertEqual(os_['status'], 'Concluída')
        self.assertEqual(float(os_['valor_mao_obra']), 0.0)
        self.assertAlmostEqual(float(os_['valor_materiais']), 75.5, places=2)
        self.assertAlmostEqual(float(os_['valor_total']), 75.5, places=2)
        self.assertIsNotNone(fin)
        self.assertAlmostEqual(float(fin['valor']), 75.5, places=2)

    def test_garantia_total_sem_cobranca_nao_cria_financeiro(self):
        """Garantia total: total 0,00 conclui sem criar lançamento de R$ 0,00."""
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Garantia Total')
        dados = {'cliente_id': str(cid), 'descricao': 'Reparo em garantia total',
                 'tecnico': 'T', 'forma_pagamento': 'PIX', 'valor_mao_obra': '0',
                 'materiais_presentes': '1', 'material_item[]': [''],
                 'material_qtd[]': [''], 'material_unit[]': [''],
                 'custo_materiais': '75.50',
                 'relatorio_tecnico': 'Serviço em garantia, sem cobrança.',
                 'acao_status': 'Concluída'}
        oid = neg.os_salvar(self.db, dados, pid)
        with ext.db(self.db) as c:
            os_ = c.execute('SELECT status,valor_total,custo_materiais FROM ordens_servico WHERE id=?',
                            (oid,)).fetchone()
            fin = c.execute('SELECT COUNT(*) FROM financeiro WHERE os_id=?',
                            (oid,)).fetchone()[0]
        self.assertEqual(os_['status'], 'Concluída')
        self.assertEqual(float(os_['valor_total']), 0.0)
        self.assertAlmostEqual(float(os_['custo_materiais']), 75.5, places=2)
        self.assertEqual(fin, 0)

    def test_completude_trata_zero_como_valor_presente(self):
        self.assertFalse(completude._vazio(0))
        self.assertFalse(completude._vazio(0.0))
        self.assertTrue(completude._vazio(None))
        self.assertTrue(completude._vazio(''))

    def test_orcamento_avulso_gera_pdf_sem_criar_os(self):
        pid = self._prestador()
        cid = self._cliente(pid, 'Condomínio Orçamento')
        sid = cat.salvar(self.db, {
            'nome': 'Revisão de portão', 'descricao': 'Revisão preventiva',
            'preco_servico': '150,00', 'tempo_horas': '1',
            'relatorio_padrao': 'Revisão realizada.',
            'materiais': 'Lubrificante | 1 | 25,00'})
        with ext.db(self.db) as c:
            for indice in range(110):
                c.execute("INSERT INTO clientes(nome,status) VALUES(?, 'Ativo')",
                          (f'Cliente Busca {indice:03d}',))
        _, base = self._servidor()
        cliente = self._login(base)
        status, html = req(cliente, base, '/orcamento')
        self.assertEqual(status, 200)
        self.assertIn('Cliente Busca 109', html)
        self.assertIn('Orçamento (não é OS)', html)
        self.assertIn('Nenhuma ordem de serviço', html)
        self.assertIn('id="busca-cliente-os"', html)
        self.assertIn('name="cliente_id"', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        with ext.db(self.db) as c:
            antes = c.execute('SELECT COUNT(*) FROM ordens_servico').fetchone()[0]
        pedido = urllib.request.Request(
            base + '/orcamento/pdf',
            urllib.parse.urlencode({'csrf': token, 'cliente_id': str(cid),
                                    'servico_id': str(sid), 'quantidade': '1'}).encode())
        with cliente.open(pedido, timeout=30) as resposta:
            self.assertEqual(resposta.status, 200)
            self.assertEqual(resposta.headers.get_content_type(), 'application/pdf')
            self.assertTrue(resposta.read().startswith(b'%PDF'))
        with ext.db(self.db) as c:
            depois = c.execute('SELECT COUNT(*) FROM ordens_servico').fetchone()[0]
        self.assertEqual(antes, depois)

    def test_yaml_corrigido_da_garantia_e_aceito(self):
        original = Path.home() / 'Downloads' / 'chatgpt erros' / 'relatorio_os_preenchido.yaml'
        if not original.is_file():
            self.skipTest('Arquivo de exemplo do ChatGPT não está disponível.')
        with self.assertRaisesRegex(ValueError, 'quantidade'):
            importacao_yaml.relatorio(original.name, original.read_bytes())
        corrigido = original.with_name('relatorio_os_preenchido_corrigido.yaml')
        dados = importacao_yaml.relatorio(corrigido.name, corrigido.read_bytes())
        self.assertIn('v9_diagnostico', dados)
        self.assertEqual(len(dados['material_yaml']), 1)
        self.assertEqual(dados['material_yaml'][0]['item'], 'Cabo de 4 vias')
        self.assertAlmostEqual(
            dados['material_yaml'][0]['quantidade'] * dados['material_yaml'][0]['valor_unitario'],
            20.0, places=2)


if __name__ == '__main__':
    unittest.main()