"""6.2 database upgrade, real role links, scoping and transactional audit."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import accounts, account_roles, web_session
from officina.application.object_policy import Principal
from officina.core.banco import criar_banco
from officina.core import cadastros_v9 as cad, prestadores_ext as ext


class RolesDatabaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/'db.sqlite')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        self.provider=ext.cadastrar(self.db,'Example Provider',
                                    'provider@example.test','Password12345')
        self.uid=cad.cadastrar_usuario(self.db,'Example Client','52998224725',
                                      '51999999999','Password12345','client@example.test')
        accounts.install(self.db)
        accounts.migrate_legacy(self.db,dry_run=False)
        self.account=accounts.find_account_by_identifier(self.db,'email','client@example.test').id
        self.provider_account=accounts.find_account_by_identifier(self.db,'email','provider@example.test').id
        with ext.db(self.db) as c:
            first=c.execute("""INSERT INTO v9_organizacoes(nome,tipo,criado_em)
                VALUES('Test Condominium','Condomínio',?)""",(ext.agora(),)).lastrowid
            second=c.execute("""INSERT INTO v9_organizacoes(nome,tipo,criado_em)
                VALUES('Other Condominium','Condomínio',?)""",(ext.agora(),)).lastrowid
            c.execute("""INSERT INTO v9_responsaveis(organizacao_id,usuario_id,
                papel,atribuido_por,atribuido_em) VALUES(?,?,'Síndico','Admin',?)""",
                (first,self.uid,ext.agora()))
            c.execute("""INSERT INTO v9_vinculos(organizacao_id,usuario_id,papel,
                situacao,criado_em) VALUES(?,?,'Zelador','Aprovado',?)""",
                (second,self.uid,ext.agora()))
        self.org1,self.org2=first,second

    def test_install_idempotent_and_default_role(self):
        accounts.install(self.db)
        accounts.install(self.db)
        with ext.db(self.db) as c:
            cols={r['name'] for r in c.execute('PRAGMA table_info(account_links)')}
        self.assertIn('client_role',cols)
        self.assertEqual('customer',accounts.account_link(self.db,self.account).client_role)

    def test_install_upgrades_existing_account_links_without_rebuild(self):
        # Recreate only the prior schema of this table to reproduce a migrated
        # checkout before the 6.2 client_role column existed.
        with ext.db(self.db) as c:
            c.execute('ALTER TABLE account_links RENAME TO old_account_links')
            c.execute("""CREATE TABLE account_links(
                id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL UNIQUE,
                provider_org_id TEXT NOT NULL DEFAULT 'autoseg',
                link_type TEXT NOT NULL,role TEXT NOT NULL,provider_id INTEGER,
                client_user_id INTEGER,client_id INTEGER,
                legacy_provider_id INTEGER,legacy_client_user_id INTEGER,
                active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)""")
            c.execute("""INSERT INTO account_links(
                id,account_id,provider_org_id,link_type,role,provider_id,
                client_user_id,client_id,legacy_provider_id,legacy_client_user_id,
                active,created_at) SELECT id,account_id,provider_org_id,
                link_type,role,provider_id,client_user_id,client_id,
                legacy_provider_id,legacy_client_user_id,active,created_at
                FROM old_account_links""")
            c.execute('DROP TABLE old_account_links')
        accounts.install(self.db)
        accounts.install(self.db)
        link=accounts.account_link(self.db,self.account)
        self.assertEqual(link.client_role,'customer')
        self.assertEqual(link.client_user_id,self.uid)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM account_links').fetchone()[0],2)

    def test_role_assignments_and_scopes(self):
        for role,expected in (('customer',set()),('porteiro',set()),
                              ('zelador',{self.org2}),('sindico',{self.org1})):
            with self.subTest(role=role):
                self.assertEqual(role,accounts.set_client_role(self.db,self.account,role).client_role)
                membership=accounts.membership_for_account(self.db,self.account)
                self.assertEqual(membership.role,role)
                self.assertEqual(set(membership.client_org_ids),expected)

    def test_shadow_uses_converted_role_not_legacy_guess(self):
        from flavors.autoseg.modules import policy_shadow, identity, auth
        self.assertEqual(identity.memberships(self.db, identity.load_identity(
            self.db, 'client', self.uid)), ())
        accounts.set_client_role(self.db, self.account, 'sindico')
        shadow = policy_shadow.principal_client(self.db, self.uid)
        self.assertEqual(shadow.role, 'sindico')
        self.assertEqual(shadow.client_org_ids, frozenset({self.org1}))
        with ext.db(self.db) as c:
            c.execute('UPDATE account_links SET active=0 WHERE account_id=?',
                      (self.account,))
        # A disabled converted link must not become an active legacy shadow.
        self.assertFalse(policy_shadow.principal_client(self.db, self.uid).active)

    def test_invalid_provider_inactive_rejected(self):
        with self.assertRaises(ValueError):
            accounts.set_client_role(self.db,self.account,'admin')
        with self.assertRaises(PermissionError):
            accounts.set_client_role(self.db,self.provider_account,'sindico')
        with ext.db(self.db) as c:
            c.execute('UPDATE accounts SET active=0 WHERE id=?',(self.account,))
        with self.assertRaises(PermissionError):
            accounts.set_client_role(self.db,self.account,'sindico')

    def test_audit_failure_rolls_back_role(self):
        def fail(_connection):
            raise RuntimeError('audit failed')
        with self.assertRaises(RuntimeError):
            accounts.set_client_role(self.db,self.account,'sindico',audit=fail)
        self.assertEqual('customer',accounts.account_link(self.db,self.account).client_role)

    def test_service_audit_and_revocation(self):
        actor=Principal(self.provider,'admin',organization_id='autoseg',
                        provider_id=self.provider)
        with (patch.object(web_session,'revoke_account') as revoke_account,
              patch.object(web_session,'revoke_identity') as revoke_identity):
            result=account_roles.change_role(self.db,actor,self.account,'sindico')
        self.assertEqual(result.client_role,'sindico')
        revoke_account.assert_called_once_with(self.account)
        revoke_identity.assert_called_once_with('client',self.uid)
        with ext.db(self.db) as c:
            row=c.execute('SELECT acao,referencia FROM portal_auditoria ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(row['referencia'],str(self.account))
        self.assertEqual(row['acao'],'Papel de cliente alterado')

    def test_employee_cannot_manage(self):
        employee=Principal(self.provider,'employee',organization_id='autoseg',
                           provider_id=self.provider)
        with self.assertRaises(PermissionError):
            account_roles.change_role(self.db,employee,self.account,'sindico')
        self.assertEqual('customer',accounts.account_link(self.db,self.account).client_role)

    def test_listing_contains_only_minimal_fields(self):
        admin=Principal(self.provider,'admin',organization_id='autoseg',
                        provider_id=self.provider)
        rows=account_roles.listing(self.db,admin)
        self.assertIn(self.account,[r.account_id for r in rows])
        self.assertFalse(any('hash' in key for key in rows[0].__dict__))

    def test_unconverted_account_explicitly_rejected(self):
        with ext.db(self.db) as c:
            c.execute('DELETE FROM account_links WHERE account_id=?',(self.account,))
        self.assertIsNone(accounts.membership_for_account(self.db,self.account))
        with self.assertRaises(PermissionError):
            accounts.set_client_role(self.db,self.account,'sindico')


if __name__=='__main__':
    unittest.main()
