"""A5a: verify receipt authorization using real SQLite transactions and callers."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from officina.core import cadastros_v9 as cad
from officina.core import fluxo_os
from officina.core import portal_negocios as neg
from officina.core import prestadores_ext as ext
from officina.core.banco import criar_banco


class FinancialReceiptAuthorizationA5aTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='a5a_receipt_')
        self.addCleanup(self.temp.cleanup)
        self.database = str(Path(self.temp.name) / 'receipt.db')
        criar_banco(self.database)
        ext.instalar(self.database)
        cad.instalar(self.database)
        fluxo_os.instalar(self.database)

        self.finalizer = ext.cadastrar(self.database, 'Finalizer A',
                                      'a5a-finalizer@example.invalid', 'SafePassword123')
        self.other = ext.cadastrar(self.database, 'Provider B',
                                  'a5a-other@example.invalid', 'SafePassword123')
        self.admin = ext.cadastrar(self.database, 'Admin',
                                  'a5a-admin@example.invalid', 'SafePassword123')
        cad.definir_admin(self.database, self.admin, True)
        with ext.db(self.database) as c:
            customer = c.execute("INSERT INTO clientes(nome,status) VALUES('A5a Client','Ativo')").lastrowid
            self.os_id = c.execute("""INSERT INTO ordens_servico(cliente_id,numero_os,status,descricao)
                        VALUES(?,'A5A-RECEIPT','Concluída','Receipt authorization')""",
                        (customer,)).lastrowid
            self.finance_id = c.execute("""INSERT INTO financeiro(os_id,cliente_id,status,valor)
                        VALUES(?,?,'Aguardando pagamento',125)""", (self.os_id, customer)).lastrowid
            c.execute("""INSERT INTO os_encerramentos(os_id,situacao,ator,prestador_id,encerrado_em)
                         VALUES(?,'Concluída','Finalizer A',?,'2026-11-14')""",
                         (self.os_id, self.finalizer))

    def _snapshot(self):
        with ext.db(self.database) as c:
            payment = c.execute('SELECT status,data_pagamento FROM financeiro WHERE id=?',
                                (self.finance_id,)).fetchone()
            events = c.execute('SELECT COUNT(*) FROM os_eventos WHERE os_id=?',
                               (self.os_id,)).fetchone()[0]
            audit_table = c.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='portal_auditoria'""").fetchone()
            audits = (c.execute('SELECT COUNT(*) FROM portal_auditoria').fetchone()[0]
                      if audit_table else 0)
            return tuple(payment), events, audits

    def _assert_denial_is_atomic(self, actor):
        original = self._snapshot()
        with self.assertRaises(PermissionError):
            neg.financeiro_receber(self.database, self.finance_id, actor)
        self.assertEqual(self._snapshot(), original,
                         'Denied receipt must not change payment, events or audit')

    def _assert_received(self, actor):
        before = self._snapshot()
        neg.financeiro_receber(self.database, self.finance_id, actor)
        payment, events, audits = self._snapshot()
        self.assertEqual(payment[0], 'Recebido')
        self.assertIsNotNone(payment[1])
        self.assertEqual(events, before[1] + 1)
        self.assertEqual(audits, before[2] + 1)

    def test_finalizer_allowed_with_flag_disabled(self):
        with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT': '0'}):
            self._assert_received(self.finalizer)

    def test_finalizer_allowed_with_flag_enabled(self):
        with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT': '1'}):
            self._assert_received(self.finalizer)

    def test_other_provider_denied_with_both_flag_values_without_side_effects(self):
        for value in ('0', '1'):
            with self.subTest(flag=value), patch.dict(os.environ, {
                    'AUTOSEG_OBJECT_POLICY_ENFORCEMENT': value}):
                self._assert_denial_is_atomic(self.other)

    def test_admin_allowed_with_recorded_finalizer(self):
        self._assert_received(self.admin)

    def test_no_finalizer_blocks_non_admin_without_side_effects(self):
        with ext.db(self.database) as c:
            c.execute('DELETE FROM os_encerramentos WHERE os_id=?', (self.os_id,))
        self._assert_denial_is_atomic(self.finalizer)
        self._assert_denial_is_atomic(self.other)

    def test_admin_allowed_without_finalizer_record(self):
        with ext.db(self.database) as c:
            c.execute('DELETE FROM os_encerramentos WHERE os_id=?', (self.os_id,))
        self._assert_received(self.admin)

    def test_none_actor_is_never_implicit_admin(self):
        self._assert_denial_is_atomic(None)
        with ext.db(self.database) as c:
            c.execute('DELETE FROM os_encerramentos WHERE os_id=?', (self.os_id,))
        self._assert_denial_is_atomic(None)

    def test_revoked_finalizer_relationship_denied_at_service_entry(self):
        # Simulate preflight while ownership is valid, then revoke before writer.
        with ext.db(self.database) as c:
            previous = c.execute('SELECT prestador_id FROM os_encerramentos WHERE os_id=?',
                                 (self.os_id,)).fetchone()
        self.assertEqual(previous[0], self.finalizer)
        with ext.db(self.database) as c:
            c.execute('UPDATE os_encerramentos SET prestador_id=? WHERE os_id=?',
                      (self.other, self.os_id))
        self._assert_denial_is_atomic(self.finalizer)
        self._assert_received(self.other)

    def test_deactivated_finalizer_current_contract_is_still_allowed(self):
        # A5a explicitly documents existing behavior: no ativo check in this service.
        with ext.db(self.database) as c:
            c.execute('UPDATE prestadores SET ativo=0 WHERE id=?', (self.finalizer,))
        self._assert_received(self.finalizer)


if __name__ == '__main__':
    unittest.main()
