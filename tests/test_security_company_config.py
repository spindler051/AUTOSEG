"""Prevent local company configuration writes by non-admin providers."""
import tempfile
import unittest
from pathlib import Path

from officina.application.local_service import LocalService
from officina.application.object_policy import Principal
from officina.core import banco, prestadores_ext as ext, cadastros_v9, catalogo_servicos, estoque_materiais, empresa_financeiro


class CompanyConfigAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='security-company-')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'company.db')
        banco.criar_banco(self.db)
        for module in (ext, cadastros_v9, catalogo_servicos, estoque_materiais, empresa_financeiro):
            module.instalar(self.db)
        self.admin_id = ext.cadastrar(self.db, 'Admin', 'adm@test.invalid', 'Pass123456789')
        self.other_id = ext.cadastrar(self.db, 'Staff', 'staff@test.invalid', 'Pass123456789')
        cadastros_v9.definir_admin(self.db, self.admin_id, True)
        self.admin = Principal(self.admin_id, 'admin', organization_id='autoseg', provider_id=self.admin_id)
        self.staff = Principal(self.other_id, 'employee', organization_id='autoseg', provider_id=self.other_id)
        self.service = LocalService(self.db)

    def test_employee_cannot_mutate_company_settings_or_pj(self):
        calls = (
            lambda: self.service.catalogo_salvar({'nome':'Forbidden'}, principal=self.staff),
            lambda: self.service.catalogo_excluir(12345, principal=self.staff),
            lambda: self.service.estoque_cadastrar({'nome':'Forbidden'},principal=self.staff),
            lambda: self.service.estoque_ajuste(12345,1,'forbidden',principal=self.staff),
            lambda: self.service.estoque_importar_lote([],principal=self.staff),
            lambda: self.service.composicao_salvar({},principal=self.staff),
            lambda: self.service.composicao_recalcular(principal=self.staff),
            lambda: self.service.empresa_registrar({},principal=self.staff),
            lambda: self.service.empresa_arquivar(12345,principal=self.staff),
            lambda: self.service.alterar_vinculo(12345,True,principal=self.staff),
            lambda: self.service.atualizar_sindico(12345,'name','phone',principal=self.staff),
            lambda: self.service.criar_prestador({'nome':'forbidden'}, principal=self.staff),
            lambda: self.service.definir_admin(self.other_id,True,principal=self.staff),
            lambda: self.service.salvar_config_prestador(self.other_id,{},principal=self.staff),
            lambda: self.service.atribuir_responsavel(12345,12345,principal=self.staff),
        )
        for fn in calls:
            with self.subTest(fn=fn),self.assertRaises(PermissionError):
                fn()
        with ext.db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM prestadores').fetchone()[0],2)
            self.assertFalse(ext.administrador(conn,self.other_id))

    def test_company_read_and_stock_access_require_correct_scope(self):
        with self.assertRaises(PermissionError):
            self.service.empresa_resumo(principal=self.staff)
        with self.assertRaises(PermissionError):
            self.service.estoque_movimentos(1,principal=None)
        self.assertIsInstance(self.service.listar_materiais_estoque(principal=self.staff),list)
        self.assertIsInstance(self.service.catalogo_listar(),list)

if __name__=='__main__':
    unittest.main()
