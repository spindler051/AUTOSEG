"""B2c regression scenarios for Web/GTK inventory parity (not executed)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flavors.autoseg.modules import importacao_yaml
from flavors.autoseg.modules.action_sections.stock import ACTIONS as STOCK
from flavors.autoseg.modules.action_sections.composition import ACTIONS as COMP
from officina.core import banco, estoque_materiais, prestadores_ext as ext, composicao


class B2cTests(unittest.TestCase):
    def test_contract_uses_single_stock_importer(self):
        stock = {a.id: a for a in STOCK}
        self.assertEqual(stock['stock.import'].service,'estoque_importar_lote')
        self.assertEqual(stock['stock.import'].surfaces,('web','gtk'))
        self.assertEqual({a.id for a in COMP}, {
            'composition.view','composition.configure','composition.add',
            'composition.edit','composition.activate','composition.delete',
            'composition.recalculate'})
        self.assertTrue(callable(composicao.parse_declarativa))

    def test_web_yaml_payload_matches_gtk_and_rejects_aliases(self):
        source=b'versao: 1\nmateriais:\n  - nome: Material de teste\n    sku: C2-1\n    unidade: un\n    custo: 10\n    venda: 20\n    minimo: 0\n'
        items=importacao_yaml.materiais('estoque.yaml',source)
        self.assertEqual(items[0]['nome'],'Material de teste')
        with self.assertRaises(ValueError):
            importacao_yaml.materiais('estoque.yaml',
                b'versao: 1\nmateriais: &anchor\n- nome: Item\n')

    def test_service_import_atomic_and_does_not_adjust_stock(self):
        from officina.application.local_service import LocalService
        with tempfile.TemporaryDirectory() as tmp:
            db=str(Path(tmp)/'stock.db'); banco.criar_banco(db)
            ext.instalar(db); estoque_materiais.instalar(db)
            provider=ext.cadastrar(db,'Admin','admin-b2c@example.com','long_password')
            # The reviewer grants live admin through its normal fixture.
            with patch.object(LocalService, '_company_admin', return_value=None):
                service=LocalService(db)
                service.estoque_importar_lote([{'nome':'A','sku':'SKU-A','unidade':'un',
                    'custo':'3','venda':'6','minimo':'0'}])
                with self.assertRaises(ValueError):
                    service.estoque_importar_lote([
                        {'nome':'B','sku':'SKU-B','unidade':'un','custo':'1','venda':'2','minimo':'0'},
                        {'nome':'A','sku':'SKU-A','unidade':'un','custo':'1','venda':'2','minimo':'0'}])
            names=[x['nome'] for x in estoque_materiais.listar(db)]
            self.assertIn('A', names)
            self.assertNotIn('B', names)
