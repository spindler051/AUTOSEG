"""Negative access tests for the client-service groundwork."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from flavors.autoseg.modules import client_service


def client(uid=7, active=True, role='customer', converted=True):
    from officina.application.object_policy import Principal
    identity = SimpleNamespace(id=uid,kind='client',active=active,
                               client_id=uid+300,display_name='Test Client')
    membership = SimpleNamespace(identity_kind='client',identity_id=uid,
        client_id=uid+300,role=role,active=active,client_org_ids=frozenset())
    principal = Principal(uid,role,organization_id='autoseg',
                          client_id=uid+300,active=active)
    return SimpleNamespace(identity=identity,membership=membership,
        principal=principal,csrf='example-csrf',source='account' if converted else 'legacy',
        account_id=uid+100 if converted else None)


class ClientServiceTest(unittest.TestCase):
    def test_denies_provider(self):
        session = client()
        session.identity.kind = 'provider'
        with self.assertRaises(PermissionError):
            client_service.list_work_items('unused',session)

    def test_denies_inactive(self):
        with self.assertRaises(PermissionError):
            client_service.list_work_items('unused',client(active=False))

    def test_denies_mismatched_membership(self):
        session = client()
        session.membership.identity_id = 8
        with self.assertRaises(PermissionError):
            client_service.list_work_items('unused',session)

    def test_scopes_list_through_service_policy(self):
        row={'id':1,'numero_os':'OS-1','status':'Aberta',
             'descricao':'Example','data_abertura':'2026-01-01'}
        with (patch.object(client_service,'_work_rows',return_value=[row]),
              patch.object(client_service,'_authorize_work') as authz):
            result=client_service.list_work_items('db',client(uid=8))
        self.assertEqual(result[0].id,1)
        authz.assert_called_once()

    def test_unconverted_client_explicitly_blocked(self):
        with self.assertRaises(PermissionError):
            client_service.list_work_items('db',client(converted=False))

    def test_denies_foreign_object_before_query(self):
        with (patch.object(client_service,'_authorize_work',
                           side_effect=PermissionError('denied')),
              patch.object(client_service.ext,'db') as sql):
            self.assertIsNone(client_service.get_work_item('db',client(),42))
            sql.assert_not_called()

    def test_denies_documents_for_nonexistent_work(self):
        with self.assertRaises(PermissionError):
            client_service.open_document('db',client(),1,2)



class ClientLinkSyncDatabaseTest(unittest.TestCase):
    """Exercise the account link SQL with a real temporary SQLite database."""

    def setUp(self):
        import sqlite3
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'db.sqlite')
        with sqlite3.connect(self.db) as c:
            c.executescript("""CREATE TABLE accounts(id INTEGER PRIMARY KEY, active INTEGER);
                CREATE TABLE v9_usuarios(id INTEGER PRIMARY KEY, cliente_pf_id INTEGER, ativo INTEGER);
                CREATE TABLE clientes(id INTEGER PRIMARY KEY, tipo_pessoa TEXT, status TEXT);
                CREATE TABLE account_links(id INTEGER PRIMARY KEY, account_id INTEGER, client_id INTEGER,
                    active INTEGER, link_type TEXT, role TEXT, client_user_id INTEGER,
                    legacy_client_user_id INTEGER);
                INSERT INTO accounts VALUES (1,1),(2,1),(3,0);
                INSERT INTO v9_usuarios VALUES (11,17,1),(12,18,1),(13,17,1);
                INSERT INTO clientes VALUES (17,'Física','Ativo'),(18,'Física','Ativo');
                INSERT INTO account_links VALUES
                    (1,1,NULL,1,'client','customer',11,11),
                    (2,2,NULL,1,'client','customer',12,12),
                    (3,3,NULL,1,'client','customer',13,13);""")

    def test_idempotent_client_link_sync(self):
        from flavors.autoseg.modules import accounts
        self.assertEqual(17, accounts.sync_client_pf_link(self.db, 1, 11))
        self.assertEqual(17, accounts.sync_client_pf_link(self.db, 1, 11))

    def test_foreign_account_does_not_link(self):
        from flavors.autoseg.modules import accounts
        with self.assertRaises(PermissionError):
            accounts.sync_client_pf_link(self.db, 2, 11)

    def test_inactive_account_does_not_link(self):
        from flavors.autoseg.modules import accounts
        with self.assertRaises(PermissionError):
            accounts.sync_client_pf_link(self.db, 3, 13)

    def test_wrong_link_role_does_not_link(self):
        import sqlite3
        from flavors.autoseg.modules import accounts
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE account_links SET link_type='provider',role='employee' WHERE id=1")
        with self.assertRaises(PermissionError):
            accounts.sync_client_pf_link(self.db, 1, 11)


if __name__ == '__main__':
    unittest.main()

class ClientWebRenderingTest(unittest.TestCase):
    def test_escapes_untrusted_descriptions(self):
        from flavors.autoseg.modules import client_web
        with (patch('flavors.autoseg.modules.client_extended_web.extra_home', return_value=''),
              patch.object(client_web.client_service, 'list_calls', return_value=()),
              patch.object(client_web.client_service, 'list_work_items', return_value=(
            client_service.ClientWorkItem(1, 'OS-1', 'Aberta', '<script>', '', '', False),
        ))):
            class Handler:
                response = None
                def pagina(self, title, text, session, status=200, cliente=False):
                    self.response = text
            handler = Handler()
            client_web.home(handler, 'db', client())
            self.assertIn('OS-1', handler.response)
            self.assertNotIn('<script>', handler.response)

    def test_escapes_description_in_actual_detail_view(self):
        from flavors.autoseg.modules import client_web
        item = client_service.ClientWorkItem(
            1, 'OS-1', 'Aberta', '<script>alert(1)</script>', '', '', False)
        class Handler:
            response = None
            def pagina(self, title, text, session, status=200, cliente=False):
                self.response = text
        handler = Handler()
        with (patch.object(client_web.client_service, 'get_work_item', return_value=item),
              patch.object(client_web.client_service, 'list_documents', return_value=())):
            client_web.item_detail(handler, 'db', client(), 1)
        self.assertIn('&lt;script&gt;', handler.response)
        self.assertNotIn('<script>', handler.response)

    def test_csrf_denies_invalid_request_before_business_operation(self):
        from flavors.autoseg.modules import client_web
        class Handler:
            status = None
            def erro(self, message, code):
                self.status = code
        handler = Handler()
        with patch.object(client_web.client_service, 'create_request') as create:
            client_web.request_submit(handler, 'db', client(), {'csrf': 'bad'})
            self.assertEqual(handler.status, 403)
            create.assert_not_called()


class ClientRequestLinkTest(unittest.TestCase):
    def test_account_without_pf_link_syncs_before_write(self):
        current=client(uid=8)
        row={'id':10,'numero_os':'OS-10','status':'Aberta',
             'descricao':'Example','data_abertura':'2026-01-01'}
        with (patch.object(client_service.access,'require_create'),
              patch.object(client_service.fluxo_pf,'garantir_perfil_pf',return_value=91) as profile,
              patch.object(client_service.accounts,'sync_client_pf_link',return_value=91) as sync,
              patch.object(client_service.fluxo_pf,'registrar_os_pf',return_value=10) as write,
              patch.object(client_service.accounts,'identity_for_account',return_value=object()),
              patch.object(client_service.accounts,'membership_for_account',return_value=object()),
              patch('flavors.autoseg.modules.identity.to_principal',return_value=current.principal),
              patch.object(client_service.access,'require_work_item'),
              patch.object(client_service.fluxo_pf,'obter_os_pf',return_value=row)):
            item=client_service.create_request('db',current,'A service request example','Normal')
        self.assertEqual(item.id,10)
        profile.assert_called_once_with('db',8)
        sync.assert_called_once_with('db',108,8)
        write.assert_called_once()

    def test_invalid_request_does_not_touch_profile(self):
        current=client(uid=8)
        with (patch.object(client_service.access,'require_create'),
              patch.object(client_service.fluxo_pf,'garantir_perfil_pf') as profile):
            with self.assertRaises(ValueError):
                client_service.create_request('db',current,'short','Normal')
            profile.assert_not_called()

    def test_database_failure_does_not_reveal_schema(self):
        import sqlite3
        with patch.object(client_service.ext,'db',
                          side_effect=sqlite3.OperationalError('sensitive schema')):
            with self.assertRaises(PermissionError) as exc:
                client_service.list_work_items('db',client())
        self.assertNotIn('sensitive schema',str(exc.exception))

    def test_org_call_lookup_requires_policy_before_sql(self):
        with (patch.object(client_service,'_authorize_call',
                           side_effect=PermissionError('denied')),
              patch.object(client_service.ext,'db') as sql):
            self.assertIsNone(client_service.get_call('db',client(uid=12),4))
            sql.assert_not_called()


class ClientDocumentContractTest(unittest.TestCase):
    def setUp(self):
        self.row = {'id': 21, 'numero_os': 'OS-21', 'status': 'Concluída',
                    'descricao': 'Fictitious work', 'data_abertura': '2026-01-01'}

    def test_document_listing_fails_before_metadata_for_foreign_work(self):
        with (patch.object(client_service.access, 'require_work_item',
                           side_effect=PermissionError('denied')),
              patch.object(client_service.ext, 'listar_notas_fiscais') as invoices,
              patch.object(client_service.fluxo, 'ultimo_documento') as reports):
            with self.assertRaises(PermissionError):
                client_service.list_documents('db', client(uid=8), 21)
            invoices.assert_not_called()
            reports.assert_not_called()

    def test_document_list_uses_only_authorized_service_data(self):
        with (patch.object(client_service, '_owned_work', return_value=self.row),
              patch.object(client_service.ext, 'listar_notas_fiscais', return_value=(
                  {'id': 4, 'nome_original': 'invoice.pdf'},)),
              patch.object(client_service.fluxo, 'ultimo_documento', return_value={'id': 3})):
            from officina.application.object_policy import Resource
            with (patch.object(client_service.access,'resource_for_work_item',
                               return_value=Resource('work_item',21,organization_id='autoseg',client_id=307)),
                  patch.object(client_service.ObjectPolicy,'require',return_value=None)):
                docs = client_service.list_documents('db', client(), 21)
        self.assertEqual({(d.id, d.kind) for d in docs}, {(-3, 'report'), (4, 'invoice')})
        self.assertTrue(all(d.work_id == 21 for d in docs))

    def test_document_read_does_not_accept_foreign_id(self):
        with (patch.object(client_service, '_owned_work', return_value=self.row),
              patch.object(client_service.ext, 'listar_notas_fiscais', return_value=()),
              patch.object(client_service.fluxo, 'ultimo_documento', return_value=None),
              patch.object(client_service.access,'require_document'),
              patch.object(client_service.ext, 'obter_nota_fiscal') as invoice_reader):
            with self.assertRaises(PermissionError):
                client_service.open_document('db', client(), 21, 999)
            invoice_reader.assert_not_called()

    def test_published_report_is_owner_scoped(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / 'published.pdf'
            filename.write_bytes(b'%PDF-1.4\n' + b'0' * 110)
            with (patch.object(client_service, '_owned_work', return_value=self.row),
                  patch.object(client_service.fluxo, 'ultimo_documento', return_value={'id': 9}),
                  patch.object(client_service.access,'require_document'),
                  patch.object(client_service.fluxo, 'validar_pdf_publicado', return_value=str(filename))):
                content, mime, safe_name = client_service.open_document('db', client(), 21, -9)
        self.assertTrue(content.startswith(b'%PDF-'))
        self.assertEqual(mime, 'application/pdf')
        self.assertEqual(safe_name, 'relatorio.pdf')

    def test_invoice_file_read_requires_matching_listing(self):
        with (patch.object(client_service, '_owned_work', return_value=self.row),
              patch.object(client_service.ext, 'listar_notas_fiscais', return_value=(
                  {'id': 4, 'nome_original': 'invoice.pdf'},)),
              patch.object(client_service.fluxo, 'ultimo_documento', return_value=None),
              patch.object(client_service.access,'require_document'),
              patch.object(client_service.ext, 'obter_nota_fiscal') as reader):
            with self.assertRaises(PermissionError):
                client_service.open_document('db', client(), 21, 5)
            reader.assert_not_called()
