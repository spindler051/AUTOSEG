"""Legacy OS number migration: dry-run, apply, aliases and next number."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from officina.core import banco
from officina.core import numeracao
from officina.core import numeracao_migracao as migracao
from officina.core import prestadores_ext as ext
class MigracaoNumeracaoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='migracao_num_')
        self.db = Path(self.tmp.name) / 'teste.db'
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        with sqlite3.connect(self.db) as c:
            cliente = c.execute(
                "INSERT INTO clientes(nome,status) VALUES('Cliente','Ativo')"
            ).lastrowid
            for numero, data in (
                ('OS-0001', '2026-11-02 10:00:00'),
                ('OS-0002', '2026-11-03 09:00:00'),
                ('OS-0003', '2026-11-03 10:00:00'),
            ):
                c.execute(
                    "INSERT INTO ordens_servico(numero_os,cliente_id,status,"
                    "data_abertura,criado_em) VALUES(?,?,'Aberta',?,?)",
                    (numero, cliente, data, data))

    def tearDown(self):
        self.tmp.cleanup()

    def _numeros(self):
        with sqlite3.connect(self.db) as c:
            return [r[0] for r in c.execute(
                'SELECT numero_os FROM ordens_servico ORDER BY id')]

    def test_dry_run_does_not_change_database(self):
        antes = self._numeros()
        relatorio = migracao.migrar(self.db, dry_run=True)
        self.assertFalse(relatorio['ja_migrado'])
        self.assertEqual(self._numeros(), antes)

    def test_apply_assigns_digits_and_preserves_alias(self):
        relatorio = migracao.migrar(self.db, backup=True, dry_run=False)
        self.assertEqual(self._numeros(), ['261102001', '261103001', '261103002'])
        self.assertTrue(relatorio['backup'])
        self.assertTrue(Path(relatorio['backup']).is_file())
        with sqlite3.connect(self.db) as c:
            aliases = dict(c.execute(
                'SELECT alias,os_id FROM os_numero_alias'))
            legados = [r[0] for r in c.execute(
                'SELECT numero_os_legado FROM ordens_servico ORDER BY id')]
            ativo = c.execute(
                "SELECT valor FROM numeracao_estado WHERE chave='ativo'").fetchone()[0]
        self.assertEqual(aliases, {'OS-0001': 1, 'OS-0002': 2, 'OS-0003': 3})
        self.assertEqual(legados, ['OS-0001', 'OS-0002', 'OS-0003'])
        self.assertEqual(ativo, '1')
        self.assertFalse(any(numero.startswith('OS') for numero in self._numeros()))

    def test_next_number_after_migration(self):
        migracao.migrar(self.db, backup=False, dry_run=False)
        with sqlite3.connect(self.db) as c:
            c.row_factory = sqlite3.Row
            numero_dia = numeracao.proximo_numero(
                c.cursor(), quando=datetime(2026, 11, 3, 12, tzinfo=timezone.utc))
            numero_hoje = banco.proximo_numero_os(c.cursor())
        self.assertRegex(numero_hoje, r'^\d{9}$')
        self.assertFalse(numero_hoje.startswith('OS'))
        self.assertEqual(numero_dia, '261103003')

    def test_second_run_is_idempotent(self):
        migracao.migrar(self.db, backup=False, dry_run=False)
        antes = self._numeros()
        relatorio = migracao.migrar(self.db, backup=False, dry_run=False)
        self.assertTrue(relatorio['ja_migrado'])
        self.assertEqual(self._numeros(), antes)


if __name__ == '__main__':
    unittest.main(verbosity=2)
