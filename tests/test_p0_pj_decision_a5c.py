"""A5c: PJ verification decisions recheck current admin role inside the writer."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import solicitacoes_pj as pj
from officina.application.object_policy import Principal
from officina.core import cadastros_v9 as cad, prestadores_ext as ext
from officina.core.banco import criar_banco


class PjDecisionAuthorizationA5cTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='a5c_pj_')
        self.addCleanup(tmp.cleanup)
        self.db = str(Path(tmp.name) / 'pj.sqlite')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        pj.instalar(self.db)
        self.admin = ext.cadastrar(self.db, 'Admin A5c', 'admin-a5c@example.invalid', 'Pass12345678')
        self.employee = ext.cadastrar(self.db, 'Employee A5c', 'employee-a5c@example.invalid', 'Pass12345678')
        cad.definir_admin(self.db, self.admin, True)
        with ext.db(self.db) as c:
            customer = c.execute("INSERT INTO clientes(nome,status) VALUES('PJ Test','Ativo')").lastrowid
            org = c.execute("""INSERT INTO v9_organizacoes
                (cliente_id,nome,tipo,criado_em) VALUES(?,'PJ Test','Empresa',?)""",
                (customer, ext.agora())).lastrowid
        self.request_id = pj.criar(self.db, org, 'Requester A5c', '51999999999',
                                   'Please repair the security equipment') ['id']

    def _snapshot(self):
        with ext.db(self.db) as c:
            tables = ('pj_solicitacoes_publicas', 'ordens_servico', 'clientes',
                      'v9_organizacoes', 'os_eventos', 'portal_auditoria')
            snapshot = {}
            for name in tables:
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone():
                    snapshot[name] = [tuple(row) for row in c.execute(f'SELECT * FROM {name} ORDER BY rowid')]
            return snapshot

    def _principal(self, pid):
        if pid is None:
            return None
        role = 'admin' if pid == self.admin else 'employee'
        return Principal(pid, role, organization_id='autoseg', provider_id=pid)

    def _decide(self, decision, actor):
        principal = self._principal(actor)
        if decision == 'accept':
            return pj.aceitar(self.db, self.request_id, ator='Displayed Name', principal=principal)
        return pj.recusar(self.db, self.request_id, 'Request is not applicable',
                         ator='Displayed Name', principal=principal)

    def _denied_unchanged(self, decision, actor):
        before = self._snapshot()
        with self.assertRaises(PermissionError):
            self._decide(decision, actor)
        self.assertEqual(before, self._snapshot(), 'Denied PJ decision must have zero mutations')

    def test_unrelated_employee_denied_for_both_decisions(self):
        for decision in ('accept', 'reject'):
            with self.subTest(decision=decision):
                self._denied_unchanged(decision, self.employee)

    def test_missing_actor_cannot_bypass_service(self):
        for decision in ('accept', 'reject'):
            with self.subTest(decision=decision):
                self._denied_unchanged(decision, None)

    def test_direct_service_without_actor_fails_closed(self):
        before = self._snapshot()
        with self.assertRaises(PermissionError):
            pj.aceitar(self.db, self.request_id)
        self.assertEqual(before, self._snapshot())
        with self.assertRaises(PermissionError):
            pj.recusar(self.db, self.request_id, 'This request is not applicable')
        self.assertEqual(before, self._snapshot())

    def test_admin_can_accept_and_creates_one_os(self):
        before = self._snapshot()
        result = self._decide('accept', self.admin)
        self.assertGreater(result['os_id'], 0)
        with ext.db(self.db) as c:
            row = c.execute('SELECT status,os_id FROM pj_solicitacoes_publicas WHERE id=?',
                            (self.request_id,)).fetchone()
            self.assertEqual(tuple(row), ('Aceito', result['os_id']))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ordens_servico').fetchone()[0],
                             len(before['ordens_servico']) + 1)

    def test_admin_can_reject_without_creating_os(self):
        before = self._snapshot()
        self.assertTrue(self._decide('reject', self.admin))
        with ext.db(self.db) as c:
            row = c.execute('SELECT status,os_id,motivo FROM pj_solicitacoes_publicas WHERE id=?',
                            (self.request_id,)).fetchone()
        self.assertEqual(row['status'], 'Recusado')
        self.assertIsNone(row['os_id'])
        self.assertEqual(row['motivo'], 'Request is not applicable')
        self.assertEqual(len(before['ordens_servico']), len(self._snapshot()['ordens_servico']))

    def test_revoked_admin_role_after_preflight_cannot_accept_or_reject(self):
        self.assertTrue(cad.prestador_admin(self.db, self.admin))  # route preflight
        cad.definir_admin(self.db, self.admin, False)  # role revoked before writer
        for decision in ('accept', 'reject'):
            with self.subTest(decision=decision):
                self._denied_unchanged(decision, self.admin)

    def test_inactive_or_excluded_admin_denied(self):
        for column in ('ativo', 'excluido'):
            with self.subTest(column=column):
                with ext.db(self.db) as c:
                    c.execute(f'UPDATE prestadores SET {column}=? WHERE id=?',
                              (0 if column == 'ativo' else 1, self.admin))
                self._denied_unchanged('accept', self.admin)
                self._denied_unchanged('reject', self.admin)
                with ext.db(self.db) as c:
                    c.execute(f'UPDATE prestadores SET {column}=? WHERE id=?',
                              (1 if column == 'ativo' else 0, self.admin))

    def test_flag_does_not_bypass_admin_guard(self):
        for flag in ('0', '1'):
            with self.subTest(flag=flag), patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT': flag}):
                self._denied_unchanged('accept', self.employee)
                self._denied_unchanged('reject', self.employee)


if __name__ == '__main__':
    unittest.main()
