"""Phase 1: offline source divergence and baseline-contract regression tests.

All CLI scenarios use a temporary copy of the relevant source files. These
checks never modify the repository and never access the network.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

from officina.surface.divergence import (
    analyze, compare_baseline, render_report, ROOT, EXPECTED, REGISTRY,
    POLICY, WEB, API, GTK, LOCAL,
)

BASELINE = 'flavors/autoseg/config/surface_divergence_baseline.json'
REPORT = 'docs/planning/SURFACE_DIVERGENCE_REPORT.md'
SCRIPT = ROOT / 'scripts/surface_divergence.py'

EXPECTED_FINDINGS = {
    'customer.list:gtk_local:read_scope_divergence': 'medium',
    'customer.detail:gtk_local:read_scope_divergence': 'medium',
}


def document():
    return yaml.safe_load((ROOT / REGISTRY).read_text(encoding='utf-8'))


def fixture_tree(target: Path) -> None:
    """Copy exact reviewed inputs to an isolated temp root for CLI tests."""
    doc = document()
    sources = {REGISTRY, POLICY, WEB, API, LOCAL, *GTK, BASELINE, REPORT}
    for row in doc['actions']:
        sources.add(row['service'].rsplit('.', 1)[0].replace('.', '/') + '.py')
        sources.update(row['negative_tests'])
    for relative in sources:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


def cli(root: Path, flag: str):
    return subprocess.run([sys.executable, str(SCRIPT), flag, '--root', str(root)],
                          text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=20, check=False)


class SurfaceDivergenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings = analyze(ROOT)
        cls.by_id = {item.id: item for item in cls.findings}
        cls.baseline = json.loads((ROOT / BASELINE).read_text(encoding='utf-8'))

    def test_01_expected_eight_customer_actions(self):
        self.assertEqual({row['id'] for row in document()['actions']}, EXPECTED)
        self.assertEqual(document()['version'], 1)

    def test_02_expected_first_divergences_have_severity(self):
        for identifier, severity in EXPECTED_FINDINGS.items():
            with self.subTest(identifier=identifier):
                self.assertIn(identifier, self.by_id)
                self.assertEqual(self.by_id[identifier].severity, severity)

    def test_02b_resolved_gtk_password_affordance_is_absent(self):
        self.assertNotIn('customer.password:gtk:affordance_mismatch', self.by_id)

    def test_03_synthetic_claimed_locked_guard_is_checked_against_code(self):
        modified = deepcopy(document())
        password = next(row for row in modified['actions'] if row['id'] == 'customer.password')
        password['writer_guard'] = 'locked'
        def removed_guard_source(relative):
            original = (ROOT / relative).read_text(encoding='utf-8')
            if relative == 'officina/core/fluxo_os.py':
                return original.replace('require_admin_locked(c, principal)',
                                        'pass  # synthetic guard removal', 1)
            return original
        findings = {item.id: item for item in analyze(
            ROOT, registry_data=modified, read_source=removed_guard_source)}
        key = 'customer.password:service:missing_writer_guard'
        self.assertIn(key, findings)
        self.assertEqual(findings[key].severity, 'high')
        self.assertNotIn('customer.password:service:edge_only_authorization', findings)

    def test_04_synthetic_undefined_capability_is_not_admin_wildcard(self):
        modified = deepcopy(document())
        action = next(row for row in modified['actions'] if row['id'] == 'customer.create')
        action['capability'] = 'customer.synthetic_typo'
        findings = {item.id: item for item in analyze(ROOT, registry_data=modified)}
        key = 'customer.create:policy:capability_undefined'
        self.assertIn(key, findings)
        self.assertEqual(findings[key].severity, 'high')

    def test_05_rederived_api_and_gtk_missing_surface(self):
        for surface in ('api', 'gtk'):
            self.assertNotIn(f'customer.merge:{surface}:missing_surface', self.by_id)
        # A synthetic missing route or button must still be reported.
        modified = deepcopy(document())
        merge = next(row for row in modified['actions'] if row['id'] == 'customer.merge')
        merge['api_markers'] = ['__impossible_phase1_route_marker__']
        merge['gtk_markers'] = ['__impossible_phase1_gtk_marker__']
        results = {item.id for item in analyze(ROOT, registry_data=modified)}
        self.assertIn('customer.merge:api:missing_surface', results)
        self.assertIn('customer.merge:gtk:missing_surface', results)

    def test_06_report_deterministic_exact_bytes(self):
        once = render_report(self.findings, self.baseline).encode('utf-8')
        twice = render_report(analyze(ROOT), self.baseline).encode('utf-8')
        self.assertEqual(once, twice)
        self.assertEqual(once, (ROOT / REPORT).read_bytes())
        self.assertTrue(once.startswith(b'# Surface divergence report\n'))

    def test_07_committed_baseline_has_no_drift(self):
        new, resolved = compare_baseline(self.findings, self.baseline)
        self.assertEqual(new, ())
        self.assertEqual(resolved, ())
        self.assertTrue(all(row.get('justification') for row in self.baseline['accepted']))

    def test_08_cli_check_exits_zero_on_temp_copy(self):
        with tempfile.TemporaryDirectory(prefix='phase1_cli_') as temp:
            dest = Path(temp)
            fixture_tree(dest)
            result = cli(dest, '--check')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('CHECK OK', result.stdout)

    def test_09_cli_check_detects_new_unbaselined_finding(self):
        with tempfile.TemporaryDirectory(prefix='phase1_new_') as temp:
            dest = Path(temp)
            fixture_tree(dest)
            path = dest / REGISTRY
            data = yaml.safe_load(path.read_text(encoding='utf-8'))
            target = next(row for row in data['actions'] if row['id'] == 'customer.deactivate')
            target['web_markers'] = ['__missing_marker_created_by_test__']
            path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding='utf-8')
            result = cli(dest, '--check')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('NEW customer.deactivate:web:missing_surface', result.stderr)

    def test_10_cli_check_detects_baselined_disappearance(self):
        with tempfile.TemporaryDirectory(prefix='phase1_resolved_') as temp:
            dest = Path(temp)
            fixture_tree(dest)
            path = dest / 'officina/application/local_service.py'
            source = path.read_text(encoding='utf-8')
            anchor = 'clientes_core.listar('
            self.assertIn(anchor, source)
            path.write_text(source.replace(anchor, 'clientes_core.listar_paginado(', 1),
                            encoding='utf-8')
            result = cli(dest, '--check')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('RESOLVED customer.list:gtk_local:read_scope_divergence', result.stderr)

    def test_11_gtk_markers_are_real_and_merge_is_exposed(self):
        app = (ROOT / GTK[0]).read_text(encoding='utf-8')
        dialogs = (ROOT / GTK[1]).read_text(encoding='utf-8')
        for row in document()['actions']:
            with self.subTest(action=row['id']):
                for marker in row['gtk_markers']:
                    self.assertTrue(marker in app or marker in dialogs, marker)
        merge = next(row for row in document()['actions'] if row['id'] == 'customer.merge')
        self.assertTrue(merge['gtk_markers'])

    def test_12_no_runtime_imports_divergence_or_registry(self):
        for section in ('flavors', 'officina'):
            for path in (ROOT / section).rglob('*.py'):
                if path in (ROOT / 'officina/surface/divergence.py',
                            ROOT / 'officina/surface/registry.py'):
                    continue
                tree = ast.parse(path.read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        self.assertTrue(all(
                            not alias.name.startswith('officina.surface.divergence') and
                            alias.name != 'officina.surface.registry'
                            for alias in node.names), path)
                    elif isinstance(node, ast.ImportFrom):
                        self.assertFalse(
                            node.module in ('officina.surface.divergence', 'officina.surface.registry') or
                            (node.module == 'officina.surface' and any(
                                alias.name in ('divergence', 'registry') for alias in node.names)), path)


if __name__ == '__main__':
    unittest.main()
