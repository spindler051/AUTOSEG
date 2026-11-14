"""Desktop API checks current actor and work relationships inside writer transactions."""
from __future__ import annotations

import os
import threading
import time
import unittest
from unittest.mock import patch

from tests import test_p0_desktop_auth as base_tests
from flavors.autoseg.modules import api_desktop, prestador_auth, accounts
from officina.application.local_service import LocalService
from officina.core import cadastros_v9 as cad, prestadores_ext as ext, fluxo_os as fluxo


class DesktopWriterTOCTOUTest(unittest.TestCase):
    setUp = base_tests.DesktopObjectAuthorizationTest.setUp
    request = base_tests.DesktopObjectAuthorizationTest.request

    def _session_id(self, name):
        with ext.db(self.db) as c:
            return c.execute('SELECT id FROM desktop_sessoes WHERE prestador_id=? '
                             'ORDER BY id DESC LIMIT 1', (self.users[name],)).fetchone()[0]

    def _save_payload(self, os_id=None, action='salvar'):
        return {'os_id':os_id or self.own, 'cliente_id':self.own_client,
                'tecnico':'', 'descricao':'Modified after preflight',
                'valor_mao_obra':0, 'valor_materiais':0, 'custo_materiais':0,
                'valor_total':125, 'forma_pagamento':'PIX', 'urgencia':'Normal',
                'observacoes':'', 'texto_adicional':'', 'dados_incompletos':0,
                'tempo_horas':0, 'composicao_json':'', 'base_percentuais':'total',
                'materiais':[], 'acao':action, 'relato':'', 'motivo':''}

    def _snapshot(self, work_id):
        with ext.db(self.db) as c:
            row = c.execute('SELECT status,descricao,valor_total FROM ordens_servico WHERE id=?',
                            (work_id,)).fetchone()
            return (tuple(row), c.execute('SELECT COUNT(*) FROM os_eventos WHERE os_id=?',
                                         (work_id,)).fetchone()[0],
                    c.execute('SELECT COUNT(*) FROM materiais_os WHERE os_id=?',
                              (work_id,)).fetchone()[0])

    def _revoke_owner(self):
        # A separate connection commits after HTTP preflight, before the writer.
        ext.atribuir(self.db, self.own, self.users['second'])
        with ext.db(self.db) as c:
            c.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',
                      (self.own, self.users['first']))

    def test_existing_os_save_rechecks_owner_after_preflight(self):
        original = LocalService.salvar_os
        for flag in ('0', '1'):
            with self.subTest(flag=flag):
                # Restore ownership for each independent race scenario.
                ext.atribuir(self.db, self.own, self.users['first'])
                with ext.db(self.db) as c:
                    c.execute('UPDATE os_prestadores SET ativo=1 WHERE os_id=? AND prestador_id=?',
                              (self.own, self.users['first']))
                def raced(service, data, **kwargs):
                    self._revoke_owner()
                    self.before = self._snapshot(self.own)
                    return original(service, data, **kwargs)
                with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}), \
                     patch.object(LocalService,'salvar_os',raced):
                    code,body=self.request('first','/os','POST',self._save_payload())
                self.assertEqual(code,404,body)
                self.assertEqual(self._snapshot(self.own),self.before)

    def test_assignment_and_unassignment_recheck_current_admin_role(self):
        for method, route, payload in (
                ('atribuir_os','/atribuir',{'prestador_id':self.users['first']}),
                ('desatribuir_os','/desatribuir',{})):
            with self.subTest(route=route):
                cad.definir_admin(self.db,self.users['admin'],True)
                original=getattr(LocalService, method)
                def raced(service,*args,**kwargs):
                    cad.definir_admin(self.db,self.users['admin'],False)
                    self.before = self._snapshot(self.other)
                    return original(service,*args,**kwargs)
                with patch.object(LocalService,method,raced):
                    code,body=self.request('admin',f'/os/{self.other}'+route,'POST',payload)
                self.assertEqual(code,404,body)
                self.assertEqual(self._snapshot(self.other),self.before)
                with ext.db(self.db) as c:
                    self.assertEqual(ext.responsavel_atual(c,self.other),self.users['second'])

    def test_start_rechecks_current_responsible(self):
        original=LocalService.iniciar_os
        def raced(service,*args,**kwargs):
            self._revoke_owner()
            self.before=self._snapshot(self.own)
            return original(service,*args,**kwargs)
        with patch.object(LocalService,'iniciar_os',raced):
            code,body=self.request('first',f'/os/{self.own}/iniciar','POST')
        self.assertEqual(code,404,body)
        self.assertEqual(self._snapshot(self.own),self.before)

    def test_draft_preparation_rechecks_admin_before_file_effect(self):
        for method,route in (('preparar_email','/email/preparar'),
                             ('preparar_nota','/nota/preparar')):
            with self.subTest(route=route):
                cad.definir_admin(self.db,self.users['admin'],True)
                original=getattr(LocalService,method)
                def raced(service,*args,**kwargs):
                    cad.definir_admin(self.db,self.users['admin'],False)
                    return original(service,*args,**kwargs)
                with patch.object(LocalService,method,raced):
                    code,body=self.request('admin',f'/os/{self.other}'+route,'POST')
                self.assertEqual(code,404,body)

    def test_pdf_publication_rechecks_before_database_commit(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with ext.db(self.db) as c:
            c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?",(self.other,))
        with TemporaryDirectory(prefix='desktop_pub_toctou_') as directory:
            source=Path(directory)/'sample.pdf'
            source.write_bytes(b'%PDF-1.4\n' + b'1'*256)
            cad.definir_admin(self.db,self.users['admin'],True)
            def generated(*args,**kwargs):
                cad.definir_admin(self.db,self.users['admin'],False)
                return str(source)
            with patch.object(ext,'gerar_pdf',generated), \
                 patch.object(ext,'RELATORIOS',Path(directory)):
                code,body=self.request('admin',f'/os/{self.other}/pdf/publicar','POST')
            self.assertEqual(code,404,body)
            with ext.db(self.db) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM os_documentos WHERE os_id=?',
                                           (self.other,)).fetchone()[0],0)

    def test_authorized_owner_and_admin_still_mutate(self):
        code,body=self.request('first',f'/os/{self.own}/iniciar','POST')
        self.assertEqual(code,200,body)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM ordens_servico WHERE id=?',
                                       (self.own,)).fetchone()[0], 'Iniciada')
        code,body=self.request('admin',f'/os/{self.other}/atribuir',
                               'POST',{'prestador_id':self.users['admin']})
        self.assertEqual(code,200,body)

    def test_writer_lock_serializes_concurrent_revocation(self):
        principal=api_desktop._desktop_session_context(
            self.db, {'id':self.users['first']})[1]
        real_guard=api_desktop._os_writer_authorize(principal,self.own,'start',session_id=self._session_id('first'))
        entered=threading.Event()
        release=threading.Event()
        revocation_attempted=threading.Event()
        revoked=threading.Event()
        results=[]
        def guarded(connection):
            real_guard(connection)
            entered.set()
            if not release.wait(8):
                raise RuntimeError('Lock test timed out.')
        def start():
            try:
                LocalService(self.db).iniciar_os(self.own,authorize=guarded)
                results.append('started')
            except Exception as error:
                results.append(error)
        def revoke():
            revocation_attempted.set()
            with ext.db(self.db) as c:
                c.execute('BEGIN IMMEDIATE')
                c.execute('DELETE FROM os_responsaveis WHERE os_id=?',(self.own,))
                c.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',
                          (self.own,self.users['first']))
            revoked.set()
        writer=threading.Thread(target=start,daemon=True)
        reader=threading.Thread(target=revoke,daemon=True)
        writer.start()
        try:
            self.assertTrue(entered.wait(5))
            reader.start()
            self.assertTrue(revocation_attempted.wait(5))
            self.assertFalse(revoked.wait(.15))
        finally:
            release.set()
            writer.join(8)
            if reader.is_alive():
                reader.join(8)
        self.assertEqual(results,['started'])
        self.assertTrue(revoked.is_set())
        with ext.db(self.db) as c:
            row=c.execute('SELECT status FROM ordens_servico WHERE id=?',(self.own,)).fetchone()
        self.assertEqual(row[0],'Iniciada')

    def test_no_write_when_membership_is_revoked_before_begin(self):
        principal=api_desktop._desktop_session_context(
            self.db, {'id':self.users['first']})[1]
        authorize=api_desktop._os_writer_authorize(principal,self.own,'edit',session_id=self._session_id('first'))
        completed=threading.Event()
        def revoke():
            with ext.db(self.db) as c:
                c.execute('BEGIN IMMEDIATE')
                c.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',
                          (self.own,self.users['first']))
                c.execute('DELETE FROM os_responsaveis WHERE os_id=?',(self.own,))
            completed.set()
        worker=threading.Thread(target=revoke,daemon=True)
        worker.start()
        self.assertTrue(completed.wait(5))
        worker.join(5)
        before=self._snapshot(self.own)
        with self.assertRaises(Exception) as denial:
            LocalService(self.db).salvar_os(
                api_desktop._os_input(self._save_payload()),authorize=authorize)
        self.assertIsInstance(denial.exception,(PermissionError, api_desktop.NaoEncontradoError))
        self.assertEqual(self._snapshot(self.own),before)


    def test_session_revoked_after_preflight_denies_writer_without_mutation(self):
        original = LocalService.salvar_os
        for flag in ('0', '1'):
            with self.subTest(flag=flag):
                result = prestador_auth.login(
                    self.db, 'first@test.invalid', 'Pass12345678')
                self.tokens['first'] = result['token']
                def revoked(service, data, **kwargs):
                    self.assertTrue(prestador_auth.revogar_sessao(
                        self.db, 'Bearer ' + self.tokens['first']))
                    self.before = self._snapshot(self.own)
                    return original(service, data, **kwargs)
                with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT': flag}), \
                     patch.object(LocalService, 'salvar_os', revoked):
                    status, body = self.request('first', '/os', 'POST', self._save_payload())
                self.assertEqual(status, 404, body)
                self.assertEqual(self._snapshot(self.own), self.before)

    def test_linked_account_disabled_after_preflight_denies_writer(self):
        accounts.install(self.db)
        with ext.db(self.db) as c:
            acc = c.execute('''INSERT INTO accounts
                (display_name,password_hash,active,created_at,updated_at)
                VALUES ('first','unused',1,'2026-11-14','2026-11-14')''').lastrowid
            c.execute('''INSERT INTO account_links
                (account_id,provider_org_id,link_type,role,provider_id,
                 legacy_provider_id,active,created_at)
                VALUES (?,'autoseg','provider','employee',?,?,1,'2026-11-14')''',
                (acc,self.users['first'],self.users['first']))
        original = LocalService.salvar_os
        for column, table in (('active', 'accounts'), ('active', 'account_links')):
            with self.subTest(table=table):
                with ext.db(self.db) as c:
                    c.execute('UPDATE accounts SET active=1 WHERE id=?', (acc,))
                    c.execute('UPDATE account_links SET active=1 WHERE account_id=?', (acc,))
                def disabled(service, data, **kwargs):
                    with ext.db(self.db) as c:
                        c.execute(f'UPDATE {table} SET {column}=0 WHERE ' +
                                  ('id=?' if table == 'accounts' else 'account_id=?'), (acc,))
                    self.before = self._snapshot(self.own)
                    return original(service, data, **kwargs)
                with patch.object(LocalService, 'salvar_os', disabled):
                    status, body = self.request('first', '/os', 'POST', self._save_payload())
                self.assertEqual(status, 404, body)
                self.assertEqual(self._snapshot(self.own), self.before)

    def test_provider_disabled_after_preflight_denies_writer(self):
        original = LocalService.salvar_os
        def disabled(service, data, **kwargs):
            with ext.db(self.db) as c:
                c.execute('UPDATE prestadores SET ativo=0 WHERE id=?',
                          (self.users['first'],))
            self.before = self._snapshot(self.own)
            return original(service, data, **kwargs)
        with patch.object(LocalService, 'salvar_os', disabled):
            status, body = self.request('first', '/os', 'POST', self._save_payload())
        self.assertEqual(status, 404, body)
        self.assertEqual(self._snapshot(self.own), self.before)


if __name__=='__main__':
    unittest.main()
