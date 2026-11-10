"""Synthetic tests for account schema, import and identity compatibility."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from flavors.autoseg.modules import accounts, identity


class AccountSchemaTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = str(Path(self.directory.name) / "accounts.db")
        with sqlite3.connect(self.db) as c:
            c.executescript("""
                CREATE TABLE prestadores(id INTEGER PRIMARY KEY,nome TEXT,email TEXT,documento TEXT,
                    telefone TEXT,senha_hash TEXT,ativo INTEGER,excluido INTEGER);
                CREATE TABLE v9_usuarios(id INTEGER PRIMARY KEY,nome TEXT,cpf TEXT,email TEXT,
                    telefone TEXT,senha_hash TEXT,ativo INTEGER,cliente_pf_id INTEGER);
                CREATE TABLE v9_admin_prestadores(prestador_id INTEGER PRIMARY KEY);
            """)
            c.executemany("INSERT INTO prestadores VALUES(?,?,?,?,?,?,?,?)", [
                (1, "Admin Test", "admin@example.test", "12345678901", "51999998888", "hashed-admin", 1, 0),
                (2, "Employee Test", "worker@example.test", "", "51988887777", "hashed-worker", 1, 0),
                (3, "Inactive Test", "inactive@example.test", "", "", "hashed-inactive", 0, 1),
            ])
            c.execute("INSERT INTO v9_admin_prestadores VALUES(1)")
            c.executemany("INSERT INTO v9_usuarios VALUES(?,?,?,?,?,?,?,?)", [
                (4, "Client Test", "12345678901", "admin@example.test", "51922223333", "hashed-client", 1, 40),
                (5, "Inactive Client", "98765432101", "client@example.test", "", "hashed-inactive-client", 0, None),
            ])

    def tearDown(self):
        self.directory.cleanup()

    def test_install_twice(self):
        accounts.install(self.db)
        accounts.install(self.db)
        self.assertEqual(accounts.login_policy(self.db).allowed_identifier_types, ("email", "cpf"))

    def test_dry_run_does_not_create_tables(self):
        before = Path(self.db).read_bytes()
        report = accounts.migrate_legacy(self.db, dry_run=True)
        self.assertTrue(report.dry_run)
        self.assertEqual(report.accounts_created, 5)
        self.assertEqual(Path(self.db).read_bytes(), before)
        with sqlite3.connect(self.db) as c:
            self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='accounts'").fetchone())

    def test_roles_hashes_activity_and_links(self):
        report = accounts.migrate_legacy(self.db, dry_run=False)
        self.assertEqual((report.providers, report.clients, report.accounts_created), (3, 2, 5))
        admin = accounts.find_account_by_identifier(self.db, "email", " ADMIN@EXAMPLE.TEST ")
        self.assertEqual(admin.password_hash, "hashed-admin")
        self.assertEqual(accounts.account_link(self.db, admin.id).role, "admin")
        employee = accounts.find_account_by_identifier(self.db, "email", "worker@example.test")
        self.assertEqual(accounts.account_link(self.db, employee.id).role, "employee")
        client = accounts.find_account_by_identifier(self.db, "cpf", "123.456.789-01")
        link = accounts.account_link(self.db, client.id)
        self.assertEqual((link.role, link.client_user_id, link.client_id), ("customer", 4, 40))
        self.assertEqual(link.provider_org_id, "autoseg")
        inactive = accounts.find_account_by_identifier(self.db, "email", "inactive@example.test")
        self.assertFalse(inactive.active)
        self.assertFalse(accounts.account_link(self.db, inactive.id).active)
        self.assertEqual(accounts.membership_for_account(self.db, admin.id).role, "admin")
        self.assertEqual(identity.to_principal(accounts.identity_for_account(self.db, admin.id),
                                               accounts.membership_for_account(self.db, admin.id)).role, "admin")

    def test_conflicts_no_pii(self):
        r = accounts.migrate_legacy(self.db, False)
        self.assertGreaterEqual(r.identifiers_skipped, 2)
        self.assertTrue(any(x["type"] == "cpf" for x in r.conflicts))
        self.assertTrue(any(x["type"] == "email" for x in r.conflicts))
        text = str(r.conflicts)
        self.assertNotIn("@example", text)
        self.assertNotIn("12345678901", text)

    def test_rerun_hash_and_activity(self):
        accounts.migrate_legacy(self.db, False)
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE prestadores SET senha_hash='new-hash',ativo=0 WHERE id=1")
        r = accounts.migrate_legacy(self.db, False)
        self.assertEqual(r.accounts_created, 0)
        self.assertEqual(r.accounts_updated, 5)
        admin = accounts.find_account_by_identifier(self.db, "email", "admin@example.test")
        self.assertFalse(admin.active)
        self.assertEqual(admin.password_hash, "new-hash")
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM accounts").fetchone()[0], 5)

    def test_normalization_and_policy(self):
        self.assertEqual(accounts.normalize_identifier("phone", "+55 51 99999-8888"), "5551999998888")
        self.assertEqual(accounts.normalize_identifier("nametag", " Test_User "), "test_user")
        with self.assertRaises(ValueError):
            accounts.normalize_identifier("cpf", "123")
        with self.assertRaises(ValueError):
            accounts.save_login_policy(self.db, ["password"])
        self.assertEqual(accounts.save_login_policy(self.db, ["email", "phone"]).allowed_identifier_types,
                         ("email", "phone"))

    def test_only_one_link(self):
        accounts.migrate_legacy(self.db, False)
        with self.assertRaises(sqlite3.IntegrityError):
            with sqlite3.connect(self.db) as c:
                c.execute("PRAGMA foreign_keys=ON")
                c.execute("INSERT INTO account_links(account_id,link_type,role,provider_id,created_at) "
                          "VALUES(1,'provider','employee',2,'now')")

    def test_inactive_client_and_client_membership(self):
        accounts.migrate_legacy(self.db, False)
        inactive = accounts.find_account_by_identifier(
            self.db, "email", "client@example.test")
        self.assertFalse(inactive.active)
        active = accounts.find_account_by_identifier(
            self.db, "cpf", "123.456.789-01")
        link = accounts.account_link(self.db, active.id)
        self.assertEqual((link.role, link.client_user_id, link.client_id),
                         ("customer", 4, 40))
        ident = accounts.identity_for_account(self.db, active.id)
        membership = accounts.membership_for_account(self.db, active.id)
        principal = identity.to_principal(ident, membership)
        self.assertEqual((principal.role, principal.client_id),
                         ("customer", 40))

    def test_phone_nametag_lookup_and_policy(self):
        accounts.install(self.db)
        accounts.save_login_policy(self.db, ["phone", "nametag"])
        with sqlite3.connect(self.db) as c:
            account_id = c.execute(
                "INSERT INTO accounts(display_name,password_hash,active,"
                "created_at,updated_at) VALUES('Test','hash',1,'now','now')"
            ).lastrowid
            c.execute(
                "INSERT INTO account_identifiers(account_id,type,value,normalized,"
                "verified,is_primary,created_at) VALUES(?,?,?,?,0,1,'now')",
                (account_id, "phone", "+55 51 99999-8888", "5551999998888"),
            )
            c.execute(
                "INSERT INTO account_identifiers(account_id,type,value,normalized,"
                "verified,is_primary,created_at) VALUES(?,?,?,?,0,0,'now')",
                (account_id, "nametag", "Test_User", "test_user"),
            )
        self.assertEqual(
            accounts.find_account_by_identifier(
                self.db, "phone", "+55 51 99999-8888").id,
            account_id,
        )
        self.assertEqual(
            accounts.find_account_by_identifier(
                self.db, "nametag", " TEST_USER ").id,
            account_id,
        )
        self.assertEqual(
            accounts.login_policy(self.db).allowed_identifier_types,
            ("phone", "nametag"),
        )

    def test_real_legacy_schema_integration(self):
        from officina.core import cadastros_v9 as cad
        from officina.core import prestadores_ext as ext
        from officina.core.banco import criar_banco

        with tempfile.TemporaryDirectory(prefix="accounts_real_") as pasta:
            banco = str(Path(pasta) / "real.db")
            criar_banco(banco)
            ext.instalar(banco)
            cad.instalar(banco)
            provider_id = ext.cadastrar(
                banco, "Provider Real", "provider.real@example.com",
                "senha-bem-segura-2026")
            cad.definir_admin(banco, provider_id, True)
            with ext.db(banco) as c:
                client_user_id = c.execute(
                    "INSERT INTO v9_usuarios(nome,cpf,telefone,email,senha_hash,"
                    "ativo,criado_em,cliente_pf_id) VALUES(?,?,?,?,?,?,?,?)",
                    ("Client Real", "12345678901", "51999999999",
                     "client.real@example.com", "hash", 1, ext.agora(), None),
                ).lastrowid
            report = accounts.migrate_legacy(banco, dry_run=False)
            self.assertEqual(report.accounts_created, 2)
            provider = accounts.find_account_by_identifier(
                banco, "email", "provider.real@example.com")
            client = accounts.find_account_by_identifier(
                banco, "cpf", "123.456.789-01")
            self.assertEqual(
                accounts.account_link(banco, provider.id).role, "admin")
            self.assertEqual(
                accounts.account_link(banco, client.id).client_user_id,
                client_user_id,
            )
            principal = identity.to_principal(
                accounts.identity_for_account(banco, provider.id),
                accounts.membership_for_account(banco, provider.id))
            self.assertEqual(principal.role, "admin")


if __name__ == "__main__":
    unittest.main()
