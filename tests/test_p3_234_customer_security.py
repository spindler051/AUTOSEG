"""Phase 3.2–3.4: customer create writer and merge parity security tests.

Uses temporary SQLite and a loopback HTTP server, never a production database.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import urllib.error
import urllib.request

from flavors.autoseg.modules import api_server, prestador_auth
from officina.application.object_policy import Principal
from officina.application import work_item_access as access
from officina.application.local_service import LocalService
from officina.core import (banco, prestadores_ext as ext,
                           cadastros_v9 as cad, portal_negocios as neg)


ROOT = Path(__file__).resolve().parents[1]


class CustomerSecurityPhase3234Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='customer_phase3234_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'test.sqlite')
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        prestador_auth.instalar(self.db)
        self.admin = ext.cadastrar(self.db, 'Merge Admin',
                                   'merge-admin@invalid.test', 'Pass12345678')
        self.employee = ext.cadastrar(self.db, 'Merge Employee',
                                      'merge-employee@invalid.test', 'Pass12345678')
        cad.definir_admin(self.db, self.admin, True)
        self.admin_actor = Principal(self.admin, 'admin', organization_id='autoseg',
                                     provider_id=self.admin)
        self.employee_actor = Principal(self.employee, 'employee',
                                        organization_id='autoseg',
                                        provider_id=self.employee)
        with ext.db(self.db) as c:
            self.source = c.execute("INSERT INTO clientes(nome,status,tipo_pessoa) VALUES('Source','Ativo','Física')").lastrowid
            self.destination = c.execute("INSERT INTO clientes(nome,status,tipo_pessoa) VALUES('Destination','Ativo','Física')").lastrowid
            self.os_id = c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao) VALUES('P3-OS',?,'Aberta','Service')", (self.source,)).lastrowid
            c.execute("INSERT INTO financeiro(os_id,cliente_id,descricao,valor) VALUES(?,?,?,?)",
                      (self.os_id,self.source,'P3 finance',10))
            neg.criar_auditoria(c)

    def _state(self):
        with ext.db(self.db) as c:
            return (
                [tuple(r) for r in c.execute('SELECT id,nome,status FROM clientes ORDER BY id')],
                [tuple(r) for r in c.execute('SELECT id,cliente_id FROM ordens_servico ORDER BY id')],
                [tuple(r) for r in c.execute('SELECT id,cliente_id FROM financeiro ORDER BY id')],
                [tuple(r) for r in c.execute('SELECT * FROM portal_auditoria ORDER BY id')],
                [tuple(r) for r in c.execute('SELECT * FROM v9_historico_clientes ORDER BY id')],
            )

    def _create(self, actor):
        return neg.cliente_salvar(self.db,
            {'tipo_pessoa':'Física','nome':'Fresh customer','status':'Ativo'},
            self.employee, principal=actor)

    def test_create_missing_principal_denied_without_mutation(self):
        before = self._state()
        with self.assertRaises(PermissionError):
            self._create(None)
        self.assertEqual(self._state(), before)

    def test_create_inactive_principal_denied_without_mutation(self):
        actor = Principal(self.employee, 'employee', organization_id='autoseg',
                          provider_id=self.employee, active=False)
        before = self._state()
        with self.assertRaises(PermissionError):
            self._create(actor)
        self.assertEqual(self._state(), before)

    def test_employee_create_allowed_and_audited_as_authenticated_actor(self):
        cid = self._create(self.employee_actor)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT nome FROM clientes WHERE id=?', (cid,)).fetchone()[0], 'Fresh customer')
            row = c.execute("SELECT prestador_id FROM portal_auditoria WHERE acao='Cliente criado' ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(row[0], self.employee)

    def test_create_audit_ignores_forged_pid(self):
        cid = neg.cliente_salvar(self.db,
            {'tipo_pessoa':'Física','nome':'True owner','status':'Ativo'},
            self.admin, principal=self.employee_actor)
        with ext.db(self.db) as c:
            row = c.execute("SELECT prestador_id FROM portal_auditoria WHERE referencia=? AND acao='Cliente criado'", (str(cid),)).fetchone()
            self.assertEqual(row[0], self.employee)

    def test_direct_local_create_requires_principal(self):
        before = self._state()
        with self.assertRaises(PermissionError):
            LocalService(self.db).salvar_cliente(None,
                {'tipo_pessoa':'Física','nome':'Should not exist','status':'Ativo'})
        self.assertEqual(self._state(), before)

    def test_create_guard_requires_open_transaction(self):
        with ext.db(self.db) as c:
            with self.assertRaises(RuntimeError):
                access.require_customer_create_locked(c, self.employee_actor)

    def test_employee_merge_denied_without_mutation(self):
        before = self._state()
        with self.assertRaises(PermissionError):
            LocalService(self.db).mesclar_clientes(self.source,self.destination,
                                                    principal=self.employee_actor)
        self.assertEqual(self._state(),before)

    def test_admin_merge_moves_orders_finance_and_audits(self):
        LocalService(self.db).mesclar_clientes(self.source,self.destination,
                                               principal=self.admin_actor)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM clientes WHERE id=?', (self.source,)).fetchone()[0], 'Inativo')
            self.assertEqual(c.execute('SELECT cliente_id FROM ordens_servico WHERE id=?', (self.os_id,)).fetchone()[0], self.destination)
            self.assertEqual(c.execute('SELECT cliente_id FROM financeiro WHERE os_id=?', (self.os_id,)).fetchone()[0], self.destination)
            self.assertEqual(c.execute("SELECT autor FROM v9_historico_clientes WHERE acao='Mesclagem' ORDER BY id DESC LIMIT 1").fetchone()[0], 'Merge Admin')

    def _request(self, name, route, payload):
        token = prestador_auth.login(self.db,
            f'merge-{name}@invalid.test', 'Pass12345678')['token']
        req = urllib.request.Request(self.base + '/api/v1/desktop' + route,
            json.dumps(payload).encode(), method='POST',
            headers={'Authorization': 'Bearer ' + token,
                     'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def _server(self):
        self.server = api_server.start(self.db, '127.0.0.1', 0)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = 'http://127.0.0.1:' + str(self.server.server_address[1])

    def test_admin_http_merge(self):
        self._server()
        status, result = self._request('admin', f'/clientes/{self.source}/mesclar',
                                        {'destino_id': self.destination})
        self.assertEqual(status, 200, result)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM clientes WHERE id=?', (self.source,)).fetchone()[0], 'Inativo')
            self.assertEqual(c.execute('SELECT cliente_id FROM financeiro WHERE os_id=?', (self.os_id,)).fetchone()[0], self.destination)

    def test_employee_http_merge_forbidden_without_mutation(self):
        self._server()
        before = self._state()
        status, _ = self._request('employee', f'/clientes/{self.source}/mesclar',
                                  {'destino_id': self.destination})
        self.assertEqual(status,403)
        self.assertEqual(self._state(),before)

    def test_invalid_http_merge_destination_is_400(self):
        self._server()
        for payload in ({},{'destino_id':self.source},{'destino_id':999999},
                        {'destino_id':'invalid'}):
            with self.subTest(payload=payload):
                status, _ = self._request('admin', f'/clientes/{self.source}/mesclar',payload)
                self.assertEqual(status,400)

    def test_gtk_merge_renderer_admin_only(self):
        source = (ROOT/'flavors/autoseg/modules/gtk_app.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        klass = next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Janela')
        method = next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='_pagina_clientes')
        class Widget:
            def __init__(self,*a,**kw): self.children=[]
            def set_hexpand(self,*a): pass
            def connect(self,*a): pass
            def append(self,child): self.children.append(child)
        class UI:
            class Tabela:
                def __init__(self,*a,**kw): self.widget=Widget()
            @staticmethod
            def botao(label,*a,**kw): return {'label':label}
            @staticmethod
            def barra(*xs): return list(xs)
        ns={'Gtk':SimpleNamespace(Box=Widget, SearchEntry=Widget,Orientation=SimpleNamespace(VERTICAL=1)), 'ui':UI}
        exec(compile(ast.Module(body=[method],type_ignores=[]),str(ROOT),'exec'),ns)
        noop=lambda *a: None
        for is_admin in (False,True):
            fake=SimpleNamespace(sessao=SimpleNamespace(admin=is_admin,permissions=frozenset()),
                web=SimpleNamespace(enabled=True), carregar_clientes=noop,
                _importar_cliente_yaml=noop,_modelo_cliente_yaml=noop,
                _atribuir_responsavel=noop, novo_cliente=noop,_editar_cliente=noop,
                _nova_os_cliente=noop,_excluir_cliente=noop,
                _desativar_cliente=noop,_mesclar_cliente=noop,
                _senha_cliente=noop,_abrir_portal_navegador=noop)
            page=ns['_pagina_clientes'](fake)
            labels=[x['label'] for x in page.children[-1]]
            self.assertEqual('Mesclar cliente' in labels,is_admin)

    def test_gtk_confirmation_discloses_irreversible_merge(self):
        content=(ROOT/'flavors/autoseg/modules/gtk_dialogos.py').read_text(encoding='utf-8')
        self.assertIn('class DialogoMesclarCliente(Adw.Dialog):',content)
        for phrase in ('ficará inativa', 'registros ', 'financeiros serão movidos',
                       'não pode', 'desfeita pela interface'):
            self.assertIn(phrase,content)
