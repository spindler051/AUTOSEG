"""Regression tests for the process-local unified session contract."""
import dataclasses
import io
import logging
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import accounts, identity, web_session as sessions
from officina.core import cadastros_v9 as cad
from officina.core import prestadores_ext as ext
from officina.core.banco import criar_banco


class WebSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'session.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        accounts.install(self.db)
        sessions.clear()
        self.addCleanup(sessions.clear)
        self.password = 'SomeStrongPassword123'
        self.credential = ext.senha_hash(self.password)
        with ext.db(self.db) as c:
            self.provider_id = c.execute(
                "INSERT INTO prestadores(nome,email,senha_hash,ativo,criado_em) "
                "VALUES(?,?,?,?,?)", ('Example Provider', 'provider@example.test',
                                      self.credential, 1, ext.agora())
            ).lastrowid
        self.ident = identity.load_identity(self.db, 'provider', self.provider_id)
        self.member = identity.memberships(self.db, self.ident)[0]
        self.principal = identity.to_principal(self.ident, self.member)

    def _make(self, **changes):
        values = dict(account_id=None, identity_record=self.ident,
                      membership=self.member, principal=self.principal,
                      credential=self.credential, source='legacy')
        values.update(changes)
        return sessions.create(self.db, **values)

    def _account(self):
        with ext.db(self.db) as c:
            aid = c.execute(
                "INSERT INTO accounts(display_name,password_hash,active,created_at,updated_at) "
                "VALUES(?,?,?,?,?)", ('Example Account', self.credential, 1,
                                      ext.agora(), ext.agora())
            ).lastrowid
            c.execute(
                "INSERT INTO account_links(account_id,provider_org_id,link_type,"
                "role,provider_id,legacy_provider_id,active,created_at) "
                "VALUES(?,'autoseg','provider','employee',?,?,1,?)",
                (aid, self.provider_id, self.provider_id, ext.agora())
            )
        ident = accounts.identity_for_account(self.db, aid)
        membership = accounts.membership_for_account(self.db, aid)
        principal = identity.to_principal(ident, membership)
        return aid, ident, membership, principal

    def test_create_resolve_preserves_identity_and_principal(self):
        aid, ident, member, principal = self._account()
        token, data = self._make(account_id=aid, identity_record=ident,
                                 membership=member, principal=principal,
                                 source='account')
        self.assertIs(sessions.resolve(self.db, token), data)
        self.assertEqual(data.principal, principal)
        self.assertEqual(data.identity, ident)
        self.assertEqual(len(data.csrf) > 30, True)
        self.assertNotEqual(token, data.csrf)

    def test_invalid_and_none_tokens(self):
        self.assertIsNone(sessions.resolve(self.db, None))
        self.assertIsNone(sessions.resolve(self.db, 'invalid'))

    def test_expiration_removes_session(self):
        with patch.object(sessions.time, 'time', return_value=100):
            token, _ = self._make(ttl=1)
        with patch.object(sessions.time, 'time', return_value=101):
            self.assertIsNone(sessions.resolve(self.db, token))
        self.assertNotIn(token, sessions._SESSIONS)

    def test_password_hash_change_revokes(self):
        token, _ = self._make()
        with ext.db(self.db) as c:
            c.execute("UPDATE prestadores SET senha_hash=? WHERE id=?",
                      (ext.senha_hash('ChangedPassword123'), self.provider_id))
        self.assertIsNone(sessions.resolve(self.db, token))
        self.assertNotIn(token, sessions._SESSIONS)

    def test_inactive_identity_and_account(self):
        token, _ = self._make()
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET ativo=0 WHERE id=?', (self.provider_id,))
        self.assertIsNone(sessions.resolve(self.db, token))
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET ativo=1 WHERE id=?', (self.provider_id,))
        aid, ident, member, principal = self._account()
        token, _ = self._make(account_id=aid, identity_record=ident,
                              membership=member, principal=principal, source='account')
        with ext.db(self.db) as c:
            c.execute('UPDATE accounts SET active=0 WHERE id=?', (aid,))
        self.assertIsNone(sessions.resolve(self.db, token))

    def test_revoke_only_one_token(self):
        first, _ = self._make()
        second, _ = self._make()
        sessions.revoke(first)
        self.assertIsNone(sessions.resolve(self.db, first))
        self.assertIsNotNone(sessions.resolve(self.db, second))

    def test_revoke_account_revokes_all(self):
        aid, ident, member, principal = self._account()
        first, _ = self._make(account_id=aid, identity_record=ident,
                              membership=member, principal=principal, source='account')
        second, _ = self._make(account_id=aid, identity_record=ident,
                               membership=member, principal=principal, source='account')
        legacy, _ = self._make()
        sessions.revoke_account(aid)
        self.assertIsNone(sessions.resolve(self.db, first))
        self.assertIsNone(sessions.resolve(self.db, second))
        self.assertIsNotNone(sessions.resolve(self.db, legacy))

    def test_revoke_identity_revokes_all_sources(self):
        aid, ident, member, principal = self._account()
        first, _ = self._make()
        second, _ = self._make(account_id=aid, identity_record=ident,
                               membership=member, principal=principal, source='account')
        sessions.revoke_identity('provider', self.provider_id)
        self.assertIsNone(sessions.resolve(self.db, first))
        self.assertIsNone(sessions.resolve(self.db, second))

    def test_prune_expired_only(self):
        with patch.object(sessions.time, 'time', return_value=100):
            expired, _ = self._make(ttl=1)
            valid, _ = self._make(ttl=100)
        with patch.object(sessions.time, 'time', return_value=102):
            sessions.prune()
            self.assertIsNone(sessions.resolve(self.db, expired))
            self.assertIsNotNone(sessions.resolve(self.db, valid))

    def test_session_repr_redacts_secrets(self):
        token, data = self._make()
        description = repr(data)
        for secret in (token, data.credential, data.csrf, data.telemetry_session):
            self.assertNotIn(secret, description)
        self.assertNotIn('credential=', description)

    def test_legacy_hash_revalidated(self):
        token, _ = self._make()
        self.assertEqual(sessions.current_credential(self.db, 'legacy', None, self.ident),
                         self.credential)
        with ext.db(self.db) as c:
            c.execute('DELETE FROM prestadores WHERE id=?', (self.provider_id,))
        self.assertIsNone(sessions.resolve(self.db, token))

    def test_no_pii_in_repr_or_logs(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            with redirect_stdout(stream), redirect_stderr(stream):
                token, data = self._make()
                print(repr(data))
                self.assertIsNotNone(sessions.resolve(self.db, token))
            output = stream.getvalue()
            for secret in ('provider@example.test', 'Example Provider',
                           self.credential, token, data.csrf):
                self.assertNotIn(secret, output)
        finally:
            root.removeHandler(handler)

    def test_inactive_link_revokes(self):
        aid, ident, member, principal = self._account()
        token, _ = self._make(account_id=aid, identity_record=ident,
                              membership=member, principal=principal, source='account')
        with ext.db(self.db) as c:
            c.execute('UPDATE account_links SET active=0 WHERE account_id=?', (aid,))
        self.assertIsNone(sessions.resolve(self.db, token))

    def test_reject_mismatched_credential_and_role(self):
        with self.assertRaises(ValueError):
            self._make(credential='wrong')
        with self.assertRaises(ValueError):
            self._make(principal=dataclasses.replace(self.principal, role='admin'))

    def test_reject_principal_from_another_identity(self):
        with self.assertRaises(ValueError):
            self._make(principal=dataclasses.replace(
                self.principal, account_id=self.principal.account_id + 1))

    def test_reject_account_source_without_link(self):
        with ext.db(self.db) as c:
            aid = c.execute(
                "INSERT INTO accounts(display_name,password_hash,active,created_at,updated_at) "
                "VALUES(?,?,?,?,?)", ('Unlinked Account', self.credential, 1,
                                      ext.agora(), ext.agora())
            ).lastrowid
        with self.assertRaises(ValueError):
            self._make(account_id=aid, source='account')

    def test_reject_link_bound_to_another_provider(self):
        aid, ident, member, principal = self._account()
        with ext.db(self.db) as c:
            second = c.execute(
                "INSERT INTO prestadores(nome,email,senha_hash,ativo,criado_em) "
                "VALUES(?,?,?,?,?)", ('Other Provider', 'other@example.test',
                                      self.credential, 1, ext.agora())
            ).lastrowid
            c.execute('UPDATE account_links SET provider_id=? WHERE account_id=?',
                      (second, aid))
        with self.assertRaises(ValueError):
            self._make(account_id=aid, identity_record=ident,
                       membership=member, principal=principal, source='account')

    def test_reject_inactive_account_or_link_on_create(self):
        aid, ident, member, principal = self._account()
        with ext.db(self.db) as c:
            c.execute('UPDATE account_links SET active=0 WHERE account_id=?', (aid,))
        with self.assertRaises(ValueError):
            self._make(account_id=aid, identity_record=ident,
                       membership=member, principal=principal, source='account')
        with ext.db(self.db) as c:
            c.execute('UPDATE account_links SET active=1 WHERE account_id=?', (aid,))
            c.execute('UPDATE accounts SET active=0 WHERE id=?', (aid,))
        with self.assertRaises(ValueError):
            self._make(account_id=aid, identity_record=ident,
                       membership=member, principal=principal, source='account')

    def test_reject_legacy_source_with_account_id(self):
        aid, _ident, _member, _principal = self._account()
        with self.assertRaises(ValueError):
            self._make(account_id=aid)

    def test_cookie_name_is_shared_with_flag_module(self):
        from flavors.autoseg.modules import login_flags
        self.assertEqual(sessions.COOKIE_NAME, login_flags.COOKIE_NAME)


if __name__ == '__main__':
    unittest.main()
