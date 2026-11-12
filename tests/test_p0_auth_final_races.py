"""Deterministic races after HTTP preflight and before the writer transaction."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from flavors.autoseg.modules import os_commands
from officina.core import (prestadores_ext as ext, atendimento_os as aten,
    cadastros_v9 as cad9, fluxo_os as fluxo, produtividade_os as prod,
    os_effect_outbox as outbox)
from officina.core.banco import criar_banco


class WriterRaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix='p0_final_race_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'db.sqlite')
        criar_banco(self.db)
        for installer in (ext.instalar, fluxo.instalar, cad9.instalar,
                          aten.instalar, prod.instalar):
            installer(self.db)
        self.employee = ext.cadastrar(self.db, 'Worker', 'racer@example.invalid', 'test-password')
        self.admin = ext.cadastrar(self.db, 'Admin', 'admin@example.invalid', 'test-password')
        cad9.definir_admin(self.db, self.admin, True)
        with ext.db(self.db) as c:
            self.cid = c.execute("INSERT INTO clientes(nome,status) VALUES('Test','Ativo')").lastrowid
            self.oid = c.execute('''INSERT INTO ordens_servico
                (numero_os,cliente_id,status,descricao,data_abertura,criado_em)
                VALUES('260099999',?,'Aberta','Test','','')''',(self.cid,)).lastrowid
        ext.assumir(self.db, self.oid, self.employee)
        outbox.install(self.db)
        self.ui = Mock()
        self.ui.redir.return_value = 'redirect'

    def snapshot(self):
        with ext.db(self.db) as c:
            return tuple(c.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                         for table in ('os_eventos','os_effect_outbox',
                                       'produtividade_rascunhos','produtividade_deslocamentos',
                                       'os_notas_fiscais','os_anexos','produtividade_rateios'))

    def test_archived_between_preflight_and_writer_rolls_back_all(self):
        commands = (
            ('iniciar', {}),
            ('em-rota', {}),
            ('salvar', {'modo_envio':'rascunho'}),
            ('rascunho/salvar', {}),
            ('rascunho/auto', {}),
            ('nota-fiscal', {'nota_fiscal':('invoice.pdf', b'%PDF-1.4\n' + b'0'*150)}),
            ('fotos', {'imagens_encerramento[]':[('photo.png', b'png')]}),
        )
        for flag in ('0','1'):
            for route, data in commands:
                with self.subTest(flag=flag,route=route):
                    with ext.db(self.db) as c:
                        c.execute('UPDATE ordens_servico SET arquivada=0,status=\'Aberta\' WHERE id=?',(self.oid,))
                    before=self.snapshot()
                    action,_=os_commands._command(f'/os/{self.oid}/{route}',data)
                    original=os_commands.WRITERS[action]
                    def raced(*args,**kwargs):
                        # This change is committed by an independent process/connection.
                        with ext.db(self.db) as c:
                            c.execute('UPDATE ordens_servico SET arquivada=1 WHERE id=?',(self.oid,))
                        return original(*args,**kwargs)
                    session={'pid':self.employee,'nome':'Worker'}
                    principal=os_commands._provider_context(self.db,session)
                    with patch.dict(os.environ, {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}), \
                         patch.dict(os_commands.WRITERS, {action:raced}):
                        with self.assertRaises(PermissionError):
                            os_commands.execute_http(self.ui,self.db,principal,
                                f'/os/{self.oid}/{route}',data,session)
                    self.assertEqual(before,self.snapshot())

    def test_role_revoked_between_preflight_and_writer(self):
        session={'pid':self.admin,'nome':'Admin'}
        principal=os_commands._provider_context(self.db,session)
        original=os_commands.WRITERS['publicar']
        for flag in ('0','1'):
            with self.subTest(flag=flag):
                cad9.definir_admin(self.db,self.admin,True)
                with ext.db(self.db) as c:
                    c.execute("UPDATE ordens_servico SET status='Concluída',arquivada=0 WHERE id=?",(self.oid,))
                previous=self.snapshot()
                def raced(*args,**kwargs):
                    cad9.definir_admin(self.db,self.admin,False)
                    return original(*args,**kwargs)
                with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}), \
                     patch.dict(os_commands.WRITERS,{'publicar':raced}):
                    with self.assertRaises(PermissionError):
                        os_commands.execute_http(self.ui,self.db,principal,
                            f'/os/{self.oid}/publicar',{},session)
                self.assertEqual(previous,self.snapshot())

    def test_denied_pending_reopen_does_not_create_customer(self):
        for flag in ('0','1'):
            with self.subTest(flag=flag):
                with ext.db(self.db) as c:
                    c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?",(self.oid,))
                    count=c.execute('SELECT count(*) FROM clientes').fetchone()[0]
                session={'pid':self.employee,'nome':'Worker'}
                principal=os_commands._provider_context(self.db,session)
                with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':flag}):
                    with self.assertRaises(PermissionError):
                        os_commands.execute_http(self.ui,self.db,principal,
                            f'/os/{self.oid}/abrir',{'cliente_busca':'Never Created'},session)
                with ext.db(self.db) as c:
                    self.assertEqual(c.execute('SELECT count(*) FROM clientes').fetchone()[0],count)
                    self.assertEqual(c.execute('SELECT status FROM ordens_servico WHERE id=?',
                                               (self.oid,)).fetchone()[0],'Pendente')

    def test_reopen_can_create_provisional_client_atomically(self):
        with ext.db(self.db) as c:
            c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?",(self.oid,))
        session={'pid':self.admin,'nome':'Admin'}
        principal=os_commands._provider_context(self.db,session)
        before=self.snapshot()
        with patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'0'}):
            self.assertEqual(os_commands.execute_http(self.ui,self.db,principal,
                f'/os/{self.oid}/abrir',{'cliente_busca':'Temporary Person'},session),'redirect')
        with ext.db(self.db) as c:
            order=c.execute('SELECT cliente_id,status FROM ordens_servico WHERE id=?',(self.oid,)).fetchone()
            customer=c.execute('SELECT nome FROM clientes WHERE id=?',(order['cliente_id'],)).fetchone()
        self.assertEqual(order['status'],'Aberta')
        self.assertEqual(customer['nome'],'Temporary Person')
        self.assertGreater(self.snapshot()[0],before[0])


if __name__ == '__main__':
    unittest.main()
