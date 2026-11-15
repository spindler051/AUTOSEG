"""Committed metadata and private staging of actual OS attachments."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import hashlib
import os
import unittest

from PIL import Image
from officina.core import os_effect_outbox as effects
from officina.core import prestadores_ext as ext, fluxo_os, atendimento_os, cadastros_v9
from officina.core.banco import criar_banco


class AttachmentEffectsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix='outbox_files_')
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/'db.sqlite')
        criar_banco(self.db)
        for installer in (ext.instalar,fluxo_os.instalar,atendimento_os.instalar,cadastros_v9.instalar):
            installer(self.db)
        self.pid=ext.cadastrar(self.db,'Worker','photo@invalid.test','test-password')
        with ext.db(self.db) as c:
            cid=c.execute("INSERT INTO clientes(nome,status) VALUES('Sample','Ativo')").lastrowid
            self.oid=c.execute("""INSERT INTO ordens_servico
                (numero_os,cliente_id,status,descricao,data_abertura,criado_em)
                VALUES('OS-171',?,'Aberta','Example','','')""",(cid,)).lastrowid
        ext.assumir(self.db,self.oid,self.pid)
        effects.install(self.db)
        self.notas=Path(self.tmp.name)/'notas'
        self.anexos=Path(self.tmp.name)/'anexos'
        self.p1=patch.object(ext,'NOTAS',self.notas)
        self.p2=patch.object(ext,'ANEXOS',self.anexos)
        self.p1.start();self.p2.start()
        self.addCleanup(self.p1.stop);self.addCleanup(self.p2.stop)

    def _row(self, effect='file'):
        with ext.db(self.db) as c:
            return dict(c.execute('SELECT * FROM os_effect_outbox WHERE effect_type=? ORDER BY id DESC LIMIT 1',
                (effect,)).fetchone())

    def test_invoice_stage_then_publish_once(self):
        content=b'%PDF-1.4\n'+b'A'*200
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            nid=ext.salvar_nota_fiscal(self.db,self.oid,self.pid,'fatura.pdf',content,
                                       connection=c,staged=True)
            document=c.execute('SELECT caminho FROM os_notas_fiscais WHERE id=?',(nid,)).fetchone()
            self.assertFalse(Path(document['caminho']).exists())
            self.assertEqual(c.execute('SELECT COUNT(*) FROM os_eventos WHERE os_id=?',(self.oid,)).fetchone()[0]>=1,True)
        row=self._row()
        self.assertEqual(row['state'],'pending')
        result=effects.publish_file(self.db,row['operation_key'])
        self.assertEqual(result['state'],'done')
        with ext.db(self.db) as c:
            path=Path(c.execute('SELECT caminho FROM os_notas_fiscais WHERE id=?',(nid,)).fetchone()[0])
        self.assertEqual(path.read_bytes(),content)
        self.assertEqual(effects.publish_file(self.db,row['operation_key'])['state'],'done')
        self.assertEqual(len(list(self.notas.glob('*.pdf'))),1)

    def test_reupload_same_invoice_after_removal_has_new_operation(self):
        content=b'%PDF-1.4\n'+b'C'*200
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            first=ext.salvar_nota_fiscal(self.db,self.oid,self.pid,'old.pdf',content,
                                        connection=c,staged=True)
        old=self._row()['operation_key']
        effects.publish_file(self.db,old)
        ext.remover_nota_fiscal(self.db,self.oid,first,self.pid,ator='Worker')
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            second=ext.salvar_nota_fiscal(self.db,self.oid,self.pid,'new.pdf',content,
                                         connection=c,staged=True)
        new=self._row()['operation_key']
        self.assertNotEqual(first,second)
        self.assertNotEqual(old,new)
        self.assertEqual(effects.publish_file(self.db,new)['state'],'done')

    def test_photo_stage_then_publish_and_recovery(self):
        output=BytesIO()
        Image.new('RGB',(5,5),'red').save(output,format='PNG')
        picture=output.getvalue()
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            ext.registrar_imagem_transacao(c,self.oid,self.pid,'foto.png',picture,staged=True)
            doc=c.execute('SELECT caminho FROM os_anexos WHERE os_id=?',(self.oid,)).fetchone()[0]
            self.assertFalse(Path(doc).exists())
        row=self._row()
        claim=effects.claim(self.db,row['operation_key'],now=1000)
        self.assertEqual(claim['state'],'processing')
        # Simulate a dead worker after commit but before linking the file.
        self.assertIn(row['operation_key'],effects.reconcile(self.db,now=1121))
        result=effects.publish_file(self.db,row['operation_key'],now=1121)
        self.assertEqual(result['state'],'done')
        self.assertEqual(Path(doc).read_bytes(),picture)
        self.assertEqual(hashlib.sha256(picture).hexdigest(),result and
            __import__('json').loads(result['result_json'])['sha256'])

    def test_rollback_leaves_no_committed_record_and_orphan_is_cleanable(self):
        content=b'%PDF-1.4\n'+b'B'*200
        with self.assertRaises(ValueError):
            with ext.db(self.db) as c:
                c.execute('BEGIN IMMEDIATE')
                ext.salvar_nota_fiscal(self.db,self.oid,self.pid,'fatura.pdf',content,
                                      connection=c,staged=True)
                raise ValueError('later validation failed')
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM os_notas_fiscais').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM os_effect_outbox').fetchone()[0],0)
        stage=list((self.notas/'.outbox-staging').iterdir())
        self.assertEqual(len(stage),1)
        self.assertEqual(effects.cleanup_orphan_stages(self.db,self.notas,minimum_age=0,
                         now=stage[0].stat().st_mtime+1),1)
        self.assertFalse(stage[0].exists())


if __name__=='__main__':
    unittest.main()
