import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import versionador

class VersionamentoTestes(unittest.TestCase):
    def test_valido(self):
        self.assertEqual(versionador.analisar_versao('9.6.0-dev.1')[:3], (9, 6, 0))
        self.assertEqual(versionador.analisar_versao('9.6.0'), (9, 6, 0, None, None))

    def test_rejeita_formato_perigoso(self):
        for texto in ('9.06.0', 'v9.6', '9.6.0-dev.0', '../9.6.0', '9.6.0-beta.1'):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                versionador.analisar_versao(texto)

    def test_evolucao(self):
        self.assertEqual(versionador.proxima_versao('9.6.0-dev.1', 'dev'), '9.6.0-dev.2')
        self.assertEqual(versionador.proxima_versao('9.6.0-dev.1', 'rc'), '9.6.0-rc.1')
        self.assertEqual(versionador.proxima_versao('9.6.0-rc.1', 'stable'), '9.6.0')
        self.assertEqual(versionador.proxima_versao('9.6.0', 'patch'), '9.6.1-dev.1')

    def test_arquivo_incoerente(self):
        with tempfile.TemporaryDirectory() as t:
            arq = Path(t) / 'versao.json'
            arq.write_text(json.dumps({'produto': 'AUTOSEG', 'versao': '9.6.0-dev.1',
                                       'canal': 'stable', 'homologado': True}))
            with patch.object(versionador, 'ARQUIVO', arq), self.assertRaises(ValueError):
                versionador.carregar()

    def test_info_nao_modifica_arquivo(self):
        antes = versionador.ARQUIVO.read_bytes()
        self.assertEqual(versionador.main(['info', '--json']), 0)
        self.assertEqual(versionador.ARQUIVO.read_bytes(), antes)

if __name__ == '__main__':
    unittest.main()
