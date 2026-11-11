"""6.2: real ownership, participant and organization-scoped permissions."""
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from officina.application.object_policy import ObjectPolicy, Principal, Resource
from officina.application.policy import PADRAO, load_policy
from officina.application.work_item_access import (resource_for_work_item,
                                                      require_work_item)


class WorkRelationshipTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'orders.db')
        with sqlite3.connect(self.db) as c:
            c.executescript("""CREATE TABLE ordens_servico(id INTEGER PRIMARY KEY,
                prestador_id INTEGER,cliente_id INTEGER);
                CREATE TABLE os_responsaveis(os_id INTEGER,prestador_id INTEGER);
                CREATE TABLE os_prestadores(os_id INTEGER,prestador_id INTEGER,ativo INTEGER);
                CREATE TABLE v9_organizacoes(id INTEGER PRIMARY KEY,cliente_id INTEGER,
                    mesclado_em INTEGER);
                CREATE TABLE v9_chamados(id INTEGER,usuario_id INTEGER,
                    organizacao_id INTEGER,os_id INTEGER);
                INSERT INTO ordens_servico VALUES(1,99,501);
                INSERT INTO ordens_servico VALUES(2,3,501);
                INSERT INTO os_responsaveis VALUES(1,2);
                INSERT INTO os_responsaveis VALUES(2,3);
                INSERT INTO os_prestadores VALUES(1,3,1);
                INSERT INTO os_prestadores VALUES(1,4,0);
                INSERT INTO os_prestadores VALUES(2,3,1);
                INSERT INTO v9_organizacoes VALUES(701,501,NULL);
                INSERT INTO v9_organizacoes VALUES(702,502,NULL);
            """)

    def provider(self,pid,role='employee',active=True):
        return Principal(pid,role,organization_id='autoseg',provider_id=pid,
                         active=active)

    def test_responsavel_nao_participante(self):
        resource=resource_for_work_item(self.db,1)
        self.assertEqual(resource.owner_id,2)
        self.assertEqual(resource.participant_ids,frozenset({3}))
        self.assertEqual('own',ObjectPolicy().relationship(self.provider(2),resource))
        self.assertTrue(require_work_item(self.db,self.provider(2),1,'edit').allowed)

    def test_participante_nao_responsavel(self):
        self.assertEqual('involved', ObjectPolicy().relationship(
            self.provider(3),resource_for_work_item(self.db,1)))
        self.assertTrue(require_work_item(self.db,self.provider(3),1,'edit').allowed)
        with self.assertRaises(PermissionError):
            require_work_item(self.db,self.provider(3),1,'conclude')
        with self.assertRaises(PermissionError):
            require_work_item(self.db,self.provider(3),1,'assume')

    def test_responsavel_e_participante(self):
        self.assertEqual('own',ObjectPolicy().relationship(
            self.provider(3),resource_for_work_item(self.db,2)))
        self.assertTrue(require_work_item(self.db,self.provider(3),2,'conclude').allowed)

    def test_sem_vinculo_e_legacy_prestador_id(self):
        for pid in (4,5,99):
            with self.subTest(pid=pid),self.assertRaises(PermissionError):
                require_work_item(self.db,self.provider(pid),1,'view')

    def test_admin_e_inativo(self):
        self.assertTrue(require_work_item(self.db,self.provider(9,'admin'),1,'edit').allowed)
        with self.assertRaises(PermissionError):
            require_work_item(self.db,self.provider(2,active=False),1,'view')

    def test_organization_scope_no_cross_organization(self):
        resource=resource_for_work_item(self.db,1)
        self.assertEqual(701,resource.client_org_id)
        sindico=Principal(16,'sindico',organization_id='autoseg',
                          client_org_ids=frozenset({701}))
        zelador=Principal(17,'zelador',organization_id='autoseg',
                          client_org_ids=frozenset({701}))
        for actor in (sindico,zelador):
            self.assertTrue(ObjectPolicy().can(actor,'view',resource).allowed)
            for action in ('edit','cancel','conclude','assign','archive'):
                self.assertFalse(ObjectPolicy().can(actor,action,resource).allowed)
        other=Principal(18,'sindico',organization_id='autoseg',
                        client_org_ids=frozenset({702}))
        self.assertFalse(ObjectPolicy().can(other,'view',resource).allowed)

    def test_customer_porteiro_only_own(self):
        resource=resource_for_work_item(self.db,1)
        for role in ('customer','porteiro'):
            self.assertFalse(ObjectPolicy().can(Principal(20,role,
                organization_id='autoseg',client_id=502), 'view',resource).allowed)
            self.assertTrue(ObjectPolicy().can(Principal(21,role,
                organization_id='autoseg',client_id=501), 'view',resource).allowed)

    def test_policy_override_changes_decision(self):
        import yaml
        config=copy.deepcopy(PADRAO)
        config['roles']['employee']['permissions'] = ['work_item.view.own']
        filename=Path(self.tmp.name)/'policy.yaml'
        filename.write_text(yaml.safe_dump(config,allow_unicode=True),encoding='utf-8')
        restricted=ObjectPolicy(load_policy(filename))
        own=resource_for_work_item(self.db,1)
        self.assertTrue(ObjectPolicy().can(self.provider(2),'edit',own).allowed)
        self.assertFalse(restricted.can(self.provider(2),'edit',own).allowed)
        self.assertTrue(restricted.can(self.provider(2),'view',own).allowed)

    def test_repository_policy_yaml_is_effective(self):
        from officina.paths import AUTOSEG_DIR
        actual = load_policy(AUTOSEG_DIR / 'config' / 'policy.yaml')
        for role in ('customer', 'porteiro', 'zelador', 'sindico'):
            self.assertIn(role, actual.roles)
            self.assertTrue(actual.allows(role,'work_item.create.request'))
            self.assertTrue(actual.allows(role,'document.download.own'))
            self.assertFalse(actual.allows(role,'finance.view.own'))
        for role in ('zelador','sindico'):
            self.assertTrue(actual.allows(role,'work_item.view.organization'))
            self.assertTrue(actual.allows(role,'document.download.organization'))
        for permission in ('work_item.conclude.own','work_item.cancel.own',
                           'work_item.archive.own','work_item.attach.involved',
                           'work_item.start.own','work_item.publish.own','work_item.send.own',
                           'document.download.involved'):
            self.assertTrue(actual.allows('employee',permission), permission)

    def test_no_client_finance_even_organization(self):
        for role in ('customer','porteiro','zelador','sindico'):
            actor=Principal(9,role,organization_id='autoseg',
                            client_org_ids=frozenset({701}))
            for kind,action in (('finance','view'),('stock','view'),
                                ('account','manage'),('work_item','edit'),
                                ('work_item','cancel'),('work_item','conclude')):
                resource=Resource(kind,organization_id='autoseg',client_org_id=701)
                self.assertFalse(ObjectPolicy().can(actor,action,resource).allowed)


if __name__=='__main__':
    unittest.main()
