"""Regression coverage for GTK OS report fields (MAIN feedback 66)."""
from pathlib import Path
import tempfile
import unittest

from officina.application.contracts import OSInput
from officina.application.desktop_context import contexto_os
from officina.application.os_write_service import OSCommand
from officina.core import (atendimento_os, banco, cadastros_v9,
                           fluxo_os, prestadores_ext as ext)


ROOT = Path(__file__).resolve().parents[1]


class GtkOsReportFieldsTest(unittest.TestCase):
    def test_os_input_and_step_zero_transport_keep_report_fields(self):
        values = OSInput(
            os_id=1, cliente_id=2, tecnico='', descricao='OS',
            valor_mao_obra=0.0, valor_materiais=0.0, custo_materiais=0.0,
            valor_total=0.0, forma_pagamento='Outro', urgencia='Normal',
            observacoes='', texto_adicional='', dados_incompletos=0,
            tempo_horas=0.0, composicao_json='', base_percentuais='total',
            materiais=(), acao='salvar', relato='', motivo='',
            v9_diagnostico='Diagnóstico', v9_execucao='Execução',
            v9_resultado='Resultado', solicitacao_original='Original',
        )
        fields = OSCommand.from_desktop(values, 7).fields
        self.assertEqual(fields['v9_diagnostico'], 'Diagnóstico')
        self.assertEqual(fields['v9_execucao'], 'Execução')
        self.assertEqual(fields['v9_resultado'], 'Resultado')
        self.assertEqual(fields['solicitacao_original'], 'Original')

    def test_gtk_dialog_exposes_and_saves_report_fields(self):
        source = (ROOT / 'flavors/autoseg/modules/gtk_dialogos.py').read_text(
            encoding='utf-8')
        for marker in (
            'Solicitação original', 'Diagnóstico', 'Serviço executado',
            'Resultado e testes',
            'v9_diagnostico=self.diagnostico.get_texto()',
            'v9_execucao=self.execucao.get_texto()',
            'v9_resultado=self.resultado.get_texto()',
            'solicitacao_original=self.solicitacao_original.get_texto()',
        ):
            self.assertIn(marker, source)

    def test_desktop_context_returns_original_and_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / 'gtk-fields.db')
            banco.criar_banco(db)
            for module in (ext, fluxo_os, atendimento_os, cadastros_v9):
                module.instalar(db)
            provider = ext.cadastrar(db, 'GTK Fields', 'gtk-fields@invalid.test',
                                     'Password12345')
            with ext.db(db) as conn:
                cid = conn.execute(
                    "INSERT INTO clientes(nome,status) VALUES('Cliente','Ativo')"
                ).lastrowid
                oid = conn.execute(
                    "INSERT INTO ordens_servico(numero_os,cliente_id,status,"
                    "descricao) VALUES('GTK-FIELDS',?,'Aberta','OS')", (cid,)
                ).lastrowid
                conn.execute(
                    "INSERT INTO os_solicitacoes(os_id,cliente_id,"
                    "descricao_original,criado_em,origem) "
                    "VALUES(?,?,?,'2026-11-19','App')",
                    (oid, cid, 'Solicitação original'))
                conn.execute(
                    "INSERT INTO v9_detalhes_os(os_id,diagnostico,execucao,"
                    "resultado,alterado_em) VALUES(?,?,?,?,?)",
                    (oid, 'Diagnóstico', 'Execução', 'Resultado', '2026-11-19'))
            context = contexto_os(db, oid)
            self.assertEqual(context['solicitacao_original'],
                             'Solicitação original')
            self.assertEqual(context['detalhes'],
                             {'diagnostico': 'Diagnóstico',
                              'execucao': 'Execução',
                              'resultado': 'Resultado'})
