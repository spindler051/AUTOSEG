"""Phase 0B: static customer registry drift checks (no runtime wiring)."""

from __future__ import annotations

import ast
from copy import deepcopy
from functools import lru_cache
from importlib import import_module
import inspect
from pathlib import Path
import tempfile
import unittest

import yaml

from officina.surface.registry import RegistryError, load_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = ROOT / 'flavors/autoseg/config/surface_registry.yaml'
POLICY_FILE = ROOT / 'flavors/autoseg/config/policy.yaml'
WEB_FILE = ROOT / 'flavors/autoseg/modules/portal_prestador.py'
API_FILE = ROOT / 'flavors/autoseg/modules/api_desktop.py'
EXPECTED = {
    'customer.create', 'customer.edit', 'customer.deactivate',
    'customer.delete', 'customer.merge', 'customer.password',
    'customer.list', 'customer.detail',
}
EXPECTED_MAPPING = {
    'customer.create': ('officina.core.portal_negocios.cliente_salvar', 'customer.create', False, 'active'),
    'customer.edit': ('officina.core.portal_negocios.cliente_salvar', 'customer.edit.involved', False, 'known_gap'),
    'customer.deactivate': ('officina.core.cadastros_v9.desativar_cliente', None, True, 'active'),
    'customer.delete': ('officina.core.portal_negocios.cliente_excluir', None, True, 'active'),
    'customer.merge': ('officina.core.cadastros_v9.mesclar_clientes', None, True, 'active'),
    'customer.password': ('officina.core.fluxo_os.definir_senha_cliente', None, True, 'active'),
    'customer.list': ('officina.integration.clientes.listar_paginado', 'customer.view.involved', False, 'active'),
    'customer.detail': ('officina.integration.clientes.obter_linha', 'customer.view.involved', False, 'known_gap'),
}


@lru_cache(maxsize=None)
def source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding='utf-8')


def service_function(dotted: str):
    module, name = dotted.rsplit('.', 1)
    return getattr(import_module(module), name)


class SurfaceRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()

    def test_01_loads_valid_schema(self):
        self.assertEqual(self.registry.version, 1)
        self.assertEqual(len(self.registry.actions), 8)
        self.assertTrue(all(row.family == 'customer' for row in self.registry.actions))

    def test_02_unique_ids(self):
        identifiers = [row.id for row in self.registry.actions]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_03_exact_inventory_rows_and_values(self):
        self.assertEqual({row.id for row in self.registry.actions}, EXPECTED)
        for row in self.registry.actions:
            with self.subTest(action=row.id):
                self.assertEqual(
                    (row.service, row.capability, row.admin_only, row.state),
                    EXPECTED_MAPPING[row.id])
        self.assertEqual(self.registry.by_id('customer.create').variant, 'create')
        self.assertEqual(self.registry.by_id('customer.edit').variant, 'edit')
        merge = self.registry.by_id('customer.merge')
        self.assertEqual(merge.api_markers,
                         ("if resto == ['mesclar'] and metodo == 'POST':",))
        self.assertTrue(merge.gtk_markers)

    def test_04_service_signatures_and_parameter_variants(self):
        for row in self.registry.actions:
            with self.subTest(action=row.id):
                signature = inspect.signature(service_function(row.service))
                for param in row.required_params:
                    self.assertIn(param, signature.parameters)
                self.assertIn('banco', row.required_params)
                self.assertTrue(callable(service_function(row.service)))

    def test_05_capabilities_are_declared_for_nonadmin_roles(self):
        config = yaml.safe_load(POLICY_FILE.read_text(encoding='utf-8'))
        self.assertIsInstance(config.get('roles'), dict)
        nonadmin = set()
        for role, config_for_role in config['roles'].items():
            if role != 'admin':
                nonadmin.update(key for key in config_for_role.get('permissions', [])
                                if key != '*')
        for row in self.registry.actions:
            if row.capability is not None:
                with self.subTest(action=row.id):
                    self.assertIn(row.capability, nonadmin)

    def test_06_admin_writers_or_explicit_password_gap(self):
        """A source-marker check, NOT a claim of behavioral coverage.

        Password is currently edge-gated and has no in-writer admin guard;
        the registry must report this gap, rather than pretending it is safe.
        """
        for row in self.registry.actions:
            if not row.admin_only:
                continue
            with self.subTest(action=row.id):
                writer_source = inspect.getsource(service_function(row.service))
                # Every admin-only action is guarded inside its writer transaction.
                self.assertEqual(row.writer_guard, 'locked')
                self.assertIn('require_admin_locked(', writer_source)
                self.assertIn('BEGIN IMMEDIATE', writer_source)

    def test_07_exact_web_api_and_ui_source_markers(self):
        web = WEB_FILE.read_text(encoding='utf-8')
        api = API_FILE.read_text(encoding='utf-8')
        for row in self.registry.actions:
            with self.subTest(action=row.id, surface='web'):
                for marker in row.web_markers:
                    self.assertIn(marker, web)
            with self.subTest(action=row.id, surface='api'):
                for marker in row.api_markers:
                    self.assertIn(marker, api)
            for marker in row.source_markers:
                with self.subTest(action=row.id, source=marker.file):
                    self.assertIn(marker.contains, source(marker.file))

    def test_08_negative_evidence_is_action_specific(self):
        """Direct errors use assertRaises; HTTP reads use exact denial assertions.

        A generic assertRaises elsewhere in a test module is NOT proof that
        customer.list or customer.detail are denied. Password remains untested.
        """
        for row in self.registry.actions:
            with self.subTest(action=row.id):
                self.assertTrue(row.negative_tests, row.id)
                self.assertTrue(row.negative_markers)
                for test_path in row.negative_tests:
                    self.assertTrue((ROOT / test_path).is_file(), test_path)
                for marker in row.negative_markers:
                    self.assertIn(marker.contains, source(marker.file))
                    if row.id not in ('customer.list', 'customer.detail'):
                        self.assertIn('assertRaises(PermissionError)', source(marker.file))
                if row.id == 'customer.list':
                    self.assertIn("def test_provider_cannot_list_unrelated_customer(self):",
                                  source('tests/test_p0_read_auth.py'))
                if row.id == 'customer.detail':
                    self.assertIn("def test_provider_cannot_read_unrelated_customer_detail(self):",
                                  source('tests/test_p0_read_auth.py'))

    def test_09_registry_is_not_imported_by_production_modules(self):
        for root_name in ('flavors', 'officina'):
            for path in (ROOT / root_name).rglob('*.py'):
                if path == ROOT / 'officina/surface/registry.py':
                    continue
                tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self.assertNotEqual(alias.name, 'officina.surface.registry', str(path))
                    elif isinstance(node, ast.ImportFrom):
                        self.assertFalse(
                            node.module == 'officina.surface.registry' or
                            (node.module == 'officina.surface' and
                             any(alias.name == 'registry' for alias in node.names)),
                            str(path))

    def test_10_admin_wildcard_does_not_create_policy_keys(self):
        policy = yaml.safe_load(POLICY_FILE.read_text(encoding='utf-8'))
        permissions = [key for role in policy['roles'].values()
                       for key in role.get('permissions', [])]
        self.assertNotIn('customer.delete', permissions)
        self.assertNotIn('customer.password', permissions)

    def test_schema_rejects_duplicate_and_invalid_data(self):
        original = yaml.safe_load(REGISTRY_FILE.read_text(encoding='utf-8'))
        cases = (
            ('duplicate id', lambda d: d['actions'].append(deepcopy(d['actions'][0]))),
            ('invalid risk', lambda d: d['actions'][0].update(risk='magical')),
            ('invalid affordance', lambda d: d['actions'][0].update(affordance='allow')),
            ('invalid state', lambda d: d['actions'][0].update(state='fixed')),
            ('missing banco', lambda d: d['actions'][0].update(required_params=['pid'])),
            ('bad capability/admin', lambda d: d['actions'][0].update(admin_only=True)),
            ('incorrect signature', lambda d: d['actions'][0].update(required_params=['banco', 'nonexistent_param'])),
            ('duplicate parameter', lambda d: d['actions'][0].update(required_params=['banco', 'banco'])),
        )
        with tempfile.TemporaryDirectory(prefix='phase0b_schema_') as folder:
            path = Path(folder) / 'registry.yaml'
            for name, change in cases:
                with self.subTest(case=name):
                    candidate = deepcopy(original)
                    change(candidate)
                    path.write_text(yaml.safe_dump(candidate, allow_unicode=True), encoding='utf-8')
                    with self.assertRaises(RegistryError):
                        load_registry(path, repo_root=ROOT)


if __name__ == '__main__':
    unittest.main()
