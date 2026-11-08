"""Teste de regressão da autenticação do cliente e formulário administrativo."""
import tempfile,types,sys,urllib.request,urllib.parse,urllib.error,urllib.request,http.cookiejar
from pathlib import Path
from test_portal_v4 import schema
from test_v9 import cpf
from officina.core import prestadores_ext as ext
from officina.core import cadastros_v9 as cad
from officina.core import fluxo_os
from officina.core import atendimento_os
from flavors.autoseg.modules.portal_prestador import PortalPrestador

def request(opener,base,path,form=None):
    req=urllib.request.Request(base+path,urllib.parse.urlencode(form).encode() if form is not None else None)
    try:
        with opener.open(req,timeout=10) as r:return r.status,r.read().decode('utf8','replace')
    except urllib.error.HTTPError as e:return e.code,e.read().decode('utf8','replace')

def main():
  with tempfile.TemporaryDirectory() as td:
    td=Path(td); db=str(td/'data.db');schema(db)
    ext.RELATORIOS=td/'relatorios';ext.ANEXOS=td/'anexos';ext.RASCUNHOS=td/'rascunhos'
    for x in (ext.RELATORIOS,ext.ANEXOS,ext.RASCUNHOS):x.mkdir()
    sys.modules['officina.core.banco']=types.SimpleNamespace(proximo_numero_os=lambda cursor:'OS-0002')
    ext.instalar(db);fluxo_os.instalar(db);atendimento_os.instalar(db);cad.instalar(db)
    adminid=ext.cadastrar(db,'Operador','operador@teste.local','Senhateste-2026')
    portal=PortalPrestador(db,'127.0.0.1',0);portal.iniciar();base='http://127.0.0.1:'+str(portal.servidor.server_port)
    try:
      browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
      status,page=request(browser,base,'/cliente');assert status==200 and 'name="cpf"' in page and 'name="senha"' in page and '/cliente/cadastro' in page,(status,page[:500])
      status,page=request(browser,base,'/cliente/cadastro');assert status==200 and 'confirmar_senha' in page and 'Escolha sua senha' in page
      status,page=request(browser,base,'/cliente/legado');assert status==200 and 'cliente_id' in page and 'name="senha"' in page
      doc=cpf(345678901)
      status,page=request(browser,base,'/pj/cadastrar',{'nome':'Usuário de Teste','cpf':doc,'telefone':'51988887777','senha':'Senha123456789','confirmar_senha':'Senha123456789'})
      assert status==200 and 'name="cpf"' in page,(status,page[-500:])
      status,page=request(browser,base,'/pj/entrar',{'cpf':doc,'senha':'Senha123456789'})
      assert status==200 and 'Minha conta' in page,(status,page[-500:])
      staff=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
      status,page=request(staff,base,'/login',{'email':'operador@teste.local','senha':'Senhateste-2026'})
      status,page=request(staff,base,'/clientes/novo');assert status==200 and 'name="senha_cliente"' in page and 'name="confirmar_senha_cliente"' in page
      import re
      csrf=re.search('name="csrf" value="([^"]+)"',page).group(1)
      d={'csrf':csrf,'tipo_pessoa':'Física','status':'Ativo','nome':'Teste Cliente Legado','senha_cliente':'SenhaCliente12345','confirmar_senha_cliente':'SenhaCliente12345'}
      status,page=request(staff,base,'/clientes/novo/salvar',d)
      assert status==200,(status,page[-700:])
      with ext.db(db) as c:
        cl=c.execute("SELECT id FROM clientes WHERE nome='Teste Cliente Legado'").fetchone()
        assert cl is not None
        assert c.execute('SELECT 1 FROM cliente_acessos WHERE cliente_id=?',(cl['id'],)).fetchone()
      assert fluxo_os.autenticar_cliente(db,cl['id'],'SenhaCliente12345') is not None
      status,page=request(staff,base,f'/clientes/{cl["id"]}')
      assert 'name="senha_cliente"' in page
      print('PASSOU v9.2: /cliente CPF+senha, cadastro com confirmação, login CPF, acesso legado e senha no cadastro administrativo')
    finally:portal.parar()
if __name__=='__main__':main()
