"""A5d: password changes require a live administrator under the writer lock.

Runs only on a temporary SQLite database and a loopback HTTP server.
Production password hashing and the authorization predicate are not mocked.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest.mock import patch

import yaml

from officina.application.object_policy import Principal
from officina.application.local_service import LocalService
from officina.core import cadastros_v9 as cad, fluxo_os as fluxo
from officina.core import prestadores_ext as ext, portal_negocios as neg
from officina.core.banco import criar_banco
from officina.surface.divergence import analyze, render_report, ROOT


class CustomerPasswordA5dTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='a5d_password_')
        self.addCleanup(tmp.cleanup)
        self.db = str(Path(tmp.name) / 'isolated.sqlite')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        fluxo.instalar(self.db)
        self.admin = ext.cadastrar(self.db, 'A5d Administrator',
                                   'a5d-admin@example.invalid', 'Pass12345678')
        self.employee = ext.cadastrar(self.db, 'A5d Employee',
                                      'a5d-employee@example.invalid', 'Pass12345678')
        cad.definir_admin(self.db, self.admin, True)
        self.admin_actor = Principal(self.admin, 'admin',
                                     organization_id='autoseg', provider_id=self.admin)
        self.employee_actor = Principal(self.employee, 'employee',
                                        organization_id='autoseg', provider_id=self.employee)
        with ext.db(self.db) as c:
            self.customer = c.execute('''INSERT INTO clientes(nome,tipo_pessoa,status)
                VALUES('A5d Test Client','Física','Ativo')''').lastrowid
            neg.criar_auditoria(c)

    def _snapshot(self):
        with ext.db(self.db) as c:
            return (
                [tuple(row) for row in c.execute(
                    'SELECT cliente_id,senha_hash,ativo,alterado_em FROM cliente_acessos ORDER BY cliente_id')],
                [tuple(row) for row in c.execute(
                    'SELECT * FROM v9_historico_clientes ORDER BY id')],
                [tuple(row) for row in c.execute('SELECT * FROM portal_auditoria ORDER BY id')],
            )

    def _denied_without_mutation(self, principal):
        before = self._snapshot()
        with self.assertRaises(PermissionError):
            fluxo.definir_senha_cliente(self.db, self.customer,
                                        'SenhaNova12345', principal=principal)
        self.assertEqual(before, self._snapshot())

    def test_admin_updates_password_hash_without_changing_existing_audit_behavior(self):
        primeira = fluxo.definir_senha_cliente(self.db, self.customer,
                                               'SenhaAnterior123', principal=self.admin_actor)
        self.assertEqual(primeira, 'SenhaAnterior123')
        before = self._snapshot()
        segunda = fluxo.definir_senha_cliente(self.db, self.customer,
                                              'SenhaNova12345', principal=self.admin_actor)
        after = self._snapshot()
        self.assertEqual(segunda, 'SenhaNova12345')
        self.assertEqual(len(after[0]), 1)
        self.assertNotEqual(after[0][0][1], before[0][0][1])
        self.assertTrue(ext.verificar_senha('SenhaNova12345', after[0][0][1]))
        # No new audit event was emitted by this existing writer before A5d.
        self.assertEqual(after[1:], before[1:])

    def test_employee_cannot_change_password(self):
        self._denied_without_mutation(self.employee_actor)

    def test_missing_principal_is_denied(self):
        self._denied_without_mutation(None)

    def test_inactive_principal_is_denied(self):
        actor = Principal(self.admin, 'admin', organization_id='autoseg',
                          provider_id=self.admin, active=False)
        self._denied_without_mutation(actor)

    def test_forged_admin_role_does_not_override_database(self):
        actor = Principal(self.employee, 'admin', organization_id='autoseg',
                          provider_id=self.employee)
        self._denied_without_mutation(actor)

    def test_revoked_admin_is_denied(self):
        cad.definir_admin(self.db, self.admin, False)
        self._denied_without_mutation(self.admin_actor)

    def test_inactive_customer_validation_still_applies(self):
        with ext.db(self.db) as c:
            c.execute("UPDATE clientes SET status='Inativo' WHERE id=?", (self.customer,))
        before = self._snapshot()
        with self.assertRaises(ValueError):
            fluxo.definir_senha_cliente(self.db, self.customer,
                                        'SenhaNova12345', principal=self.admin_actor)
        self.assertEqual(before, self._snapshot())

    def test_local_service_rejects_employee(self):
        before = self._snapshot()
        with self.assertRaises(PermissionError):
            LocalService(self.db).definir_senha_cliente(
                self.customer, 'SenhaNova12345', principal=self.employee_actor)
        self.assertEqual(before, self._snapshot())

    @staticmethod
    def _http(browser, base, url, data=None):
        payload = urllib.parse.urlencode(data).encode() if data is not None else None
        request = urllib.request.Request(base + url, data=payload)
        try:
            with browser.open(request, timeout=20) as reply:
                return reply.status, reply.read().decode('utf-8', 'replace')
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode('utf-8', 'replace')

    def test_web_non_admin_denied_and_admin_succeeds(self):
        from flavors.autoseg.modules.portal_prestador import PortalPrestador
        # Accounts are legacy test fixtures; exercise the operational fallback.
        with patch.dict(os.environ, {'AUTOSEG_UNIFIED_LOGIN': '0'}):
            portal = PortalPrestador(self.db, '127.0.0.1', 0)
            portal.iniciar()
            self.addCleanup(portal.parar)
            base = f'http://127.0.0.1:{portal.porta}'
            def browser(email):
                b = urllib.request.build_opener(
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                status, _ = self._http(b, base, '/login',
                                       {'email': email, 'senha':'Pass12345678'})
                self.assertEqual(status, 200)
                return b
            employee = browser('a5d-employee@example.invalid')
            admin = browser('a5d-admin@example.invalid')
            endpoint = f'/clientes/{self.customer}/salvar'
            form = {'nome':'A5d Test Client', 'tipo_pessoa':'Física',
                    'status':'Ativo','senha_cliente':'SenhaWebA5d12345',
                    'confirmar_senha_cliente':'SenhaWebA5d12345'}
            employee_page = self._http(employee, base, '/clientes/novo')[1]
            token = re.search(r'name="csrf" value="([^"]+)"', employee_page)
            self.assertIsNotNone(token)
            original = self._snapshot()
            status, _ = self._http(employee, base, endpoint,
                                   dict(form, csrf=token.group(1)))
            self.assertEqual(status, 403)
            self.assertEqual(original, self._snapshot())
            admin_page = self._http(admin, base, f'/clientes/{self.customer}')[1]
            token = re.search(r'name="csrf" value="([^"]+)"', admin_page)
            self.assertIsNotNone(token)
            status, _ = self._http(admin, base, endpoint,
                                   dict(form, csrf=token.group(1)))
            self.assertEqual(status, 200)
            with ext.db(self.db) as c:
                row = c.execute('SELECT senha_hash FROM cliente_acessos WHERE cliente_id=?',
                                (self.customer,)).fetchone()
            self.assertIsNotNone(row)
            self.assertTrue(ext.verificar_senha('SenhaWebA5d12345', row['senha_hash']))


class HighBaselineCannotBeSilencedTest(unittest.TestCase):
    """CLI checks use a separate fixture, never modifying tracked source files."""
    def _copy_fixture(self, root: Path):
        registry = yaml.safe_load((ROOT / 'flavors/autoseg/config/surface_registry.yaml')
                                  .read_text(encoding='utf-8'))
        paths = {
            'flavors/autoseg/config/surface_registry.yaml',
            'flavors/autoseg/config/policy.yaml',
            'flavors/autoseg/config/surface_divergence_baseline.json',
            'docs/planning/SURFACE_DIVERGENCE_REPORT.md',
            'flavors/autoseg/modules/portal_prestador.py',
            'flavors/autoseg/modules/api_desktop.py',
            'flavors/autoseg/modules/gtk_app.py',
            'flavors/autoseg/modules/gtk_dialogos.py',
            'officina/application/local_service.py',
        }
        for action in registry['actions']:
            paths.add(action['service'].rsplit('.', 1)[0].replace('.', '/') + '.py')
            paths.update(action['negative_tests'])
        for relative in paths:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    @staticmethod
    def _regress_writer(root: Path):
        path = root / 'officina/core/fluxo_os.py'
        source = path.read_text(encoding='utf-8')
        marker = 'require_admin_locked(c, principal)'
        if marker not in source:
            raise AssertionError('Password guard disappeared from project source')
        path.write_text(source.replace(marker, 'pass  # synthetic removal', 1),
                        encoding='utf-8')

    @staticmethod
    def _cli(root: Path, command: str):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/surface_divergence.py'),
                               command, '--root', str(root)],
                              capture_output=True, text=True, timeout=30, check=False)

    def test_update_baseline_refuses_high_finding(self):
        with tempfile.TemporaryDirectory(prefix='a5d_cli_update_') as td:
            root = Path(td)
            self._copy_fixture(root)
            self._regress_writer(root)
            baseline = root / 'flavors/autoseg/config/surface_divergence_baseline.json'
            before = baseline.read_bytes()
            result = self._cli(root, '--update-baseline')
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('HIGH findings cannot be baselined', result.stderr)
            self.assertEqual(baseline.read_bytes(), before)

    def test_check_rejects_hand_edited_high_baseline(self):
        with tempfile.TemporaryDirectory(prefix='a5d_cli_check_') as td:
            root = Path(td)
            self._copy_fixture(root)
            self._regress_writer(root)
            findings = analyze(root)
            self.assertTrue(any(item.severity == 'high' for item in findings))
            file = root / 'flavors/autoseg/config/surface_divergence_baseline.json'
            old = json.loads(file.read_text(encoding='utf-8'))
            known = {row['id']: row['justification'] for row in old['accepted']}
            manual = {'version': 1, 'accepted': [
                {'id': finding.id, 'justification': known.get(
                    finding.id, 'Intentionally forged high acceptance for regression test')}
                for finding in sorted(findings, key=lambda x: x.id)
            ]}
            file.write_text(json.dumps(manual, indent=2) + '\n', encoding='utf-8')
            (root / 'docs/planning/SURFACE_DIVERGENCE_REPORT.md').write_text(
                render_report(findings, manual), encoding='utf-8')
            result = self._cli(root, '--check')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('HIGH FINDINGS NOT BASELINEABLE', result.stderr)


if __name__ == '__main__':
    unittest.main()
