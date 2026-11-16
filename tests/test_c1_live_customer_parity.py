"""C1 reviewer regressions: projection, role changes, and hidden fields.

Run on Arch after applying the C1 patch; no tests were run while authoring.
"""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from flavors.autoseg.modules.autoseg_form_contracts import CUSTOMER, customer_fields
from officina.application.customer_form_security import safe_customer_edit
from officina.application.live_provider import resolve as live_provider
from officina.application.local_service import LocalService
from officina.application.object_policy import Principal
from officina.core import banco, cadastros_v9 as cad, prestadores_ext as ext


class CustomerFormParityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_c1_form_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'customers.db')
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        self.admin = ext.cadastrar(self.db, 'Admin',
                                  'c1-admin@invalid.test', 'Pass12345678')
        self.employee = ext.cadastrar(self.db, 'Employee',
                                     'c1-employee@invalid.test', 'Pass12345678')
        cad.definir_admin(self.db, self.admin, True)
        with ext.db(self.db) as c:
            self.customer = c.execute('''INSERT INTO clientes
                (nome,tipo_pessoa,status,observacoes,administradora_email)
                VALUES('Client','Jurídica','Ativo','private notes','secret@invalid.test')''').lastrowid
            self.other = c.execute('''INSERT INTO clientes
                (nome,tipo_pessoa,status,observacoes)
                VALUES('Other','Jurídica','Ativo','not involved')''').lastrowid
            oid = c.execute('''INSERT INTO ordens_servico
                (numero_os,cliente_id,status,descricao)
                VALUES('C1-1',?,'Aberta','Test')''', (self.customer,)).lastrowid
            c.execute('''INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em)
                VALUES(?,?,?)''',(oid,self.employee,ext.agora()))
        self.admin_actor = Principal(self.admin,'admin',organization_id='autoseg',
                                     provider_id=self.admin)
        self.employee_actor = Principal(self.employee,'employee',
                                        organization_id='autoseg',
                                        provider_id=self.employee)
        self.service = LocalService(self.db)

    def test_create_is_available_to_employee_and_matches_contract_order(self):
        projected = customer_fields(self.db,self.employee_actor)
        self.assertEqual([field.id for field in projected],
                         [field.id for field in CUSTOMER.fields])
        self.assertIn('nome',{field.id for field in projected})

    def test_employee_edit_uses_canonical_subset_and_drops_hidden_values(self):
        visible = customer_fields(self.db,self.employee_actor,
                                  customer_id=self.customer)
        ids = [field.id for field in visible]
        self.assertEqual(ids,[field.id for field in CUSTOMER.fields if field.id in ids])
        self.assertIn('nome',ids)
        self.assertNotIn('observacoes',ids)
        self.assertNotIn('administradora_email',ids)
        with ext.db(self.db) as c:
            current = c.execute('SELECT * FROM clientes WHERE id=?',
                                (self.customer,)).fetchone()
        tampered = dict(current)
        tampered.update(nome='Updated',observacoes='hacked',
                        administradora_email='hacked@invalid.test')
        safe = safe_customer_edit(self.db,self.employee_actor,current,tampered)
        self.assertEqual(safe['nome'],'Updated')
        self.assertEqual(safe['observacoes'],'private notes')
        self.assertEqual(safe['administradora_email'],'secret@invalid.test')

    def test_stale_admin_loses_hidden_fields_and_foreign_edit(self):
        stale = replace(self.employee_actor,role='admin')
        self.assertEqual(live_provider(self.db,stale).role,'employee')
        fields = customer_fields(self.db,stale,customer_id=self.customer)
        self.assertNotIn('observacoes', {field.id for field in fields})
        with self.assertRaises(PermissionError):
            customer_fields(self.db,stale,customer_id=self.other)
        with self.assertRaises(PermissionError):
            self.service.salvar_cliente(self.other,{'nome':'hacked'},principal=stale)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT nome FROM clientes WHERE id=?',
                                       (self.other,)).fetchone()[0],'Other')

    def test_revocation_cannot_render_or_save(self):
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET ativo=0 WHERE id=?',(self.employee,))
        with self.assertRaises(PermissionError):
            customer_fields(self.db,self.employee_actor,
                            customer_id=self.customer)
        with self.assertRaises(PermissionError):
            self.service.salvar_cliente(self.customer,{'nome':'hacked'},
                                        principal=self.employee_actor)


if __name__ == '__main__':
    unittest.main()
