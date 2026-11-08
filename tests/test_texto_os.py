"""Generic free text attached to a service order (not a warranty-specific field)."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from officina.core import banco
from officina.core import cadastros_v9
from officina.core import fluxo_os
from officina.core import portal_negocios as neg
from officina.core import prestadores_ext as ext
from flavors.autoseg.modules import texto_os
class TextoOsConfigTest(unittest.TestCase):
    def setUp(self):
        self.anterior = os.environ.get('AUTOSEG_BASE')
        self.tmp = tempfile.TemporaryDirectory(prefix='texto_os_')
        os.environ['AUTOSEG_BASE'] = self.tmp.name

    def tearDown(self):
        if self.anterior is None:
            os.environ.pop('AUTOSEG_BASE', None)
        else:
            os.environ['AUTOSEG_BASE'] = self.anterior
        self.tmp.cleanup()

    def escrever(self, texto):
        (Path(self.tmp.name) / 'texto_os.yaml').write_text(
            texto, encoding='utf-8')

    def test_defaults_are_configurable_and_start_empty(self):
        config = texto_os.carregar()
        self.assertEqual(config['versao'], 1)
        self.assertTrue(config['campo']['rotulo'])
        self.assertEqual(texto_os.padrao(), '')

    def test_yaml_can_rename_label_and_set_default(self):
        self.escrever(
            'versao: 1\n'
            'campo:\n'
            '  rotulo: "Condições"\n'
            '  titulo_pdf: "Condições do atendimento"\n'
            '  padrao: "Texto padrão configurável."\n'
            '  ajuda: "Edite livremente."\n')
        self.assertEqual(texto_os.rotulo(), 'Condições')
        self.assertEqual(texto_os.titulo_pdf(), 'Condições do atendimento')
        self.assertEqual(texto_os.padrao(), 'Texto padrão configurável.')
        self.assertEqual(texto_os.ajuda(), 'Edite livremente.')

    def test_invalid_yaml_falls_back(self):
        self.escrever('versao: 2\ncampo: []\n')
        self.assertEqual(texto_os.rotulo(), 'Texto adicional')


class TextoOsPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='texto_os_db_')
        self.db = Path(self.tmp.name) / 'teste.db'
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        fluxo_os.instalar(self.db)
        cadastros_v9.instalar(self.db)
        self.pid = ext.cadastrar(
            self.db, 'Técnico A', 'a@example.org', 'senha-teste-a!')
        with ext.db(self.db) as c:
            self.cliente = c.execute(
                "INSERT INTO clientes(nome,status) VALUES('Cliente Teste','Ativo')"
            ).lastrowid

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_has_generic_column_and_save_keeps_text(self):
        with sqlite3.connect(self.db) as conexao:
            colunas = [linha[1] for linha in conexao.execute(
                'PRAGMA table_info(ordens_servico)')]
        self.assertIn('texto_adicional', colunas)
        oid = neg.os_salvar(self.db, {
            'cliente_id': str(self.cliente),
            'descricao': 'Serviço de teste',
            'tecnico': '',
            'forma_pagamento': 'PIX',
            'urgencia': 'Normal',
            'acao_status': 'salvar',
            'texto_adicional': 'Texto livre que pode ser qualquer coisa.',
            'valor_mao_obra': '10,00',
            'valor_materiais_manual': '0',
            'custo_materiais': '0',
            'tempo_horas': '0',
            'base_percentuais': 'total',
        }, self.pid)
        with ext.db(self.db) as c:
            self.assertEqual(
                c.execute('SELECT texto_adicional FROM ordens_servico WHERE id=?',
                          (oid,)).fetchone()[0],
                'Texto livre que pode ser qualquer coisa.')


if __name__ == '__main__':
    unittest.main(verbosity=2)
