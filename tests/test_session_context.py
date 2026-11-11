"""Shared context contract tests without gi/GTK dependencies."""
import dataclasses
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from officina.application.contracts import SessionContext
from officina.application.policy import load_policy
from officina.application.session import Sessao, navigation_for_session
from flavors.autoseg.modules import api_desktop


class SessionContextTest(unittest.TestCase):
    def context(self, role):
        ident=SimpleNamespace(kind='provider',id=14,display_name='Example')
        membership=SimpleNamespace(active=True)
        principal=SimpleNamespace(active=True,role=role,organization_id='autoseg',
                                  provider_id=14,client_id=None,client_org_ids=frozenset())
        return SessionContext.from_identity(ident,membership,principal,account_id=None)

    def test_context_has_only_safe_fields(self):
        admin=self.context('admin')
        self.assertTrue(admin.has('provider.manage.all'))
        self.assertEqual(admin.context_label,'Portal do prestador')
        for field in dataclasses.fields(SessionContext):
            self.assertNotIn(field.name,('token','csrf','credential','password_hash','email'))
        self.assertNotIn('credential',repr(admin))

    def test_employee_cannot_gain_admin_permission(self):
        employee=self.context('employee')
        self.assertFalse(employee.has('provider.manage.all'))
        self.assertFalse(employee.has('account.manage.all'))
        self.assertTrue(employee.has('work_item.view.own'))

    def test_gtk_navigation_uses_context_without_gi(self):
        items=[('inicio','Início','home'),('prestadores','Prestadores','users')]
        guest=Sessao('remote',14,'Employee','',False,role='employee',
                     permissions=self.context('employee').permissions)
        admin=Sessao('remote',14,'Admin','',True,role='admin',
                     permissions=self.context('admin').permissions)
        self.assertEqual([i[0] for i in navigation_for_session(items,guest)],['inicio'])
        self.assertEqual(len(navigation_for_session(items,admin)),2)
        self.assertFalse(guest.can('provider.manage.all'))

    def test_legacy_saved_gtk_context_is_conservative(self):
        sessao=Sessao.from_dict({'mode':'remote','prestador_id':3,'nome':'Legacy',
                                'email':'','admin':False})
        self.assertEqual(sessao.role,'employee')
        self.assertEqual(sessao.permissions,frozenset())
        self.assertFalse(sessao.can('provider.manage.all'))

    def test_desktop_api_context_preserves_legacy_payload(self):
        context=self.context('employee')
        payload={'id':14,'nome':'Example','email':'example.invalid','admin':False}
        out={**payload, **api_desktop._context_api(context)}
        for key in payload:
            self.assertEqual(out[key],payload[key])
        self.assertEqual(out['role'],'employee')
        self.assertIn('permissions',out)
        self.assertEqual(out['context_label'],'Portal do prestador')

    def test_direct_service_policy_remains_separate(self):
        from officina.application.object_policy import ObjectPolicy,Principal,Resource
        p=Principal(account_id=14,role='employee',provider_id=14)
        decision=ObjectPolicy().can(p,'manage',Resource('account',organization_id='autoseg'))
        self.assertFalse(decision.allowed)


if __name__=='__main__':
    unittest.main()

class DesktopMeHttpContractTest(unittest.TestCase):
    """Real service and auth via a transport handler, without GTK."""
    def setUp(self):
        import tempfile
        from pathlib import Path
        from officina.core.banco import criar_banco
        from officina.core import prestadores_ext as ext, cadastros_v9 as cad
        from flavors.autoseg.modules import prestador_auth
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/'desktop.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        prestador_auth.instalar(self.db)
        self.password='DesktopSecret123'
        self.pid=ext.cadastrar(self.db,'Example','example@example.test',self.password)

    def _me(self):
        import io
        from types import SimpleNamespace
        from flavors.autoseg.modules import prestador_auth
        auth=prestador_auth.login(self.db,'example@example.test',self.password)
        self.assertIsNotNone(auth)
        class Handler:
            server=SimpleNamespace(server_address=('127.0.0.1',0))
            client_address=('127.0.0.1',50000)
            path='/api/v1/desktop/me'
            wfile=io.BytesIO()
            status=None
            headers={'Authorization':'Bearer '+auth['token']}
            def send_response(self,status):
                self.status=status
            def send_header(self,*args):
                pass
            def end_headers(self):
                pass
        handler=Handler()
        self.assertTrue(api_desktop.handle(handler,handler.path,self.db,'GET'))
        self.assertEqual(handler.status,200)
        import json
        return json.loads(handler.wfile.getvalue())['data']

    def test_employee_context_via_actual_me_handler(self):
        info=self._me()
        self.assertEqual(info['role'],'employee')
        self.assertNotIn('*',info['permissions'])
        self.assertNotIn('account.manage.all',info['permissions'])
        for old in ('id','nome','email','admin'):
            self.assertIn(old,info)

    def test_admin_context_via_actual_me_handler(self):
        from officina.core import cadastros_v9 as cad
        cad.definir_admin(self.db,self.pid,True)
        info=self._me()
        self.assertEqual(info['role'],'admin')
        self.assertIn('*',info['permissions'])
        self.assertTrue(info['admin'])
