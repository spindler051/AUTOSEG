"""Company cash ledger: contributions, expenses and isolation from OS/stock."""
import tempfile
import unittest
from pathlib import Path

import empresa_financeiro as empresa
import prestadores_ext as ext
from banco import criar_banco


class EmpresaFinanceiroTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_empresa_')
        self.db = str(Path(self.tmp.name) / 'teste.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        empresa.instalar(self.db)
        self.julio = ext.cadastrar(
            self.db, 'Julio', 'julio@example.org', 'senha-segura-2026')
        self.joao_paulo = ext.cadastrar(
            self.db, 'João Paulo', 'joao.paulo@example.org', 'senha-segura-2026')
        self.joao_lucas = ext.cadastrar(
            self.db, 'João Lucas', 'joao.lucas@example.org', 'senha-segura-2026')
        with ext.db(self.db) as c:
            self.cliente_id = c.execute(
                "INSERT INTO clientes(nome,status,criado_em) VALUES(?,?,?)",
                ('Cliente Teste', 'Ativo', ext.agora())).lastrowid
            self.os_id = c.execute(
                "INSERT INTO ordens_servico"
                "(numero_os,cliente_id,status,valor_total,custo_materiais,criado_em) "
                "VALUES(?,?,?,?,?,?)",
                ('OS-TESTE', self.cliente_id, 'Concluída', 350.0, 75.0,
                 ext.agora())).lastrowid

    def tearDown(self):
        self.tmp.cleanup()

    def _registrar_aportes(self):
        empresa.registrar(self.db, 'aporte', 'Aporte inicial', '30,00',
                          '05/11/2026', prestador_id=self.joao_paulo)
        empresa.registrar(self.db, 'aporte', 'Aporte inicial', '60,00',
                          '05/11/2026', prestador_id=self.joao_lucas)
        empresa.registrar(self.db, 'aporte', 'Aporte inicial', '40,00',
                          '05/11/2026', prestador_id=self.julio)

    def test_contributions_and_expenses_summary(self):
        self._registrar_aportes()
        empresa.registrar(
            self.db, 'api', 'Crédito da API', '20,00', '05/11/2026',
            categoria='API DeepSeek')
        empresa.registrar(
            self.db, 'material', 'Conector e cabo', '15,00', '05/11/2026',
            os_id=self.os_id)
        empresa.registrar(
            self.db, 'despesa', 'Taxa bancária', '5,00', '05/11/2026')

        resumo = empresa.resumo(self.db)
        self.assertEqual(resumo['aportes_centavos'], 13000)
        self.assertEqual(resumo['material_centavos'], 1500)
        self.assertEqual(resumo['api_centavos'], 2000)
        self.assertEqual(resumo['outras_despesas_centavos'], 500)
        self.assertEqual(resumo['despesas_centavos'], 4000)
        self.assertEqual(resumo['saldo_centavos'], 9000)
        por_nome = {x['nome']: x['total_centavos']
                    for x in resumo['por_investidor']}
        self.assertEqual(por_nome, {
            'João Paulo': 3000,
            'João Lucas': 6000,
            'Julio': 4000,
        })
        self.assertEqual(len(empresa.listar(self.db)), 6)

    def test_material_reference_does_not_change_os_or_stock(self):
        with ext.db(self.db) as c:
            antes = dict(c.execute(
                'SELECT valor_total,custo_materiais,status FROM ordens_servico '
                'WHERE id=?', (self.os_id,)).fetchone())
        empresa.registrar(
            self.db, 'material', 'Material sem SKU', '99,90',
            '05/11/2026', os_id=self.os_id)
        with ext.db(self.db) as c:
            depois = dict(c.execute(
                'SELECT valor_total,custo_materiais,status FROM ordens_servico '
                'WHERE id=?', (self.os_id,)).fetchone())
            movimentos = c.execute(
                'SELECT * FROM empresa_movimentos').fetchall()
        self.assertEqual(antes, depois)
        self.assertEqual(movimentos[0]['os_id'], self.os_id)
        self.assertEqual(movimentos[0]['valor_centavos'], 9990)

    def test_aporte_requires_active_investor(self):
        with self.assertRaisesRegex(ValueError, 'investidor'):
            empresa.registrar(
                self.db, 'aporte', 'Sem investidor', '10,00', '05/11/2026')
        with ext.db(self.db) as c:
            c.execute('UPDATE prestadores SET ativo=0 WHERE id=?', (self.julio,))
        with self.assertRaisesRegex(ValueError, 'inativo'):
            empresa.registrar(
                self.db, 'aporte', 'Investidor inativo', '10,00',
                '05/11/2026', prestador_id=self.julio)

    def test_os_link_is_only_allowed_for_material(self):
        with self.assertRaisesRegex(ValueError, 'material'):
            empresa.registrar(
                self.db, 'api', 'API com OS', '10,00', '05/11/2026',
                os_id=self.os_id)
        with self.assertRaisesRegex(ValueError, 'não encontrada'):
            empresa.registrar(
                self.db, 'material', 'OS inexistente', '10,00',
                '05/11/2026', os_id=999999)

    def test_archive_preserves_history_and_updates_totals(self):
        self._registrar_aportes()
        movimentos = empresa.listar(self.db)
        alvo = next(x for x in movimentos if x['valor_centavos'] == 6000)
        self.assertTrue(empresa.arquivar(self.db, alvo['id']))
        self.assertFalse(empresa.arquivar(self.db, alvo['id']))
        self.assertEqual(empresa.resumo(self.db)['aportes_centavos'], 7000)
        ativos = empresa.listar(self.db)
        self.assertEqual(len(ativos), 2)
        historico = empresa.listar(self.db, incluir_arquivados=True)
        self.assertEqual(len(historico), 3)
        arquivado = next(x for x in historico if x['id'] == alvo['id'])
        self.assertEqual(arquivado['ativo'], 0)
        self.assertTrue(arquivado['arquivado_em'])

    def test_validation_and_date_formats(self):
        for tipo in ('invalido', '', None):
            with self.assertRaisesRegex(ValueError, 'Tipo'):
                empresa.registrar(
                    self.db, tipo, 'Teste', '10,00', '05/11/2026')
        for valor in ('0', '-1', 'abc', ''):
            with self.assertRaises(ValueError):
                empresa.registrar(
                    self.db, 'despesa', 'Teste', valor, '05/11/2026')
        with self.assertRaisesRegex(ValueError, 'Data'):
            empresa.registrar(
                self.db, 'despesa', 'Teste', '10,00', '31/02/2026')
        empresa.registrar(
            self.db, 'despesa', 'Data ISO', '10,00', '2026-11-05')
        self.assertEqual(empresa.listar(self.db)[0]['data'], '2026-11-05')


if __name__ == '__main__':
    unittest.main(verbosity=2)
