"""Testes do relatório PDF do cliente (formatação e composição financeira).

Verifica que a linha TOTAL não expõe tags HTML literais (regressão do bug
``<b>TOTAL</b>``) e que o valor total é renderizado corretamente.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import prestadores_ext as ext

COMP_OS0010 = {
    "aviso": "",
    "componentes": [
        {"id": "materiais", "modo": "materiais", "nome": "Materiais",
         "obrigatorio": True, "ordem": 1, "percentual": 0.0, "valor_centavos": 0},
        {"id": "hora_tecnica", "modo": "hora", "nome": "Mão de obra / hora técnica",
         "obrigatorio": True, "ordem": 2, "percentual": 8.63, "valor_centavos": 10000},
        {"id": "visita", "modo": "fixo", "nome": "Taxa mínima de visita",
         "obrigatorio": True, "ordem": 3, "percentual": 21.58, "valor_centavos": 25000},
        {"id": "administrativo", "modo": "percentual", "nome": "Custos administrativos",
         "obrigatorio": False, "ordem": 4, "percentual": 10.0, "valor_centavos": 11583},
        {"id": "operacional", "modo": "percentual",
         "nome": "Custos operacionais e tecnológicos",
         "obrigatorio": False, "ordem": 5, "percentual": 10.0, "valor_centavos": 11583},
        {"id": "risco", "modo": "percentual", "nome": "Margem de risco e contingência",
         "obrigatorio": False, "ordem": 6, "percentual": 5.0, "valor_centavos": 5792},
        {"id": "outros", "modo": "residual",
         "nome": "Outros custos e margem de contribuição",
         "obrigatorio": False, "ordem": 7, "percentual": 44.78, "valor_centavos": 51875},
    ],
    "total_centavos": 115833,
    "versao": 1,
}


class PdfRelatorioTest(unittest.TestCase):
    def setUp(self):
        self.anterior = os.environ.get("AUTOSEG_BASE")
        self.pasta = tempfile.TemporaryDirectory()
        os.environ["AUTOSEG_BASE"] = self.pasta.name
        self.db = Path(self.pasta.name) / "teste.db"
        import banco
        import fluxo_os
        import atendimento_os
        import cadastros_v9
        banco.criar_banco(self.db)
        for modulo in (ext, fluxo_os, atendimento_os, cadastros_v9):
            modulo.instalar(self.db)
        import produtividade_os
        produtividade_os.instalar(self.db)
        self._criar_os()

    def tearDown(self):
        if self.anterior is None:
            os.environ.pop("AUTOSEG_BASE", None)
        else:
            os.environ["AUTOSEG_BASE"] = self.anterior
        self.pasta.cleanup()

    def _criar_os(self):
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO clientes (nome, documento, tipo_pessoa, status, cidade) "
                      "VALUES (?,?,?,?,?)",
                      ("Condomínio Edifício Palermo", "12.345.678/0001-90",
                       "Jurídica", "Ativo", "Porto Alegre"))
            cliente_id = c.execute("SELECT id FROM clientes").fetchone()[0]
            c.execute(
                "INSERT INTO ordens_servico (id, numero_os, cliente_id, status, "
                "valor_total, valor_mao_obra, valor_materiais, forma_pagamento, "
                "data_abertura, data_conclusao, composicao_json, tempo_horas) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (10, "OS-0010", cliente_id, "Concluída", 1158.33, 0.0, 0.0,
                 "PIX", "2026-10-30 12:55:56", "2026-11-03 12:03:49",
                 json.dumps(COMP_OS0010, ensure_ascii=False), 0.0))

    def test_pdf_sem_tags_html_literais(self):
        caminho = ext.gerar_pdf(self.db, 10)
        self.assertTrue(Path(caminho).is_file())
        from pypdf import PdfReader
        leitor = PdfReader(str(caminho))
        texto = "\n".join((p.extract_text() or "") for p in leitor.pages)
        self.assertNotIn("<b>", texto)
        self.assertNotIn("</b>", texto)
        self.assertNotIn("&lt;b&gt;", texto)
        self.assertIn("TOTAL", texto)

    def test_pdf_total_valor_correto(self):
        caminho = ext.gerar_pdf(self.db, 10)
        from pypdf import PdfReader
        leitor = PdfReader(str(caminho))
        texto = "\n".join((p.extract_text() or "") for p in leitor.pages)
        self.assertIn("R$ 1.158,33", texto)
        self.assertIn("100,00%", texto)

    def test_composicao_soma_total(self):
        # Garante que a composição da OS-0010 soma exatamente o total.
        self.assertEqual(COMP_OS0010["total_centavos"], 115833)
        self.assertEqual(
            sum(c["valor_centavos"] for c in COMP_OS0010["componentes"]), 115833)


if __name__ == "__main__":
    unittest.main(verbosity=2)
