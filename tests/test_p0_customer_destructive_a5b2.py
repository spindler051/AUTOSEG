"""A5b-2: destructive customer commands require live administrator authority."""
from __future__ import annotations

import ast
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from officina.application.object_policy import Principal
from officina.application.local_service import LocalService
from officina.application.session import Sessao
from officina.application import work_item_access as access
from officina.core import cadastros_v9 as cad, portal_negocios as neg
from officina.core import prestadores_ext as ext
from officina.core.banco import criar_banco


def _locked_customer_writer(db, customer_id, actor, pipe):
    try:
        with ext.db(db) as c:
            c.execute('BEGIN IMMEDIATE')
            access.require_admin_locked(c, actor)
            pipe.send('locked')
            if pipe.recv() != 'release':
                raise RuntimeError('Unexpected synchronization message')
            c.execute("UPDATE clientes SET status='Inativo' WHERE id=?", (customer_id,))
        pipe.send('committed')
    except Exception as exc:
        pipe.send(('error', type(exc).__name__, str(exc)))
    finally:
        pipe.close()


def _revoke_locked_admin(db, provider, pipe):
    try:
        with sqlite3.connect(db, timeout=0) as c:
            c.execute('PRAGMA busy_timeout=0')
            try:
                c.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as exc:
                if 'locked' not in str(exc).lower():
                    raise
                pipe.send('blocked')
            else:
                c.rollback()
                raise AssertionError('Revoker acquired writer lock too early')
        pipe.send('revoking')
        with ext.db(db) as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM v9_admin_prestadores WHERE prestador_id=?', (provider,))
        pipe.send('revoked')
    except Exception as exc:
        pipe.send(('error', type(exc).__name__, str(exc)))
    finally:
        pipe.close()


class DestructiveCustomerAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='a5b2_destructive_')
        self.addCleanup(self.temp.cleanup)
        self.db = str(Path(self.temp.name) / 'test.sqlite')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        self.admin = ext.cadastrar(self.db, 'A5b2 Admin', 'a5b2-admin@invalid.test', 'Pass12345678')
        self.employee = ext.cadastrar(self.db, 'A5b2 Employee', 'a5b2-employee@invalid.test', 'Pass12345678')
        cad.definir_admin(self.db, self.admin, True)
        self.admin_actor = Principal(self.admin, 'admin', organization_id='autoseg', provider_id=self.admin)
        self.employee_actor = Principal(self.employee, 'employee', organization_id='autoseg', provider_id=self.employee)
        with ext.db(self.db) as c:
            self.source = c.execute("INSERT INTO clientes(nome,tipo_pessoa,status) VALUES('Source','Física','Ativo')").lastrowid
            self.dest = c.execute("INSERT INTO clientes(nome,tipo_pessoa,status) VALUES('Destination','Física','Ativo')").lastrowid
            self.os_id = c.execute("INSERT INTO ordens_servico(cliente_id,numero_os,status,descricao) VALUES(?,'A5B2-OS','Aberta','Work')", (self.source,)).lastrowid
            neg.criar_auditoria(c)

    def _state(self):
        with ext.db(self.db) as c:
            return (
                [tuple(x) for x in c.execute('SELECT id,nome,status,observacoes FROM clientes ORDER BY id')],
                [tuple(x) for x in c.execute('SELECT id,cliente_id FROM ordens_servico ORDER BY id')],
                [tuple(x) for x in c.execute('SELECT * FROM v9_historico_clientes ORDER BY id')],
                [tuple(x) for x in c.execute('SELECT * FROM portal_auditoria ORDER BY id')],
            )

    def _call(self, operation, actor, *, pid=None):
        if operation == 'deactivate':
            return cad.desativar_cliente(self.db, self.source, principal=actor)
        if operation == 'merge':
            return cad.mesclar_clientes(self.db, self.source, self.dest, principal=actor)
        return neg.cliente_excluir(self.db, self.dest,
                                  actor.provider_id if actor is not None else pid,
                                  principal=actor)

    def _deny_unchanged(self, operation, actor, *, pid=None):
        before = self._state()
        with self.assertRaises(PermissionError):
            self._call(operation, actor, pid=pid)
        self.assertEqual(self._state(), before)

    def test_direct_calls_without_actor_fail_closed(self):
        for operation in ('deactivate', 'merge', 'delete'):
            with self.subTest(operation=operation):
                self._deny_unchanged(operation, None, pid=0)

    def test_employee_cannot_deactivate_delete_or_merge(self):
        for operation in ('deactivate', 'merge', 'delete'):
            with self.subTest(operation=operation):
                self._deny_unchanged(operation, self.employee_actor)

    def test_admin_deactivates_once_with_history(self):
        cad.desativar_cliente(self.db, self.source, principal=self.admin_actor)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM clientes WHERE id=?', (self.source,)).fetchone()[0], 'Inativo')
            self.assertEqual(c.execute("SELECT count(*) FROM v9_historico_clientes WHERE acao='Desativação' AND cliente_id=?", (self.source,)).fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT autor FROM v9_historico_clientes WHERE acao='Desativação' AND cliente_id=?", (self.source,)).fetchone()[0], 'A5b2 Admin')

    def test_admin_deletes_unlinked_customer_and_audits_real_actor(self):
        neg.cliente_excluir(self.db, self.dest, 0, principal=self.admin_actor)
        with ext.db(self.db) as c:
            self.assertIsNone(c.execute('SELECT 1 FROM clientes WHERE id=?', (self.dest,)).fetchone())
            row=c.execute("SELECT prestador_id,acao FROM portal_auditoria WHERE acao='Cliente excluído' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(tuple(row), (self.admin,'Cliente excluído'))

    def test_admin_merges_and_moves_os(self):
        with ext.db(self.db) as c:
            finance_id=c.execute("INSERT INTO financeiro(os_id,cliente_id,descricao,valor) VALUES(?,?,?,?)",
                                 (self.os_id,self.source,'A5b2 finance',10)).lastrowid
        cad.mesclar_clientes(self.db, self.source, self.dest, principal=self.admin_actor)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT cliente_id FROM ordens_servico WHERE id=?', (self.os_id,)).fetchone()[0], self.dest)
            self.assertEqual(c.execute('SELECT cliente_id FROM financeiro WHERE id=?', (finance_id,)).fetchone()[0],self.dest)
            self.assertEqual(c.execute('SELECT status FROM clientes WHERE id=?', (self.source,)).fetchone()[0], 'Inativo')
            self.assertEqual(c.execute("SELECT count(*) FROM v9_historico_clientes WHERE acao='Mesclagem'", ()).fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT autor FROM v9_historico_clientes WHERE acao='Mesclagem'").fetchone()[0], 'A5b2 Admin')

    def test_forged_admin_role_without_admin_row_is_denied(self):
        forged=Principal(self.employee, 'admin', organization_id='autoseg', provider_id=self.employee)
        for operation in ('deactivate', 'merge', 'delete'):
            with self.subTest(operation=operation):
                self._deny_unchanged(operation, forged)

    def test_missing_inactive_and_invalid_principals_denied(self):
        invalid=(None,
                 Principal(self.admin,'admin',organization_id='autoseg',provider_id=None),
                 Principal(self.admin,'admin',organization_id='autoseg',provider_id=self.admin,active=False),
                 Principal(self.admin,'admin',organization_id='other',provider_id=self.admin))
        for actor in invalid:
            for operation in ('deactivate','merge','delete'):
                with self.subTest(actor=actor,operation=operation):
                    self._deny_unchanged(operation,actor,pid=0)

    def test_revoked_admin_denied(self):
        cad.definir_admin(self.db, self.admin, False)
        for operation in ('deactivate','merge','delete'):
            with self.subTest(operation=operation):
                self._deny_unchanged(operation,self.admin_actor)

    def test_database_deactivated_admin_is_denied(self):
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET ativo=0 WHERE id=?', (self.admin,))
        for operation in ('deactivate','merge','delete'):
            with self.subTest(operation=operation):
                self._deny_unchanged(operation,self.admin_actor)

    def test_writer_helper_requires_an_existing_transaction(self):
        with ext.db(self.db) as c:
            with self.assertRaises(RuntimeError):
                access.require_admin_locked(c,self.admin_actor)

    def test_both_policy_flags_enforce(self):
        for value in ('0','1'):
            with self.subTest(flag=value), patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':value}):
                self._deny_unchanged('deactivate',self.employee_actor)
                self._deny_unchanged('delete',self.employee_actor)
                self._deny_unchanged('merge',self.employee_actor)

    def test_local_service_audits_authenticated_actor_not_zero(self):
        LocalService(self.db).excluir_cliente(self.dest, principal=self.admin_actor)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute("SELECT prestador_id FROM portal_auditoria WHERE acao='Cliente excluído' ORDER BY id DESC LIMIT 1").fetchone()[0], self.admin)

    def test_revoke_after_writer_lock_serializes(self):
        ctx=multiprocessing.get_context('spawn')
        wparent,wchild=ctx.Pipe()
        writer=ctx.Process(target=_locked_customer_writer,args=(self.db,self.source,self.admin_actor,wchild))
        writer.start();wchild.close();self.addCleanup(self._cleanup,writer,wparent)
        self._expect(wparent,'locked')
        rparent,rchild=ctx.Pipe()
        revoker=ctx.Process(target=_revoke_locked_admin,args=(self.db,self.admin,rchild))
        revoker.start();rchild.close();self.addCleanup(self._cleanup,revoker,rparent)
        self._expect(rparent,'blocked')
        self._expect(rparent,'revoking')
        wparent.send('release')
        self._expect(wparent,'committed')
        writer.join(8);self.assertEqual(writer.exitcode,0)
        self._expect(rparent,'revoked')
        revoker.join(8);self.assertEqual(revoker.exitcode,0)
        self._deny_unchanged('merge',self.admin_actor)

    @staticmethod
    def _cleanup(proc, pipe):
        if proc.is_alive():proc.terminate()
        proc.join(4)
        if proc.is_alive():proc.kill();proc.join(4)
        pipe.close()

    def _expect(self, pipe, value):
        self.assertTrue(pipe.poll(12),'Cross-process message missing')
        self.assertEqual(pipe.recv(),value)

    @staticmethod
    def _gtk_customer_action_labels(session):
        """Execute the real page renderer against minimal GTK widget stand-ins."""
        source=Path(__file__).resolve().parents[1] / 'flavors/autoseg/modules/gtk_app.py'
        tree=ast.parse(source.read_text(encoding='utf-8'),filename=str(source))
        window=next(node for node in tree.body
                    if isinstance(node,ast.ClassDef) and node.name=='Janela')
        page=next(node for node in window.body
                  if isinstance(node,ast.FunctionDef) and node.name=='_pagina_clientes')

        class Widget:
            def __init__(self,*_args,**_kwargs):
                self.children=[]
            def set_hexpand(self,_value):
                pass
            def connect(self,*_args):
                pass
            def append(self,child):
                self.children.append(child)

        class Ui:
            class Tabela:
                def __init__(self,*_args,**_kwargs):
                    self.widget=Widget()
            @staticmethod
            def botao(label,*_args,**_kwargs):
                return {'label':label}
            @staticmethod
            def barra(*controls):
                return list(controls)

        gtk=SimpleNamespace(Box=Widget,SearchEntry=Widget,
                            Orientation=SimpleNamespace(VERTICAL=1))
        globals_={'Gtk':gtk,'ui':Ui}
        exec(compile(ast.Module(body=[page],type_ignores=[]),str(source),'exec'),globals_)
        noop=lambda *_args: None
        fake=SimpleNamespace(sessao=session,web=SimpleNamespace(enabled=False),
                             carregar_clientes=noop,_importar_cliente_yaml=noop,
                             _modelo_cliente_yaml=noop,_atribuir_responsavel=noop,
                             novo_cliente=noop,_editar_cliente=noop,
                             _nova_os_cliente=noop,_excluir_cliente=noop,
                             _desativar_cliente=noop,_mesclar_cliente=noop)
        rendered=globals_['_pagina_clientes'](fake)
        return [control['label'] for control in rendered.children[-1]]

    def test_gtk_remote_admin_empty_permissions_shows_destructive_action(self):
        session=Sessao('remote',self.admin,'Admin','',True,
                       permissions=frozenset())
        labels=self._gtk_customer_action_labels(session)
        self.assertEqual(labels.count('Desativar cliente'),1)
        self.assertEqual(labels.count('Excluir cliente'),1)

    def test_gtk_remote_employee_empty_permissions_hides_destructive_action(self):
        session=Sessao('remote',self.employee,'Employee','',False,
                       permissions=frozenset())
        labels=self._gtk_customer_action_labels(session)
        self.assertNotIn('Desativar cliente',labels)
        self.assertNotIn('Excluir cliente',labels)

    def test_gtk_local_admin_shows_destructive_action(self):
        session=Sessao('local',self.admin,'Admin','',True,
                       permissions=frozenset({'*'}))
        labels=self._gtk_customer_action_labels(session)
        self.assertIn('Desativar cliente',labels)
        self.assertIn('Excluir cliente',labels)

    def test_gtk_local_employee_hides_destructive_action(self):
        session=Sessao('local',self.employee,'Employee','',False,
                       permissions=frozenset())
        labels=self._gtk_customer_action_labels(session)
        self.assertNotIn('Desativar cliente',labels)
        self.assertNotIn('Excluir cliente',labels)
