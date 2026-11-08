"""Configurable OS numbering: policy, timezone, sequence and clock guard."""
import sqlite3
import tempfile
import unittest
import warnings
from datetime import datetime, timezone
from pathlib import Path

from officina.core import numeracao
class NumeracaoPolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='numeracao_')
        self.path = Path(self.tmp.name) / 'numeracao.yaml'

    def tearDown(self):
        self.tmp.cleanup()

    def escrever(self, texto):
        self.path.write_text(texto, encoding='utf-8')

    def test_default_uses_sao_paulo_date(self):
        policy = numeracao.carregar(self.path)
        momento = datetime(2026, 11, 7, 2, 0, tzinfo=timezone.utc)
        # 02:00 UTC ainda é 23:00 de 2026-11-06 em São Paulo.
        self.assertEqual(policy.compor(momento, 1), '261106001')
        self.assertEqual(policy.compor(momento, 999), '261106999')

    def test_letters_and_custom_and_uuid(self):
        policy = numeracao._de_dict({
            'versao': 1, 'modo': 'date_sequence',
            'fuso': 'America/Sao_Paulo',
            'data': {'formato': '%y%m%d'},
            'sequencia': {'estilo': 'letters', 'largura': 3},
        })
        momento = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(policy.compor(momento, 1), '261107A')
        self.assertEqual(policy.compor(momento, 26), '261107Z')
        self.assertEqual(policy.compor(momento, 27), '261107AA')

        custom = numeracao._de_dict({
            'versao': 1, 'modo': 'custom',
            'fuso': 'America/Sao_Paulo',
            'data': {'formato': '%Y'},
            'sequencia': {'estilo': 'numeric', 'largura': 4},
            'custom': {'template': 'AUT-{data}-{sequencia}'},
        })
        self.assertEqual(custom.compor(momento, 7), 'AUT-2026-0007')

        uid = numeracao._de_dict({
            'versao': 1, 'modo': 'uuid',
            'fuso': 'America/Sao_Paulo',
        })
        numero = uid.compor(momento)
        self.assertEqual(len(numero), 32)
        int(numero, 16)

    def test_invalid_policy_fails_loudly(self):
        self.escrever('versao: 2\nmodo: date_sequence\n')
        with self.assertRaises(numeracao.ErroNumeracao):
            numeracao.carregar(self.path)

    def test_runtime_reload_changes_policy(self):
        self.escrever('''versao: 1
modo: date_sequence
fuso: America/Sao_Paulo
prefixo: ""
data: {formato: "%y%m%d"}
sequencia: {estilo: numeric, largura: 3}
''')
        store = numeracao.PoliticaStore(self.path)
        self.assertEqual(store.revision, 1)
        self.escrever('''versao: 1
modo: date_sequence
fuso: America/Sao_Paulo
prefixo: "OS-"
data: {formato: "%y%m%d"}
sequencia: {estilo: numeric, largura: 3}
''')
        store.reload()
        self.assertEqual(store.revision, 2)
        self.assertTrue(store.politica.compor(
            datetime(2026, 11, 7, 12, tzinfo=timezone.utc), 1).startswith('OS-'))


class NumeracaoSequenceTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_daily_sequence_increments_and_resets(self):
        p = numeracao.carregar(Path('/caminho/que/nao/existe.yaml'))
        dia1 = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
        dia2 = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
        with self.conn:
            self.assertEqual(numeracao.proximo_numero(self.conn, p, dia1), '261107001')
            self.assertEqual(numeracao.proximo_numero(self.conn, p, dia1), '261107002')
            self.assertEqual(numeracao.proximo_numero(self.conn, p, dia2), '261108001')

    def test_daily_limit_fails_clear(self):
        p = numeracao._de_dict({
            'versao': 1, 'modo': 'date_sequence',
            'fuso': 'America/Sao_Paulo',
            'data': {'formato': '%y%m%d'},
            'sequencia': {'estilo': 'numeric', 'largura': 3, 'maximo_por_dia': 2},
        })
        dia = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
        with self.conn:
            self.assertEqual(numeracao.proximo_numero(self.conn, p, dia), '261107001')
            self.assertEqual(numeracao.proximo_numero(self.conn, p, dia), '261107002')
            with self.assertRaises(numeracao.NumeroEsgotadoError):
                numeracao.proximo_numero(self.conn, p, dia)

    def test_clock_backwards_is_rejected(self):
        p = numeracao.carregar(Path('/caminho/que/nao/existe.yaml'))
        dia = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
        anterior = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
        with self.conn:
            numeracao.proximo_numero(self.conn, p, dia)
            with self.assertRaises(numeracao.RelogioInconsistenteError):
                numeracao.proximo_numero(self.conn, p, anterior)

    def test_clock_warning_mode_continues_with_unique_number(self):
        p = numeracao._de_dict({
            'versao': 1, 'modo': 'date_sequence',
            'fuso': 'America/Sao_Paulo',
            'data': {'formato': '%y%m%d'},
            'sequencia': {'estilo': 'numeric', 'largura': 3},
            'guardas': {'relogio': 'avisar'},
        })
        dia = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)
        anterior = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
        with self.conn:
            numeracao.proximo_numero(self.conn, p, dia)
            with warnings.catch_warnings(record=True) as avisos:
                warnings.simplefilter('always')
                numero = numeracao.proximo_numero(self.conn, p, anterior)
        self.assertEqual(numero, '261106001')
        self.assertTrue(avisos)


if __name__ == '__main__':
    unittest.main(verbosity=2)
