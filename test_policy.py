"""Runtime-configurable permission policy (no auth wiring yet)."""
import tempfile
import unittest
from pathlib import Path

from application.policy import PolicyError, PolicyStore, load_policy


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='policy_')
        self.path = Path(self.tmp.name) / 'policy.yaml'

    def tearDown(self):
        self.tmp.cleanup()

    def escrever(self, texto):
        self.path.write_text(texto, encoding='utf-8')

    def test_default_policy_matches_roles(self):
        policy = load_policy(self.path)
        self.assertTrue(policy.allows('admin', 'work_item.delete'))
        self.assertTrue(policy.allows('admin', 'qualquer.coisa'))
        self.assertTrue(policy.allows('employee', 'work_item.view.own'))
        self.assertFalse(policy.allows('employee', 'finance.view.all'))
        self.assertFalse(policy.allows('employee', 'work_item.delete'))
        self.assertTrue(policy.allows('customer', 'work_item.view.own'))
        self.assertFalse(policy.allows('customer', 'work_item.view.all'))

    def test_field_visibility_by_relationship(self):
        policy = load_policy(self.path)
        self.assertEqual(policy.field_scope('admin', 'customer.documento'), 'all')
        self.assertEqual(policy.field_scope('employee', 'customer.documento'),
                         'involved')
        self.assertTrue(policy.can_view_field(
            'employee', 'customer.documento', 'involved'))
        self.assertFalse(policy.can_view_field(
            'employee', 'customer.documento', 'other'))
        self.assertTrue(policy.can_view_field(
            'customer', 'customer.documento', 'own'))
        self.assertFalse(policy.can_view_field(
            'customer', 'customer.documento', 'involved'))
        self.assertTrue(policy.can_view_field(
            'admin', 'customer.documento', 'other'))

    def test_runtime_reload_changes_phone_policy(self):
        self.escrever('''versao: 1
roles:
  admin: {permissions: ["*"]}
  employee: {permissions: ["customer.contact.view.involved"]}
  customer: {permissions: ["customer.contact.view.own"]}
campos:
  customer.telefone: {admin: all, employee: involved, customer: own}
''')
        store = PolicyStore(self.path)
        self.assertEqual(store.revision, 1)
        self.assertTrue(store.policy.can_view_field(
            'employee', 'customer.telefone', 'involved'))

        self.escrever('''versao: 1
roles:
  admin: {permissions: ["*"]}
  employee: {permissions: ["customer.contact.view.involved"]}
  customer: {permissions: ["customer.contact.view.own"]}
campos:
  customer.telefone: {admin: all, employee: none, customer: own}
''')
        store.reload()
        self.assertEqual(store.revision, 2)
        self.assertFalse(store.policy.can_view_field(
            'employee', 'customer.telefone', 'involved'))
        self.assertTrue(store.policy.can_view_field(
            'customer', 'customer.telefone', 'own'))

    def test_invalid_reload_keeps_last_good_policy(self):
        self.escrever('''versao: 1
roles:
  admin: {permissions: ["*"]}
campos:
  customer.email: {admin: all}
''')
        store = PolicyStore(self.path)
        self.escrever('versao: 2\nroles: []\n')
        with self.assertRaises(PolicyError):
            store.reload()
        self.assertEqual(store.revision, 1)
        self.assertTrue(store.policy.can_view_field(
            'admin', 'customer.email', 'other'))

    def test_prefix_wildcard(self):
        self.escrever('''versao: 1
roles:
  support: {permissions: ["work_item.*"]}
campos: {}
''')
        policy = load_policy(self.path)
        self.assertTrue(policy.allows('support', 'work_item.view.own'))
        self.assertFalse(policy.allows('support', 'finance.view.all'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
