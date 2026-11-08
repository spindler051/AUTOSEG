"""HTTP real: cadastro PF, cadastro PJ+OS, consulta em Clientes/OS e PDF."""
import http.cookiejar
import re
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from officina.core.banco import criar_banco
from flavors.autoseg.modules.portal_prestador import PortalPrestador
from flavors.autoseg.modules.servidor_web import ServidorPortal
from officina.core import prestadores_ext as ext
def request(browser,base,rota,dados=None):
    payload=urllib.parse.urlencode(dados).encode() if dados is not None else None
    with browser.open(urllib.request.Request(base+rota,payload),timeout=12) as r:
        return r.read(),r.headers.get('Content-Type','')

def csrf(body):
    match=re.search(rb'name="csrf" value="([^"]+)"',body)
    if not match:raise AssertionError('CSRF não localizado')
    return match.group(1).decode()

class Rev03HttpTest(unittest.TestCase):
    def test_cadastro_direto_e_orcamento_pdf(self):
        with tempfile.TemporaryDirectory(prefix='autoseg_rev03_http_') as pasta:
            db=str(Path(pasta)/'app.db')
            criar_banco(db)
            ext.instalar(db)
            ext.cadastrar(db,'Prestador de Teste','prestador@example.org','senha-segura-2026')
            cliente=ServidorPortal(db,porta=0,host='127.0.0.1')
            prestador=PortalPrestador(db,host='127.0.0.1',porta=0)
            try:
                cliente.iniciar();prestador.iniciar()
                cli='http://127.0.0.1:'+str(cliente.porta)
                pre='http://127.0.0.1:'+str(prestador.porta)
                bc=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                bp=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                b,_=request(bc,cli,'/cadastrar',{'cpf':'52998224725','senha':'Senha-Tecnica-2026','confirmar_senha':'Senha-Tecnica-2026'})
                self.assertIn(b'Meu painel',b)
                b,_=request(bc,cli,'/nova-organizacao')
                self.assertIn(b'name="telefone"',b)
                self.assertIn(b'name="descricao"',b)
                dados={'csrf':csrf(b),'nome':'Condomínio Vinte e Um Fictício','tipo':'Condomínio',
                       'endereco':'Avenida das Flores 123','cidade':'Porto Alegre','bairro':'Centro',
                       'telefone':'(51) 98888-7777','cnpj':'','papel':'Morador','unidade':'Portaria',
                       'solicitante_nome':'Cliente de Teste','solicitante_telefone':'(51) 98888-7777',
                       'descricao':'Portão parou de funcionar ao amanhecer.',
                       'urgencia':'Normal'}
                b,_=request(bc,cli,'/nova-organizacao',dados)
                self.assertIn('Solicitação registrada'.encode(),b)
                b,_=request(bp,pre,'/login',{'email':'prestador@example.org','senha':'senha-segura-2026'})
                self.assertIn(b'Vis\xc3\xa3o geral',b)
                b,_=request(bp,pre,'/clientes')
                self.assertIn('Condomínio Vinte e Um'.encode(),b)
                b,_=request(bp,pre,'/os')
                self.assertIn('Condomínio Vinte e Um'.encode(),b)
                self.assertIn(b'Aberta',b)
                b,_=request(bp,pre,'/servicos/novo')
                self.assertIn(b'name="preco_servico"',b)
                b,_=request(bp,pre,'/servicos/salvar',{
                    'csrf':csrf(b),'nome':'Ajuste de Portão','descricao':'Verificação e ajuste',
                    'preco_servico':'140,00','materiais':'Parafuso | 2 | 1,50',
                    'relatorio_padrao':'Executar verificação e ajustes técnicos.'})
                self.assertIn('Ajuste de Portão'.encode(),b)
                b,_=request(bc,cli,'/orcamento')
                self.assertIn('Ajuste de Portão'.encode(),b)
                pdf,tipo=request(bc,cli,'/orcamento/pdf',{'csrf':csrf(b),'servico_id':'1','quantidade':'2'})
                self.assertTrue(pdf.startswith(b'%PDF-'))
                self.assertIn('application/pdf',tipo)
                b,_=request(bp,pre,'/os/nova')
                self.assertIn(b'catalogo-os-json',b)
            finally:
                prestador.parar();cliente.parar()

if __name__=='__main__':unittest.main(verbosity=2)
