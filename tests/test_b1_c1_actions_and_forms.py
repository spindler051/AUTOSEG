"""B1/C1: server-resolved actions and the customer field contract."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from officina.application.customer_form_security import safe_customer_edit
from officina.application.object_policy import Principal
from officina.core import banco, cadastros_v9 as cad, prestadores_ext as ext
from flavors.autoseg.modules.autoseg_actions import ACTIONS, resolved_actions
from flavors.autoseg.modules.autoseg_form_contracts import CUSTOMER, WORK, customer_fields


class ActionsAndFormsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='b1c1_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'test.db')
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        self.admin = ext.cadastrar(self.db, 'Admin', 'admin@example.invalid', 'Password12345')
        self.employee = ext.cadastrar(self.db, 'Employee', 'employee@example.invalid', 'Password12345')
        self.other = ext.cadastrar(self.db, 'Other', 'other@example.invalid', 'Password12345')
        cad.definir_admin(self.db, self.admin, True)
        with ext.db(self.db) as c:
            self.client = c.execute('''INSERT INTO clientes
                (nome,status,tipo_pessoa,documento,telefone,email,endereco,cidade,
                 observacoes,administradora_email)
                VALUES('Client','Ativo','Física','11111111111','51999999999',
                       'client@example.invalid','Rua A','Porto Alegre',
                       'hidden note','hidden@example.invalid')''').lastrowid
            self.own_os = c.execute('''INSERT INTO ordens_servico
                (numero_os,cliente_id,status,descricao)
                VALUES('B1-1',?,'Aberta','Work')''', (self.client,)).lastrowid
            self.other_os = c.execute('''INSERT INTO ordens_servico
                (numero_os,cliente_id,status,descricao)
                VALUES('B1-2',?,'Aberta','Other')''', (self.client,)).lastrowid
            c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)',
                      (self.own_os, self.employee, ext.agora()))
            c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)',
                      (self.other_os, self.other, ext.agora()))
        self.admin_actor = Principal(self.admin, 'admin', organization_id='autoseg',
                                     provider_id=self.admin)
        self.employee_actor = Principal(self.employee, 'employee', organization_id='autoseg',
                                        provider_id=self.employee)

    def _current(self):
        with ext.db(self.db) as c:
            return dict(c.execute('SELECT * FROM clientes WHERE id=?', (self.client,)).fetchone())

    def _ids(self, principal, os_id):
        return {a.id for a in resolved_actions(self.db, principal, 'work',
                                               object_id=os_id, surface='gtk')}

    def test_customer_fields_are_server_projections(self):
        admin_fields = {f.id for f in customer_fields(self.db, self.admin_actor,
                                                      customer_id=self.client)}
        self.assertEqual(admin_fields, {f.id for f in CUSTOMER.fields})
        employee_fields = {f.id for f in customer_fields(self.db, self.employee_actor,
                                                         customer_id=self.client)}
        self.assertIn('nome', employee_fields)
        self.assertIn('status', employee_fields)
        self.assertNotIn('observacoes', employee_fields)
        self.assertNotIn('administradora_email', employee_fields)
        self.assertNotIn('tipo_pessoa', employee_fields)

    def test_hidden_values_survive_employee_edit(self):
        current = self._current()
        submitted = dict(current)
        submitted.update(nome='Renamed', telefone='51000000000',
                         observacoes='', administradora_email='', tipo_pessoa='Jurídica')
        merged = safe_customer_edit(self.db, self.employee_actor, current, submitted)
        self.assertEqual(merged['nome'], 'Renamed')
        self.assertEqual(merged['telefone'], '51000000000')
        self.assertEqual(merged['observacoes'], 'hidden note')
        self.assertEqual(merged['administradora_email'], 'hidden@example.invalid')
        self.assertEqual(merged['tipo_pessoa'], 'Física')

    def test_stale_admin_role_is_rechecked_against_the_database(self):
        # Same provider, but the session still claims admin after denotion.
        stale = Principal(self.employee, 'admin', organization_id='autoseg',
                          provider_id=self.employee)
        current = self._current()
        submitted = dict(current)
        submitted.update(observacoes='tampered', tipo_pessoa='Jurídica')
        merged = safe_customer_edit(self.db, stale, current, submitted)
        self.assertEqual(merged['observacoes'], 'hidden note')
        self.assertEqual(merged['tipo_pessoa'], 'Física')

    def test_work_actions_are_object_and_role_scoped(self):
        admin = self._ids(self.admin_actor, self.own_os)
        self.assertTrue({'work.edit', 'work.conclude', 'work.assign',
                         'work.archive', 'work.reopen'}.issubset(admin))
        employee = self._ids(self.employee_actor, self.own_os)
        self.assertTrue({'work.open', 'work.edit', 'work.start',
                         'work.conclude'}.issubset(employee))
        self.assertFalse({'work.assign', 'work.archive', 'work.reopen'}.intersection(employee))
        unrelated = self._ids(self.employee_actor, self.other_os)
        self.assertNotIn('work.edit', unrelated)
        self.assertNotIn('work.conclude', unrelated)

    def test_every_work_action_has_both_adapters(self):
        work = [a for a in ACTIONS if a.section == 'work']
        self.assertTrue(work)
        for action in work:
            with self.subTest(action=action.id):
                self.assertTrue(action.gtk_handler)
                self.assertTrue(action.web_href)
                self.assertIn('gtk', action.surfaces)
                self.assertIn('web', action.surfaces)

    def test_work_form_contract_has_the_core_fields(self):
        names = {field.id for field in WORK.fields}
        for name in ('cliente_id', 'descricao', 'forma_pagamento', 'valor_mao_obra',
                     'valor_total', 'material_item[]', 'material_qtd[]'):
            with self.subTest(field=name):
                self.assertIn(name, names)

    def test_adaptive_shell_source(self):
        app = (Path(__file__).resolve().parents[1] /
               'flavors/autoseg/modules/gtk_app.py').read_text()
        commons = (Path(__file__).resolve().parents[1] /
                   'flavors/autoseg/modules/gtk_comum.py').read_text()
        self.assertIn('set_size_request(360, 480)', app)
        self.assertIn('max-width: 600sp', app)
        self.assertIn('Adw.BreakpointBin', app)
        self.assertIn('Adw.BreakpointBin', commons)


if __name__ == '__main__':
    unittest.main()
