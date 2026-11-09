"""Teste real HTTP entre clientes e prestadores, com usuários/OS fictícios."""
import http.cookiejar
import re
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from officina.core.banco import criar_banco,proximo_numero_os
from officina.core import prestadores_ext as ext
from officina.core import cadastros_v9 as cad
from flavors.autoseg.scripts.CRIAR_CADASTROS_FICTICIOS_DEV import cpf_ficticio,cnpj_ficticio
from flavors.autoseg.modules.portal_prestador import PortalPrestador
from flavors.autoseg.modules.servidor_web import ServidorPortal


def request(browser,base,url,body=None):
    data=urllib.parse.urlencode(body).encode() if body is not None else None
    with browser.open(urllib.request.Request(base+url,data),timeout=12) as r:
        return r.read().decode('utf-8','replace')


def token(html):
    m=re.search(r'name="csrf" value="([^"]+)"',html)
    if not m:raise AssertionError('CSRF ausente')
    return m.group(1)


class PF_PJ_HTTP(unittest.TestCase):
    def test_login_prestador_nomeia_pf_cliente_ve_os_e_outro_local_bloqueia(self):
        with tempfile.TemporaryDirectory(prefix='autoseg_pf_pj_http_') as tmp:
            banco=str(Path(tmp)/'db.db')
            criar_banco(banco);ext.instalar(banco);cad.instalar(banco)
            pid_prestador=ext.cadastrar(banco,'Prestador DEV','dev-prestador@example.invalid','senha-forte-ficticia-123')
            cad.definir_admin(banco,pid_prestador,True)
            uid=cad.cadastrar_usuario(banco,'Pessoa Teste','%s'%cpf_ficticio('987644450'),
                                      '51999999999','senha-pf-ficticia-123')
            with ext.db(banco) as c:
                for nome,docbase in (('Condomínio Teste Um','976655440001'),
                                     ('Condomínio Teste Dois','976655440002')):
                    doc=cnpj_ficticio(docbase)
                    cid=c.execute("INSERT INTO clientes(nome,tipo_pessoa,documento,status) VALUES(?,'Jurídica',?,'Ativo')",(nome,doc)).lastrowid
                    org=cad.sincronizar_cliente_pj(c,cid)
                    c.execute('UPDATE v9_organizacoes SET situacao=? WHERE id=?',('Validado',org))
                    c.execute('''INSERT INTO ordens_servico(numero_os,cliente_id,descricao,status)
                                 VALUES(?,?,?,'Aberta')''',
                              (proximo_numero_os(c.cursor()),cid,'OS administrativa de '+nome))
            cliente=ServidorPortal(banco,porta=0,host='127.0.0.1')
            prestador=PortalPrestador(banco,porta=0,host='127.0.0.1')
            try:
                cliente.iniciar();prestador.iniciar()
                base_c='http://127.0.0.1:'+str(cliente.porta)
                base_p='http://127.0.0.1:'+str(prestador.porta)
                bc=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                bp=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                html=request(bc,base_c,'/entrar-pf',{'cpf':cpf_ficticio('987644450'),
                                                    'senha':'senha-pf-ficticia-123'})
                self.assertIn('Meu painel',html)
                html=request(bc,base_c,'/cliente/vinculo/novo?org=1')
                self.assertIn('name="cnpj"',html)
                self.assertIn('Representante legal',html)
                with self.assertRaises(urllib.error.HTTPError) as err:
                    request(bc,base_c,'/sindico?org=1')
                self.assertEqual(err.exception.code,403)
                html=request(bp,base_p,'/login',{'email':'dev-prestador@example.invalid',
                                                 'senha':'senha-forte-ficticia-123'})
                self.assertIn('Visão geral',html)
                html=request(bp,base_p,'/organizacoes/responsaveis')
                self.assertIn('Nomear síndico / gestor',html)
                self.assertIn('Pessoa Teste',html)
                html=request(bp,base_p,'/organizacoes/responsavel/atribuir',
                             {'csrf':token(html),'org_id':'1','usuario_id':str(uid)})
                self.assertIn('Pessoa Teste',html)
                html=request(bc,base_c,'/painel')
                self.assertIn('Organizações sob sua responsabilidade',html)
                html=request(bc,base_c,'/sindico?org=1')
                self.assertIn('OS administrativa de Condomínio Teste Um',html)
                self.assertNotIn('OS administrativa de Condomínio Teste Dois',html)
                with self.assertRaises(urllib.error.HTTPError) as err:
                    request(bc,base_c,'/sindico?org=2')
                self.assertEqual(err.exception.code,403)
            finally:
                prestador.parar();cliente.parar()


if __name__=='__main__':unittest.main(verbosity=2)
