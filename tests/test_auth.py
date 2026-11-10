"""Tests for the library-only unified authentication service."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flavors.autoseg.modules import auth, identity
from officina.core import cadastros_v9 as cad9
from officina.core import prestadores_ext as ext
from officina.core.banco import criar_banco


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="auth_test_")
        self.banco = str(Path(self.temp.name) / "auth.db")
        criar_banco(self.banco)
        ext.instalar(self.banco)
        cad9.instalar(self.banco)
        self.pwd = "ExamplePassword2026"
        with ext.db(self.banco) as c:
            self.provider = c.execute(
                "INSERT INTO prestadores(nome,email,senha_hash,ativo,criado_em) "
                "VALUES (?,?,?,?,?)",
                ("Provider Example", "provider@example.test", ext.senha_hash(self.pwd), 1, ext.agora()),
            ).lastrowid
            self.client = c.execute(
                "INSERT INTO v9_usuarios(nome,cpf,telefone,email,senha_hash,ativo,criado_em) "
                "VALUES (?,?,?,?,?,?,?)",
                ("Client Example", "12345678909", "51912345678", "client@example.test",
                 ext.senha_hash(self.pwd), 1, ext.agora()),
            ).lastrowid
        # Explicitly test the contract with accounts absent, even if installed.
        self.accounts_patch = patch.object(auth, "accounts", None)
        self.accounts_patch.start()

    def tearDown(self):
        self.accounts_patch.stop()
        self.temp.cleanup()

    def error(self, code, identifier, password=None):
        with self.assertRaises(auth.LoginError) as raised:
            auth.authenticate(self.banco, identifier, password or self.pwd)
        self.assertEqual(raised.exception.code, code)
        if identifier:
            self.assertNotIn(identifier, str(raised.exception))
        self.assertNotIn(self.pwd, str(raised.exception))

    def test_legacy_provider_email(self):
        result = auth.authenticate(self.banco, "  PROVIDER@EXAMPLE.TEST ", self.pwd)
        self.assertEqual((result.source, result.account_id), ("legacy", None))
        self.assertEqual(result.identity.kind, "provider")
        self.assertEqual(result.principal.provider_id, self.provider)
        self.assertEqual(result.principal.role, "employee")

    def test_legacy_client_cpf(self):
        result = auth.authenticate(self.banco, "123.456.789-09", self.pwd)
        self.assertEqual(result.source, "legacy")
        self.assertEqual(result.identity.kind, "client")
        self.assertEqual(result.principal.role, "customer")

    def test_wrong_password_does_not_enumerate(self):
        self.error("invalid", "provider@example.test", "WrongPassword123")
        self.error("invalid", "missing@example.test", "WrongPassword123")

    def test_inactive_provider(self):
        with ext.db(self.banco) as c:
            c.execute("UPDATE prestadores SET ativo=0 WHERE id=?", (self.provider,))
        self.error("inactive", "provider@example.test")
        self.error("invalid", "provider@example.test", "WrongPassword123")

    def test_inactive_client(self):
        with ext.db(self.banco) as c:
            c.execute("UPDATE v9_usuarios SET ativo=0 WHERE id=?", (self.client,))
        self.error("inactive", "12345678909")

    def test_legacy_email_ambiguity(self):
        with ext.db(self.banco) as c:
            c.execute("UPDATE v9_usuarios SET email=? WHERE id=?",
                      ("provider@example.test", self.client))
        self.error("ambiguous", "provider@example.test")

    def test_default_policy_and_unsupported(self):
        self.assertEqual(auth.allowed_identifier_types(self.banco), ("email", "cpf"))
        self.error("unsupported", "5191234567")
        self.error("unsupported", "client_tag")
        self.error("invalid", "", "WrongPassword123")

    def test_email_only_policy_rejects_cpf(self):
        fake = SimpleNamespace(
            login_policy=lambda _: SimpleNamespace(allowed_identifier_types=("email",)),
            normalize_identifier=self._normalize,
        )
        with patch.object(auth, "accounts", fake):
            self.error("unsupported", "12345678909")

    @staticmethod
    def _normalize(kind, value):
        # The fake account interface is only used by policy tests.
        with patch.object(auth, "accounts", None):
            return auth.normalize_identifier(kind, value)

    def test_password_strength(self):
        self.assertEqual(auth.validate_password_strength("short1")[0], False)
        self.assertEqual(auth.validate_password_strength("OnlyLettersLong")[0], False)
        self.assertEqual(auth.validate_password_strength("StrongPassword2026"), (True, ""))
        policy = SimpleNamespace(password_min_length=6, require_letter_number=False)
        self.assertEqual(auth.validate_password_strength("abcdef", policy), (True, ""))

    def test_invalid_policy_fallback(self):
        fake = SimpleNamespace(login_policy=lambda _: SimpleNamespace(
            allowed_identifier_types=("password",)))
        with patch.object(auth, "accounts", fake):
            self.assertEqual(auth.allowed_identifier_types(self.banco), ("email", "cpf"))

    def test_new_account(self):
        ident = identity.load_identity(self.banco, "provider", self.provider)
        membership = identity.memberships(self.banco, ident)[0]
        account = SimpleNamespace(id=60, password_hash=ext.senha_hash(self.pwd), active=True)
        fake = SimpleNamespace(
            login_policy=lambda _: SimpleNamespace(allowed_identifier_types=("email", "cpf")),
            normalize_identifier=self._normalize,
            find_account_by_identifier=lambda _, kind, value: account if kind == "email" else None,
            identity_for_account=lambda _, aid: ident,
            membership_for_account=lambda _, aid: membership,
        )
        with patch.object(auth, "accounts", fake):
            result = auth.authenticate(self.banco, "provider@example.test", self.pwd)
        self.assertEqual((result.account_id, result.source), (60, "account"))
        self.assertEqual(result.principal.provider_id, self.provider)

    def test_multiple_account_candidates_ambiguous(self):
        first = SimpleNamespace(id=1)
        second = SimpleNamespace(id=2)
        fake = SimpleNamespace(
            login_policy=lambda _: SimpleNamespace(
                allowed_identifier_types=("cpf", "phone")),
            normalize_identifier=self._normalize,
            find_account_by_identifier=lambda _, kind, value: first if kind == "cpf" else second,
        )
        with patch.object(auth, "accounts", fake):
            self.error("ambiguous", "12345678909")

    def test_account_inactive_and_bad_password(self):
        account = SimpleNamespace(id=1, password_hash=ext.senha_hash(self.pwd), active=False)
        fake = SimpleNamespace(
            login_policy=lambda _: SimpleNamespace(allowed_identifier_types=("email",)),
            normalize_identifier=self._normalize,
            find_account_by_identifier=lambda *_: account,
        )
        with patch.object(auth, "accounts", fake):
            self.error("inactive", "provider@example.test")
            self.error("invalid", "provider@example.test", "WrongPassword123")

    def test_no_password_or_identifier_in_errors(self):
        for code in ("invalid", "ambiguous", "inactive", "unsupported"):
            message = str(auth.LoginError(code))
            self.assertNotIn("@", message)
            self.assertNotIn("pbkdf2", message)
            self.assertNotIn(self.pwd, message)

    def test_inactive_duplicate_email_does_not_block_active_provider(self):
        with ext.db(self.banco) as c:
            c.execute("UPDATE v9_usuarios SET email=?,ativo=0 WHERE id=?",
                      ("provider@example.test", self.client))
        result = auth.authenticate(
            self.banco, "provider@example.test", self.pwd)
        self.assertEqual(result.source, "legacy")
        self.assertEqual(result.principal.provider_id, self.provider)

    def test_real_account_store_login_and_policy(self):
        from flavors.autoseg.modules import accounts as account_store

        account_store.install(self.banco)
        report = account_store.migrate_legacy(self.banco, dry_run=False)
        self.assertGreaterEqual(report.accounts_created, 2)
        with patch.object(auth, "accounts", account_store):
            provider = auth.authenticate(
                self.banco, "provider@example.test", self.pwd)
            self.assertEqual(
                (provider.source, provider.principal.role),
                ("account", "employee"))
            client = auth.authenticate(
                self.banco, "123.456.789-09", self.pwd)
            self.assertEqual(
                (client.source, client.principal.role),
                ("account", "customer"))
            account_store.save_login_policy(self.banco, ["email"])
            with self.assertRaises(auth.LoginError) as raised:
                auth.authenticate(self.banco, "123.456.789-09", self.pwd)
            self.assertEqual(raised.exception.code, "unsupported")

    def test_real_phone_and_nametag_login(self):
        from flavors.autoseg.modules import accounts as account_store

        account_store.install(self.banco)
        account_store.migrate_legacy(self.banco, dry_run=False)
        provider = account_store.find_account_by_identifier(
            self.banco, "email", "provider@example.test")
        with sqlite3.connect(self.banco) as c:
            c.execute(
                "INSERT INTO account_identifiers(account_id,type,value,"
                "normalized,verified,is_primary,created_at) "
                "VALUES(?,?,?,?,0,0,'now')",
                (provider.id, "phone", "+55 51 99999-8888",
                 "5551999998888"),
            )
            c.execute(
                "INSERT INTO account_identifiers(account_id,type,value,"
                "normalized,verified,is_primary,created_at) "
                "VALUES(?,?,?,?,0,0,'now')",
                (provider.id, "nametag", "Provider_Tag", "provider_tag"),
            )
            c.execute(
                "INSERT INTO account_identifiers(account_id,type,value,"
                "normalized,verified,is_primary,created_at) "
                "VALUES(?,?,?,?,0,0,'now')",
                (provider.id, "nametag", "12345", "12345"),
            )
        account_store.save_login_policy(
            self.banco, ["email", "phone", "nametag"])
        with patch.object(auth, "accounts", account_store):
            by_phone = auth.authenticate(
                self.banco, "+55 51 99999-8888", self.pwd)
            by_tag = auth.authenticate(
                self.banco, "provider_tag", self.pwd)
            by_numeric_tag = auth.authenticate(
                self.banco, "12345", self.pwd)
        self.assertEqual(by_phone.principal.provider_id, self.provider)
        self.assertEqual(by_tag.principal.provider_id, self.provider)
        self.assertEqual(by_numeric_tag.principal.provider_id, self.provider)


if __name__ == "__main__":
    unittest.main()
