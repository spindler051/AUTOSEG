"""Phase 3.6 — object/field read parity and redacted-edit preservation."""
import tempfile
import unittest
from pathlib import Path

from flavors.autoseg.modules.api_desktop import _scoped_customer_detail
from officina.application.local_service import LocalService
from officina.application.object_policy import Principal
from officina.core import banco, cadastros_v9 as cad, prestadores_ext as ext


class CustomerDetailParityTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='p36_detail_')
        self.addCleanup(tmp.cleanup)
        self.db = str(Path(tmp.name) / 'test.db')
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        self.admin = ext.cadastrar(self.db, 'P36 Admin', 'p36admin@invalid.test', 'Pass12345678')
        self.employee = ext.cadastrar(self.db, 'P36 Employee', 'p36employee@invalid.test', 'Pass12345678')
        self.other = ext.cadastrar(self.db, 'P36 Other', 'p36other@invalid.test', 'Pass12345678')
        cad.definir_admin(self.db, self.admin, True)
        self.admin_actor = Principal(self.admin, 'admin', organization_id='autoseg', provider_id=self.admin)
        self.actor = Principal(self.employee, 'employee', organization_id='autoseg', provider_id=self.employee)
        with ext.db(self.db) as c:
            self.customer = c.execute("INSERT INTO clientes(nome,status,tipo_pessoa,documento,telefone,observacoes,administradora_email) VALUES('P36 Visible','Ativo','Física','11111111111','51988887777','Private internal note','private@invalid.test')").lastrowid
            self.other_customer = c.execute("INSERT INTO clientes(nome,status,tipo_pessoa) VALUES('P36 Hidden','Ativo','Física')").lastrowid
            os_id = c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao) VALUES('P36-OWN',?,'Aberta','Work')",(self.customer,)).lastrowid
            c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)',(os_id,self.employee,ext.agora()))

    def test_local_detail_without_principal_denied(self):
        with self.assertRaises(PermissionError):
            LocalService(self.db).obter_cliente(self.customer)

    def test_employee_detail_matches_api_and_redacts_private_fields(self):
        local = LocalService(self.db).obter_cliente(self.customer, principal=self.actor)
        api = _scoped_customer_detail(self.db, self.actor, self.customer)
        self.assertEqual(local, api)
        self.assertEqual(local.campos['nome'], 'P36 Visible')
        self.assertNotIn('observacoes', local.campos)
        self.assertNotIn('administradora_email', local.campos)

    def test_gtk_hides_fields_missing_from_scoped_projection(self):
        source = (Path(__file__).resolve().parents[1] / 'flavors/autoseg/modules/gtk_dialogos.py').read_text()
        # The server's field projection drives visibility; the widget table is
        # only an adapter and the old self.dados loop is gone.
        self.assertIn('from flavors.autoseg.modules.autoseg_form_contracts import customer_fields', source)
        self.assertIn('self._fields = customer_fields', source)
        self.assertIn('for group_name, names in sections:', source)
        self.assertIn('if name in projected', source)
        self.assertIn('self._customer_widgets = {}', source)

    def test_unrelated_customer_denied(self):
        with self.assertRaises(PermissionError):
            LocalService(self.db).obter_cliente(self.other_customer, principal=self.actor)

    def test_admin_sees_complete_customer(self):
        item = LocalService(self.db).obter_cliente(self.customer, principal=self.admin_actor)
        self.assertEqual(item.campos.get('observacoes'), 'Private internal note')
        self.assertEqual(item, _scoped_customer_detail(self.db, self.admin_actor, self.customer))

    def test_inactive_principal_denied(self):
        inactive = Principal(self.employee,'employee',organization_id='autoseg',
                             provider_id=self.employee,active=False)
        with self.assertRaises(PermissionError):
            LocalService(self.db).obter_cliente(self.customer, principal=inactive)

    def test_redacted_values_survive_employee_edit(self):
        service = LocalService(self.db)
        # Intentionally try to clear the two fields that are absent in the scoped detail.
        service.salvar_cliente(self.customer,
             {'nome':'Updated visible','observacoes':'', 'administradora_email':'',
              'tipo_pessoa':'Jurídica'}, principal=self.actor)
        with ext.db(self.db) as c:
            record = c.execute('SELECT nome,observacoes,administradora_email,tipo_pessoa FROM clientes WHERE id=?',
                                (self.customer,)).fetchone()
        self.assertEqual(record['nome'],'Updated visible')
        self.assertEqual(record['observacoes'],'Private internal note')
        self.assertEqual(record['administradora_email'],'private@invalid.test')
        self.assertEqual(record['tipo_pessoa'],'Física')

    def test_edit_of_unrelated_customer_denied_unchanged(self):
        with ext.db(self.db) as c:
            before = tuple(c.execute('SELECT * FROM clientes WHERE id=?',(self.other_customer,)).fetchone())
        with self.assertRaises(PermissionError):
            LocalService(self.db).salvar_cliente(self.other_customer,
                {'nome':'Tampered'}, principal=self.actor)
        with ext.db(self.db) as c:
            after = tuple(c.execute('SELECT * FROM clientes WHERE id=?',(self.other_customer,)).fetchone())
        self.assertEqual(before,after)
