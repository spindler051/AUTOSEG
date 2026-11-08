"""HTTP real REV04: YAML reutilizável, formulário de catálogo e permissões de estoque."""
import http.cookiejar
import re
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path
from banco import criar_banco
from portal_prestador import PortalPrestador
import prestadores_ext as ext
import estoque_materiais as est


def fetch(opener,url,data=None,content_type=None):
    headers={}
    if isinstance(data,dict):data=urllib.parse.urlencode(data,doseq=True).encode()
    if content_type:headers['Content-Type']=content_type
    req=urllib.request.Request(url,data,headers=headers)
    with opener.open(req,timeout=12) as r:return r.read().decode('utf-8','replace')


def campo_csrf(texto):
    m=re.search('name="csrf" value="([^"]+)"',texto)
    assert m,'CSRF ausente'
    return m.group(1)


def enviar_yaml(opener,url,csrf,filename,conteudo):
    boundary='AUTOSegRev04Boundary123'
    binary=(f'--{boundary}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{csrf}\r\n'
      f'--{boundary}\r\nContent-Disposition: form-data; name="yaml"; filename="{filename}"\r\n'
      'Content-Type: application/x-yaml\r\n\r\n').encode()+conteudo+(f'\r\n--{boundary}--\r\n').encode()
    return fetch(opener,url,binary,f'multipart/form-data; boundary={boundary}')


class Rev04Http(unittest.TestCase):
    def test_servico_yaml_catalogo_e_estoque_admin_sem_permissao(self):
        with tempfile.TemporaryDirectory(prefix='rev04_http_') as tmp:
            db=str(Path(tmp)/'app.db');criar_banco(db);ext.instalar(db)
            ext.cadastrar(db,'Prestador REV04','prestador@example.invalid','SenhaSegura123456')
            serv=PortalPrestador(db,host='127.0.0.1',porta=0)
            try:
                serv.iniciar()
                base=f'http://127.0.0.1:{serv.porta}'
                bc=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                txt=fetch(bc,base+'/login',{'email':'prestador@example.invalid','senha':'SenhaSegura123456'})
                self.assertIn('Visão geral',txt)
                form=fetch(bc,base+'/servicos/novo')
                self.assertIn('id="lista-materiais-servico"',form)
                self.assertIn('/servicos/yaml',form)
                self.assertIn('/modelos/servico.yaml',form)
                doc=Path(__file__).with_name('modelo_servico.yaml').read_bytes()
                pre=enviar_yaml(bc,base+'/servicos/yaml',campo_csrf(form),'servico.yaml',doc)
                self.assertIn('Cadastro de controle remoto PPA',pre)
                self.assertIn('material_nome[]',pre)
                self.assertIn('Control',pre)
                # Nenhum produto no banco até confirmação do formulário.
                self.assertEqual(est.listar(db),[])
                salvo=fetch(bc,base+'/servicos/salvar',{'csrf':campo_csrf(pre),'nome':'Serviço fictício YAML','descricao':'Teste de visual',
                    'preco_servico':'25','material_nome[]':['Sensor demo'],'material_qtd[]':['1'],'material_valor[]':['12,50'],
                    'relatorio_padrao':'Inspecionar e testar.'})
                self.assertIn('Serviço fictício YAML',salvo)
                # Segurança: estoque existe, mas exige admin.
                with self.assertRaises(urllib.error.HTTPError) as ctx:bc.open(base+'/estoque',timeout=10)
                self.assertEqual(ctx.exception.code,403)
                os_form=fetch(bc,base+'/os/nova')
                self.assertNotIn('Estoque disponível',os_form)
            finally:serv.parar()

if __name__=='__main__':unittest.main(verbosity=2)
