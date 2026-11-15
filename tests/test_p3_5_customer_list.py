"""Phase 3.5 — GTK-local and Desktop API customer list use one authorization projection."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules.api_desktop import _scoped_customer_list
from officina.application.local_service import LocalService
from officina.application.object_policy import Principal
from officina.core import banco, cadastros_v9 as cad, prestadores_ext as ext


class CustomerListParityTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='p35_customer_list_')
        self.addCleanup(temp.cleanup)
        self.db = str(Path(temp.name) / 'fixture.db')
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        self.admin = ext.cadastrar(self.db, 'P35 Admin', 'p35admin@invalid.test', 'Pass12345678')
        self.staff = ext.cadastrar(self.db, 'P35 Staff', 'p35staff@invalid.test', 'Pass12345678')
        self.other = ext.cadastrar(self.db, 'P35 Other', 'p35other@invalid.test', 'Pass12345678')
        cad.definir_admin(self.db, self.admin, True)
        self.actor = Principal(self.staff, 'employee', organization_id='autoseg', provider_id=self.staff)
        self.admin_actor = Principal(self.admin, 'admin', organization_id='autoseg', provider_id=self.admin)
        with ext.db(self.db) as c:
            self.own_customer = c.execute("INSERT INTO clientes(nome,status,documento,telefone,cidade) VALUES('Shared Customer','Ativo','11111111111','5199991111','Porto Alegre')").lastrowid
            self.secret_customer = c.execute("INSERT INTO clientes(nome,status,documento,telefone,cidade) VALUES('Secret Customer','Ativo','22222222222','5199992222','Canoas')").lastrowid
            own_os = c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao) VALUES('P35-OWN',?,'Aberta','Work')", (self.own_customer,)).lastrowid
            other_os = c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao) VALUES('P35-OTHER',?,'Aberta','Work')", (self.secret_customer,)).lastrowid
            c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)',(own_os,self.staff,ext.agora()))
            c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)',(other_os,self.other,ext.agora()))
            self.own_os = own_os

    def test_local_list_without_actor_denied(self):
        with self.assertRaises(PermissionError):
            LocalService(self.db).listar_clientes('')

    def test_unrelated_customer_hidden_from_employee_and_same_as_api(self):
        local = LocalService(self.db).listar_clientes('', principal=self.actor)
        api = _scoped_customer_list(self.db, self.actor, '')
        self.assertEqual(local, api)
        self.assertEqual([c.id for c in local], [self.own_customer])
        self.assertNotIn(self.secret_customer, [c.id for c in local])

    def test_admin_sees_both_and_same_as_api(self):
        local = LocalService(self.db).listar_clientes('', principal=self.admin_actor)
        self.assertEqual(local, _scoped_customer_list(self.db, self.admin_actor, ''))
        self.assertEqual({c.id for c in local}, {self.own_customer, self.secret_customer})

    def test_inactive_principal_denied(self):
        inactive = Principal(self.staff, 'employee', organization_id='autoseg',
                             provider_id=self.staff, active=False)
        with self.assertRaises(PermissionError):
            LocalService(self.db).listar_clientes('', principal=inactive)

    def test_revoked_involvement_no_longer_exposes_customer(self):
        with ext.db(self.db) as c:
            c.execute('DELETE FROM os_responsaveis WHERE os_id=? AND prestador_id=?',
                      (self.own_os,self.staff))
        self.assertEqual(LocalService(self.db).listar_clientes('', principal=self.actor), [])
