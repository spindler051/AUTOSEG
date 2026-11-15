"""Production authorization gate for the OS effect outbox installer.

The migration is additive and stays opt-in: a non-DEV database needs the
explicit flag and a fresh verified backup, never an environment default.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from officina.core import os_effect_outbox as outbox
from officina.core.banco import criar_banco
from scripts.autoseg import install_os_effect_outbox as installer


class OutboxProductionInstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='outbox_prod_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'dados.db')
        criar_banco(self.db)

    def _run(self, *args, dev=False):
        env = {'AUTOSEG_DEV': '1'} if dev else {}
        with patch.dict(os.environ, env, clear=False):
            if not dev:
                os.environ.pop('AUTOSEG_DEV', None)
            return installer.main(list(args))

    def _installed(self, path=None):
        with sqlite3.connect(path or self.db) as connection:
            return connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='os_effect_outbox'").fetchone() is not None

    def test_non_dev_is_refused_without_the_flag(self):
        with self.assertRaises(SystemExit):
            self._run('--database', self.db, '--status')
        self.assertFalse(self._installed())

    def test_production_install_requires_a_backup(self):
        with self.assertRaises(SystemExit):
            self._run('--database', self.db, '--allow-production')
        self.assertFalse(self._installed())

    def test_production_install_creates_table_and_verified_backup(self):
        backup = str(Path(self.tmp.name) / 'pre-outbox.db')
        self.assertEqual(self._run('--database', self.db, '--allow-production',
                                   '--backup', backup), 0)
        self.assertTrue(self._installed())
        self.assertTrue(Path(backup).is_file())
        with sqlite3.connect(backup) as connection:
            self.assertEqual(connection.execute('PRAGMA quick_check').fetchone()[0], 'ok')
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(
                connection.execute('SELECT COUNT(*) FROM os_effect_outbox').fetchone()[0], 0)

    def test_production_status_needs_no_backup(self):
        backup = str(Path(self.tmp.name) / 'pre-outbox.db')
        self._run('--database', self.db, '--allow-production', '--backup', backup)
        self.assertEqual(self._run('--database', self.db, '--allow-production',
                                   '--status'), 0)

    def test_dev_install_gate_is_unchanged(self):
        self.assertEqual(self._run('--database', self.db, '--backup',
                                   str(Path(self.tmp.name) / 'dev.db'), dev=True), 0)
        self.assertTrue(self._installed())

    def test_production_rollback_requires_a_backup(self):
        self._run('--database', self.db, '--allow-production',
                  '--backup', str(Path(self.tmp.name) / 'install.db'))
        with self.assertRaises(SystemExit):
            self._run('--database', self.db, '--allow-production', '--rollback')
        self.assertTrue(self._installed())


if __name__ == '__main__':
    unittest.main()
