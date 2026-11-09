"""Fluxo HTTP real 8765/8766 com portas efêmeras e SQLite descartável."""
import http.cookiejar
import re
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from officina.core.banco import criar_banco
from officina.core import cadastros_v9 as cad
from officina.core import prestadores_ext as ext
from flavors.autoseg.modules.portal_prestador import PortalPrestador
from flavors.autoseg.modules.servidor_web import ServidorPortal


def pedido(browser, base, url, dados=None):
    body=urllib.parse.urlencode(dados).encode() if dados is not None else None
    req=urllib.request.Request(base+url,body)
    with browser.open(req,timeout=12) as r:
        return r.read().decode('utf-8','replace')


def token(s):
    m=re.search(r'name="csrf" value="([^"]+)"',s)
    if not m:raise AssertionError('CSRF não disponível')
    return m.group(1)


class HttpTest(unittest.TestCase):
    def test_cliente_para_pendencias_prestador_e_formularios(self):
        with tempfile.TemporaryDirectory(prefix='autoseg_http_novo_') as pasta:
            db=str(Path(pasta)/'app.db')
            criar_banco(db)
            ext.instalar(db)
            prov_id=ext.cadastrar(db,'Prestador Teste','prestador@example.org','senha-bem-segura-2026')
            cliente=ServidorPortal(db,porta=0,host='127.0.0.1')
            prestador=PortalPrestador(db,host='127.0.0.1',porta=0)
            try:
                cliente.iniciar();prestador.iniciar()
                web_cliente='http://127.0.0.1:'+str(cliente.porta)
                web_prestador='http://127.0.0.1:'+str(prestador.porta)
                bc=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                bp=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                # Novo cliente: login CPF e senha sem passar pelo prestador.
                html=pedido(bc,web_cliente,'/')
                self.assertIn('name="cpf"',html)
                html=pedido(bc,web_cliente,'/cadastrar',{'cpf':'52998224725',
                    'senha':'Senha-Tecnica-2026','confirmar_senha':'Senha-Tecnica-2026'})
                self.assertIn('Meu painel',html)
                org=cad.criar_organizacao(db,1,'Condomínio HTTP de Testes','Condomínio',cidade='Porto Alegre',papel='Morador',endereco='Rua Exemplo 100',unidade='Portaria')
                html=pedido(bc,web_cliente,f'/chamado/novo?org={org}')
                self.assertIn('name="org_id"',html)
                html=pedido(bc,web_cliente,'/chamado/novo',{'csrf':token(html),'org_id':str(org),
                    'papel':'Morador','solicitante_nome':'Morador de Testes',
                    'solicitante_telefone':'(51) 99999-0000','unidade':'Apto 101',
                    'urgencia':'Normal','descricao':'Portão automático falhou durante os testes.'})
                self.assertIn('Sua solicitação foi registrada',html)
                # Login do prestador; a OS deve estar na fila normal, mesmo sem CNPJ.
                html=pedido(bp,web_prestador,'/login',{'email':'prestador@example.org','senha':'senha-bem-segura-2026'})
                self.assertIn('Visão geral',html)
                html=pedido(bp,web_prestador,'/clientes')
                self.assertIn('Condomínio HTTP de Testes',html)
                html=pedido(bp,web_prestador,'/os')
                self.assertIn('Condomínio HTTP de Testes',html)
                self.assertIn('Aberta',html)
                html=pedido(bp,web_prestador,'/os/1')
                # A OS ainda não é do prestador: fotos exigem responsável ou admin.
                self.assertIn('Somente o responsável ou administrador pode adicionar fotos',html)
                html=pedido(bp,web_prestador,'/os/nova')
                self.assertIn('id="c_cliente_id"',html)
                self.assertIn('id="modelo-material"',html)
                self.assertIn('Nenhum material é obrigatório',html)
                html=pedido(bp,web_prestador,'/clientes/novo')
                self.assertIn('action="/clientes/yaml"',html)
                # portal do cliente conserva a página principal e o login CPF.
                self.assertIn('Acompanhe seus pedidos',pedido(bc,web_cliente,'/painel'))
            finally:
                prestador.parar();cliente.parar()

if __name__=='__main__':unittest.main(verbosity=2)
