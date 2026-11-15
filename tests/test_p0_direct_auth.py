"""P0 direct missing-check coverage, independent of the broader TOCTOU fix."""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flavors.autoseg.modules import os_commands
from officina.application.object_policy import Principal
from officina.application.policy import PADRAO, load_policy, PolicyStore
from officina.application import work_item_access as access
from officina.core import prestadores_ext as ext, cadastros_v9 as cad, fluxo_os
from officina.core import portal_negocios as neg
from officina.core.banco import criar_banco


class EffectivePolicyTest(unittest.TestCase):
    def test_repository_yaml_and_fallback_have_same_explicit_roles(self):
        from officina.application.policy import _policy_from_dict
        shipped = Path(__file__).resolve().parents[1] / 'flavors/autoseg/config/policy.yaml'
        repository_policy = load_policy(shipped)
        fallback = _policy_from_dict(PADRAO)
        for policy in (repository_policy, fallback):
            self.assertTrue(policy.allows('employee', 'customer.create'))
            self.assertTrue(policy.allows('employee', 'customer.edit.involved'))
            self.assertFalse(policy.allows('employee', 'customer.edit.all'))
            self.assertTrue(policy.allows('admin', 'customer.edit.involved'))
            for role in ('customer', 'porteiro', 'zelador', 'sindico'):
                self.assertFalse(policy.allows(role, 'customer.edit.involved'))

    def test_external_override_precedes_repository_and_warns_when_stale(self):
        import yaml
        import officina.application.policy as policy_module
        with tempfile.TemporaryDirectory() as location:
            with patch.dict(os.environ, {'AUTOSEG_BASE': location}):
                self.assertTrue(load_policy().allows('employee', 'customer.edit.involved'))
                external = Path(location) / 'policy.yaml'
                old = yaml.safe_load((Path(__file__).resolve().parents[1] /
                                    'flavors/autoseg/config/policy.yaml').read_text())
                old['roles']['employee']['permissions'].remove('customer.edit.involved')
                external.write_text(yaml.safe_dump(old,allow_unicode=True))
                policy_module._EXTERNAL_POLICY_WARNED.discard(str(external))
                with self.assertLogs('autoseg.policy', 'WARNING') as logs:
                    overridden = load_policy()
                self.assertFalse(overridden.allows('employee', 'customer.edit.involved'))
                self.assertIn('update it manually', logs.output[0])
                self.assertEqual(PolicyStore().path, external)
                external.unlink()
                self.assertTrue(load_policy().allows('employee', 'customer.edit.involved'))


class DirectAuthorizationDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p0_missing_checks_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'test.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        fluxo_os.instalar(self.db)
        self.owner = ext.cadastrar(self.db, 'Provider A', 'direct-a@invalid.test', 'Pass12345678')
        self.other = ext.cadastrar(self.db, 'Provider B', 'direct-b@invalid.test', 'Pass12345678')
        self.admin = ext.cadastrar(self.db, 'Admin', 'direct-admin@invalid.test', 'Pass12345678')
        cad.definir_admin(self.db,self.admin,True)
        with ext.db(self.db) as c:
            self.customer = c.execute("INSERT INTO clientes(nome,status) VALUES('Protected Client','Ativo')").lastrowid
            self.os_id = c.execute("INSERT INTO ordens_servico(cliente_id,numero_os,status,descricao) "
                                   "VALUES(?,'AUTH-OS','Aberta','Protected work')",
                                   (self.customer,)).lastrowid
            self.receipt_os = c.execute("INSERT INTO ordens_servico(cliente_id,numero_os,status,descricao) "
                                       "VALUES(?,'AUTH-FIN','Concluída','Closed work')",
                                       (self.customer,)).lastrowid
            self.finance_id = c.execute("INSERT INTO financeiro(os_id,cliente_id,status,valor) "
                                        "VALUES(?,?,'Aguardando pagamento',700)",
                                        (self.receipt_os,self.customer)).lastrowid
            c.execute('INSERT INTO os_encerramentos(os_id,situacao,ator,prestador_id,encerrado_em) '
                      "VALUES(?,'Concluída','Provider A',?, '2026-11-14')",
                      (self.receipt_os,self.owner))
            c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) '
                      'VALUES(?,?,?)', (self.os_id,self.owner,ext.agora()))
        self.principal_a = Principal(self.owner, 'employee',organization_id='autoseg',provider_id=self.owner)
        self.principal_b = Principal(self.other, 'employee',organization_id='autoseg',provider_id=self.other)
        self.principal_admin = Principal(self.admin, 'admin',organization_id='autoseg',provider_id=self.admin)

    def test_customer_create_is_distinct_from_edit(self):
        self.assertTrue(access.require_customer_create(self.principal_a).allowed)
        self.assertTrue(access.require_customer_create(self.principal_b).allowed)
        self.assertTrue(access.require_customer_write(self.db,self.principal_a,self.customer).allowed)
        with self.assertRaises(PermissionError):
            access.require_customer_write(self.db,self.principal_b,self.customer)
        self.assertTrue(access.require_customer_write(self.db,self.principal_admin,self.customer).allowed)
        with self.assertRaises(PermissionError):
            access.require_customer_create(Principal(self.owner,'employee',organization_id='autoseg',provider_id=self.owner,active=False))

    def test_revoked_relationship_does_not_grant_customer_write(self):
        with ext.db(self.db) as c:
            c.execute('INSERT INTO os_prestadores(os_id,prestador_id,ativo,atribuido_em) '
                      'VALUES(?,?,1,?)', (self.os_id,self.other,ext.agora()))
        self.assertTrue(access.require_customer_write(self.db,self.principal_b,self.customer).allowed)
        with ext.db(self.db) as c:
            c.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',
                      (self.os_id,self.other))
        with self.assertRaises(PermissionError):
            access.require_customer_write(self.db,self.principal_b,self.customer)
        with ext.db(self.db) as c:
            c.execute('DELETE FROM os_responsaveis WHERE os_id=?', (self.os_id,))
        with self.assertRaises(PermissionError):
            access.require_customer_write(self.db,self.principal_a,self.customer)

    def test_financial_receipt_checks_finalizer_or_admin_in_transaction(self):
        with ext.db(self.db) as c:
            before=c.execute('SELECT status,data_pagamento FROM financeiro WHERE id=?',
                             (self.finance_id,)).fetchone()
            audit_exists=bool(c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='portal_auditoria'").fetchone())
            before_audit=(c.execute('SELECT COUNT(*) FROM portal_auditoria').fetchone()[0]
                          if audit_exists else 0)
            before_events=c.execute('SELECT COUNT(*) FROM os_eventos WHERE os_id=?',
                                    (self.receipt_os,)).fetchone()[0]
        for actor in (self.other, None):
            with self.subTest(actor=actor),self.assertRaises(PermissionError):
                neg.financeiro_receber(self.db,self.finance_id,actor)
        with ext.db(self.db) as c:
            after=c.execute('SELECT status,data_pagamento FROM financeiro WHERE id=?',
                            (self.finance_id,)).fetchone()
            self.assertEqual(tuple(before),tuple(after))
            after_exists=bool(c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='portal_auditoria'").fetchone())
            after_audit=(c.execute('SELECT COUNT(*) FROM portal_auditoria').fetchone()[0]
                         if after_exists else 0)
            self.assertEqual(after_audit,before_audit)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM os_eventos WHERE os_id=?',
                                       (self.receipt_os,)).fetchone()[0],before_events)
        neg.financeiro_receber(self.db,self.finance_id,self.owner)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM financeiro WHERE id=?',
                                       (self.finance_id,)).fetchone()[0],'Recebido')

    def test_admin_can_receive_even_without_finalizer(self):
        with ext.db(self.db) as c:
            c.execute('DELETE FROM os_encerramentos WHERE os_id=?',(self.receipt_os,))
        with self.assertRaises(PermissionError):
            neg.financeiro_receber(self.db,self.finance_id,self.owner)
        neg.financeiro_receber(self.db,self.finance_id,self.admin)

    def test_flag_off_denies_every_sensitive_portal_writer_family(self):
        # Only the writer is replaced. The real Resource, SQL scope and ObjectPolicy execute.
        cases = (
            ('save','/os/{}/salvar',{'acao_status':'salvar'}),
            ('pending','/os/{}/salvar',{'acao_status':'Pendente'}),
            ('conclude','/os/{}/salvar',{'acao_status':'Concluída'}),
            ('cancel','/os/{}/cancelar',{}),
            ('draft-auto','/os/{}/rascunho/auto',{}),
            ('draft-save','/os/{}/rascunho/salvar',{}),
            ('attachment','/os/{}/anexo/1/remover',{}),
            ('photos','/os/{}/fotos',{}),
            ('invoice-attach','/os/{}/nota-fiscal',{}),
            ('invoice-remove','/os/{}/nota-fiscal/1/remover',{}),
            ('rateio','/os/{}/rateio',{}),
            ('reopen','/os/{}/abrir',{}),
            ('archive','/os/{}/arquivar',{}),
            ('assign','/os/{}/atribuir',{}),
            ('route','/os/{}/rota',{}),
            ('start','/os/{}/iniciar',{}),
            ('publish','/os/{}/publicar',{}),
            ('email-retry','/os/{}/reenviar-email',{}),
        )
        for flag in ('0','1'):
            with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                for label,raw,body in cases:
                    path=raw.format(self.os_id)
                    action,_=os_commands._command(path,body)
                    writer=Mock()
                    with self.subTest(flag=flag,family=label),patch.dict(os_commands.WRITERS,{action:writer}):
                        with self.assertRaises(PermissionError):
                            os_commands.execute_http(object(),self.db,self.principal_b,
                                  path,body,{'pid':self.other,'nome':'Provider B'})
                        writer.assert_not_called()

    def test_flag_off_enforces_inside_writer_transaction(self):
        with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'0'}):
            with ext.db(self.db) as connection:
                connection.execute('BEGIN IMMEDIATE')
                with self.assertRaises(PermissionError):
                    os_commands._transaction_guard(self.db,self.principal_b,
                         self.os_id,'edit')(connection)
                self.assertTrue(os_commands._transaction_guard(self.db,self.principal_a,
                         self.os_id,'edit')(connection).allowed)

    def test_create_and_assume_exceptions_with_flag_off(self):
        with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'0'}):
            for route in ('/os/rapida/salvar','/os/nova/salvar'):
                action,_=os_commands._command(route,{})
                writer=Mock(return_value='created')
                with patch.dict(os_commands.WRITERS,{action:writer}):
                    self.assertEqual(os_commands.execute_http(object(),self.db,self.principal_b,
                        route,{}, {'pid':self.other,'nome':'Provider B'}),'created')
                writer.assert_called_once()
            with ext.db(self.db) as c:
                unassigned=c.execute("INSERT INTO ordens_servico(cliente_id,numero_os,status,descricao) "
                                     "VALUES(?,'QUEUE-OS','Aberta','Shareable')",
                                     (self.customer,)).lastrowid
            class UI:
                def redir(self,url):return url
            response=os_commands.execute_http(UI(),self.db,self.principal_b,
                f'/os/{unassigned}/assumir',{}, {'pid':self.other,'nome':'Provider B'})
            self.assertIn('/os/',response)
            with ext.db(self.db) as c:
                self.assertEqual(ext.responsavel_atual(c,unassigned),self.other)
