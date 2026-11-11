"""Opt-in durable web session tests; no GTK or external services required."""
import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import accounts, identity, web_session
from officina.core import cadastros_v9 as cad, prestadores_ext as ext
from officina.core.banco import criar_banco


class DurableWebSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'durable.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        accounts.install(self.db)
        web_session.install(self.db)
        self.env = patch.dict(os.environ, {'AUTOSEG_WEB_SESSION_DURABLE':'1'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.hash = ext.senha_hash('SecretForTests123')
        with ext.db(self.db) as c:
            self.pid = c.execute(
                'INSERT INTO prestadores(nome,email,senha_hash,ativo,criado_em) VALUES(?,?,?,?,?)',
                ('Example', 'example@example.invalid', self.hash, 1, ext.agora())).lastrowid
        self.ident = identity.load_identity(self.db, 'provider', self.pid)
        self.member = identity.memberships(self.db,self.ident)[0]
        self.principal = identity.to_principal(self.ident,self.member)

    def make(self, **changes):
        args=dict(account_id=None,identity_record=self.ident,
                  membership=self.member,principal=self.principal,
                  credential=self.hash,source='legacy')
        args.update(changes)
        return web_session.create(self.db, **args)

    def account(self):
        with ext.db(self.db) as c:
            aid = c.execute(
                'INSERT INTO accounts(display_name,password_hash,active,created_at,updated_at) VALUES(?,?,?,?,?)',
                ('Account',self.hash,1,ext.agora(),ext.agora())).lastrowid
            c.execute('''INSERT INTO account_links(account_id,provider_org_id,link_type,
                role,provider_id,legacy_provider_id,active,created_at)
                VALUES(?,'autoseg','provider','employee',?,?,1,?)''',
                (aid,self.pid,self.pid,ext.agora()))
        ident = accounts.identity_for_account(self.db,aid)
        membership = accounts.membership_for_account(self.db,aid)
        return aid,ident,membership,identity.to_principal(ident,membership)

    def test_create_resolve_reopen_second_connection(self):
        token,session=self.make()
        with sqlite3.connect(self.db) as other:
            self.assertEqual(1,other.execute('SELECT count(*) FROM web_sessions').fetchone()[0])
        self.assertEqual(session.membership, web_session.resolve(self.db,token).membership)
        self.assertEqual(session.csrf,web_session.resolve(self.db,token).csrf)
        # Simulated new process, clears process-local memory only.
        web_session.clear()
        self.assertIsNotNone(web_session.resolve(self.db,token))

    def test_token_and_credential_never_in_database(self):
        token,data=self.make()
        with ext.db(self.db) as c:
            row = c.execute('SELECT * FROM web_sessions').fetchone()
        stored=' '.join(str(v) for v in row)
        for secret in (token,self.hash,self.ident.display_name,self.ident.email):
            self.assertNotIn(secret,stored)
        self.assertEqual(row['token_hash'],hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(row['credential_fingerprint'],hashlib.sha256(self.hash.encode()).hexdigest())
        self.assertEqual(json.loads(row['client_org_ids']),[])
        for secret in (token,self.hash,data.csrf,data.telemetry_session):
            self.assertNotIn(secret,repr(data))

    def test_revoke_propagates_across_connections(self):
        token,_=self.make()
        web_session.revoke(self.db,token)
        self.assertIsNone(web_session.resolve(self.db,token))

    def test_expiration_removes_and_prune_keeps_valid(self):
        with patch.object(web_session.time,'time',return_value=100):
            expired,_=self.make(ttl=1)
            valid,_=self.make(ttl=100)
        with patch.object(web_session.time,'time',return_value=102):
            web_session.prune(self.db)
            self.assertIsNone(web_session.resolve(self.db,expired))
            self.assertIsNotNone(web_session.resolve(self.db,valid))
        with patch.object(web_session.time,'time',return_value=201):
            self.assertIsNone(web_session.resolve(self.db,valid))

    def test_revoke_account_and_identity(self):
        aid,ident,member,principal=self.account()
        one,_=self.make(account_id=aid, identity_record=ident,membership=member,
                        principal=principal,source='account')
        two,_=self.make(account_id=aid, identity_record=ident,membership=member,
                        principal=principal,source='account')
        legacy,_=self.make()
        web_session.revoke_account(self.db,aid)
        self.assertIsNone(web_session.resolve(self.db,one))
        self.assertIsNone(web_session.resolve(self.db,two))
        self.assertIsNotNone(web_session.resolve(self.db,legacy))
        web_session.revoke_identity(self.db,'provider',self.pid)
        self.assertIsNone(web_session.resolve(self.db,legacy))

    def test_password_reset_and_activation_revoke(self):
        token,_=self.make()
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET senha_hash=? WHERE id=?',
                      (ext.senha_hash('Other12345678'),self.pid))
        self.assertIsNone(web_session.resolve(self.db,token))
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET senha_hash=? WHERE id=?',(self.hash,self.pid))
        token,_=self.make()
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET ativo=0 WHERE id=?',(self.pid,))
        self.assertIsNone(web_session.resolve(self.db,token))

    def test_role_change_revokes_on_resolve(self):
        aid,ident,member,principal=self.account()
        token,_=self.make(account_id=aid,identity_record=ident,membership=member,
                          principal=principal,source='account')
        with ext.db(self.db) as c:
            c.execute('INSERT INTO v9_admin_prestadores(prestador_id,autorizado_em) VALUES(?,?)',
                      (self.pid,ext.agora()))
        self.assertIsNone(web_session.resolve(self.db,token))

    def test_flag_off_ignores_stored_sessions(self):
        token,_=self.make()
        with patch.dict(os.environ,{'AUTOSEG_WEB_SESSION_DURABLE':'0'}):
            self.assertIsNone(web_session.resolve(self.db,token))
        self.assertIsNotNone(web_session.resolve(self.db,token))

    def test_other_process_resolves_then_revokes(self):
        import subprocess
        import sys
        token,_=self.make()
        root=str(Path(__file__).resolve().parents[1])
        env={**os.environ,'PYTHONPATH':root,'AUTOSEG_WEB_SESSION_DURABLE':'1'}
        program=(
            'from flavors.autoseg.modules import web_session as s;'
            'import sys;'
            'print(int(s.resolve(sys.argv[1],sys.argv[2]) is not None));'
            's.revoke(sys.argv[1],sys.argv[2])'
        )
        result=subprocess.check_output([sys.executable,'-c',program,self.db,token],
                                       cwd=root,env=env,text=True)
        self.assertEqual(result.strip(),'1')
        self.assertIsNone(web_session.resolve(self.db,token))

    def test_corrupted_org_ids_are_rejected_and_removed(self):
        token,_=self.make()
        with ext.db(self.db) as c:
            c.execute('UPDATE web_sessions SET client_org_ids=?',('[true]',))
        self.assertIsNone(web_session.resolve(self.db,token))
        with ext.db(self.db) as c:
            self.assertEqual(0,c.execute('SELECT count(*) FROM web_sessions').fetchone()[0])

    def test_uninstalled_schema_fails_closed(self):
        missing = str(Path(self.tmp.name) / 'no_session.db')
        criar_banco(missing)
        self.assertIsNone(web_session.resolve(missing,'any-opaque-token'))

    def test_explicit_install_idempotent_and_clear(self):
        web_session.install(self.db)
        token,_=self.make()
        web_session.clear(self.db)
        self.assertIsNone(web_session.resolve(self.db,token))


if __name__=='__main__':
    unittest.main()
