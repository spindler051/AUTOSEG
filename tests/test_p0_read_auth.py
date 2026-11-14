"""Read authorization regression tests for shared provider resources."""
from __future__ import annotations

import http.cookiejar
import json
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import os_commands
from flavors.autoseg.modules.portal_prestador import PortalPrestador
from officina.application.object_policy import Principal
from officina.application import work_item_access as access
from officina.core import prestadores_ext as ext, cadastros_v9 as cad, fluxo_os
from officina.core.banco import criar_banco
from officina.integration import clientes as clientes_core
from officina.repositories import ordens


def request(browser, base, path, payload=None):
    body = urllib.parse.urlencode(payload).encode() if payload is not None else None
    try:
        with browser.open(urllib.request.Request(base + path, body), timeout=20) as result:
            return result.status, result.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode('utf-8', 'replace')


class ReadAuthorizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='read_authorization_')
        cls.old_base = os.environ.get('AUTOSEG_BASE')
        os.environ['AUTOSEG_BASE'] = cls.tmp.name
        cls.banco = str(Path(cls.tmp.name) / 'sandbox.db')
        criar_banco(cls.banco)
        for installer in (ext.instalar, fluxo_os.instalar, cad.instalar):
            installer(cls.banco)
        cls.first = ext.cadastrar(cls.banco, 'First Provider', 'first@invalid.test', 'password123')
        cls.second = ext.cadastrar(cls.banco, 'Second Provider', 'second@invalid.test', 'password123')
        cls.participant = ext.cadastrar(cls.banco, 'Participant', 'part@invalid.test', 'password123')
        cls.admin = ext.cadastrar(cls.banco, 'Administrator', 'admin@invalid.test', 'password123')
        cad.definir_admin(cls.banco, cls.admin, True)
        with ext.db(cls.banco) as c:
            cls.c1 = c.execute("INSERT INTO clientes(nome,status,email,documento) VALUES('Visible Name','Ativo','first@customer.invalid','11111111111')").lastrowid
            cls.c2 = c.execute("INSERT INTO clientes(nome,status,email,documento) VALUES('Secret Customer','Ativo','secret@customer.invalid','22222222222')").lastrowid
            cls.c3 = c.execute("INSERT INTO clientes(nome,status,email,documento) VALUES('Shared Customer','Ativo','shared@customer.invalid','33333333333')").lastrowid
            def insert_os(number,cid,status,value):
                return c.execute('''INSERT INTO ordens_servico
                    (numero_os,cliente_id,status,descricao,valor_total,data_abertura,criado_em)
                    VALUES(?,?,?,?,?,'2026-11-14','2026-11-14')''',
                    (number,cid,status,'INTERNAL NOTES: hidden payload',value)).lastrowid
            cls.own = insert_os('OWN-RD-1',cls.c1,'Aberta',111.0)
            cls.other = insert_os('OTHER-RD-2',cls.c2,'Iniciada',99999.0)
            cls.closed = insert_os('CLOSED-RD-3',cls.c2,'Concluída',80000.0)
            cls.own_closed = insert_os('OWN-RD-4',cls.c1,'Concluída',222.0)
            cls.shared = insert_os('SHARED-RD-5',cls.c3,'Aberta',12345.0)
            c.execute("INSERT INTO financeiro(os_id,cliente_id,status,valor) VALUES(?,?,'Recebido',300)",(cls.own,cls.c1))
            c.execute("INSERT INTO financeiro(os_id,cliente_id,status,valor) VALUES(?,?,'Aguardando pagamento',40000)",(cls.other,cls.c2))
        for oid,pid in ((cls.own,cls.first),(cls.other,cls.second)):
            ext.assumir(cls.banco,oid,pid)
        with ext.db(cls.banco) as c:
            for oid,pid in ((cls.own_closed,cls.first),(cls.closed,cls.second)):
                c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)', (oid,pid,ext.agora()))

            c.execute('''INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo)
                         VALUES(?,?,?,1)''',(cls.other,cls.participant,ext.agora()))
        cls.server = PortalPrestador(cls.banco,'127.0.0.1',0)
        cls.server.iniciar()
        cls.base = 'http://127.0.0.1:' + str(cls.server.porta)
        cls.browsers = {}
        for name,email in (('first','first@invalid.test'),('second','second@invalid.test'),
                           ('participant','part@invalid.test'),('admin','admin@invalid.test')):
            browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            status,html=request(browser,cls.base,'/login',{'email':email,'senha':'password123'})
            if status != 200:
                raise AssertionError((name,status,html[:300]))
            cls.browsers[name] = browser

    @classmethod
    def tearDownClass(cls):
        cls.server.parar()
        if cls.old_base is None:
            os.environ.pop('AUTOSEG_BASE',None)
        else:
            os.environ['AUTOSEG_BASE'] = cls.old_base
        cls.tmp.cleanup()

    def http(self,name,path):
        return request(self.browsers[name],self.base,path)

    def principal(self,name):
        return os_commands._provider_context(self.banco,
            {'pid':getattr(self,name),'nome':name})

    def test_provider_cannot_read_unrelated_os(self):
        status, body = self.http('first',f'/os/OTHER-RD-2')
        self.assertEqual(status,200)
        self.assertIn('fila compartilhada',body)
        self.assertNotIn('INTERNAL NOTES',body)
        self.assertNotIn('99999',body)
        self.assertNotIn('secret@customer.invalid',body)

    def test_provider_cannot_download_unrelated_pdf(self):
        self.assertEqual(self.http('first','/os/OTHER-RD-2/pdf')[0],404)

    def test_provider_cannot_read_unrelated_os_report_yaml(self):
        self.assertEqual(self.http('first','/os/OTHER-RD-2/relatorio.yaml')[0],404)

    def test_provider_cannot_view_unrelated_historical_os(self):
        self.assertEqual(self.http('first','/os/CLOSED-RD-3')[0],404)
        status,body=self.http('first','/historico')
        self.assertEqual(status,200)
        self.assertNotIn('CLOSED-RD-3',body)
        self.assertIn('OWN-RD-4',body)

    def test_provider_cannot_list_unrelated_customer(self):
        status,body=self.http('first','/clientes')
        self.assertEqual(status,200)
        self.assertNotIn('Secret Customer',body)
        self.assertIn('Visible Name',body)

    def test_provider_cannot_read_unrelated_customer_detail(self):
        self.assertEqual(self.http('first',f'/clientes/{self.c2}')[0],404)

    def test_provider_cannot_read_unrelated_customer_contact(self):
        self.assertEqual(self.http('first',f'/clientes/{self.c2}/contato')[0],404)

    def test_provider_cannot_read_unrelated_customer_pii(self):
        status,body=self.http('first','/clientes')
        self.assertNotIn('22222222222',body)
        self.assertNotIn('secret@customer.invalid',body)

    def test_provider_dashboard_does_not_expose_global_finance(self):
        status,body=self.http('first','/')
        self.assertEqual(status,200)
        self.assertNotIn('40.000',body)
        self.assertNotIn('99.999',body)
        self.assertEqual(ordens.financeiro_resumo_scoped(self.banco,self.first)['recebido'],300)
        self.assertEqual(ordens.financeiro_resumo_scoped(self.banco,self.first)['pendente'],0)

    def test_provider_dashboard_does_not_expose_unrelated_customers(self):
        status,body=self.http('first','/')
        self.assertEqual(status,200)
        self.assertNotIn('Secret Customer',body)
        self.assertEqual(ordens.clientes_ativos_scoped(self.banco,self.first),1)

    def test_admin_can_read_all_authorized_resources(self):
        status,body=self.http('admin',f'/clientes/{self.c2}')
        self.assertEqual(status,200)
        self.assertIn('secret@customer.invalid',body)
        self.assertEqual(self.http('admin','/os/OTHER-RD-2')[0],200)
        self.assertIn('CLOSED-RD-3',self.http('admin','/historico')[1])

    def test_owner_can_read_own_os(self):
        self.assertTrue(access.require_read_work_item(self.banco,self.principal('first'),self.own).allowed)
        self.assertEqual(self.http('first','/os/OWN-RD-1')[0],200)

    def test_participant_can_read_involved_os(self):
        self.assertTrue(access.require_read_work_item(self.banco,self.principal('participant'),self.other).allowed)
        status,body=self.http('participant','/os/OTHER-RD-2')
        self.assertEqual(status,200)
        self.assertNotIn('fila compartilhada',body)

    def test_revoked_membership_cannot_read_resource(self):
        with ext.db(self.banco) as c:
            c.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',(self.other,self.participant))
        try:
            with self.assertRaises(PermissionError):
                access.require_read_work_item(self.banco,self.principal('participant'),self.other)
            self.assertEqual(self.http('participant','/os/OTHER-RD-2/pdf')[0],404)
        finally:
            with ext.db(self.banco) as c:
                c.execute('UPDATE os_prestadores SET ativo=1 WHERE os_id=? AND prestador_id=?',(self.other,self.participant))

    def test_flag_off_and_on_both_enforce_reads(self):
        for flag in ('0','1'):
            with self.subTest(flag=flag),patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                with self.assertRaises(PermissionError):
                    os_commands.authorize_get(self.banco,self.principal('first'),f'/os/{self.other}/pdf')
                self.assertEqual(self.http('first','/os/OTHER-RD-2/pdf')[0],404)

    def test_active_queue_hides_financials_for_unrelated_provider(self):
        status,body=self.http('first','/os')
        self.assertEqual(status,200)
        self.assertIn('OTHER-RD-2',body)
        self.assertNotIn('99999',body)
        self.assertNotIn('secret@customer.invalid',body)
        self.assertNotIn(f'/clientes/{self.c2}',body)

    def test_customer_search_supports_formatted_document(self):
        total, rows = clientes_core.listar_paginado(
            '111.111.111-11', banco=self.banco, provider_id=self.first)
        self.assertEqual(total,1)
        self.assertEqual(rows[0]['nome'],'Visible Name')

    def test_customer_picker_returns_only_id_and_name(self):
        status,body=self.http('first','/clientes/busca?q=Secret')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body),[{'id':self.c2,'nome':'Secret Customer'}])

    def test_reduced_claim_obeys_existing_write_policy(self):
        with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'1'}):
            status,body=self.http('first','/os/SHARED-RD-5')
            self.assertEqual(status,200)
            self.assertIn('fila compartilhada',body)
            self.assertNotIn('Assumir OS</button>',body)

    def test_active_queue_reduced_view_allows_claim_without_form_fields(self):
        status,body=self.http('first','/os/SHARED-RD-5')
        self.assertEqual(status,200)
        self.assertIn('Assumir OS',body)
        self.assertNotIn('INTERNAL NOTES',body)
        self.assertNotIn('12345',body)
        self.assertNotIn('form-os',body)

    def test_closed_unrelated_has_same_response_as_missing(self):
        self.assertEqual(self.http('first','/os/CLOSED-RD-3')[0],404)
        self.assertEqual(self.http('first','/os/999999999')[0],404)

    def test_customer_projection_omits_unpermitted_fields_in_sql(self):
        total, rows = clientes_core.listar_paginado(
            banco=self.banco, provider_id=self.first, allowed_fields=('nome',))
        self.assertEqual(total,1)
        self.assertEqual(rows[0]['nome'],'Visible Name')
        self.assertEqual(rows[0]['email'],'')
        self.assertEqual(rows[0]['documento'],'')

    def test_z_claim_from_reduced_view(self):
        status,html=self.http('first','/os/SHARED-RD-5')
        self.assertEqual(status,200)
        token=re.search(r'name="csrf" value="([^"]+)"',html)
        self.assertIsNotNone(token)
        try:
            status,body=request(self.browsers['first'],self.base,
                                '/os/SHARED-RD-5/assumir',{'csrf':token.group(1)})
            self.assertEqual(status,200)
            self.assertNotIn('fila compartilhada',body)
            with ext.db(self.banco) as connection:
                self.assertEqual(ext.responsavel_atual(connection,self.shared),self.first)
        finally:
            with ext.db(self.banco) as connection:
                connection.execute('DELETE FROM os_responsaveis WHERE os_id=?',(self.shared,))
                connection.execute('DELETE FROM os_prestadores WHERE os_id=?',(self.shared,))


if __name__ == '__main__':
    unittest.main()
