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
import estoque_materiais as estoque
import fluxo_os as fluxo
import gmail_service
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
                            'descricao': 'Portão da garagem não abre.'})
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


if __name__ == '__main__':
    unittest.main()
