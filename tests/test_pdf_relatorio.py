"""Testes do relatório PDF do cliente (formatação e composição financeira).

Verifica que a linha TOTAL não expõe tags HTML literais (regressão do bug
``<b>TOTAL</b>``) e que o valor total é renderizado corretamente.
"""
import io
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from officina.core import prestadores_ext as ext
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
        ext.ANEXOS = Path(self.pasta.name) / "anexos"
        ext.RELATORIOS = Path(self.pasta.name) / "relatorios"
        ext.ANEXOS.mkdir(exist_ok=True)
        ext.RELATORIOS.mkdir(exist_ok=True)
        from officina.core import banco
        from officina.core import fluxo_os
        from officina.core import atendimento_os
        from officina.core import cadastros_v9
        banco.criar_banco(self.db)
        for modulo in (ext, fluxo_os, atendimento_os, cadastros_v9):
            modulo.instalar(self.db)
        from officina.core import produtividade_os
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

    def _criar_os_com_relato(self, os_id, numero, status, resumo, relato):
        with sqlite3.connect(self.db) as c:
            cliente_id = c.execute("SELECT id FROM clientes LIMIT 1").fetchone()[0]
            c.execute(
                "INSERT INTO ordens_servico (id, numero_os, cliente_id, status, "
                "valor_total, valor_mao_obra, valor_materiais, forma_pagamento, "
                "data_abertura, data_conclusao, composicao_json, tempo_horas) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (os_id, numero, cliente_id, status, 1158.33, 0.0, 0.0,
                 "PIX", "2026-10-30 12:55:56",
                 "2026-11-03 12:03:49" if status != "Pendente" else None,
                 json.dumps(COMP_OS0010, ensure_ascii=False), 0.0))
            c.execute(
                "INSERT INTO v9_detalhes_os(os_id, diagnostico, execucao, resultado, alterado_em) "
                "VALUES (?,?,?,?,?)",
                (os_id, resumo, "Resumo da execução", "Resumo do resultado",
                 "2026-11-06 10:00:00"))
            c.execute(
                "INSERT INTO os_atendimentos(os_id, rascunho, atualizado_em, ultimo_editor) "
                "VALUES (?,?,?,?)",
                (os_id, relato, "2026-11-06 10:00:00", "Prestador"))

    @staticmethod
    def _texto_pdf(caminho):
        from pypdf import PdfReader
        leitor = PdfReader(str(caminho))
        return " ".join(" ".join((p.extract_text() or "") for p in leitor.pages).split())

    def test_pdf_os_pendente_usa_relatorio_completo(self):
        relato = ("Relatório completo do atendimento pendente. "
                  "Diagnóstico detalhado com todo o histórico do local. "
                  "Serviço executado e resultado dos testes.")
        self._criar_os_com_relato(20, "OS-0020", "Pendente",
                                  "Resumo do diagnóstico", relato)
        texto = self._texto_pdf(ext.gerar_pdf(self.db, 20))
        self.assertIn("Resumo do diagnóstico", texto)
        self.assertIn("Relatório completo do atendimento pendente", texto)
        self.assertIn("Diagnóstico detalhado com todo o histórico do local", texto)

    def test_pdf_os_concluida_mantem_resumo(self):
        relato = "Relatório completo que não deve substituir o resumo da OS concluída."
        self._criar_os_com_relato(21, "OS-0021", "Concluída",
                                  "Resumo do diagnóstico", relato)
        texto = self._texto_pdf(ext.gerar_pdf(self.db, 21))
        self.assertIn("Resumo do diagnóstico", texto)
        self.assertNotIn("Relatório completo que não deve substituir", texto)

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

    def test_pdf_pendente_zero_omite_composicao(self):
        vazia = {"aviso": "", "componentes": [], "total_centavos": 0, "versao": 1}
        with sqlite3.connect(self.db) as c:
            c.execute(
                "UPDATE ordens_servico SET status='Pendente', valor_total=0, "
                "valor_mao_obra=0, valor_materiais=0, data_conclusao=NULL, "
                "composicao_json=? WHERE id=10",
                (json.dumps(vazia),))
        texto = self._texto_pdf(ext.gerar_pdf(self.db, 10))
        self.assertNotIn("COMPOSIÇÃO DO VALOR", texto)
        self.assertIn("VALORES E PAGAMENTO", texto)
        self.assertIn("04 VALORES E PAGAMENTO", texto)

    def test_pdf_pendente_com_valor_mantem_composicao(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE ordens_servico SET status='Pendente', "
                      "data_conclusao=NULL WHERE id=10")
        texto = self._texto_pdf(ext.gerar_pdf(self.db, 10))
        self.assertIn("COMPOSIÇÃO DO VALOR", texto)
        self.assertIn("05 VALORES E PAGAMENTO", texto)

    def test_pdf_respeita_orientacao_exif_da_foto(self):
        imagem = Image.new("RGB", (120, 60), (200, 30, 30))
        exif = Image.Exif()
        exif[274] = 6  # rotação de 90° no EXIF, comum em fotos de celular
        buffer = io.BytesIO()
        imagem.save(buffer, format="JPEG", exif=exif)
        with ext.db(self.db) as conexao:
            ext.registrar_imagem_transacao(
                conexao, 10, None, "foto-celular.jpg", buffer.getvalue(),
                permitir_colaboracao=True)
        caminho = ext.gerar_pdf(self.db, 10)
        from pypdf import PdfReader
        leitor = PdfReader(str(caminho))
        dimensoes = [pagina_imagem.image.size
                     for pagina in leitor.pages for pagina_imagem in pagina.images]
        self.assertIn((60, 120), dimensoes)

    def test_pdf_filename_uses_only_public_number(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE ordens_servico SET numero_os='261107001' WHERE id=10")
        caminho = Path(ext.gerar_pdf(self.db, 10))
        self.assertEqual(caminho.name, '261107001.pdf')
        self.assertNotIn('OS-', caminho.name)

    def test_pdf_inclui_texto_adicional_generico(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE ordens_servico SET texto_adicional=? WHERE id=10",
                      ("Texto livre configurável no relatório.",))
        texto = self._texto_pdf(ext.gerar_pdf(self.db, 10))
        self.assertIn("Texto livre configurável no relatório.", texto)

    def test_composicao_soma_total(self):
        # Garante que a composição da OS-0010 soma exatamente o total.
        self.assertEqual(COMP_OS0010["total_centavos"], 115833)
        self.assertEqual(
            sum(c["valor_centavos"] for c in COMP_OS0010["componentes"]), 115833)


if __name__ == "__main__":
    unittest.main(verbosity=2)
