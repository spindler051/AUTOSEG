"""Negative authorization tests for the in-process desktop adapter."""
import tempfile
import unittest
from pathlib import Path

from officina.application.local_service import LocalService
from officina.application.object_policy import Principal
from officina.core import banco, prestadores_ext as ext, cadastros_v9, fluxo_os, atendimento_os


class LocalOSAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'local.db')
        banco.criar_banco(self.db)
        for install in (ext.instalar, cadastros_v9.instalar, fluxo_os.instalar,
                        atendimento_os.instalar):
            install(self.db)
        self.admin_id = ext.cadastrar(self.db, 'admin', 'admin@invalid.test', 'Password12345')
        self.first_id = ext.cadastrar(self.db, 'first', 'first@invalid.test', 'Password12345')
        self.other_id = ext.cadastrar(self.db, 'other', 'other@invalid.test', 'Password12345')
        cadastros_v9.definir_admin(self.db, self.admin_id, True)
        self.admin = Principal(self.admin_id, 'admin', organization_id='autoseg', provider_id=self.admin_id)
        self.first = Principal(self.first_id, 'employee', organization_id='autoseg', provider_id=self.first_id)
        self.other = Principal(self.other_id, 'employee', organization_id='autoseg', provider_id=self.other_id)
        with ext.db(self.db) as c:
            client = c.execute("INSERT INTO clientes(nome,status) VALUES('Local Test','Ativo')").lastrowid
            self.os_first = c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao) VALUES('LOCAL-A',?,'Aberta','A')", (client,)).lastrowid
            self.os_other = c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status,descricao) VALUES('LOCAL-B',?,'Aberta','B')", (client,)).lastrowid
            for ident,pid in ((self.os_first,self.first_id),(self.os_other,self.other_id)):
                c.execute('INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) VALUES(?,?,?)', (ident,pid,ext.agora()))
        self.service = LocalService(self.db)

    def test_local_os_lists_fail_closed_and_are_scoped(self):
        for call in (lambda: self.service.listar_os_ativas(),
                     lambda: self.service.listar_os_recentes(),
                     lambda: self.service.listar_os_para_escolha(),
                     lambda: self.service.listar_os_para_atribuicao()):
            with self.subTest(call=call),self.assertRaises(PermissionError):
                call()
        self.assertEqual({r.id for r in self.service.listar_os_ativas(principal=self.first)}, {self.os_first})
        self.assertEqual({r.id for r in self.service.listar_os_recentes(principal=self.first)}, {self.os_first})
        self.assertEqual({r.id for r in self.service.listar_os_ativas(principal=self.admin)}, {self.os_first,self.os_other})

    def test_local_context_pdf_and_mutations_denied_without_involvement(self):
        for fn in (lambda: self.service.contexto_os(self.os_other,principal=self.first),
                   lambda: self.service.contexto_atribuicao(self.os_other,principal=self.first),
                   lambda: self.service.contar_anexos_os(self.os_other,principal=self.first),
                   lambda: self.service.pdf_publicado(self.os_other,principal=self.first),
                   lambda: self.service.iniciar_os(self.os_other,principal=self.first),
                   lambda: self.service.atribuir_os(self.os_other,self.first_id,principal=self.first),
                   lambda: self.service.preparar_email(self.os_other,principal=self.first),
                   lambda: self.service.preparar_nota(self.os_other,principal=self.first),
                   lambda: self.service.iniciar_os(self.os_first)):
            with self.subTest(fn=fn),self.assertRaises(PermissionError):
                fn()
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM ordens_servico WHERE id=?',(self.os_other,)).fetchone()[0],'Aberta')
            self.assertEqual(ext.responsavel_atual(c,self.os_other),self.other_id)

if __name__ == '__main__':
    unittest.main()
