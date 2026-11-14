"""A5b: customer edits must authorize against the writer's current SQLite snapshot."""
from __future__ import annotations

import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from officina.application.object_policy import Principal
from officina.application import work_item_access as access
from officina.core import cadastros_v9 as cad, fluxo_os
from officina.core import portal_negocios as neg
from officina.core import prestadores_ext as ext
from officina.core.banco import criar_banco


def _edit_with_writer_lock(db, customer, pid, principal, signal):
    """Pause at the real audit boundary, after the service has acquired its lock."""
    original = neg.audit

    def audited(connection, *args):
        signal.send('writer_locked')
        if signal.recv() != 'release':
            raise RuntimeError('Unexpected writer release message')
        return original(connection, *args)

    neg.audit = audited
    try:
        neg.cliente_salvar(db, {'tipo_pessoa':'Física','nome':'Writer changed',
                               'status':'Ativo'}, pid, customer, principal=principal)
        signal.send(('result', 'committed'))
    except Exception as exc:
        signal.send(('result', type(exc).__name__, str(exc)))
    finally:
        signal.close()


def _revoke_under_lock(db, work_id, provider, signal):
    try:
        with sqlite3.connect(db, timeout=0) as c:
            c.execute('PRAGMA busy_timeout=0')
            try:
                c.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as exc:
                if 'locked' not in str(exc).lower():
                    raise
                signal.send('lock_busy')
            else:
                c.rollback()
                raise AssertionError('Revoker acquired the writer lock prematurely')
        signal.send('about_to_revoke')
        with ext.db(db) as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM os_responsaveis WHERE os_id=? AND prestador_id=?',
                      (work_id,provider))
            c.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',
                      (work_id,provider))
        signal.send('revoked')
    except Exception as exc:
        signal.send(('error', type(exc).__name__, str(exc)))
    finally:
        signal.close()


class CustomerWriterTransactionTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='a5b_customer_')
        self.addCleanup(tmp.cleanup)
        self.db = str(Path(tmp.name) / 'test.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        fluxo_os.instalar(self.db)
        self.owner = ext.cadastrar(self.db,'A5b owner','a5b-owner@invalid.test','Pass12345678')
        self.other = ext.cadastrar(self.db,'A5b unrelated','a5b-other@invalid.test','Pass12345678')
        self.admin = ext.cadastrar(self.db,'A5b admin','a5b-admin@invalid.test','Pass12345678')
        cad.definir_admin(self.db,self.admin,True)
        with ext.db(self.db) as c:
            self.customer = c.execute("INSERT INTO clientes(nome,tipo_pessoa,status) VALUES('Initial','Física','Ativo')").lastrowid
            self.os_id = c.execute("INSERT INTO ordens_servico(cliente_id,numero_os,status,descricao) VALUES(?,'A5B','Aberta','Work')",
                                   (self.customer,)).lastrowid
            c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)',
                      (self.os_id,self.owner,ext.agora()))
            neg.criar_auditoria(c)
        self.owner_actor = Principal(self.owner,'employee',organization_id='autoseg',provider_id=self.owner)
        self.other_actor = Principal(self.other,'employee',organization_id='autoseg',provider_id=self.other)
        self.admin_actor = Principal(self.admin,'admin',organization_id='autoseg',provider_id=self.admin)

    def _fields(self):
        with ext.db(self.db) as c:
            row=c.execute('SELECT '+','.join(neg.CLIENTE_CAMPOS)+' FROM clientes WHERE id=?',
                          (self.customer,)).fetchone()
            audits=list(c.execute('SELECT id,prestador_id,acao,referencia,detalhes FROM portal_auditoria ORDER BY id'))
            return tuple(row), [tuple(r) for r in audits]

    def _edit(self, actor, name='Edited', *, pid=None):
        return neg.cliente_salvar(self.db,{'tipo_pessoa':'Física','nome':name,'status':'Ativo'},
                                 actor.provider_id if pid is None and actor is not None else pid,
                                 self.customer,principal=actor)

    def _deny_unchanged(self, actor, *, pid=None):
        before=self._fields()
        with self.assertRaises(PermissionError):
            self._edit(actor,pid=pid)
        self.assertEqual(self._fields(),before)

    def test_involved_provider_edit_preserves_diff_audit_and_return(self):
        old=self._fields()
        self.assertEqual(self._edit(self.owner_actor),self.customer)
        fields,audits=self._fields()
        self.assertEqual(fields[neg.CLIENTE_CAMPOS.index('nome')],'Edited')
        self.assertEqual(len(audits),len(old[1])+1)
        self.assertEqual(audits[-1][2:4],('Cliente alterado',str(self.customer)))
        self.assertIn('Initial → Edited',audits[-1][4])

    def test_unrelated_provider_and_missing_customer_deny_without_mutation(self):
        self._deny_unchanged(self.other_actor)
        before=self._fields()
        with self.assertRaises(PermissionError):
            neg.cliente_salvar(self.db,{'tipo_pessoa':'Física','nome':'No match','status':'Ativo'},
                              self.owner, 987654, principal=self.owner_actor)
        self.assertEqual(self._fields(),before)

    def test_admin_can_edit(self):
        self.assertEqual(self._edit(self.admin_actor),self.customer)

    def test_direct_service_call_after_relationship_revoked_is_denied(self):
        with ext.db(self.db) as c:
            c.execute('DELETE FROM os_responsaveis WHERE os_id=? AND prestador_id=?',
                      (self.os_id,self.owner))
        self._deny_unchanged(self.owner_actor)

    def test_missing_inactive_and_unlinked_principals_fail_closed(self):
        for actor in (None,
                      Principal(self.owner,'employee',organization_id='autoseg',
                                provider_id=self.owner,active=False),
                      Principal(self.owner,'employee',organization_id='autoseg',
                                provider_id=None)):
            with self.subTest(actor=actor):
                self._deny_unchanged(actor,pid=self.owner)
        before=self._fields()
        with self.assertRaises(PermissionError):
            neg.cliente_salvar(self.db,{'tipo_pessoa':'Física','nome':'No principal',
                                       'status':'Ativo'},self.owner,self.customer)
        self.assertEqual(self._fields(),before)

    def test_inactive_participant_only_does_not_grant_edit(self):
        with ext.db(self.db) as c:
            c.execute('DELETE FROM os_responsaveis WHERE os_id=?', (self.os_id,))
            c.execute('INSERT INTO os_prestadores(os_id,prestador_id,ativo,atribuido_em) '
                      'VALUES(?,?,0,?)',(self.os_id,self.owner,ext.agora()))
        self._deny_unchanged(self.owner_actor)

    def test_responsavel_only_link_is_sufficient(self):
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM os_prestadores WHERE os_id=?',
                                       (self.os_id,)).fetchone()[0],0)
        self.assertEqual(self._edit(self.owner_actor),self.customer)

    def test_both_enforcement_flags_deny_unrelated(self):
        for flag in ('0','1'):
            with self.subTest(flag=flag),patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                self._deny_unchanged(self.other_actor)

    def test_creation_remains_possible_without_existing_os(self):
        access.require_customer_create(self.owner_actor)
        created=neg.cliente_salvar(self.db,{'tipo_pessoa':'Física','nome':'New A5b','status':'Ativo'},self.owner)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT nome FROM clientes WHERE id=?',(created,)).fetchone()[0],
                             'New A5b')

    def test_revoke_after_writer_lock_serializes(self):
        ctx=multiprocessing.get_context('spawn')
        parent,child=ctx.Pipe()
        writer=ctx.Process(target=_edit_with_writer_lock,
                           args=(self.db,self.customer,self.owner,self.owner_actor,child))
        writer.start(); child.close()
        self.addCleanup(self._cleanup_process,writer,parent)
        self._expect(parent,'writer_locked')
        revoke_parent,revoke_child=ctx.Pipe()
        revoker=ctx.Process(target=_revoke_under_lock,
                            args=(self.db,self.os_id,self.owner,revoke_child))
        revoker.start(); revoke_child.close()
        self.addCleanup(self._cleanup_process,revoker,revoke_parent)
        self._expect(revoke_parent,'lock_busy')
        self._expect(revoke_parent,'about_to_revoke')
        self.assertEqual(self._fields()[0][neg.CLIENTE_CAMPOS.index('nome')],'Initial')
        parent.send('release')
        self._expect(parent,('result','committed'))
        writer.join(6); self.assertEqual(writer.exitcode,0)
        self._expect(revoke_parent,'revoked')
        revoker.join(6); self.assertEqual(revoker.exitcode,0)
        self.assertEqual(self._fields()[0][neg.CLIENTE_CAMPOS.index('nome')],'Writer changed')
        self._deny_unchanged(self.owner_actor)

    @staticmethod
    def _cleanup_process(process,conn):
        if process.is_alive(): process.terminate()
        process.join(5)
        if process.is_alive(): process.kill();process.join(5)
        conn.close()

    def _expect(self,pipe,expected):
        self.assertTrue(pipe.poll(12),f'Timed out waiting for {expected}')
        actual=pipe.recv()
        self.assertEqual(actual,expected)

if __name__=='__main__': unittest.main()
