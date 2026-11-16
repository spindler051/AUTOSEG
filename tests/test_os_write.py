"""Application-level OS save used by the desktop dialog."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from officina.core import atendimento_os
from officina.core import banco
from officina.core import cadastros_v9
from officina.core import composicao
from officina.core import estoque_materiais
from officina.core import fluxo_os
from officina.core import prestadores_ext as ext
from officina.core import produtividade_os
from officina.application.contracts import OSInput
from officina.application.local_service import LocalService
from officina.application.object_policy import Principal


class OSWriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='os_write_')
        self.db = Path(self.tmp.name) / 'teste.db'
        banco.criar_banco(self.db)
        for modulo in (ext, fluxo_os, atendimento_os, cadastros_v9,
                       estoque_materiais, produtividade_os):
            modulo.instalar(self.db)
        composicao.instalar()
        composicao.instalar_banco(self.db)
        pid = ext.cadastrar(self.db, 'Local admin', 'admin-os@test.invalid', 'Password12345')
        cadastros_v9.definir_admin(self.db, pid, True)
        self.actor = Principal(pid, 'admin', organization_id='autoseg',provider_id=pid)
        self.service = LocalService(self.db)
        with ext.db(self.db) as conexao:
            self.cliente = conexao.execute(
                "INSERT INTO clientes(nome,status) VALUES('Cliente Teste','Ativo')"
            ).lastrowid

    def tearDown(self):
        self.tmp.cleanup()

    def entrada(self, **mudancas):
        dados = dict(
            os_id=None,
            cliente_id=self.cliente,
            tecnico='',
            descricao='Serviço de teste',
            valor_mao_obra=10.0,
            valor_materiais=0.0,
            custo_materiais=0.0,
            valor_total=10.0,
            forma_pagamento='PIX',
            urgencia='Normal',
            observacoes='',
            texto_adicional='Texto livre de teste.',
            dados_incompletos=0,
            tempo_horas=0.0,
            composicao_json='',
            base_percentuais='total',
            materiais=(),
            acao='salvar',
            relato='',
            motivo='',
            imagens=(),
        )
        dados.update(mudancas)
        return OSInput(**dados)

    def test_create_and_update_os_keeps_generic_text(self):
        criada = self.service.salvar_os(self.entrada(), principal=self.actor)
        self.assertTrue(criada.criada)
        with ext.db(self.db) as conexao:
            linha = conexao.execute(
                'SELECT texto_adicional,status FROM ordens_servico WHERE id=?',
                (criada.os_id,)).fetchone()
        self.assertEqual(linha['texto_adicional'], 'Texto livre de teste.')
        self.assertEqual(linha['status'], 'Aberta')

        atualizada = self.service.salvar_os(self.entrada(
            os_id=criada.os_id,
            descricao='Serviço atualizado',
            texto_adicional='Outro texto.',
            # Labor (10) plus the new material (2 x 5) must close the
            # canonical Web composition; do not bypass it in local mode.
            valor_materiais=10.0,
            valor_total=20.0,
            materiais=({'item': 'Fita', 'quantidade': 2,
                        'unidade': 'un', 'valor_unitario': 5},),
        ), principal=self.actor)
        self.assertEqual(atualizada.os_id, criada.os_id)
        with ext.db(self.db) as conexao:
            linha = conexao.execute(
                'SELECT descricao,texto_adicional FROM ordens_servico WHERE id=?',
                (criada.os_id,)).fetchone()
            material = conexao.execute(
                'SELECT item,quantidade FROM materiais_os WHERE os_id=?',
                (criada.os_id,)).fetchone()
        self.assertEqual(linha['descricao'], 'Serviço atualizado')
        self.assertEqual(linha['texto_adicional'], 'Outro texto.')
        self.assertEqual((material['item'], material['quantidade']), ('Fita', 2.0))

    def test_desktop_context_returns_os_dialog_data(self):
        criada = self.service.salvar_os(self.entrada(), principal=self.actor)
        contexto = self.service.contexto_os(criada.os_id, principal=self.actor)
        self.assertEqual(contexto["dados"]["id"], criada.os_id)
        self.assertEqual(contexto["dados"]["texto_adicional"], "Texto livre de teste.")
        self.assertTrue(contexto["clientes"])
        self.assertEqual(self.service.contar_anexos_os(criada.os_id, principal=self.actor), 0)
        atribuicao = self.service.contexto_atribuicao(criada.os_id, principal=self.actor)
        self.assertEqual(atribuicao["ordem"]["numero_os"], "OS-0001")
        self.assertIsNotNone(self.service.contexto_os_rapida(principal=self.actor)["clientes"])
        self.assertIsNotNone(self.service.contexto_movimento_empresa(principal=self.actor)["oses"])

    def test_pendente_and_concluida_change_status(self):
        criada = self.service.salvar_os(self.entrada(), principal=self.actor)
        pendente = self.service.salvar_os(self.entrada(
            os_id=criada.os_id, acao='Pendente', relato='Aguardando peça.'), principal=self.actor)
        self.assertEqual(pendente.os_id, criada.os_id)
        with ext.db(self.db) as conexao:
            self.assertEqual(
                conexao.execute('SELECT status FROM ordens_servico WHERE id=?',
                                (criada.os_id,)).fetchone()[0],
                'Pendente')
        with patch.object(fluxo_os, 'publicar_relatorio', return_value=None):
            concluida = self.service.salvar_os(self.entrada(
                os_id=criada.os_id, acao='Concluída', relato='Serviço concluído.',
                sem_nota_fiscal=True, sem_destinatario=True), principal=self.actor)
        self.assertTrue(concluida.encerrada)
        with ext.db(self.db) as conexao:
            self.assertEqual(
                conexao.execute('SELECT status FROM ordens_servico WHERE id=?',
                                (criada.os_id,)).fetchone()[0],
                'Concluída')
            encerramento = conexao.execute(
                'SELECT situacao FROM os_encerramentos WHERE os_id=?',
                (criada.os_id,)).fetchone()
            financeiro = conexao.execute(
                'SELECT valor,status FROM financeiro WHERE os_id=?',
                (criada.os_id,)).fetchone()
        self.assertEqual(encerramento['situacao'], 'Concluída')
        self.assertEqual(float(financeiro['valor']), 10.0)
        self.assertEqual(financeiro['status'], 'Aguardando pagamento')


if __name__ == '__main__':
    unittest.main(verbosity=2)
