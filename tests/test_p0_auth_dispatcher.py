"""Operational recovery, proof-of-content publication and DEV-only rollback."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from officina.core import os_effect_outbox as effects, prestadores_ext as ext
from scripts.autoseg import dispatch_os_effect_outbox as worker
from scripts.autoseg import install_os_effect_outbox as migrate


class DispatcherAndRollbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix='outbox_worker_')
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/'db.sqlite')
        with ext.db(self.db) as c:
            c.executescript('''CREATE TABLE ordens_servico(id INTEGER PRIMARY KEY,
                numero_os TEXT,status TEXT,cliente_id INTEGER);
                INSERT INTO ordens_servico VALUES(7,'OS-777','Concluída',1);
                CREATE TABLE os_documentos(id INTEGER PRIMARY KEY,os_id INTEGER,
                  tipo TEXT,versao INTEGER,caminho TEXT,sha256 TEXT,publicado_em TEXT);
                CREATE TABLE clientes(id INTEGER PRIMARY KEY,email TEXT);
                INSERT INTO clientes VALUES(1,'test@example.invalid');
                CREATE TABLE os_entregas(os_id INTEGER PRIMARY KEY,documento_id INTEGER,
                   destinatario TEXT,email_status TEXT,nf_status TEXT,atualizado_em TEXT);
                CREATE TABLE produtividade_email(os_id INTEGER PRIMARY KEY,
                   destinatarios_json TEXT,status TEXT,message_id TEXT,erro TEXT,
                   atualizado_em TEXT);''')
        effects.install(self.db)

    def test_status_dryrun_and_safe_rollback(self):
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            effect=effects.enqueue_email(c,7,'one','send',recipient_refs=['cliente'])
        self.assertEqual(worker.summary(self.db)['states'][0]['count'],1)
        before=effects.get(self.db,effect['operation_key'])
        self.assertEqual(worker.run_once(self.db,dry_run=True)[0]['state'],'pending')
        self.assertEqual(effects.get(self.db,effect['operation_key']),before)
        with patch.dict(os.environ,{'AUTOSEG_DEV':'1'}):
            with self.assertRaises(SystemExit):
                migrate.main(['--database',self.db,'--rollback',
                              '--backup',str(Path(self.tmp.name)/'denied.db')])
        self.assertTrue(effects.get(self.db,effect['operation_key']))
        with ext.db(self.db) as c:
            c.execute("UPDATE os_effect_outbox SET state='done' WHERE operation_key=?",
                      (effect['operation_key'],))
        backup=str(Path(self.tmp.name)/'accepted.db')
        with patch.dict(os.environ,{'AUTOSEG_DEV':'1'}):
            self.assertEqual(migrate.main(['--database',self.db,'--rollback','--backup',backup]),0)
        with ext.db(self.db) as c:
            self.assertFalse(effects.installed(c))
            self.assertTrue(c.execute('SELECT 1 FROM ordens_servico WHERE id=7').fetchone())
        self.assertTrue(Path(backup).is_file())

    def test_orphan_pdf_must_match_generated_digest(self):
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            effect=effects.enqueue_pdf(c,7,'pdfrev')
        root=Path(self.tmp.name)/'reports'
        target=root/'publicados'/'OS-777_relatorio_v1.pdf'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'%PDF-1.4\n'+b'wrong'*40)
        candidate=Path(self.tmp.name)/'expected.pdf'
        candidate.write_bytes(b'%PDF-1.4\n'+b'right'*40)
        with patch.object(ext,'RELATORIOS',root):
            with self.assertRaisesRegex(RuntimeError,'PDFConflict'):
                effects.publish_pdf(self.db,effect['operation_key'],generate=lambda *_:candidate)
        self.assertEqual(target.read_bytes(),b'%PDF-1.4\n'+b'wrong'*40)
        self.assertEqual(effects.get(self.db,effect['operation_key'])['state'],'failed')
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM os_documentos').fetchone()[0],0)

    def test_processing_expired_email_stays_unknown_and_updates_projections(self):
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute("INSERT INTO produtividade_email VALUES(7,'[\"cliente\"]','pendente',NULL,'','')")
            c.execute("INSERT INTO os_entregas VALUES(7,1,'original@example.invalid','aguardando_api','','')")
            effect=effects.enqueue_email(c,7,'emailrev',recipient_refs=['cliente'])
        claimed=effects.claim(self.db,effect['operation_key'],now=100)
        self.assertTrue(claimed)
        self.assertEqual(effects.reconcile(self.db,now=300),[])
        self.assertEqual(effects.get(self.db,effect['operation_key'])['state'],'unknown')
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM produtividade_email').fetchone()[0],'unknown')
            self.assertEqual(c.execute('SELECT email_status FROM os_entregas').fetchone()[0],'unknown')


if __name__=='__main__':
    unittest.main()
