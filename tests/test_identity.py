"""Read-only legacy identity-contract tests with synthetic SQLite records."""
import sqlite3
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from flavors.autoseg.modules import identity, policy_shadow


class IdentityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="identity_contract_")
        self.banco = str(Path(self.temp.name) / "identity.db")
        with sqlite3.connect(self.banco) as connection:
            connection.executescript("""
                CREATE TABLE prestadores (
                    id INTEGER PRIMARY KEY, nome TEXT, email TEXT,
                    documento TEXT, senha_hash TEXT, ativo INTEGER, excluido INTEGER DEFAULT 0
                );
                CREATE TABLE v9_usuarios (
                    id INTEGER PRIMARY KEY, nome TEXT, email TEXT, cpf TEXT,
                    senha_hash TEXT, ativo INTEGER, cliente_pf_id INTEGER
                );
                CREATE TABLE v9_admin_prestadores (prestador_id INTEGER PRIMARY KEY);
                INSERT INTO prestadores VALUES
                    (1, 'Admin', 'Admin@Example.test', '123.456.789-09', 'secret1', 1, 0),
                    (2, 'Employee', 'worker@example.test', '11111111111', 'secret2', 1, 0),
                    (3, 'Inactive', 'inactive@example.test', '', 'secret3', 0, 0),
                    (4, 'Shared Provider', 'shared@example.test', '', 'secret4', 1, 0),
                    (5, 'Archived', 'archived@example.test', '', 'secret5', 1, 1);
                INSERT INTO v9_usuarios VALUES
                    (10, 'Client', 'Client@Example.test', '22233344455', 'secret6', 1, 200),
                    (11, 'Shared Client', 'shared@example.test', '33344455566', 'secret7', 1, 201),
                    (12, 'Inactive Client', 'old@example.test', '44455566677', 'secret8', 0, 202);
                INSERT INTO v9_admin_prestadores VALUES (1);
            """)

    def tearDown(self):
        self.temp.cleanup()

    def test_provider_admin(self):
        found = identity.resolve_identifier(self.banco, "admin@example.test")
        self.assertEqual(len(found), 1)
        ident = identity.load_identity(self.banco, "provider", 1)
        self.assertEqual(found[0], ident)
        membership, = identity.memberships(self.banco, ident)
        self.assertEqual(membership.role, "admin")
        principal = identity.to_principal(ident, membership)
        self.assertEqual((principal.role, principal.provider_id), ("admin", 1))

    def test_provider_employee(self):
        ident = identity.load_identity(self.banco, "provider", 2)
        membership, = identity.memberships(self.banco, ident)
        self.assertEqual(membership.role, "employee")
        self.assertEqual(identity.to_principal(ident, membership).role, "employee")

    def test_client_email_cpf_and_membership(self):
        ident = identity.load_identity(self.banco, "client", 10)
        self.assertEqual(identity.resolve_identifier(self.banco, "Client@Example.test"), (ident,))
        self.assertEqual(identity.resolve_identifier(self.banco, "222.333.444-55"), (ident,))
        membership, = identity.memberships(self.banco, ident)
        self.assertEqual(membership.role, "customer")
        principal = identity.to_principal(ident, membership)
        self.assertEqual(principal.client_id, 200)

    def test_inactive_identity_and_principal(self):
        for kind, id_value in (("provider", 3), ("client", 12), ("provider", 5)):
            ident = identity.load_identity(self.banco, kind, id_value)
            self.assertFalse(ident.active)
            self.assertFalse(identity.to_principal(
                ident, identity.memberships(self.banco, ident)[0]).active)
        self.assertFalse(identity.resolve_identifier(
            self.banco, "inactive@example.test")[0].active)

    def test_email_case_insensitive_and_trimmed(self):
        found = identity.resolve_identifier(self.banco, "  ADMIN@EXAMPLE.TEST  ")
        self.assertEqual([(i.kind, i.id) for i in found], [("provider", 1)])

    def test_masked_document_and_provider_document(self):
        self.assertEqual(identity.resolve_identifier(
            self.banco, "123.456.789-09")[0].provider_id, 1)
        self.assertEqual(identity.resolve_identifier(
            self.banco, "11111111111")[0].provider_id, 2)

    def test_nonexistent_and_invalid_identifier(self):
        for value in ("", " ", "not-an-email", "bad@@example.test", "123", None):
            self.assertEqual(identity.resolve_identifier(self.banco, value), ())
        self.assertEqual(identity.resolve_identifier(self.banco, "absent@example.test"), ())

    def test_shared_email_returns_both_in_deterministic_order(self):
        found = identity.resolve_identifier(self.banco, "shared@example.test")
        self.assertEqual([(i.kind, i.id) for i in found],
                         [("provider", 4), ("client", 11)])

    def test_memberships_do_not_claim_a_tenant(self):
        for kind, id_value in (("provider", 1), ("provider", 2), ("client", 10)):
            ident = identity.load_identity(self.banco, kind, id_value)
            self.assertIsNone(identity.memberships(self.banco, ident)[0].provider_org_id)

    def test_identity_excludes_password_fields(self):
        names = {field.name for field in fields(identity.Identity)}
        self.assertFalse(names & {"password", "senha", "senha_hash", "password_hash"})
        self.assertFalse(hasattr(identity.load_identity(self.banco, "provider", 1), "senha_hash"))

    def test_identity_does_not_include_role(self):
        self.assertNotIn("role", {field.name for field in fields(identity.Identity)})
        self.assertEqual(identity.memberships(
            self.banco, identity.load_identity(self.banco, "provider", 1))[0].role, "admin")

    def test_mismatched_membership_is_rejected(self):
        provider = identity.load_identity(self.banco, "provider", 1)
        other_provider = identity.memberships(
            self.banco, identity.load_identity(self.banco, "provider", 2))[0]
        client = identity.memberships(
            self.banco, identity.load_identity(self.banco, "client", 10))[0]
        for membership in (other_provider, client):
            with self.assertRaises(ValueError):
                identity.to_principal(provider, membership)

    def test_principal_shadow_delegate_and_missing_records(self):
        self.assertEqual(policy_shadow.principal_provider(self.banco, 1).role, "admin")
        self.assertEqual(policy_shadow.principal_provider(self.banco, 2).role, "employee")
        self.assertEqual(policy_shadow.principal_client(self.banco, 10).client_id, 200)
        self.assertFalse(policy_shadow.principal_provider(self.banco, 999).active)
        self.assertFalse(policy_shadow.principal_client(self.banco, 999).active)

    def test_shadow_inactive_and_none_client_id(self):
        self.assertFalse(policy_shadow.principal_provider(self.banco, 3).active)
        self.assertFalse(policy_shadow.principal_client(self.banco, 12).active)

    def test_real_legacy_schema_integration(self):
        from officina.core import cadastros_v9 as cad
        from officina.core import prestadores_ext as ext
        from officina.core.banco import criar_banco

        with tempfile.TemporaryDirectory(prefix="identity_real_") as pasta:
            banco = str(Path(pasta) / "real.db")
            criar_banco(banco)
            ext.instalar(banco)
            cad.instalar(banco)
            provider_id = ext.cadastrar(
                banco, "Provider Real", "provider.real@example.com",
                "senha-bem-segura-2026")
            cad.definir_admin(banco, provider_id, True)
            with ext.db(banco) as c:
                client_id = c.execute(
                    "INSERT INTO v9_usuarios(nome,cpf,telefone,email,senha_hash,"
                    "ativo,criado_em,cliente_pf_id) VALUES(?,?,?,?,?,?,?,?)",
                    ("Client Real", "12345678901", "51999999999",
                     "client.real@example.com", "hash", 1, ext.agora(), None),
                ).lastrowid
            provider = identity.resolve_identifier(
                banco, "provider.real@example.com")[0]
            client = identity.resolve_identifier(
                banco, "123.456.789-01")[0]
            self.assertEqual(
                identity.memberships(banco, provider)[0].role, "admin")
            self.assertEqual(
                identity.memberships(banco, client)[0].role, "customer")
            self.assertEqual(
                policy_shadow.principal_provider(banco, provider_id).role,
                "admin")
            self.assertEqual(
                policy_shadow.principal_client(banco, client_id).role,
                "customer")


if __name__ == "__main__":
    unittest.main()
