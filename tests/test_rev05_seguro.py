"""REV05 — testes locais sem abrir conexões externas ou enviar mensagens."""
import unittest
from pathlib import Path
from flavors.autoseg.modules import importacao_yaml as imp
from flavors.autoseg.modules.tuneis_dev import PORTAS, obter_executavel

class TestesRev05(unittest.TestCase):
    def test_tuneis_somente_dev(self):
        self.assertEqual(PORTAS,(8865,8866))
    def test_yaml_materiais_modelo(self):
        arquivo=Path(__file__).parents[1] / 'flavors/autoseg/templates/modelo_materiais.yaml'
        lista=imp.materiais(arquivo.name,arquivo.read_bytes())
        self.assertEqual(len(lista),2)
        self.assertEqual(lista[0]['unidade'],'metro')
        self.assertEqual(lista[0]['venda'],'5,00')
    def test_yaml_material_duplicado(self):
        data=b'versao: 1\nmateriais:\n  - nome: Cabo USB\n  - nome: Cabo USB\n'
        with self.assertRaises(ValueError):imp.materiais('a.yml',data)
    def test_yaml_material_nega_alias(self):
        data=b'versao: 1\nmateriais:\n  - &x {nome: Cabo USB}\n  - *x\n'
        with self.assertRaises(ValueError):imp.materiais('a.yml',data)
    def test_yaml_material_nao_aceita_estoque_direto(self):
        data=b'versao: 1\nmateriais:\n  - nome: Cabo USB\n    saldo: 9999999\n'
        with self.assertRaises(ValueError):imp.materiais('a.yml',data)

if __name__=='__main__':unittest.main()
