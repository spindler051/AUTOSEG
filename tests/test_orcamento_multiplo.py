"""Orçamento com vários serviços, materiais adicionais e importação YAML."""
import http.cookiejar
import io
import re
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from pypdf import PdfReader

from officina.core import catalogo_servicos as catalogo
from officina.core import estoque_materiais as estoque
from flavors.autoseg.modules import importacao_yaml as iy
from officina.core import portal_negocios as neg
from officina.core import prestadores_ext as ext
from officina.core.banco import criar_banco
from flavors.autoseg.modules.portal_prestador import PortalPrestador


def request(opener, url, data=None, content_type=None):
    headers = {}
    if isinstance(data, dict):
        data = urllib.parse.urlencode(data, doseq=True).encode()
    elif isinstance(data, list):
        data = urllib.parse.urlencode(data).encode()
    if content_type:
        headers['Content-Type'] = content_type
    req = urllib.request.Request(url, data, headers=headers)
    with opener.open(req, timeout=20) as resposta:
        return resposta.status, resposta.headers.get_content_type(), resposta.read()


def enviar_yaml(opener, url, csrf, filename, conteudo):
    boundary = 'AUTOSegOrcamentoBoundary123'
    binary = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{csrf}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="yaml"; filename="{filename}"\r\n'
        'Content-Type: application/x-yaml\r\n\r\n'
    ).encode() + conteudo + f'\r\n--{boundary}--\r\n'.encode()
    return request(opener, url, binary,
                   f'multipart/form-data; boundary={boundary}')


class OrcamentoMultiplo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_orcamento_')
        self.db = str(Path(self.tmp.name) / 'teste.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        catalogo.instalar(self.db)
        self.pid = ext.cadastrar(self.db, 'Prestador Orçamento',
                                 'orcamento@example.org', 'senha-bem-segura-2026')
        dados = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados.update(nome='Condomínio Orçamento Teste', tipo_pessoa='Jurídica',
                     status='Ativo', documento='12345678000195')
        self.cid = neg.cliente_salvar(self.db, dados, self.pid)
        self.s1 = catalogo.salvar(self.db, {
            'nome': 'Serviço Um', 'descricao': 'Primeiro serviço',
            'preco_servico': '100,00', 'materiais': 'Cabo | 1 | 20,00'})
        self.s2 = catalogo.salvar(self.db, {
            'nome': 'Serviço Dois', 'descricao': 'Segundo serviço',
            'preco_servico': '50,00'})
        self.m1 = estoque.cadastrar(self.db, 'Material Um', venda='5,00')
        self.servidor = PortalPrestador(self.db, host='127.0.0.1', porta=0)
        self.servidor.iniciar()
        self.base = f'http://127.0.0.1:{self.servidor.porta}'
        self.browser = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        _, _, html = request(self.browser, self.base + '/login',
                             {'email': 'orcamento@example.org',
                              'senha': 'senha-bem-segura-2026'})
        self.assertIn('Visão geral', html.decode())
        _, _, formulario = request(self.browser, self.base + '/orcamento')
        self.csrf = re.search(r'name="csrf" value="([^"]+)"',
                              formulario.decode()).group(1)

    def tearDown(self):
        self.servidor.parar()
        self.tmp.cleanup()

    def _pdf(self, dados):
        status, tipo, corpo = request(
            self.browser, self.base + '/orcamento/pdf',
            [('csrf', self.csrf)] + dados)
        self.assertEqual(status, 200)
        self.assertEqual(tipo, 'application/pdf')
        self.assertTrue(corpo.startswith(b'%PDF'))
        return '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(corpo)).pages)

    def test_formulario_multiplo_e_yaml_oficial(self):
        _, _, html = request(self.browser, self.base + '/orcamento')
        texto = html.decode()
        for marcador in ('id="busca-cliente-os"', 'id="lista-servicos-orcamento"',
                         'id="lista-materiais-orcamento"', 'id="modelo-servico-orcamento"',
                         'id="modelo-material-orcamento"', 'id="yaml-orcamento"',
                         '/modelos/orcamento.yaml', 'name="servico_id[]"',
                         'name="material_id[]"', 'name="validade"',
                         'name="condicoes"', 'total-orcamento'):
            self.assertIn(marcador, texto)
        _, _, modelo = request(self.browser, self.base + '/modelos/orcamento.yaml')
        self.assertIn('MODELO OFICIAL DE ORÇAMENTO', modelo.decode())

    def test_pdf_com_varios_servicos_e_materiais_sem_criar_os(self):
        texto = self._pdf([
            ('cliente_id', str(self.cid)),
            ('servico_id[]', str(self.s1)), ('servico_qtd[]', '1'),
            ('servico_id[]', str(self.s2)), ('servico_qtd[]', '2'),
            ('material_id[]', str(self.m1)), ('material_qtd[]', '3'),
            ('validade', '45'),
            ('condicoes', 'Pagamento em 30 dias após a aprovação.'),
        ])
        self.assertIn('Serviço Um', texto)
        self.assertIn('Serviço Dois', texto)
        self.assertIn('Material Um', texto)
        self.assertIn('Materiais adicionais', texto)
        self.assertIn('235,00', texto)
        self.assertIn('Validade: 45 dia(s)', texto)
        self.assertIn('Pagamento em 30 dias após a aprovação', texto)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ordens_servico').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM financeiro').fetchone()[0], 0)

    def test_yaml_preenche_formulario_e_gera_pdf(self):
        conteudo = f'''versao: 1
orcamento:
  cliente_nome: Condomínio Orçamento Teste
  servicos:
    - id: {self.s1}
      quantidade: 1
    - nome: Serviço Dois
      quantidade: 2
  materiais:
    - nome: Material Um
      quantidade: 3
'''.encode()
        status, _, html = enviar_yaml(
            self.browser, self.base + '/orcamento/yaml', self.csrf,
            'orcamento.yaml', conteudo)
        self.assertEqual(status, 200)
        texto = html.decode()
        self.assertIn('YAML importado', texto)
        self.assertIn('Condomínio Orçamento Teste', texto)
        self.assertIn('name="servico_qtd[]"', texto)
        self.assertIn('value="2"', texto)
        self.assertIn('value="3"', texto)
        self._pdf([
            ('cliente_id', str(self.cid)),
            ('servico_id[]', str(self.s1)), ('servico_qtd[]', '1'),
            ('servico_id[]', str(self.s2)), ('servico_qtd[]', '2'),
            ('material_id[]', str(self.m1)), ('material_qtd[]', '3'),
        ])

    def test_parser_yaml_exige_saida_limpa(self):
        modelo = (Path(__file__).parents[1] / 'flavors/autoseg/templates/modelo_orcamento.yaml').read_bytes()
        self.assertEqual(iy.orcamento('modelo_orcamento.yaml', modelo, self.db), {})
        dados = yaml.safe_load(modelo)
        dados['modelo']['orcamento'] = {
            'cliente_nome': 'Condomínio Orçamento Teste',
            'servicos': [{'nome': 'Serviço Um', 'quantidade': 1}],
            'materiais': [{'nome': 'Material Um', 'quantidade': 2}],
        }
        preenchido = yaml.safe_dump(dados, allow_unicode=True, sort_keys=False).encode()
        self.assertEqual(iy.orcamento('modelo_orcamento.yaml', preenchido, self.db), {})
        saida = '''versao: 1
orcamento:
  cliente_nome: Condomínio Orçamento Teste
  servicos:
    - nome: Serviço Um
      quantidade: 1
  materiais:
    - nome: Material Um
      quantidade: 2
'''.encode('utf-8')
        pre = iy.orcamento('orcamento.yaml', saida, self.db)
        self.assertEqual(pre['cliente_id'], self.cid)
        self.assertEqual(pre['servicos'][0]['id'], self.s1)
        self.assertEqual(pre['materiais'][0]['id'], self.m1)
        self.assertEqual(pre['total_centavos'], 12000 + 1000)

    def test_parser_yaml_rejeita_campos_e_identificadores_invalidos(self):
        def validar(texto):
            return iy.orcamento('x.yaml', texto.encode(), self.db)

        with self.assertRaisesRegex(ValueError, 'exatamente um cliente'):
            validar(f'''versao: 1
orcamento:
  cliente_id: {self.cid}
  cliente_nome: Condomínio Orçamento Teste
  servicos:
    - id: {self.s1}
      quantidade: 1
''')
        with self.assertRaisesRegex(ValueError, 'campo desconhecido'):
            validar(f'''versao: 1
orcamento:
  cliente_id: {self.cid}
  servicos:
    - id: {self.s1}
      quantidade: 1
      preco: 10
''')
        with self.assertRaisesRegex(ValueError, 'id OU o nome'):
            validar(f'''versao: 1
orcamento:
  cliente_id: {self.cid}
  servicos:
    - id: {self.s1}
      nome: Serviço Um
      quantidade: 1
''')
        with self.assertRaisesRegex(ValueError, 'pelo menos um'):
            validar(f'''versao: 1
orcamento:
  cliente_id: {self.cid}
  servicos: []
  materiais: []
''')
        with self.assertRaisesRegex(ValueError, 'Quantidade'):
            validar(f'''versao: 1
orcamento:
  cliente_id: {self.cid}
  servicos:
    - id: {self.s1}
      quantidade: 0
''')


if __name__ == '__main__':
    unittest.main(verbosity=2)
