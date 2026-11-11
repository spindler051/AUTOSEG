"""6.2: command writes are impossible when ObjectPolicy denies the operation."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import os

from flavors.autoseg.modules import os_commands
from officina.application.object_policy import Principal


class AuthorizedCommandTest(unittest.TestCase):
    def setUp(self):
        self.enforce=patch.dict(os.environ,{'AUTOSEG_OBJECT_POLICY_ENFORCEMENT':'1'})
        self.enforce.start()
        self.addCleanup(self.enforce.stop)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=str(Path(self.tmp.name)/'db.sqlite')
        with sqlite3.connect(self.db) as c:
            c.executescript("""CREATE TABLE ordens_servico(id INTEGER PRIMARY KEY,
                prestador_id INTEGER,cliente_id INTEGER,descricao TEXT);
                CREATE TABLE os_responsaveis(os_id INTEGER,prestador_id INTEGER);
                CREATE TABLE os_prestadores(os_id INTEGER,prestador_id INTEGER,ativo INTEGER);
                CREATE TABLE v9_organizacoes(id INTEGER,cliente_id INTEGER,mesclado_em INTEGER);
                CREATE TABLE v9_chamados(id INTEGER,usuario_id INTEGER,
                    organizacao_id INTEGER,os_id INTEGER);
                INSERT INTO ordens_servico VALUES(1,99,42,'Original');
                INSERT INTO os_responsaveis VALUES(1,2);
                INSERT INTO os_prestadores VALUES(1,3,1);
            """)
        self.owner=Principal(2,'employee',organization_id='autoseg',provider_id=2)
        self.participant=Principal(3,'employee',organization_id='autoseg',provider_id=3)
        self.other=Principal(99,'employee',organization_id='autoseg',provider_id=99)
        self.session={'pid':2,'nome':'Owner','csrf':'unused'}

    def _call(self,path,principal,body=None):
        return os_commands.execute_http(object(),self.db,principal,path,body or {},
                                        self.session)

    def test_real_action_not_url_for_conclude_and_cancel(self):
        writer=Mock()
        with patch.dict(os_commands.WRITERS,{'salvar':writer}):
            self._call('/os/1/salvar',self.participant,{'acao_status':'salvar'})
            writer.assert_called_once()
            writer.reset_mock()
            for payload in ({'acao_status':'Concluída'},
                            {'acao_status':'Cancelada'},
                            {'cancelar_os':'1','acao_status':'salvar'}):
                with self.subTest(payload=payload),self.assertRaises(PermissionError):
                    self._call('/os/1/salvar',self.participant,payload)
                writer.assert_not_called()

    def test_denial_prevents_writer_and_db_mutation_for_each_route(self):
        cases=[
            ('/os/1/abrir',{}),('/os/1/salvar',{'acao_status':'salvar'}),
            ('/os/1/salvar',{'acao_status':'Concluída'}),
            ('/os/1/cancelar',{}),('/os/1/publicar',{}),
            ('/os/1/atribuir',{}),('/os/1/arquivar',{}),
            ('/os/1/rota',{}),('/os/1/iniciar',{}),
            ('/os/1/em-rota',{}),('/os/1/cancelar-rota',{}),
            ('/os/1/rascunho/auto',{}),('/os/1/rascunho/salvar',{}),
            ('/os/1/fotos',{}),('/os/1/rateio',{}),
            ('/os/1/yaml',{}),('/os/1/nota-fiscal',{}),
            ('/os/1/nota-fiscal/1/remover',{}),
            ('/os/1/anexo/1/mover',{}),('/os/1/anexo/1/remover',{}),
            ('/os/1/anexo/1/girar',{}),('/os/1/anexo/1/publico',{}),
            ('/os/1/reenviar-email',{}),
        ]
        with sqlite3.connect(self.db) as c:
            original=c.execute('SELECT descricao FROM ordens_servico WHERE id=1').fetchone()[0]
        for route,body in cases:
            action,_oid=os_commands._command(route,body)
            writer=Mock()
            with self.subTest(route=route),patch.dict(os_commands.WRITERS,{action:writer}):
                with self.assertRaises(PermissionError):
                    self._call(route,self.other,body)
                writer.assert_not_called()
                with sqlite3.connect(self.db) as c:
                    result=c.execute('SELECT descricao FROM ordens_servico WHERE id=1').fetchone()[0]
                self.assertEqual(original,result)

    def test_creation_checks_policy_before_writer(self):
        inactive=Principal(3,'employee',organization_id='autoseg',
                           provider_id=3,active=False)
        for route in ('/os/nova/salvar','/os/rapida/salvar'):
            action,_=os_commands._command(route,{})
            writer=Mock()
            with patch.dict(os_commands.WRITERS,{action:writer}),self.assertRaises(PermissionError):
                self._call(route,inactive,{})
            writer.assert_not_called()

    def test_admin_authorized_and_owner_edits(self):
        admin=Principal(7,'admin',organization_id='autoseg',provider_id=7)
        for principal,route in ((admin,'/os/1/abrir'),(self.owner,'/os/1/salvar')):
            action,_=os_commands._command(route,{})
            writer=Mock(return_value='service-result')
            with patch.dict(os_commands.WRITERS,{action:writer}):
                self.assertEqual('service-result',self._call(route,principal,{}))
            writer.assert_called_once()

    def test_unknown_action_denied_closed(self):
        with self.assertRaises(PermissionError):
            self._call('/os/1/suspicious',self.owner,{})


if __name__=='__main__':
    unittest.main()
