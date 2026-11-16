"""B1 reviewer regressions: real OS service transitions and action parity.

Run on the Arch review host; this patch was authored without executing tests.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flavors.autoseg.modules.autoseg_actions import resolved_actions
from flavors.autoseg.modules import os_commands
from officina.application.local_service import LocalService
from officina.application.object_policy import Principal
from officina.core import (banco, cadastros_v9 as cad, prestadores_ext as ext,
                           atendimento_os as aten, fluxo_os as fluxo,
                           produtividade_os as prod)


class WorkActionsExecutionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_b1_work_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'work.db')
        banco.criar_banco(self.db)
        for install in (ext.instalar, cad.instalar, aten.instalar,
                        fluxo.instalar, prod.instalar):
            install(self.db)
        self.admin = ext.cadastrar(self.db, 'Administrator',
                                  'b1-admin@invalid.test', 'Pass12345678')
        self.employee = ext.cadastrar(self.db, 'Employee',
                                     'b1-employee@invalid.test', 'Pass12345678')
        self.foreign = ext.cadastrar(self.db, 'Foreign',
                                    'b1-foreign@invalid.test', 'Pass12345678')
        cad.definir_admin(self.db, self.admin, True)
        with ext.db(self.db) as c:
            customer = c.execute(
                "INSERT INTO clientes(nome,status,tipo_pessoa) "
                "VALUES('B1 customer','Ativo','Física')").lastrowid
            self.open_id = c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao) "
                "VALUES('B1-OPEN',?,'Aberta','Test')", (customer,)).lastrowid
            self.closed_id = c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao) "
                "VALUES('B1-CLOSED',?,'Concluída','Test')", (customer,)).lastrowid
            self.foreign_id = c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao) "
                "VALUES('B1-FOREIGN',?,'Concluída','Test')", (customer,)).lastrowid
            for oid,pid in ((self.open_id,self.employee),
                            (self.closed_id,self.employee),
                            (self.foreign_id,self.foreign)):
                c.execute('''INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em)
                             VALUES(?,?,?)''', (oid,pid,ext.agora()))
        self.admin_actor = Principal(self.admin, 'admin',
                                     organization_id='autoseg', provider_id=self.admin)
        self.employee_actor = Principal(self.employee, 'employee',
                                        organization_id='autoseg', provider_id=self.employee)
        self.service = LocalService(self.db)

    def _actions(self, actor, oid, surface):
        return tuple((a.id,a.label,a.priority,a.confirm)
                     for a in resolved_actions(self.db, actor, 'work',
                                               object_id=oid, surface=surface))

    def _row(self, oid):
        with ext.db(self.db) as c:
            return dict(c.execute('SELECT * FROM ordens_servico WHERE id=?', (oid,)).fetchone())

    def test_actions_same_ids_labels_order_and_confirmation_web_gtk(self):
        for actor in (self.admin_actor,self.employee_actor):
            for oid in (None,self.open_id,self.closed_id,self.foreign_id):
                with self.subTest(pid=actor.provider_id, oid=oid):
                    self.assertEqual(self._actions(actor,oid,'web'),
                                     self._actions(actor,oid,'gtk'))

    def test_reopen_only_ended_nonarchived_work(self):
        initial = {a[0] for a in self._actions(self.admin_actor,self.closed_id,'web')}
        self.assertIn('work.reopen',initial)
        self.assertNotIn('work.reopen', {a[0] for a in self._actions(
            self.admin_actor,self.open_id,'web')})
        self.assertNotIn('work.reopen', {a[0] for a in self._actions(
            self.employee_actor,self.closed_id,'web')})
        before = self._row(self.open_id)
        with self.assertRaises(PermissionError):
            self.service.reabrir_os(self.open_id, principal=self.admin_actor)
        self.assertEqual(self._row(self.open_id), before)
        self.assertTrue(self.service.reabrir_os(self.closed_id,
                                                 principal=self.admin_actor))
        self.assertEqual(self._row(self.closed_id)['status'], 'Aberta')
        self.assertNotIn('work.reopen', {a[0] for a in self._actions(
            self.admin_actor,self.closed_id,'gtk')})

    def test_web_command_executes_real_reopen_service(self):
        class WebAdapter:
            @staticmethod
            def redir(target):
                return target

        result = os_commands.execute_http(
            WebAdapter(), self.db, self.admin_actor,
            f'/os/{self.closed_id}/reabrir', {},
            {'pid': self.admin, 'nome': 'Administrator'})
        self.assertIn('/os/', result)
        self.assertEqual(self._row(self.closed_id)['status'], 'Aberta')

    def test_foreign_and_archived_work_cannot_reopen(self):
        old = self._row(self.foreign_id)
        with self.assertRaises(PermissionError):
            self.service.reabrir_os(self.foreign_id,
                                    principal=self.employee_actor)
        self.assertEqual(self._row(self.foreign_id), old)
        with ext.db(self.db) as c:
            c.execute('UPDATE ordens_servico SET arquivada=1 WHERE id=?',
                      (self.closed_id,))
        old = self._row(self.closed_id)
        self.assertNotIn('work.reopen', {a[0] for a in self._actions(
            self.admin_actor,self.closed_id,'gtk')})
        with self.assertRaises(PermissionError):
            self.service.reabrir_os(self.closed_id,
                                    principal=self.admin_actor)
        self.assertEqual(self._row(self.closed_id), old)

    def test_invalid_sessions_and_revocation_have_no_actions(self):
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET ativo=0 WHERE id=?', (self.employee,))
        with self.assertRaises(PermissionError):
            self._actions(self.employee_actor,self.open_id,'web')
        with self.assertRaises(PermissionError):
            self.service.reabrir_os(self.closed_id,
                                    principal=self.employee_actor)

    def test_web_command_registry_contains_reopen_with_object_policy(self):
        command,os_id = os_commands._command('/os/9/reabrir', {})
        self.assertEqual((command,os_id), ('reabrir',9))
        self.assertEqual(os_commands._permission(command,{}), 'reopen')
        self.assertIn(command, os_commands.WRITERS)


if __name__ == '__main__':
    unittest.main()
