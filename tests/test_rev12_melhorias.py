"""Testes das 7 melhorias REV12 (banco temporário, sem dados reais)."""
import http.cookiejar
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from officina.core import atendimento_os as aten
from officina.core import cadastros_v9 as cad
from officina.core import catalogo_servicos as cat
from flavors.autoseg.modules import cliente_fluxo_v94 as fluxo_pf
from officina.core import fluxo_os as fluxo
from flavors.autoseg.modules import pdf_cliente_v9
from officina.core import portal_negocios as neg
from officina.core import prestadores_ext as ext
from officina.core import produtividade_os as prod
from officina.core.banco import criar_banco
from test_v9 import cpf


def browser():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def req(client, base, path, data=None, binary=False):
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    pedido = urllib.request.Request(base + path, body)
    try:
        with client.open(pedido, timeout=20) as resposta:
            bruto = resposta.read()
            return resposta.status, (bruto if binary else bruto.decode('utf-8', 'replace'))
    except urllib.error.HTTPError as erro:
        bruto = erro.read()
        return erro.code, (bruto if binary else bruto.decode('utf-8', 'replace'))


def csrf(html):
    achado = re.search(r'name="csrf" value="([^"]+)"', html)
    assert achado, 'CSRF não encontrado'
    return achado.group(1)


def multipart(client, base, path, campos, arquivos):
    fronteira = '----autosegrev12' + uuid.uuid4().hex
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
            return resposta.status, resposta.read()
    except urllib.error.HTTPError as erro:
        bruto = erro.read()
        return erro.code, (bruto if binary else bruto.decode('utf-8', 'replace'))


class MelhoriasRev12(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_rev12_')
        self.dir = Path(self.tmp.name)
        self.db = str(self.dir / 'teste.db')
        criar_banco(self.db)
        for modulo in (ext, fluxo, aten, cad, cat, prod):
            modulo.instalar(self.db)
        ext.ANEXOS = self.dir / 'anexos'
        ext.RELATORIOS = self.dir / 'relatorios'
        ext.RASCUNHOS = self.dir / 'rascunhos'
        ext.NOTAS = self.dir / 'notas_fiscais'
        for pasta in (ext.ANEXOS, ext.RELATORIOS, ext.RASCUNHOS, ext.NOTAS):
            pasta.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _client_portal(self, document='52998224725', password='Senha-Boa-123456'):
        """Provision converted identity and use only the unified HTTP origin."""
        from unittest.mock import patch
        from flavors.autoseg.modules import accounts
        from flavors.autoseg.modules.portal_prestador import PortalPrestador
        uid = cad.cadastrar_usuario(self.db, 'Cliente de teste', document,
                                    '51999998888', password, 'cliente-rev12@example.test')
        accounts.install(self.db)
        accounts.migrate_legacy(self.db, dry_run=False)
        flag = patch.dict(os.environ, {'AUTOSEG_UNIFIED_LOGIN': '1'})
        flag.start()
        self.addCleanup(flag.stop)
        servidor = PortalPrestador(self.db, '127.0.0.1', 0)
        servidor.iniciar()
        self.addCleanup(servidor.parar)
        base = f'http://127.0.0.1:{servidor.porta}'
        cliente = browser()
        status, html = req(cliente, base, '/login',
                           {'identificador': document, 'senha': password})
        self.assertEqual(status, 200)
        self.assertIn('Minhas ordens de serviço', html)
        return uid, cliente, base

    # ---------------------------------------------------------------- 1
    def test_alteracao_de_senha_http(self):
        document, old, new = '52998224725', 'Senha-Antiga-123', 'Senha-Nova-456'
        _, cliente, base = self._client_portal(document, old)
        status, html = req(cliente, base, '/cliente/senha')
        self.assertEqual(status, 200)
        token = csrf(html)
        status, html = req(cliente, base, '/cliente/senha', {
            'csrf': token, 'senha_atual': 'errada', 'nova_senha': new,
            'confirmar_senha': new})
        self.assertEqual(status, 409)
        self.assertIn('Senha atual incorreta', html)
        status, html = req(cliente, base, '/cliente/senha', {
            'csrf': token, 'senha_atual': old, 'nova_senha': new,
            'confirmar_senha': new})
        self.assertEqual(status, 200)
        self.assertIn('Officina Web', html)
        outro = browser()
        _, html = req(outro, base, '/login', {'identificador': document, 'senha': old})
        self.assertNotIn('Minhas ordens de serviço', html)
        _, html = req(outro, base, '/login', {'identificador': document, 'senha': new})
        self.assertIn('Minhas ordens de serviço', html)

    # ---------------------------------------------------------------- 2
    def test_chamado_condominio_exige_nome_e_telefone(self):
        _, cliente, base = self._client_portal()
        dados_cli = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados_cli.update(nome='Condomínio Teste', tipo_pessoa='Jurídica',
                         status='Ativo', documento='12345678000195')
        cid = neg.cliente_salvar(self.db, dados_cli, 0)
        with ext.db(self.db) as c:
            org = c.execute('SELECT id FROM v9_organizacoes WHERE cliente_id=?',
                            (cid,)).fetchone()['id']
        status, html = req(cliente, base, f'/cliente/chamado/novo?org={org}')
        self.assertEqual(status, 200)
        token = csrf(html)
        self.assertIn('solicitante_telefone', html)
        form = {'csrf': token, 'org_id': str(org), 'papel': 'Morador',
                'unidade': 'Apto 101', 'urgencia': 'Normal',
                'solicitante_nome': 'Cliente Teste',
                'descricao': 'Portão da garagem não abre corretamente.'}
        status, html = req(cliente, base, '/cliente/chamado/novo', form)
        self.assertEqual(status, 409)
        self.assertIn('telefone', html.lower())
        form['solicitante_telefone'] = '51999998888'
        status, html = req(cliente, base, '/cliente/chamado/novo', form)
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            chamado = c.execute('SELECT * FROM v9_chamados ORDER BY id DESC LIMIT 1').fetchone()
            self.assertEqual(chamado['solicitante_nome'], 'Cliente Teste')
            self.assertEqual(chamado['solicitante_telefone'], '51999998888')
            obs = c.execute('SELECT observacoes FROM ordens_servico WHERE id=?',
                            (chamado['os_id'],)).fetchone()['observacoes']
            self.assertIn('51999998888', obs)

    # ---------------------------------------------------------------- 3/6
    def test_multiplos_destinatarios_e_bcc(self):
        pid = ext.cadastrar(self.db, 'Técnico', 'tec@example.org', 'senha-bem-segura-2026')
        dados = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados.update(nome='Condomínio Multi', tipo_pessoa='Jurídica', status='Ativo',
                     email='cliente@example.org', sindico_email='sindico@example.org',
                     administradora_email='adm@example.org')
        cid = neg.cliente_salvar(self.db, dados, pid)
        d = {'cliente_id': str(cid), 'descricao': 'Serviço multi', 'tecnico': 'T',
             'forma_pagamento': 'PIX', 'valor_mao_obra': '10', 'valor_materiais_manual': '0',
             'relatorio_tecnico': 'x', 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, d, pid)
        self.assertEqual(len(prod.destinatarios_para_os(
            self.db, oid, ['sindico', 'cliente', 'administradora'], 'extra@example.org')), 4)
        self.assertEqual(len(prod.destinatarios_para_os(self.db, oid, ['cliente'], '')), 1)

    # ---------------------------------------------------------------- 4
    def test_pdf_logo_e_selo_em_todas_as_paginas(self):
        import pypdf
        pid = ext.cadastrar(self.db, 'Técnico', 'tec@example.org', 'senha-bem-segura-2026')
        dados = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados.update(nome='Cliente PDF', tipo_pessoa='Física', status='Ativo')
        cid = neg.cliente_salvar(self.db, dados, pid)
        d = {'cliente_id': str(cid), 'descricao': 'Serviço longo', 'tecnico': 'T',
             'forma_pagamento': 'PIX', 'valor_mao_obra': '10', 'valor_materiais_manual': '0',
             'relatorio_tecnico': 'x', 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, d, pid)
        ext.atribuir(self.db, oid, pid)
        with ext.db(self.db) as c:
            for i in range(45):
                c.execute('INSERT INTO materiais_os(os_id,item,quantidade,valor_unitario,valor_total) '
                          'VALUES(?,?,?,?,?)', (oid, f'Material {i}', 1, 1, 1))
        conclusao = dict(d)
        conclusao['acao_status'] = 'Concluída'
        conclusao['relatorio_tecnico'] = ('Relatório técnico detalhado. ' * 90)[:4900]
        neg.os_salvar(self.db, conclusao, pid, oid)
        caminho = pdf_cliente_v9.gerar(self.db, oid)
        leitor = pypdf.PdfReader(caminho)
        self.assertGreaterEqual(len(leitor.pages), 2)
        self.assertGreaterEqual(len(leitor.pages[0].images), 2)
        for pagina in leitor.pages[1:]:
            self.assertGreaterEqual(len(pagina.images), 1)

        materiais = '\n'.join(f'Material {i} | 1 | 10,00' for i in range(30))
        sid = cat.salvar(self.db, {'nome': 'Serviço PDF', 'descricao': 'Descrição',
                                   'preco_servico': '100', 'materiais': materiais})
        orcamento = cat.pdf_orcamento(self.db, sid, 5, 'Cliente PDF')
        destino = self.dir / 'orcamento.pdf'
        destino.write_bytes(orcamento)
        leitor = pypdf.PdfReader(str(destino))
        self.assertGreaterEqual(len(leitor.pages), 2)
        self.assertGreaterEqual(len(leitor.pages[0].images), 2)
        for pagina in leitor.pages[1:]:
            self.assertGreaterEqual(len(pagina.images), 1)

    # ---------------------------------------------------------------- 5
    def test_nota_fiscal_upload_download_e_deduplicacao(self):
        from flavors.autoseg.modules.portal_prestador import PortalPrestador
        pid = ext.cadastrar(self.db, 'Prestador NF', 'nf@example.org', 'senha-bem-segura-2026')
        dados = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados.update(nome='Cliente NF', tipo_pessoa='Física', status='Ativo')
        cid = neg.cliente_salvar(self.db, dados, pid)
        d = {'cliente_id': str(cid), 'descricao': 'Serviço NF', 'tecnico': 'T',
             'forma_pagamento': 'PIX', 'valor_mao_obra': '10', 'valor_materiais_manual': '0',
             'relatorio_tecnico': 'x', 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, d, pid)
        ext.atribuir(self.db, oid, pid)
        servidor = PortalPrestador(self.db, '127.0.0.1', 0)
        servidor.iniciar()
        self.addCleanup(servidor.parar)
        base = f'http://127.0.0.1:{servidor.servidor.server_port}'
        prestador = browser()
        status, html = req(prestador, base, '/login',
                           {'email': 'nf@example.org', 'senha': 'senha-bem-segura-2026'})
        token = csrf(html)
        pdf = b'%PDF-1.4\n% nota fiscal ficticia\n%%EOF\n'
        status, corpo = multipart(prestador, base, f'/os/{oid}/nota-fiscal',
                                  [('csrf', token)], [('nota_fiscal', 'nf.pdf', pdf, 'application/pdf')])
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            notas = c.execute('SELECT * FROM os_notas_fiscais WHERE os_id=?', (oid,)).fetchall()
        self.assertEqual(len(notas), 1)
        nid = notas[0]['id']
        status, corpo = multipart(prestador, base, f'/os/{oid}/nota-fiscal',
                                  [('csrf', token)], [('nota_fiscal', 'nf.pdf', pdf, 'application/pdf')])
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM os_notas_fiscais WHERE os_id=?',
                                       (oid,)).fetchone()[0], 1)
        status, dados_pdf = req(prestador, base, f'/os/{oid}/nota-fiscal/{nid}', binary=True)
        self.assertEqual(status, 200)
        self.assertTrue(dados_pdf.startswith(b'%PDF'))
        outro = ext.cadastrar(self.db, 'Outro', 'outro@example.org', 'senha-bem-segura-2026')
        intruso = browser()
        req(intruso, base, '/login', {'email': 'outro@example.org', 'senha': 'senha-bem-segura-2026'})
        status, corpo = req(intruso, base, f'/os/{oid}/nota-fiscal/{nid}', binary=True)
        self.assertIn(status, (403, 404))

    # ---------------------------------------------------------------- 7
    def test_atribuir_sindico_reutiliza_mesmo_nucleo(self):
        dados = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados.update(nome='Condomínio Síndico', tipo_pessoa='Jurídica', status='Ativo',
                     documento='11222333000181')
        cid = neg.cliente_salvar(self.db, dados, 0)
        with ext.db(self.db) as c:
            org = c.execute('SELECT id FROM v9_organizacoes WHERE cliente_id=?', (cid,)).fetchone()['id']
        uid = fluxo_pf.criar_conta(self.db, cpf(545678901), 'Senha-Boa-123456')
        papel = cad.atribuir_responsavel(self.db, org, uid, 'Desktop AUTOSEG')
        self.assertEqual(papel, 'Síndico')
        with ext.db(self.db) as c:
            r = c.execute('SELECT usuario_id,papel FROM v9_responsaveis WHERE organizacao_id=?',
                          (org,)).fetchone()
            v = c.execute('SELECT papel,situacao FROM v9_vinculos WHERE organizacao_id=? AND usuario_id=?',
                          (org, uid)).fetchone()
        self.assertEqual(r['usuario_id'], uid)
        self.assertEqual(r['papel'], 'Síndico')
        self.assertEqual(v['situacao'], 'Aprovado')
        cad.remover_responsavel(self.db, org, 'Desktop AUTOSEG')
        with ext.db(self.db) as c:
            self.assertIsNone(c.execute('SELECT 1 FROM v9_responsaveis WHERE organizacao_id=?',
                                        (org,)).fetchone())

    def test_os_rapida_cria_aberta_e_atribuicao_nao_muda_status(self):
        from flavors.autoseg.modules.portal_prestador import PortalPrestador
        pid = ext.cadastrar(self.db, 'Prestador Rápido', 'rapido@example.org', 'senha-bem-segura-2026')
        dados = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados.update(nome='Condomínio Rápido', tipo_pessoa='Jurídica', status='Ativo')
        cid = neg.cliente_salvar(self.db, dados, pid)
        servidor = PortalPrestador(self.db, '127.0.0.1', 0)
        servidor.iniciar()
        self.addCleanup(servidor.parar)
        base = f'http://127.0.0.1:{servidor.servidor.server_port}'
        prestador = browser()
        status, html = req(prestador, base, '/login',
                           {'email': 'rapido@example.org', 'senha': 'senha-bem-segura-2026'})
        token = csrf(html)
        status, html = req(prestador, base, '/os/rapida')
        self.assertEqual(status, 200)
        self.assertIn('Nova ordem de serviço', html)
        status, html = req(prestador, base, '/os/rapida/salvar', {
            'csrf': token, 'cliente_texto': f'{cid} — Condomínio Rápido',
            'descricao': 'Solicitação criada pelo fluxo rápido', 'prestador_id': str(pid),
            'forma_pagamento': 'PIX'})
        self.assertEqual(status, 200)
        with ext.db(self.db) as c:
            row = c.execute("SELECT id,status FROM ordens_servico WHERE descricao LIKE '%fluxo rápido%'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['status'], 'Aberta')
            self.assertEqual(c.execute('SELECT prestador_id FROM os_responsaveis WHERE os_id=?',
                                       (row['id'],)).fetchone()['prestador_id'], pid)
            # Atribuir novamente não muda o status.
            ext.atribuir(self.db, row['id'], pid)
            self.assertEqual(c.execute('SELECT status FROM ordens_servico WHERE id=?',
                                       (row['id'],)).fetchone()['status'], 'Aberta')

    def test_logo_e_icone_na_origem_unica(self):
        from flavors.autoseg.modules.portal_prestador import PortalPrestador
        servidor = PortalPrestador(self.db, '127.0.0.1', 0)
        servidor.iniciar()
        self.addCleanup(servidor.parar)
        base = f'http://127.0.0.1:{servidor.porta}'
        for rota in ('/logo.png', '/icone.png'):
            status, image = req(browser(), base, rota, binary=True)
            self.assertEqual(status, 200)
            self.assertTrue(image.startswith(b'\x89PNG'))

    def test_yaml_modelo_com_instrucoes_e_saida_estrita(self):
        from flavors.autoseg.modules import importacao_yaml as iy
        modelo = (Path(__file__).parents[1] / 'flavors/autoseg/templates/modelo_relatorio_os.yaml').read_bytes()
        self.assertEqual(iy.relatorio('modelo_relatorio_os.yaml', modelo), {})
        saida = ('versao: 1\nos:\n  diagnostico: Diagnóstico X\n  execucao: Execução Y\n'
                 '  resultado: OK\n  relatorio_tecnico: Recomendação Z\n  materiais: []\n').encode('utf-8')
        dados = iy.relatorio('saida.yaml', saida)
        self.assertEqual(dados['v9_diagnostico'], 'Diagnóstico X')
        with self.assertRaises(ValueError):
            iy.relatorio('ruim.yaml', b'versao: 1\ninstrucoes: {}\nos: {}\n')

    def test_form_os_um_rascunho_e_nota_apos_fotos(self):
        from flavors.autoseg.modules.portal_prestador import PortalPrestador
        pid = ext.cadastrar(self.db, 'Prestador Form', 'form@example.org', 'senha-bem-segura-2026')
        dados = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados.update(nome='Cliente Form', tipo_pessoa='Física', status='Ativo')
        cid = neg.cliente_salvar(self.db, dados, pid)
        d = {'cliente_id': str(cid), 'descricao': 'Serviço do formulário', 'tecnico': 'T',
             'forma_pagamento': 'PIX', 'valor_mao_obra': '10', 'valor_materiais_manual': '0',
             'relatorio_tecnico': 'x', 'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.db, d, pid)
        ext.atribuir(self.db, oid, pid)
        servidor = PortalPrestador(self.db, '127.0.0.1', 0)
        servidor.iniciar(); self.addCleanup(servidor.parar)
        base = f'http://127.0.0.1:{servidor.servidor.server_port}'
        prestador = browser()
        status, html = req(prestador, base, '/login',
                           {'email': 'form@example.org', 'senha': 'senha-bem-segura-2026'})
        token = csrf(html)
        status, html = req(prestador, base, f'/os/{oid}')
        self.assertEqual(status, 200)
        self.assertIn('data-auto-save="1"', html)
        self.assertIn('rascunho-auto-status', html)
        self.assertNotIn(f'formaction="/os/{oid}/rascunho/salvar"', html)
        pos_fotos = html.find('name="imagens_encerramento[]"')
        pos_nota = html.find('name="nota_fiscal"')
        pos_confirmar = html.find('id="abrir-situacao-os"')
        self.assertGreater(pos_fotos, -1)
        self.assertGreater(pos_nota, pos_fotos)
        self.assertGreater(pos_confirmar, pos_nota)


if __name__ == '__main__':
    unittest.main(verbosity=2)
