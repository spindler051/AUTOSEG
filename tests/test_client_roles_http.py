"""6.2 HTTP end-to-end admin role changes and provider route negatives."""
import http.cookiejar
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import accounts,web_session
from flavors.autoseg.modules.portal_prestador import PortalPrestador
from officina.core.banco import criar_banco
from officina.core import cadastros_v9 as cad,prestadores_ext as ext


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


class RolesHttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/'db.sqlite')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        self.admin=ext.cadastrar(self.db,'Admin Example','admin@example.test','Password12345')
        self.employee=ext.cadastrar(self.db,'Employee Example','employee@example.test','Password12345')
        self.client=cad.cadastrar_usuario(self.db,'Client Example','52998224725',
                     '51999999999','Password12345','client@example.test')
        with ext.db(self.db) as c:
            c.execute('INSERT INTO v9_admin_prestadores(prestador_id,autorizado_em) VALUES(?,?)',
                      (self.admin,ext.agora()))
        accounts.install(self.db)
        accounts.migrate_legacy(self.db,dry_run=False)
        self.client_account=accounts.find_account_by_identifier(self.db,'email',
                                                       'client@example.test').id
        web_session.clear()
        self.addCleanup(web_session.clear)
        self.flag=patch.dict(os.environ,{'AUTOSEG_UNIFIED_LOGIN':'1','AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'1'})
        self.flag.start()
        self.addCleanup(self.flag.stop)
        self.portal=PortalPrestador(self.db,'127.0.0.1',0)
        self.portal.iniciar()
        self.addCleanup(self.portal.parar)
        self.base='http://127.0.0.1:'+str(self.portal.porta)

    def browser(self):
        return urllib.request.build_opener(NoRedirect(),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def req(self,browser,path,data=None):
        payload=urllib.parse.urlencode(data).encode() if data is not None else None
        req=urllib.request.Request(self.base+path,payload)
        try:
            with browser.open(req,timeout=15) as response:
                try:body=response.read()
                except (ConnectionError,OSError):
                    if response.status!=303:raise
                    body=b''
                return response.status,response.headers,body
        except urllib.error.HTTPError as error:
            try:body=error.read()
            except (ConnectionError,OSError):body=b''
            return error.code,error.headers,body

    def login(self,email):
        browser=self.browser()
        code,headers,_=self.req(browser,'/login',
                               {'identificador':email,'senha':'Password12345'})
        self.assertEqual(303,code)
        return browser

    def csrf(self,browser):
        code,headers,body=self.req(browser,'/')
        self.assertEqual(200,code)
        value=re.search(rb'name="csrf" value="([^"]+)"',body)
        self.assertIsNotNone(value)
        return value.group(1).decode()

    def test_enforcement_switch_independent_of_unified_login(self):
        from flavors.autoseg.modules import object_policy_flags, login_flags
        with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'0',
                                     'AUTOSEG_UNIFIED_LOGIN':'1'}):
            self.assertFalse(object_policy_flags.enforcement_enabled(self.db))
            self.assertTrue(login_flags.unified_login_enabled(self.db))
        with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'1',
                                     'AUTOSEG_UNIFIED_LOGIN':'0'}):
            self.assertTrue(object_policy_flags.enforcement_enabled(self.db))
            self.assertFalse(login_flags.unified_login_enabled(self.db))

    def _unassigned_employee_os(self):
        with ext.db(self.db) as c:
            cid=c.execute("""INSERT INTO clientes(nome,status,tipo_pessoa)
                VALUES('Permission fixture','Ativo','Física')""").lastrowid
            oid=c.execute("""INSERT INTO ordens_servico(
                numero_os,cliente_id,data_abertura,descricao,valor_mao_obra,
                valor_materiais,valor_total,forma_pagamento,status,observacoes)
                VALUES('OS-919',?,'2026-01-01','Permission test item',0,0,0,'','Aberta','')""",
                (cid,)).lastrowid
        ext.atribuir(self.db,oid,self.admin)
        return oid

    def test_switch_http_detail_pdf_and_accounts(self):
        oid=self._unassigned_employee_os()
        employee=self.login('employee@example.test')
        admin=self.login('admin@example.test')
        with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'1'}):
            for route in (f'/os/{oid}', f'/os/{oid}/pdf'):
                with self.subTest(route=route):
                    status,_,_=self.req(employee,route)
                    self.assertIn(status,(403,404))
            self.assertEqual(200,self.req(admin,'/contas')[0])
            self.assertIn(self.req(employee,'/contas')[0],(403,404))
        with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'0'}):
            status,headers,body=self.req(employee,f'/os/{oid}')
            if status==303:
                status,_,body=self.req(employee,headers['Location'])
            self.assertEqual(200,status)
            self.assertIn(b'OS-919',body)
            # PDF is absent, but the legacy endpoint is reached (409), not policy 404.
            status,headers,_=self.req(employee,f'/os/{oid}/pdf')
            if status==303:
                status,_,_=self.req(employee,headers['Location'])
            self.assertNotEqual(404,status)
            self.assertEqual(404,self.req(admin,'/contas')[0])

    def test_switch_http_write_routes_and_role_assignment(self):
        from unittest.mock import Mock
        from flavors.autoseg.modules import os_commands
        oid=self._unassigned_employee_os()
        employee=self.login('employee@example.test')
        admin=self.login('admin@example.test')
        employee_csrf=self.csrf(employee)
        admin_csrf=self.csrf(admin)
        cases=((f'/os/{oid}/salvar','salvar',{'acao_status':'salvar'}),
               (f'/os/{oid}/atribuir','atribuir',{'prestador_destino':str(self.employee)}),
               (f'/os/{oid}/cancelar','cancelar',{'motivo_encerramento':'Teste'}),
               (f'/os/{oid}/arquivar','arquivar',{}),
               (f'/os/{oid}/anexo/1/remover','remove_attachment',{}),
               (f'/os/{oid}/nota-fiscal','attach_invoice',{}))
        for route,action,fields in cases:
            def writer(_banco,_principal,_oid,_data,*,ui,session,path,quer_json):
                return ui.redir('/os')
            from unittest.mock import Mock
            mocked=Mock(side_effect=writer)
            with self.subTest(route=route),patch.dict(os_commands.WRITERS,{action:mocked}):
                with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'1'}):
                    status,_,_=self.req(employee,route,dict(fields,csrf=employee_csrf))
                    self.assertIn(status,(403,404))
                    mocked.assert_not_called()
                with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'0'}):
                    status,headers,_=self.req(employee,route,dict(fields,csrf=employee_csrf))
                    self.assertEqual(303,status)
                    self.assertEqual('/os',headers.get('Location'))
                    mocked.assert_called_once()
        with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'0'}):
            code,_,_=self.req(admin,f'/contas/{self.client_account}/papel',
                              {'csrf':admin_csrf,'papel':'zelador'})
            self.assertEqual(404,code)
            self.assertEqual('customer',accounts.account_link(self.db,self.client_account).client_role)
        with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'1'}):
            code,headers,_=self.req(admin,f'/contas/{self.client_account}/papel',
                                  {'csrf':admin_csrf,'papel':'zelador'})
            self.assertEqual(303,code)
            self.assertEqual('zelador',accounts.account_link(self.db,self.client_account).client_role)

    def test_admin_changes_papel_and_revokes_session(self):
        admin=self.login('admin@example.test')
        code,headers,body=self.req(admin,'/contas')
        self.assertEqual(200,code)
        self.assertIn(b'Contas de cliente',body)
        csrf=self.csrf(admin)
        code,headers,_=self.req(admin,f'/contas/{self.client_account}/papel',
                                {'csrf':csrf,'papel':'zelador'})
        self.assertEqual(303,code)
        self.assertEqual('/contas',headers.get('Location'))
        self.assertEqual('zelador',accounts.account_link(self.db,self.client_account).client_role)
        with ext.db(self.db) as c:
            event=c.execute("SELECT acao FROM portal_auditoria ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual('Papel de cliente alterado',event['acao'])

    def test_employee_client_csrf_and_provider_target_denied(self):
        admin=self.login('admin@example.test')
        employee=self.login('employee@example.test')
        client=self.login('client@example.test')
        admin_csrf=self.csrf(admin)
        employee_csrf=self.csrf(employee)
        for browser in (employee,client):
            status,_,_=self.req(browser,'/contas')
            self.assertIn(status,(403,404))
        for browser,csrf in ((employee,employee_csrf),(admin,'wrong'),
                             (client,'wrong')):
            status,_,_=self.req(browser,f'/contas/{self.client_account}/papel',
                                {'csrf':csrf,'papel':'sindico'})
            self.assertIn(status,(403,404))
        provider_account=accounts.find_account_by_identifier(
            self.db,'email','employee@example.test').id
        status,_,_=self.req(admin,f'/contas/{provider_account}/papel',
                            {'csrf':admin_csrf,'papel':'sindico'})
        self.assertIn(status,(403,404))
        self.assertEqual('customer',accounts.account_link(self.db,self.client_account).client_role)

    def test_employee_cannot_read_or_modify_another_os(self):
        with ext.db(self.db) as c:
            cid=c.execute("""INSERT INTO clientes(nome,status,tipo_pessoa)
                 VALUES('Fictitious client','Ativo','Física')""").lastrowid
            oid=c.execute("""INSERT INTO ordens_servico(
                numero_os,cliente_id,data_abertura,descricao,valor_mao_obra,
                valor_materiais,valor_total,forma_pagamento,status,observacoes)
                VALUES('OS-550',?,'2026-01-01','Private description',0,0,0,'','Aberta','')""",
                (cid,)).lastrowid
        ext.atribuir(self.db,oid,self.admin)
        browser=self.login('employee@example.test')
        csrf=self.csrf(browser)
        for route,body in ((f'/os/{oid}',None),(f'/os/{oid}/relatorio.yaml',None),
                           (f'/os/{oid}/pdf',None),
                           (f'/os/{oid}/salvar',{'csrf':csrf,'acao_status':'Concluída'}),
                           (f'/os/{oid}/cancelar',{'csrf':csrf}),
                           (f'/os/{oid}/atribuir',{'csrf':csrf,'prestador_destino':str(self.employee)}),
                           (f'/os/{oid}/arquivar',{'csrf':csrf}),
                           (f'/os/{oid}/publicar',{'csrf':csrf}),
                           (f'/os/{oid}/fotos',{'csrf':csrf}),
                           (f'/os/{oid}/rateio',{'csrf':csrf}),
                           (f'/os/{oid}/nota-fiscal',{'csrf':csrf})):
            with self.subTest(route=route):
                code,headers,contents=self.req(browser,route,body)
                self.assertIn(code,(403,404))
                self.assertNotIn(b'Private description',contents)
        with ext.db(self.db) as c:
            row=c.execute('SELECT status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
        self.assertEqual(row['status'],'Aberta')


if __name__=='__main__':
    unittest.main()
