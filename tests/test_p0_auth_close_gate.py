"""Single-transaction attachment commands, durable operations and email projections."""
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from flavors.autoseg.modules import os_commands, gmail_service
from officina.core import (prestadores_ext as ext, fluxo_os, atendimento_os,
                          cadastros_v9, produtividade_os, os_effect_outbox as effects)
from officina.core.banco import criar_banco


class CloseGateHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix='auth_close_')
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/'db.sqlite')
        criar_banco(self.db)
        for install in (ext.instalar,fluxo_os.instalar,atendimento_os.instalar,
                        cadastros_v9.instalar,produtividade_os.instalar):
            install(self.db)
        self.pid=ext.cadastrar(self.db,'Worker','worker@example.invalid','valid-password')
        self.admin=ext.cadastrar(self.db,'Admin','admin@example.invalid','valid-password')
        cadastros_v9.definir_admin(self.db,self.admin,True)
        with ext.db(self.db) as c:
            cid=c.execute("INSERT INTO clientes(nome,status,email) VALUES('Example','Ativo','example@example.invalid')").lastrowid
            self.oid=c.execute('''INSERT INTO ordens_servico
                (numero_os,cliente_id,status,descricao,data_abertura,criado_em)
                VALUES('OS-400',?,'Aberta','Example','','')''',(cid,)).lastrowid
        ext.assumir(self.db,self.oid,self.pid)
        effects.install(self.db)
        self.notas=Path(self.tmp.name)/'notas'
        self.anexos=Path(self.tmp.name)/'anexos'
        for name,value in (('NOTAS',self.notas),('ANEXOS',self.anexos)):
            patcher=patch.object(ext,name,value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.ui=Mock()
        self.ui.redir.return_value='redirect'
        self.session={'pid':self.pid,'nome':'Worker'}
        self.principal=os_commands._provider_context(self.db,self.session)

    def photo(self):
        stream=BytesIO()
        Image.new('RGB',(7,5),'blue').save(stream,format='PNG')
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            ext.registrar_imagem_transacao(c,self.oid,self.pid,'picture.png',stream.getvalue(),staged=True)
        with ext.db(self.db) as c:
            row=c.execute('SELECT id,caminho FROM os_anexos WHERE os_id=? ORDER BY id DESC',
                          (self.oid,)).fetchone()
        with ext.db(self.db) as c:
            key=c.execute("SELECT operation_key FROM os_effect_outbox WHERE action='attachment-add' ORDER BY id DESC").fetchone()[0]
        effects.publish_file(self.db,key)
        return row['id'],Path(row['caminho'])

    def invoice(self):
        data=b'%PDF-1.4\n'+b'Q'*180
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            nid=ext.salvar_nota_fiscal(self.db,self.oid,self.pid,'sample.pdf',data,
                                       connection=c,staged=True)
            row=c.execute('SELECT caminho FROM os_notas_fiscais WHERE id=?',(nid,)).fetchone()
            key=c.execute("SELECT operation_key FROM os_effect_outbox WHERE action LIKE 'invoice-%' ORDER BY id DESC").fetchone()[0]
        effects.publish_file(self.db,key)
        return nid,Path(row['caminho'])

    def command(self,route,payload=None):
        return os_commands.execute_http(self.ui,self.db,self.principal,
            f'/os/{self.oid}/{route}',payload or {},self.session)

    def test_move_publish_rotate_and_remove_use_shared_writers(self):
        first,path=self.photo()
        second,_=self.photo()
        for flag in ('0','1'):
            with self.subTest(flag=flag),patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                self.command(f'anexo/{first}/mover',{'direcao':'down'})
                self.command(f'anexo/{first}/publico',{'visivel':'1','legenda':'Approved'})
        old=hashlib.sha256(path.read_bytes()).hexdigest()
        self.command(f'anexo/{first}/girar')
        self.assertTrue(path.is_file())
        self.assertNotEqual(old,hashlib.sha256(path.read_bytes()).hexdigest())
        with ext.db(self.db) as c:
            image=c.execute('SELECT sha256 FROM os_anexos WHERE id=?',(first,)).fetchone()
            self.assertEqual(image['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.command(f'anexo/{first}/remover')
        self.assertFalse(path.exists())
        with ext.db(self.db) as c:
            self.assertIsNone(c.execute('SELECT id FROM os_anexos WHERE id=?',(first,)).fetchone())
            self.assertEqual(c.execute("SELECT state FROM os_effect_outbox WHERE action='attachment-remove'").fetchone()[0],'done')

    def test_invoice_removal_after_commit(self):
        nid,path=self.invoice()
        self.command(f'nota-fiscal/{nid}/remover')
        self.assertFalse(path.exists())
        with ext.db(self.db) as c:
            self.assertIsNone(c.execute('SELECT id FROM os_notas_fiscais WHERE id=?',(nid,)).fetchone())
            self.assertEqual(c.execute("SELECT state FROM os_effect_outbox WHERE action='invoice-remove'").fetchone()[0],'done')

    def test_rollback_restores_quarantine_and_metadata(self):
        aid,path=self.photo()
        with patch.object(ext,'remover_anexo',side_effect=ValueError('Injected failure')):
            with self.assertRaises(ValueError):
                self.command(f'anexo/{aid}/remover')
        self.assertTrue(path.exists())
        with ext.db(self.db) as c:
            self.assertTrue(c.execute('SELECT 1 FROM os_anexos WHERE id=?',(aid,)).fetchone())
            self.assertEqual(c.execute("SELECT COUNT(*) FROM os_effect_outbox WHERE action='attachment-remove'").fetchone()[0],0)

    def test_post_commit_crash_removal_reconciles(self):
        aid,path=self.photo()
        original=effects.publish_file
        def crash(*_args,**_kw): raise RuntimeError('Worker crashed after DB commit')
        with patch.object(effects,'publish_file',side_effect=crash):
            with self.assertRaises(RuntimeError): self.command(f'anexo/{aid}/remover')
        self.assertFalse(path.exists())
        with ext.db(self.db) as c:
            record=c.execute("SELECT operation_key,state FROM os_effect_outbox WHERE action='attachment-remove'").fetchone()
            self.assertEqual(record['state'],'pending')
        self.assertEqual(original(self.db,record['operation_key'])['state'],'done')
        self.assertEqual(original(self.db,record['operation_key'])['state'],'done')

    def test_cancellation_between_preflight_and_writer_leaves_attachment_intact(self):
        aid,path=self.photo()
        for flag in ('0','1'):
            with self.subTest(flag=flag):
                with ext.db(self.db) as c:
                    c.execute("UPDATE ordens_servico SET status='Aberta',arquivada=0 WHERE id=?",(self.oid,))
                action='remove_attachment'
                actual=os_commands.WRITERS[action]
                def racing(*args,**kw):
                    with ext.db(self.db) as c:
                        c.execute("UPDATE ordens_servico SET arquivada=1 WHERE id=?",(self.oid,))
                    return actual(*args,**kw)
                with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}), \
                     patch.dict(os_commands.WRITERS,{action:racing}), \
                     self.assertRaises(PermissionError):
                    self.command(f'anexo/{aid}/remover')
                self.assertTrue(path.is_file())
                with ext.db(self.db) as c:
                    self.assertTrue(c.execute('SELECT 1 FROM os_anexos WHERE id=?',(aid,)).fetchone())
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM os_effect_outbox WHERE action='attachment-remove'").fetchone()[0],0)

    def test_mid_writer_event_error_rolls_back_and_restores_file(self):
        aid,path=self.photo()
        with patch.object(ext,'evento',side_effect=RuntimeError('event writer failed')):
            with self.assertRaises(RuntimeError):
                self.command(f'anexo/{aid}/remover')
        self.assertTrue(path.is_file())
        with ext.db(self.db) as c:
            self.assertTrue(c.execute('SELECT 1 FROM os_anexos WHERE id=?',(aid,)).fetchone())
            self.assertEqual(c.execute("SELECT COUNT(*) FROM os_effect_outbox WHERE action='attachment-remove'").fetchone()[0],0)

    def test_rotation_is_recoverable_after_commit_before_file_promotion(self):
        aid,path=self.photo()
        original=path.read_bytes()
        with patch.object(effects,'publish_file',side_effect=RuntimeError('crash before promotion')):
            with self.assertRaises(RuntimeError):
                self.command(f'anexo/{aid}/girar')
        self.assertEqual(path.read_bytes(),original)
        with ext.db(self.db) as c:
            row=c.execute("SELECT operation_key FROM os_effect_outbox WHERE action='attachment-rotate'").fetchone()
        self.assertTrue(row)
        self.assertEqual(effects.publish_file(self.db,row['operation_key'])['state'],'done')
        self.assertNotEqual(path.read_bytes(),original)
        self.assertEqual(effects.publish_file(self.db,row['operation_key'])['state'],'done')

    def test_uncommitted_quarantine_restored_after_restart(self):
        aid,path=self.photo()
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        operation='a'*64
        trash=effects.quarantine_file(self.anexos,path,operation,
                                       source_id=aid,source_sha256=digest)
        self.assertFalse(path.exists())
        self.assertTrue(trash.exists())
        self.assertEqual(effects.cleanup_orphan_trash(self.db,self.anexos,
            minimum_age=0,now=trash.stat().st_mtime+2),1)
        self.assertTrue(path.exists())
        self.assertFalse(trash.exists())

    def test_manual_resend_requires_acknowledgment_and_unique_key(self):
        with ext.db(self.db) as c:
            c.execute("INSERT INTO os_documentos(os_id,tipo,versao,caminho,sha256,publicado_em) VALUES(?,'relatorio_pdf',1,'sample','digest','')",(self.oid,))
        self.assertRaises(ValueError,self.command,'reenviar-email',{'reenviar_operacao':'a'*20})
        self.assertRaises(ValueError,self.command,'reenviar-email',{'confirmar_duplicata':'1'})
        data={'reenviar_operacao':'a'*20,'confirmar_duplicata':'1',
              'destinatario_sel[]':['cliente']}
        with patch.object(effects,'deliver_email',return_value=None) as delivery:
            self.command('reenviar-email',data)
            self.command('reenviar-email',data)
            self.assertEqual(delivery.call_count,2)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM os_effect_outbox WHERE action='send-manual'").fetchone()[0],1)
            stored=c.execute('SELECT destinatarios_json FROM produtividade_email WHERE os_id=?',
                             (self.oid,)).fetchone()[0]
        self.assertEqual(json.loads(stored),['example@example.invalid'])
        with ext.db(self.db) as c:
            payload=c.execute('SELECT payload_json FROM os_effect_outbox WHERE action=?',
                              ('send-manual',)).fetchone()[0]
        self.assertEqual(json.loads(payload)['recipient_refs'],['cliente'])
        self.assertNotIn('@',payload)


    def test_publish_attachment_on_closed_os(self):
        aid,_=self.photo()
        for state in ('Concluída','Pendente','Cancelada'):
            for flag in ('0','1'):
                with self.subTest(state=state,flag=flag),patch.dict(
                        os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                    with ext.db(self.db) as c:
                        c.execute('UPDATE ordens_servico SET status=?,arquivada=0 WHERE id=?',
                                  (state,self.oid))
                    self.command(f'anexo/{aid}/publico',{'visivel':'1','legenda':'Authorized'})
                    with ext.db(self.db) as c:
                        row=c.execute('SELECT visivel,legenda FROM v9_anexos_visiveis '
                            'WHERE anexo_id=?',(aid,)).fetchone()
                        event=c.execute("SELECT COUNT(*) FROM os_eventos WHERE os_id=? "
                            "AND acao='Evidência para o cliente'",(self.oid,)).fetchone()[0]
                    self.assertEqual(tuple(row),(1,'Authorized'))
                    self.assertGreaterEqual(event,1)
                    with ext.db(self.db) as c:
                        c.execute('UPDATE ordens_servico SET arquivada=1 WHERE id=?',
                                  (self.oid,))
                    with self.assertRaises(PermissionError):
                        self.command(f'anexo/{aid}/publico',{'visivel':'0','legenda':'Denied'})
                    with ext.db(self.db) as c:
                        self.assertEqual(c.execute('SELECT legenda FROM v9_anexos_visiveis '
                            'WHERE anexo_id=?',(aid,)).fetchone()[0],'Authorized')
                        c.execute('UPDATE ordens_servico SET arquivada=0 WHERE id=?',
                                  (self.oid,))
        stranger=ext.cadastrar(self.db,'Stranger','stranger@example.invalid','very-long-password')
        unauthorized={'pid':stranger,'nome':'Stranger'}
        principal=os_commands._provider_context(self.db,unauthorized)
        with self.assertRaises(PermissionError):
            os_commands.execute_http(self.ui,self.db,principal,
                f'/os/{self.oid}/anexo/{aid}/publico',
                {'visivel':'0','legenda':'Unauthorized'},unauthorized)

    def test_rollback_keeps_legacy_email_recipients(self):
        from scripts.autoseg import install_os_effect_outbox as migration
        with ext.db(self.db) as c:
            c.execute("INSERT INTO os_documentos(os_id,tipo,versao,caminho,sha256,publicado_em) "
                      "VALUES(?,'relatorio_pdf',1,'mock','digest','')",(self.oid,))
        payload={'reenviar_operacao':'x'*25,'confirmar_duplicata':'1',
                 'destinatario_sel[]':['cliente']}
        with patch.object(effects,'deliver_email',return_value=None):
            self.command('reenviar-email',payload)
        with ext.db(self.db) as c:
            key=c.execute('SELECT operation_key,payload_json FROM os_effect_outbox '
                          "WHERE action='send-manual'").fetchone()
            self.assertEqual(json.loads(key['payload_json'])['recipient_refs'],['cliente'])
            c.execute("UPDATE os_effect_outbox SET state='done' WHERE operation_key=?",
                      (key['operation_key'],))
        backup=str(Path(self.tmp.name)/'rollback-backup.db')
        with patch.dict(os.environ,{'AUTOSEG_DEV':'1'}):
            self.assertEqual(migration.main(['--database',self.db,'--rollback',
                                             '--backup',backup]),0)
        with patch.object(fluxo_os,'publicar_relatorio',return_value=None),patch.object(
                gmail_service,'enviar_relatorio_os_concluida') as sender:
            self.command('reenviar-email',{})
            self.assertEqual(sender.call_args.args[2],['example@example.invalid'])
            self.command('reenviar-email',{'destinatario_sel[]':['cliente']})
            self.assertEqual(sender.call_args.args[2],['example@example.invalid'])

    def test_email_dispatch_uses_operation_refs_not_mutable_projection(self):
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            produtividade_os.registrar_envio(self.db,self.oid,['example@example.invalid'],
                                 'pendente',connection=c)
            row=effects.enqueue_email(c,self.oid,'email-v1','send',
                                      recipient_refs=['cliente'])
            c.execute("UPDATE produtividade_email SET destinatarios_json=? WHERE os_id=?",
                      (json.dumps(['other@example.invalid']),self.oid))
        with patch.object(gmail_service,'_enviar_relatorio_os_concluida',
                          return_value='sent-id') as sender:
            self.assertEqual(gmail_service.enviar_operacao_outbox(
                self.db,self.oid,row['operation_key']),'sent-id')
        self.assertEqual(sender.call_args.args[2],['example@example.invalid'])

    def test_rollback_converts_old_reference_projection(self):
        from scripts.autoseg import install_os_effect_outbox as migration
        with ext.db(self.db) as c:
            c.execute('INSERT INTO produtividade_email '
                '(os_id,destinatarios_json,status,message_id,erro,atualizado_em) '
                "VALUES(?,?,'enviado','','','')",
                (self.oid,json.dumps(['cliente'])))
        with patch.dict(os.environ,{'AUTOSEG_DEV':'1'}):
            self.assertEqual(migration.main(['--database',self.db,'--rollback',
                '--backup',str(Path(self.tmp.name)/'old-backup.db')]),0)
        with ext.db(self.db) as c:
            row=c.execute('SELECT destinatarios_json FROM produtividade_email '
                'WHERE os_id=?',(self.oid,)).fetchone()
        self.assertEqual(json.loads(row[0]),['example@example.invalid'])

    def test_quarantine_restore_with_minimum_age_zero(self):
        from scripts.autoseg import dispatch_os_effect_outbox as dispatcher
        aid,path=self.photo()
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        key='e'*64
        effects.quarantine_file(self.anexos,path,key,source_id=aid,source_sha256=digest)
        with patch.dict(os.environ,{'AUTOSEG_DEV':'1'}):
            self.assertEqual(dispatcher.main(['--database',self.db,'--cleanup-trash']),0)
            self.assertFalse(path.exists())
            self.assertEqual(dispatcher.main(['--database',self.db,'--cleanup-trash',
                                              '--minimum-age','0']),0)
        self.assertTrue(path.exists())


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/'db.sqlite')
        with ext.db(self.db) as c:
            c.executescript('''CREATE TABLE os_documentos(os_id INTEGER,tipo TEXT,versao INTEGER);
             CREATE TABLE produtividade_email(os_id INTEGER PRIMARY KEY,destinatarios_json TEXT,
                status TEXT,message_id TEXT,erro TEXT,atualizado_em TEXT);
             CREATE TABLE os_entregas(os_id INTEGER PRIMARY KEY,documento_id INTEGER,
                destinatario TEXT,email_status TEXT,nf_status TEXT,atualizado_em TEXT);
             INSERT INTO produtividade_email VALUES(7,'["cliente"]','pendente',NULL,'','');
             INSERT INTO os_entregas VALUES(7,1,'original@example.invalid','aguardando_api','','');''')
        effects.install(self.db)
        with ext.db(self.db) as c:
            c.execute('BEGIN IMMEDIATE')
            self.row=effects.enqueue_email(c,7,'rev','send')

    def test_outbox_and_projection_finalization_is_atomic(self):
        claim=effects.claim(self.db,self.row['operation_key'])
        original=effects._project_email
        with patch.object(effects,'_project_email',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):
                effects.finish(self.db,self.row['operation_key'],claim['claim_token'],state='done')
        self.assertEqual(effects.get(self.db,self.row['operation_key'])['state'],'processing')
        effects.finish(self.db,self.row['operation_key'],claim['claim_token'],state='done',
                       result={'provider_message_id':'test-id'})
        with ext.db(self.db) as c:
            status=c.execute('SELECT status,message_id FROM produtividade_email').fetchone()
            delivery=c.execute('SELECT email_status,destinatario FROM os_entregas').fetchone()
        self.assertEqual((status['status'],status['message_id']),('enviado','test-id'))
        self.assertEqual((delivery['email_status'],delivery['destinatario']),
                         ('enviado','original@example.invalid'))

    def test_failed_and_unknown_update_projections(self):
        claim=effects.claim(self.db,self.row['operation_key'])
        effects.finish(self.db,self.row['operation_key'],claim['claim_token'],
                       state='failed',error='sem_destinatario')
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM produtividade_email').fetchone()[0],
                             'sem_destinatario')
            self.assertEqual(c.execute('SELECT email_status FROM os_entregas').fetchone()[0],
                             'sem_destinatario')
        claim=effects.claim(self.db,self.row['operation_key'])
        effects.finish(self.db,self.row['operation_key'],claim['claim_token'],
                       state='unknown',error='provider_outcome_unknown')
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM produtividade_email').fetchone()[0],
                             'unknown')


if __name__=='__main__':
    unittest.main()
