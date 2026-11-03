import http.cookiejar,os,re,tempfile,unittest,urllib.request,urllib.parse
from banco import criar_banco
from servidor_web import ServidorPortal
import prestadores_ext as ext
class Http(unittest.TestCase):
 def setUp(self):
  f,self.path=tempfile.mkstemp(suffix='.db');os.close(f);criar_banco(self.path)
  self.s=ServidorPortal(caminho_banco=self.path,porta=0,host='127.0.0.1');self.s.iniciar()
  self.url='http://127.0.0.1:'+str(self.s.porta)
  self.op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def tearDown(self):self.s.parar();os.unlink(self.path)
 def get(self,path):
  with self.op.open(self.url+path,timeout=5) as r:return r.read().decode('utf8')
 def post(self,path,params):
  req=urllib.request.Request(self.url+path,urllib.parse.urlencode(params).encode('utf8'))
  with self.op.open(req,timeout=5) as r:return r.geturl(),r.read().decode('utf8')
 def test_pessoa_portaria_os_whatsapp(self):
  homepage=self.get('/');self.assertIn('Entre na sua conta',homepage);self.assertLess(homepage.index('Entre na sua conta'),homepage.index('Link público deste portal'))
  self.assertNotIn('href="//cadastro',homepage)
  _,page=self.post('/cadastrar',{'cpf':'52998224725','senha':'senha-muito-forte-123','confirmar_senha':'senha-muito-forte-123'})
  self.assertIn('Meu painel',page)
  csrf=re.search(r'name="csrf" value="([^"]+)',page).group(1)
  url,page=self.post('/nova-organizacao',{'csrf':csrf,'tipo':'Condomínio','nome':'Residencial Sol', 'endereco':'Rua das Rosas 100','cidade':'Porto Alegre','bairro':'Centro','cnpj':'','telefone':'51999998888','unidade':'Porteiro','papel':'Funcionário','solicitante_nome':'Pessoa da portaria','solicitante_telefone':'51999998888','descricao':'Portão quebrado no acesso principal','urgencia':'Normal'})
  self.assertIn('whatsapp=1',url)
  with ext.db(self.path) as c:
   org=c.execute('SELECT id FROM v9_organizacoes ORDER BY id DESC LIMIT 1').fetchone()['id']
  url,page=self.post('/chamado/novo',{'csrf':csrf,'org_id':str(org),'unidade':'Porteiro','papel':'Funcionário','descricao':'Portão quebrado','urgencia':'Normal','solicitante_nome':'Pessoa da portaria','solicitante_telefone':'51999998888'})
  self.assertIn('whatsapp=1',url);self.assertIn('Avisar AUTOSEG pelo WhatsApp',page)
  self.assertIn('wa.me/5551992692007',page)
  self.assertIn('/static/cliente_whatsapp.js',page)
  with ext.db(self.path) as c:
   ch=c.execute('SELECT os_id FROM v9_chamados ORDER BY id DESC LIMIT 1').fetchone()
   self.assertTrue(ch['os_id']);o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(ch['os_id'],)).fetchone()
   self.assertEqual(o['status'],'Aberta')
if __name__=='__main__':unittest.main()
