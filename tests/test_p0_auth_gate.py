"""Transactional authorization of the provider order reopen command."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flavors.autoseg.modules import os_commands
from officina.core import (atendimento_os as aten, cadastros_v9 as cad9,
                           fluxo_os as fluxo, prestadores_ext as ext,
                           produtividade_os as prod)
from officina.core.banco import criar_banco


class ReopenGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='p0_auth_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'test.db')
        criar_banco(self.db)
        for install in (ext.instalar, fluxo.instalar, cad9.instalar, aten.instalar, prod.instalar):
            install(self.db)
        self.employee = ext.cadastrar(self.db, 'Worker', 'worker@invalid.test', 'test-password')
        self.admin = ext.cadastrar(self.db, 'Manager', 'manager@invalid.test', 'test-password')
        cad9.definir_admin(self.db, self.admin, True)
        with ext.db(self.db) as c:
            self.cid = c.execute("INSERT INTO clientes(nome,status) VALUES('Sample','Ativo')").lastrowid
            self.oid = c.execute('''INSERT INTO ordens_servico
                (numero_os,cliente_id,status,descricao,data_abertura,criado_em)
                VALUES('260000000',?,'Pendente','Sample','','')''',(self.cid,)).lastrowid
        ext.assumir(self.db, self.oid, self.employee)
        self.ui = Mock()
        self.ui.redir.return_value = 'redirect'
        self.url = f'/os/{self.oid}/abrir'

    def _call(self, pid):
        session = {'pid':pid,'nome':'Worker' if pid == self.employee else 'Manager'}
        principal = os_commands._provider_context(self.db, session)
        return os_commands.execute_http(self.ui, self.db, principal,
                                        self.url, {}, session)

    def _state(self):
        with ext.db(self.db) as c:
            return (c.execute('SELECT status,cliente_id FROM ordens_servico WHERE id=?',
                              (self.oid,)).fetchone(),
                    c.execute('SELECT count(*) FROM os_eventos WHERE os_id=?',
                              (self.oid,)).fetchone()[0])

    def test_pending_requires_reopen_role_both_flags(self):
        for flag in ('0','1'):
            with self.subTest(flag=flag),patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                old,events = self._state()
                with self.assertRaises(PermissionError):
                    self._call(self.employee)
                new,after_events = self._state()
                self.assertEqual((old['status'],old['cliente_id'],events),
                                 (new['status'],new['cliente_id'],after_events))

    def test_admin_reopens_pending_both_flags(self):
        for flag in ('0','1'):
            with self.subTest(flag=flag),patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                with ext.db(self.db) as c:
                    c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?",(self.oid,))
                self.assertEqual(self._call(self.admin),'redirect')
                current,_ = self._state()
                self.assertEqual(current['status'],'Aberta')

    def test_race_state_becomes_pending_between_preflight_and_writer(self):
        original = os_commands.WRITERS['abrir']
        for flag in ('0','1'):
            with self.subTest(flag=flag),patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                with ext.db(self.db) as c:
                    c.execute("UPDATE ordens_servico SET status='Aberta' WHERE id=?",(self.oid,))
                # The preflight sees Aberta; a separate connection changes status.
                def racing_writer(*args,**kwargs):
                    with ext.db(self.db) as c:
                        c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?",(self.oid,))
                    return original(*args,**kwargs)
                with patch.dict(os_commands.WRITERS,{'abrir':racing_writer}):
                    with self.assertRaises(PermissionError):
                        self._call(self.employee)
                state,_ = self._state()
                self.assertEqual(state['status'],'Pendente')

    def test_route_rechecks_relationship_inside_business_writer(self):
        with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT': '1'}):
            with ext.db(self.db) as c:
                c.execute("UPDATE ordens_servico SET status='Aberta' WHERE id=?",
                          (self.oid,))
            route = f'/os/{self.oid}/rota'
            original = os_commands.WRITERS['rota']

            def racing_writer(*args, **kwargs):
                with ext.db(self.db) as c:
                    c.execute('UPDATE os_responsaveis SET prestador_id=? WHERE os_id=?',
                              (self.admin, self.oid))
                    c.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',
                              (self.oid, self.employee))
                return original(*args, **kwargs)

            session = {'pid': self.employee, 'nome': 'Worker'}
            principal = os_commands._provider_context(self.db, session)
            with patch.dict(os_commands.WRITERS, {'rota': racing_writer}):
                with self.assertRaises(PermissionError):
                    os_commands.execute_http(self.ui, self.db, principal, route,
                                             {'ativo':'1'}, session)
            with ext.db(self.db) as c:
                self.assertFalse(c.execute('SELECT 1 FROM produtividade_deslocamentos '
                                           'WHERE os_id=?', (self.oid,)).fetchone())

    def test_admin_archive_rechecks_archived_status(self):
        with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT': '1'}):
            route = f'/os/{self.oid}/arquivar'
            original = os_commands.WRITERS['arquivar']

            def racing_writer(*args, **kwargs):
                with ext.db(self.db) as c:
                    c.execute('UPDATE ordens_servico SET arquivada=1 WHERE id=?',
                              (self.oid,))
                return original(*args, **kwargs)

            session = {'pid': self.admin, 'nome': 'Manager'}
            principal = os_commands._provider_context(self.db, session)
            with patch.dict(os_commands.WRITERS, {'arquivar': racing_writer}):
                with self.assertRaises(PermissionError):
                    os_commands.execute_http(self.ui, self.db, principal, route, {}, session)
            with ext.db(self.db) as c:
                self.assertEqual(c.execute('SELECT arquivada FROM ordens_servico '
                                           'WHERE id=?', (self.oid,)).fetchone()[0], 1)

    def test_race_responsibility_changed_with_enforcement(self):
        with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'1'}):
            with ext.db(self.db) as c:
                c.execute("UPDATE ordens_servico SET status='Aberta' WHERE id=?",(self.oid,))
            original = os_commands.WRITERS['abrir']
            def racing_writer(*args,**kwargs):
                with ext.db(self.db) as c:
                    c.execute('UPDATE os_responsaveis SET prestador_id=? WHERE os_id=?',
                              (self.admin,self.oid))
                    c.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',
                              (self.oid,self.employee))
                return original(*args,**kwargs)
            with patch.dict(os_commands.WRITERS,{'abrir':racing_writer}):
                with self.assertRaises(PermissionError):
                    self._call(self.employee)
            state,_ = self._state()
            self.assertEqual(state['status'],'Aberta')


if __name__ == '__main__':
    unittest.main()
