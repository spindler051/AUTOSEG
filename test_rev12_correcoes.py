"""Correções pós-REV12: OS rápida, PDFs, CNPJ de prestador, exclusões e e-mails.

Usa exclusivamente banco e pastas temporárias; nenhum e-mail real é enviado.
"""
import http.cookiejar
import io
import json
import re
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import atendimento_os as aten
import cadastros_v9 as cad
import catalogo_servicos as cat
import completude
import estoque_materiais as estoque
import fluxo_os as fluxo
import gmail_service
import importacao_yaml
import pdf_cliente_v9
import portal_negocios as neg
import prestadores_ext as ext
import produtividade_os as prod
from banco import criar_banco
from portal_prestador import PortalPrestador
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
        self.assertIn('name="q"', html)
        self.assertIn('Condomínio Alfa', html)
        self.assertIn('Empresa Beta', html)
        self.assertIn('Abrir OS para este cliente', html)

        status, html = req(cliente, base, '/os/rapida?q=Alfa')
        self.assertEqual(status, 200)
        self.assertIn('Condomínio Alfa', html)
        self.assertNotIn('Empresa Beta', html)

        status, html = req(cliente, base, f'/os/rapida?cliente={alfa}')
        self.assertEqual(status, 200)
        self.assertIn('name="cliente_id"', html)
        self.assertIn('name="descricao"', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        status, html = req(cliente, base, '/os/rapida/salvar',
                           {'csrf': token, 'cliente_id': str(alfa),
                            'descricao': 'Portão da garagem não abre.',
                            'forma_pagamento': 'PIX'})
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            ordem = c.execute('SELECT cliente_id,status,descricao FROM ordens_servico '
                              'ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(ordem['cliente_id'], alfa)
        self.assertEqual(ordem['status'], 'Aberta')
        self.assertIn('Portão da garagem', ordem['descricao'])

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
        import gmail_service
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
        import gmail_service
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
            self.assertEqual(reg['status'], 'enviado')
            self.assertIn('pendente', capt['assunto'].lower())
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
        self.assertRegex(html, r'<select id="c_acao_status" name="acao_status"[^>]*>\s*'
                               r'<option value=""[^>]*>Selecione a situação</option>')
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
        self.assertIn('A receber (minha produção)</span><strong>R$ 700,00</strong>', html)
        self.assertIn('Recebido (minha produção)</span><strong>R$ 0,00</strong>', html)
        self.assertIn('Minha parcela', html)
        token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
        req(cliente_a, base, f'/financeiro/{fid}/receber', {'csrf': token})
        _, html = req(cliente_a, base, '/financeiro')
        self.assertIn('A receber (minha produção)</span><strong>R$ 0,00</strong>', html)
        self.assertIn('Recebido (minha produção)</span><strong>R$ 700,00</strong>', html)

        cliente_b = self._login(base, 'tecnico.b@exemplo.com.br')
        status, html = req(cliente_b, base, '/financeiro')
        self.assertEqual(status, 200)
        self.assertIn('A receber (minha produção)</span><strong>R$ 300,00</strong>', html)
        self.assertIn('Minha produção como técnico secundário', html)

        prod.confirmar_repasse(self.db, oid, a, b, '300,00')
        _, html = req(cliente_b, base, '/financeiro')
        self.assertIn('A receber (minha produção)</span><strong>R$ 0,00</strong>', html)
        self.assertIn('Recebido (minha produção)</span><strong>R$ 300,00</strong>', html)

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
        _, base = self._servidor()
        cliente = self._login(base)
        status, html = req(cliente, base, '/orcamento')
        self.assertEqual(status, 200)
        self.assertIn('Orçamento (não é OS)', html)
        self.assertIn('Nenhuma ordem de serviço é criada', html)
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
