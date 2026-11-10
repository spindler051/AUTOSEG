"""Read-only unified-login feature-flag contract tests."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import login_flags


class LoginFlagsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "synthetic.db"
        sqlite3.connect(self.db).close()

    def _schema(self, policy='["email", "cpf"]'):
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY, display_name TEXT DEFAULT '',
                    password_hash TEXT DEFAULT '', active INTEGER,
                    created_at TEXT DEFAULT '', updated_at TEXT DEFAULT '',
                    password_changed_at TEXT);
                CREATE TABLE account_identifiers (
                    id INTEGER PRIMARY KEY, account_id INTEGER, type TEXT,
                    value TEXT, normalized TEXT, verified INTEGER DEFAULT 0,
                    is_primary INTEGER DEFAULT 0, created_at TEXT DEFAULT '');
                CREATE TABLE account_links (
                    id INTEGER PRIMARY KEY, account_id INTEGER,
                    provider_org_id TEXT, link_type TEXT, role TEXT,
                    provider_id INTEGER, client_user_id INTEGER,
                    client_id INTEGER, legacy_provider_id INTEGER,
                    legacy_client_user_id INTEGER, active INTEGER,
                    created_at TEXT DEFAULT '');
                CREATE TABLE login_policy (
                    id INTEGER PRIMARY KEY, allowed_identifier_types TEXT,
                    password_min_length INTEGER DEFAULT 12,
                    require_letter_number INTEGER DEFAULT 1,
                    updated_at TEXT DEFAULT '');
                INSERT INTO accounts(id, active) VALUES (1, 1), (2, 1);
                INSERT INTO account_links(account_id, link_type, active, provider_org_id)
                    VALUES (1, 'provider', 1, 'autoseg');
                INSERT INTO account_links(account_id, link_type, active, provider_org_id)
                    VALUES (2, 'client', 1, 'autoseg');
            """)
            db.execute("INSERT INTO login_policy VALUES (1, ?, 12, 1, '')",
                       (policy,))

    def test_default_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(login_flags.unified_login_enabled())

    def test_enabled_values(self):
        for value in ("1", "true", "on", "yes", "TrUe", " YES "):
            with self.subTest(value=value), patch.dict(os.environ, {"AUTOSEG_UNIFIED_LOGIN": value}):
                self.assertTrue(login_flags.unified_login_enabled())

    def test_disabled_values(self):
        for value in ("0", "false", "off", "", "banana"):
            with self.subTest(value=value), patch.dict(os.environ, {"AUTOSEG_UNIFIED_LOGIN": value}):
                self.assertFalse(login_flags.unified_login_enabled())

    def test_missing_accounts(self):
        report = login_flags.activation_report(self.db)
        self.assertFalse(report["accounts_installed"])
        self.assertFalse(report["ready"])
        self.assertEqual(report["accounts"], 0)
        self.assertIn("accounts_not_installed", report["blockers"])

    def test_ready_schema(self):
        self._schema()
        report = login_flags.activation_report(self.db)
        self.assertTrue(report["ready"])
        self.assertEqual((report["accounts"], report["providers"], report["clients"]), (2, 1, 1))
        self.assertEqual(report["policy_types"], ("email", "cpf"))
        self.assertIsNone(report["conflicts"])
        self.assertEqual(report["cookie_name"], "autosseg_unified")

    def test_policy_password_rejected(self):
        self._schema('["email", "password"]')
        report = login_flags.activation_report(self.db)
        self.assertFalse(report["ready"])
        self.assertIn("login_policy_invalid", report["blockers"])

    def test_policy_empty_rejected(self):
        self._schema('[]')
        self.assertIn("login_policy_invalid", login_flags.activation_report(self.db)["blockers"])

    def test_no_writes(self):
        self._schema()
        before = self.db.read_bytes()
        login_flags.activation_report(self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_missing_file_not_created(self):
        missing = self.db.with_name("missing.db")
        report = login_flags.activation_report(missing)
        self.assertFalse(missing.exists())
        self.assertEqual(report["blockers"], ("database_unavailable",))

    def test_incomplete_schema_not_ready(self):
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY)")
        report = login_flags.activation_report(self.db)
        self.assertFalse(report["ready"])
        self.assertIn("accounts_schema_incomplete", report["blockers"])

    def test_missing_client_not_ready(self):
        self._schema()
        with sqlite3.connect(self.db) as db:
            db.execute("DELETE FROM account_links WHERE link_type='client'")
        self.assertIn("clients_not_migrated", login_flags.activation_report(self.db)["blockers"])

    def test_inactive_only_not_ready(self):
        self._schema()
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE accounts SET active=0")
            db.execute("UPDATE account_links SET active=0")
        report = login_flags.activation_report(self.db)
        self.assertFalse(report["ready"])
        self.assertIn("accounts_inactive", report["blockers"])
        self.assertIn("active_providers_not_migrated", report["blockers"])
        self.assertIn("active_clients_not_migrated", report["blockers"])

    def test_flag_does_not_override_blockers(self):
        with patch.dict(os.environ, {"AUTOSEG_UNIFIED_LOGIN": "1"}):
            report = login_flags.activation_report(self.db)
        self.assertTrue(report["flag"])
        self.assertFalse(report["ready"])


if __name__ == "__main__":
    unittest.main()
