"""Real-session, real-SQL desktop BOLA/IDOR regression tests."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import api_server, prestador_auth
from officina.application.http_service import HttpService
from officina.core import (banco, prestadores_ext as ext, cadastros_v9 as cad,
                           fluxo_os, atendimento_os, catalogo_servicos)


class DesktopObjectAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='desktop_object_auth_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'desktop.db')
        banco.criar_banco(self.db)
        for installer in (ext.instalar, cad.instalar, fluxo_os.instalar,
                          atendimento_os.instalar, prestador_auth.instalar,
                          catalogo_servicos.instalar):
            installer(self.db)
        self.users = {}
        for name in ('first','second','participant','admin'):
            pid = ext.cadastrar(self.db, name, f'{name}@test.invalid', 'Pass12345678')
            self.users[name] = pid
        cad.definir_admin(self.db, self.users['admin'], True)
        with ext.db(self.db) as c:
            own_client = c.execute("INSERT INTO clientes(nome,status,email,documento,telefone) VALUES ('Own Client','Ativo','own@invalid.test','11111111111','111111')").lastrowid
            other_client = c.execute("INSERT INTO clientes(nome,status,email,documento,telefone) VALUES ('Secret Client','Ativo','secret@invalid.test','22222222222','222222')").lastrowid
            self.other_client = other_client
            self.own_client = own_client
            self.own = c.execute("""INSERT INTO ordens_servico (numero_os,cliente_id,status,descricao,valor_total,data_abertura,criado_em)
                VALUES ('A-OS',?,'Aberta','private internal note A',19,'2026-11-14','2026-11-14')""",(own_client,)).lastrowid
            self.other = c.execute("""INSERT INTO ordens_servico (numero_os,cliente_id,status,descricao,valor_total,data_abertura,criado_em)
                VALUES ('B-OS',?,'Iniciada','secret internal note B',98765,'2026-11-14','2026-11-14')""",(other_client,)).lastrowid
            self.closed = c.execute("""INSERT INTO ordens_servico (numero_os,cliente_id,status,descricao,valor_total,data_abertura,criado_em)
                VALUES ('C-OS',?,'Concluída','closed private B',99999,'2026-11-14','2026-11-14')""",(other_client,)).lastrowid
            c.execute("INSERT INTO financeiro(os_id,cliente_id,valor,status) VALUES(?,? ,55000,'Recebido')",(self.other,other_client))
        for os_id, actor in ((self.own,'first'),(self.other,'second')):
            ext.assumir(self.db,os_id,self.users[actor])
        with ext.db(self.db) as c:
            c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)',
                      (self.closed,self.users['second'],ext.agora()))
            c.execute('INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo) VALUES(?,?,?,1)',
                      (self.other,self.users['participant'],ext.agora()))
        self.server = api_server.start(self.db,'127.0.0.1',0)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = 'http://127.0.0.1:'+str(self.server.server_address[1])
        self.tokens = {}
        for name in self.users:
            result = prestador_auth.login(self.db,f'{name}@test.invalid','Pass12345678')
            self.assertIsNotNone(result)
            self.tokens[name] = result['token']

    def request(self,name,path,method='GET',payload=None,headers=None):
        body=json.dumps(payload or {}).encode('utf-8') if method!='GET' else None
        request=urllib.request.Request(self.base+'/api/v1/desktop'+path,
                     data=body, method=method,
                     headers={'Authorization':'Bearer '+self.tokens[name],
                              'Content-Type':'application/json',**(headers or {})})
        try:
            with urllib.request.urlopen(request,timeout=10) as response:
                return response.status,json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code,json.loads(error.read())

    def test_provider_cannot_read_unrelated_os_objects(self):
        for suffix in ('/contexto','/contexto-atribuicao','/anexos/contar','/pdf/arquivo'):
            with self.subTest(suffix=suffix):
                self.assertEqual(self.request('first',f'/os/{self.other}'+suffix)[0],404)
        self.assertEqual(self.request('first',f'/os/contexto?os_id={self.other}')[0],404)

    def test_unrelated_and_missing_return_same_404(self):
        for suffix in ('/contexto','/pdf/arquivo','/anexos/contar'):
            self.assertEqual(self.request('first',f'/os/{self.other}'+suffix),
                             self.request('first',f'/os/999999'+suffix))

    def test_provider_cannot_write_other_os(self):
        routes=(('/atribuir',{'prestador_id':self.users['first']}),
                ('/desatribuir',{}),('/iniciar',{}),('/pdf/publicar',{}),
                ('/email/preparar',{}),('/nota/preparar',{}))
        for route,payload in routes:
            with self.subTest(route=route):
                status,body=self.request('first',f'/os/{self.other}'+route,'POST',payload)
                self.assertEqual(status,404,body)
        with ext.db(self.db) as c:
            self.assertEqual(ext.responsavel_atual(c,self.other), self.users['second'])
            self.assertEqual(c.execute('SELECT status FROM ordens_servico WHERE id=?',
                                       (self.other,)).fetchone()[0],'Iniciada')

    def test_localhost_and_shared_token_not_object_grants(self):
        with patch.dict(os.environ, {'AUTOSEG_DESKTOP_TOKEN':'test-secret'}):
            status,_=self.request('first',f'/os/{self.other}/contexto',
                                   headers={'X-AUTOSEG-Desktop-Token':'test-secret'})
            self.assertEqual(status,404)

    def test_admin_reads_full_and_can_operate(self):
        status,data=self.request('admin',f'/os/{self.other}/contexto')
        self.assertEqual(status,200,data)
        self.assertEqual(data['data']['dados']['valor_total'],98765)
        status,data=self.request('admin',f'/os/{self.other}/atribuir','POST',
                                  {'prestador_id':self.users['admin']})
        self.assertEqual(status,200,data)

    def test_owner_and_participant_can_read(self):
        self.assertEqual(self.request('first',f'/os/{self.own}/contexto')[0],200)
        self.assertEqual(self.request('participant',f'/os/{self.other}/contexto')[0],200)

    def test_revoked_participant_denied_immediately(self):
        self.assertEqual(self.request('participant',f'/os/{self.other}/contexto')[0],200)
        with ext.db(self.db) as c:
            c.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',
                      (self.other,self.users['participant']))
        self.assertEqual(self.request('participant',f'/os/{self.other}/contexto')[0],404)

    def test_both_flag_states_enforce_reads_and_writes(self):
        for flag in ('0','1'):
            with self.subTest(flag=flag),patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                self.assertEqual(self.request('first',f'/os/{self.other}/contexto')[0],404)
                self.assertEqual(self.request('first',f'/os/{self.other}/iniciar','POST')[0],404)

    def test_shared_queue_reduced_json_has_exact_keys(self):
        keys={'id','numero_os','cliente','status','data_abertura',
              'atualizado_em','responsavel','participantes'}
        for endpoint in ('/os/ativas','/os/recentes'):
            status,data=self.request('first',endpoint)
            self.assertEqual(status,200,data)
            other=next(row for row in data['data'] if row['numero_os']=='B-OS')
            self.assertEqual(set(other),keys)
            self.assertNotIn('98765',json.dumps(other))
            self.assertNotIn('secret@invalid.test',json.dumps(other))
            self.assertNotIn('secret internal note',json.dumps(other))
            self.assertNotIn('22222222222',json.dumps(other))
            self.assertNotIn('C-OS',str(data))
            own=next(row for row in data['data'] if row['numero_os']=='A-OS')
            self.assertIn('valor_total',own)

    def test_assignment_lists_are_admin_only(self):
        for endpoint in ('/os/escolha','/os/atribuicao'):
            self.assertEqual(self.request('first',endpoint)[0],403)
            self.assertEqual(self.request('admin',endpoint)[0],200)

    def test_customer_and_dashboard_scoped(self):
        status,data=self.request('first','/clientes')
        self.assertEqual(status,200,data)
        text=json.dumps(data)
        self.assertNotIn('Secret Client',text)
        self.assertNotIn('secret@invalid.test',text)
        self.assertEqual(self.request('first',f'/clientes/{self.other_client}')[0],404)
        self.assertEqual(self.request('first',f'/clientes/{self.own_client}')[0],200)
        status,data=self.request('first','/resumo')
        self.assertEqual(status,200,data)
        self.assertEqual(data['data']['financeiro_recebido'],0)
        self.assertEqual(self.request('first','/financeiro')[0],403)

    def test_remote_desktop_client_accepts_reduced_rows_without_money(self):
        client=HttpService(self.base)
        client.login('first@test.invalid','Pass12345678')
        for rows in (client.listar_os_ativas(),client.listar_os_recentes(6)):
            own=next(row for row in rows if row.numero_os=='A-OS')
            other=next(row for row in rows if row.numero_os=='B-OS')
            self.assertEqual(own.origem,'App')
            self.assertEqual(other.origem,'Compartilhada')
            self.assertEqual(other.forma_pagamento,'')
            self.assertIn('second',other.responsavel)

    def test_minimal_customer_picker_not_customer_management(self):
        for path in ('/clientes/busca', '/contexto/os-rapida'):
            status,data=self.request('first',path)
            self.assertEqual(status,200,data)
            customers=(data['data'] if path == '/clientes/busca'
                       else data['data']['clientes'])
            self.assertIn({'id':self.other_client,'nome':'Secret Client'},customers)
            self.assertTrue(all(set(row)=={'id','nome'} for row in customers))
            self.assertNotIn('secret@invalid.test',json.dumps(data))

    def test_non_admin_is_denied_adjacent_global_customer_data(self):
        for path in ('/historico','/relatorios','/pj/painel',
                     '/portal/solicitacoes','/financeiro/resumo',
                     '/contexto/responsavel','/clientes/ativo?documento=22222222222'):
            with self.subTest(path=path):
                self.assertEqual(self.request('first',path)[0],403)

    def test_customer_picker_does_not_allow_unrelated_detail(self):
        self.assertEqual(self.request('first','/clientes/busca')[0],200)
        self.assertEqual(self.request('first',f'/clientes/{self.other_client}/ativo')[0],404)

    def test_customer_order_count_does_not_enumerate_others_work(self):
        with ext.db(self.db) as c:
            other = c.execute("""INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao)
                VALUES ('EXTRA-CLOSED',?,'Concluída','hidden')""",
                (self.own_client,)).lastrowid
            c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)',
                      (other,self.users['second'],ext.agora()))
        status,result=self.request('first',f'/clientes/{self.own_client}/os/contar')
        self.assertEqual(status,200,result)
        self.assertEqual(result['data']['total'],1)
        status,result=self.request('admin',f'/clientes/{self.own_client}/os/contar')
        self.assertEqual(status,200,result)
        self.assertEqual(result['data']['total'],2)

    def test_customer_creation_and_edit_require_distinct_permissions(self):
        # The picker does not imply that the record can be modified.
        self.assertEqual(self.request('first',f'/clientes/{self.other_client}',
                                      'PUT',{'dados':{'nome':'Hacked Client'}})[0],404)
        status,created=self.request('first','/clientes','POST',
                          {'dados':{'nome':'New Customer Via Desktop',
                                    'tipo_pessoa':'Física','status':'Ativo','documento':''}})
        self.assertEqual(status,200,created)
        new_id=created['data']['id']
        self.assertEqual(self.request('first',f'/clientes/{new_id}',
                                      'PUT',{'dados':{'nome':'No Unrelated Edit'}})[0],404)
        status,record=self.request('first',f'/clientes/{self.own_client}',
                         'PUT',{'dados':{'nome':'Involved Customer Updated'}})
        self.assertEqual(status,200,record)

    def test_existing_os_status_mapping_does_not_promote_edit_to_conclude(self):
        from flavors.autoseg.modules import api_desktop
        from unittest.mock import patch
        fields={'os_id':self.other,'cliente_id':self.other_client,'tecnico':'',
                'descricao':'Existing OS with participant','valor_mao_obra':0,
                'valor_materiais':0,'custo_materiais':0,'valor_total':0,
                'forma_pagamento':'PIX','urgencia':'Normal','observacoes':'',
                'texto_adicional':'','dados_incompletos':0,'tempo_horas':0,
                'composicao_json':'','base_percentuais':'total','materiais':[],
                'acao':'','relato':'','motivo':''}
        for flag in ('0','1'):
            with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                for status in ('Concluída','Cancelada'):
                    with self.subTest(flag=flag,status=status):
                        with patch.object(api_desktop.LocalService,'salvar_os') as service:
                            code,_=self.request('participant','/os','POST',
                                            {**fields,'acao':status})
                            self.assertEqual(code,403)
                            service.assert_not_called()
                with patch.object(api_desktop.LocalService,'salvar_os',return_value={'os_id':self.other}) as service:
                    code,_=self.request('participant','/os','POST',
                                       {**fields,'acao':'Pendente'})
                    self.assertEqual(code,200)
                    service.assert_called_once()

    def test_catalogue_global_and_stock_admin(self):
        self.assertEqual(self.request('first','/catalogo/servicos')[0],200)
        self.assertEqual(self.request('first','/estoque/materiais')[0],403)


if __name__ == '__main__':
    unittest.main()
