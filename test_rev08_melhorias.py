"""REV08 dev.2: regressão de catálogo/estoque usando exclusivamente SQLite temporário."""
from pathlib import Path
import tempfile
import unittest

from banco import criar_banco
import catalogo_servicos as catalogo
import estoque_materiais as estoque


class Rev08EstoqueTestes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_rev08_')
        self.banco = str(Path(self.tmp.name) / 'rev08.db')
        criar_banco(self.banco)
        estoque.instalar(self.banco)
        catalogo.instalar(self.banco)

    def tearDown(self):
        self.tmp.cleanup()

    def test_importacao_lote_valida(self):
        ids = estoque.importar_lote(self.banco, [
            {'nome':'Conector RJ45','sku':'RJ-45','venda':'2,50'},
            {'nome':'Câmera IP','unidade':'un','custo':'120,00', 'venda':'180,00'}])
        self.assertEqual(len(ids),2)
        itens=estoque.listar(self.banco)
        self.assertEqual(len(itens),2)
        self.assertEqual([x['saldo'] for x in itens],[0.0,0.0])
        self.assertEqual(estoque.movimentos(self.banco),[])

    def test_importacao_invalida_nao_grava_parcial(self):
        with self.assertRaises(ValueError):
            estoque.importar_lote(self.banco,[
                {'nome':'Fonte 12V'},
                {'nome':'Material inválido','minimo':'-2'}])
        self.assertEqual(estoque.listar(self.banco),[])

    def test_importacao_repetida_rejeitada_sem_movimentar(self):
        estoque.importar_lote(self.banco,[{'nome':'Câmera IP'}])
        with self.assertRaises(ValueError):
            estoque.importar_lote(self.banco,[{'nome':'Camera  IP'},{'nome':'Outro'}])
        self.assertEqual(len(estoque.listar(self.banco)),1)
        self.assertEqual(estoque.movimentos(self.banco),[])

    def test_importacao_duplicada_no_proprio_lote(self):
        with self.assertRaises(ValueError):
            estoque.importar_lote(self.banco,[{'nome':'Câmera IP'},{'nome':'camera ip'}])
        self.assertEqual(estoque.listar(self.banco),[])

    def test_importacao_codigo_ou_preco_invalido_rejeita(self):
        with self.assertRaises(ValueError):
            estoque.importar_lote(self.banco,[{'nome':'Primeiro'}, {'nome':'Segundo','venda':'0/1'}])
        self.assertEqual(estoque.listar(self.banco),[])

    def test_servico_gera_material_catalogo_sem_baixar_saldo(self):
        dados={'nome':'Instalação de câmera','descricao':'teste','preco_servico':'100',
               'material_nome[]':['Cabo UTP','Conector RJ45'],
               'material_qtd[]':['10','2'],
               'material_valor[]':['4,00','3,00']}
        sid=catalogo.salvar(self.banco,dados)
        self.assertIsInstance(sid,int)
        produtos=estoque.listar(self.banco)
        self.assertEqual(len(produtos),2)
        self.assertTrue(all(x['saldo']==0 for x in produtos))
        self.assertEqual(estoque.movimentos(self.banco),[])
        catalogo.salvar(self.banco,dados,sid)
        self.assertEqual(len(estoque.listar(self.banco)),2)

    def test_servico_usa_catalogo_existente_sem_alterar_preco(self):
        estoque.importar_lote(self.banco,[{'nome':'Câmera IP','venda':'500,00'}])
        catalogo.salvar(self.banco,{'nome':'Configuração','preco_servico':'50',
              'material_nome[]':['Camera IP'],'material_qtd[]':['1'],
              'material_valor[]':['100,00']})
        produtos=estoque.listar(self.banco)
        self.assertEqual(len(produtos),1)
        self.assertEqual(produtos[0]['venda_centavos'],50000)

    def test_sugestoes_normalizadas(self):
        estoque.importar_lote(self.banco,[{'nome':'Câmera IP','sku':'CAM01'},
                                         {'nome':'Conector RJ45'}])
        self.assertEqual([x['nome'] for x in estoque.sugerir(self.banco,'CAMERA')], ['Câmera IP'])
        self.assertEqual([x['nome'] for x in estoque.sugerir(self.banco,'cam01')], ['Câmera IP'])
        self.assertEqual(estoque.sugerir(self.banco,''),[])


if __name__ == '__main__':
    unittest.main()
