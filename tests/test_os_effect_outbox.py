"""DEV-only SQLite outbox: commit, lease, restart and uncertain delivery."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import os
import sqlite3
import unittest

from officina.core import os_effect_outbox as outbox
from officina.core import prestadores_ext as ext

PDF = b'%PDF-1.4\n' + b'x' * 200


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix='outbox_test_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'database.db')
        self.root = Path(self.tmp.name) / 'pdf'
        with sqlite3.connect(self.db) as c:
            c.executescript('''
                CREATE TABLE clients_unchanged(id INTEGER PRIMARY KEY, name TEXT);
                INSERT INTO clients_unchanged VALUES(1,'original');
                CREATE TABLE clientes(id INTEGER PRIMARY KEY,email TEXT);
                INSERT INTO clientes VALUES(1,'sample@example.invalid');
                CREATE TABLE ordens_servico(id INTEGER PRIMARY KEY,numero_os TEXT,
                    status TEXT,cliente_id INTEGER);
                INSERT INTO ordens_servico VALUES(7,'OS-7','Concluída',1);
                CREATE TABLE os_documentos(id INTEGER PRIMARY KEY,os_id INTEGER,
                    tipo TEXT,versao INTEGER,caminho TEXT,sha256 TEXT,publicado_em TEXT,
                    UNIQUE(os_id,tipo,versao));
                CREATE TABLE os_entregas(os_id INTEGER PRIMARY KEY,
                    documento_id INTEGER,destinatario TEXT,email_status TEXT,
                    nf_status TEXT,atualizado_em TEXT);
            ''')
        outbox.install(self.db)

    def _enqueue(self, kind='pdf', revision='rev1', action='publish'):
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            if kind == 'pdf':
                return outbox.enqueue_pdf(c, 7, revision, action)
            if kind == 'email':
                return outbox.enqueue_email(c, 7, revision, action)
            return outbox.enqueue_file(c, 7, revision, action, 1, 'a' * 64)

    def test_schema_is_additive_and_install_idempotent(self):
        with sqlite3.connect(self.db) as c:
            before = c.execute('SELECT * FROM clients_unchanged').fetchall()
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        outbox.install(self.db)
        with sqlite3.connect(self.db) as c:
            after = c.execute('SELECT * FROM clients_unchanged').fetchall()
            tables_after = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertEqual(before, after)
        self.assertEqual(tables_after - tables, set())
        self.assertEqual(outbox.get(self.db, 'unknown'), None)

    def test_requires_transaction_and_no_unmigrated_access(self):
        path = str(Path(self.tmp.name) / 'not_installed.db')
        with sqlite3.connect(path) as c:
            c.execute('CREATE TABLE os_documentos(os_id INTEGER,tipo TEXT,versao INTEGER)')
        with ext.db(path) as c:
            with self.assertRaises(RuntimeError):
                outbox.enqueue_pdf(c, 7, 'one')
            c.execute('BEGIN IMMEDIATE')
            with self.assertRaises(outbox.OutboxUnavailable):
                outbox.enqueue_pdf(c, 7, 'one')

    def test_commit_and_rollback_of_intention(self):
        key = outbox.operation_key(7, 'reversed', 'publish', 'pdf')
        with self.assertRaises(ValueError):
            with ext.db(self.db) as c:
                c.execute('BEGIN IMMEDIATE')
                outbox.enqueue_pdf(c, 7, 'reversed')
                raise ValueError('Domain writer rejected')
        self.assertIsNone(outbox.get(self.db, key))
        row = self._enqueue()
        self.assertEqual(outbox.get(self.db, row['operation_key'])['state'], 'pending')

    def test_key_deduplicates_revision_and_reserves_next_pdf_version(self):
        first = self._enqueue()
        repeat = self._enqueue()
        other = self._enqueue(revision='rev2')
        self.assertEqual(first['operation_key'], repeat['operation_key'])
        self.assertEqual((first['version_reserved'], other['version_reserved']), (1, 2))
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM os_effect_outbox').fetchone()[0], 2)

    def test_no_sensitive_payload_fields(self):
        with self.assertRaises(ValueError):
            with ext.db(self.db) as c:
                c.execute('BEGIN IMMEDIATE')
                outbox._queue(c, 7, 'rev', 'mail', 'email', payload={'recipient': 'hidden@example.invalid'})
        self._enqueue('email')
        with sqlite3.connect(self.db) as c:
            all_payloads = str(c.execute('SELECT payload_json FROM os_effect_outbox').fetchall())
        self.assertNotIn('hidden@example.invalid', all_payloads)

    def test_two_workers_claim_once(self):
        row = self._enqueue()
        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(executor.map(lambda _: outbox.claim(self.db, row['operation_key']), range(2)))
        self.assertEqual(sum(bool(x) for x in claims), 1)
        self.assertEqual(outbox.get(self.db, row['operation_key'])['attempts'], 1)

    def test_pdf_recovers_after_crash_without_duplicate_version(self):
        row = self._enqueue()
        source = Path(self.tmp.name) / 'source.pdf'
        source.write_bytes(PDF)
        with patch.object(ext, 'RELATORIOS', self.root):
            first = outbox.claim(self.db, row['operation_key'], now=1000)
            self.assertIsNotNone(first)
            self.root.joinpath('publicados').mkdir(parents=True)
            published = self.root / 'publicados' / 'OS-7_relatorio_v1.pdf'
            published.write_bytes(PDF)
            self.assertEqual(outbox.reconcile(self.db, now=1121, lease_seconds=120), [row['operation_key']])
            result = outbox.publish_pdf(self.db, row['operation_key'], now=1121,
                                         generate=lambda *_: self.fail('Must reuse published file'))
        self.assertEqual(result['state'], 'done')
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM os_documentos').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT versao FROM os_documentos').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT sha256 FROM os_documentos').fetchone()[0], hashlib.sha256(PDF).hexdigest())

    def test_pdf_generation_failure_can_retry_and_reuse_reserved_version(self):
        row = self._enqueue()
        source = Path(self.tmp.name) / 'source.pdf'
        source.write_bytes(PDF)
        with patch.object(ext, 'RELATORIOS', self.root):
            with self.assertRaises(FileNotFoundError):
                outbox.publish_pdf(self.db, row['operation_key'], generate=lambda *_: Path('/not/a/pdf'))
            self.assertEqual(outbox.get(self.db, row['operation_key'])['state'], 'failed')
            result = outbox.publish_pdf(self.db, row['operation_key'], generate=lambda *_: source)
            self.assertEqual(result['state'], 'done')
            repeat = outbox.publish_pdf(self.db, row['operation_key'], generate=lambda *_: self.fail('Duplicate PDF'))
        self.assertEqual(repeat['state'], 'done')
        self.assertEqual(outbox.get(self.db, row['operation_key'])['attempts'], 2)

    def test_email_uncertain_never_retries(self):
        row = self._enqueue('email')
        sends = []
        def sender(os_id, key):
            sends.append((os_id, key))
            raise RuntimeError('Provider timed out after send')
        with self.assertRaises(outbox.DispatchUncertain):
            outbox.deliver_email(self.db, row['operation_key'], sender)
        self.assertEqual(outbox.get(self.db, row['operation_key'])['state'], 'unknown')
        outbox.deliver_email(self.db, row['operation_key'], sender)
        self.assertEqual(len(sends), 1)
        self.assertNotIn(row['operation_key'], outbox.reconcile(self.db, now=10000000))

    def test_email_expired_processing_becomes_unknown_on_restart(self):
        row = self._enqueue('email')
        outbox.claim(self.db, row['operation_key'], now=1000)
        self.assertEqual(outbox.reconcile(self.db, now=1121), [])
        self.assertEqual(outbox.get(self.db, row['operation_key'])['state'], 'unknown')

    def test_email_confirmed_pre_dispatch_failure_can_retry(self):
        row = self._enqueue('email')
        with self.assertRaises(outbox.PreDispatchError):
            outbox.deliver_email(self.db, row['operation_key'],
                                 lambda *_: (_ for _ in ()).throw(outbox.PreDispatchError('Unavailable')))
        self.assertEqual(outbox.get(self.db, row['operation_key'])['state'], 'failed')
        self.assertEqual(outbox.deliver_email(self.db, row['operation_key'],
                          lambda *_: 'provider-id')['state'], 'done')

    def test_manual_resend_requires_acknowledgement_and_new_revision(self):
        first = self._enqueue('email')
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            with self.assertRaises(PermissionError):
                outbox.manual_email_retry(c, 7, 'rev2', 'resend', duplicate_acknowledged=False)
            retried = outbox.manual_email_retry(c, 7, 'rev2', 'resend', duplicate_acknowledged=True)
        self.assertNotEqual(first['operation_key'], retried['operation_key'])

    def test_backup_verified_and_downgrade_is_additive(self):
        backup = Path(self.tmp.name) / 'backup.db'
        outbox.backup_database(self.db, backup)
        with sqlite3.connect(backup) as c:
            self.assertEqual(c.execute('PRAGMA quick_check').fetchone()[0], 'ok')
        with sqlite3.connect(self.db) as c:
            c.execute('DROP TABLE os_effect_outbox')
            self.assertEqual(c.execute('SELECT name FROM clients_unchanged').fetchone()[0], 'original')


if __name__ == '__main__':
    unittest.main()
