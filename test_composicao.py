"""Testes do motor de composição configurável do valor."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import composicao


class ComposicaoTest(unittest.TestCase):
    def setUp(self):
        self.anterior = os.environ.get("AUTOSEG_BASE")
        self.pasta = tempfile.TemporaryDirectory()
        os.environ["AUTOSEG_BASE"] = self.pasta.name
        composicao.instalar()

    def tearDown(self):
        if self.anterior is None:
            os.environ.pop("AUTOSEG_BASE", None)
        else:
            os.environ["AUTOSEG_BASE"] = self.anterior
        self.pasta.cleanup()

    def test_exemplo_200(self):
        comp = composicao.calcular(total_centavos=20000, materiais_centavos=0, horas=1)
        valores = {x["nome"]: x["valor_centavos"] for x in comp["componentes"]}
        self.assertEqual(comp["total_centavos"], 20000)
        self.assertEqual(sum(valores.values()), 20000)
        self.assertEqual(valores["Materiais"], 0)
        self.assertEqual(valores["Mão de obra / hora técnica"], 10000)
        self.assertEqual(valores["Taxa mínima de visita"], 3000)
        self.assertEqual(valores["Custos administrativos"], 2000)
        self.assertEqual(valores["Custos operacionais e tecnológicos"], 2000)
        self.assertEqual(valores["Margem de risco e contingência"], 1000)
        self.assertEqual(valores["Outros custos e margem de contribuição"], 2000)

    def test_sem_materiais_todos_os_componentes(self):
        comp = composicao.calcular(total_centavos=20000, materiais_centavos=0, horas=1)
        self.assertEqual(len(comp["componentes"]), 7)
        self.assertTrue(all("valor_centavos" in item for item in comp["componentes"]))
        self.assertTrue(all(item["valor_centavos"] >= 0 for item in comp["componentes"]))

    def test_total_calculado_sem_valor_final(self):
        comp = composicao.calcular(materiais_centavos=0, horas=1)
        self.assertEqual(comp["total_centavos"], 17333)
        self.assertEqual(sum(x["valor_centavos"] for x in comp["componentes"]), 17333)

    def test_total_menor_que_componentes_fixos(self):
        comp = composicao.calcular(total_centavos=10000, materiais_centavos=0, horas=1)
        self.assertEqual(comp["total_centavos"], 10000)
        self.assertEqual(sum(x["valor_centavos"] for x in comp["componentes"]), 10000)
        self.assertTrue(comp["aviso"])

    def test_configuracao_em_runtime(self):
        config = composicao.carregar()
        config["componentes"].append({
            "id": "teste_runtime",
            "nome": "Componente novo",
            "modo": "fixo",
            "valor": 1000,
            "ativo": True,
            "obrigatorio": False,
            "ordem": 8,
            "aplicavel_a": [],
        })
        composicao.salvar(config)
        comp = composicao.calcular(total_centavos=20000, materiais_centavos=0, horas=1)
        self.assertIn("Componente novo", [x["nome"] for x in comp["componentes"]])
        self.assertEqual(sum(x["valor_centavos"] for x in comp["componentes"]), 20000)

    def test_componente_inativo(self):
        config = composicao.carregar()
        for componente in config["componentes"]:
            if componente["id"] == "visita":
                componente["ativo"] = False
        composicao.salvar(config)
        comp = composicao.calcular(total_centavos=20000, materiais_centavos=0, horas=1)
        self.assertNotIn("Taxa mínima de visita", [x["nome"] for x in comp["componentes"]])

    def test_formula(self):
        config = {
            "versao": 1,
            "componentes": [
                {"id": "base", "nome": "Base", "modo": "fixo", "valor": 10000,
                 "ordem": 1, "ativo": True},
                {"id": "formula", "nome": "Fórmula", "modo": "formula",
                 "formula": "base * 0.1", "ordem": 2, "ativo": True},
                {"id": "resto", "nome": "Resto", "modo": "residual",
                 "ordem": 3, "ativo": True},
            ],
        }
        composicao.salvar(config)
        comp = composicao.calcular(total_centavos=20000, materiais_centavos=0, horas=0)
        valores = {x["id"]: x["valor_centavos"] for x in comp["componentes"]}
        self.assertEqual(valores["base"], 10000)
        self.assertEqual(valores["formula"], 1000)
        self.assertEqual(valores["resto"], 9000)
        self.assertEqual(sum(valores.values()), 20000)

    def test_aplicavel_por_tipo(self):
        config = {
            "versao": 1,
            "componentes": [
                {"id": "base", "nome": "Base", "modo": "fixo", "valor": 1000,
                 "ordem": 1, "ativo": True},
                {"id": "portao", "nome": "Portão", "modo": "fixo", "valor": 2000,
                 "ordem": 2, "ativo": True, "aplicavel_a": ["Portão automático"]},
                {"id": "resto", "nome": "Resto", "modo": "residual",
                 "ordem": 3, "ativo": True},
            ],
        }
        composicao.salvar(config)
        com_portao = composicao.calcular(total_centavos=10000, tipo_servico="Portão automático")
        sem_portao = composicao.calcular(total_centavos=10000, tipo_servico="Outro")
        self.assertIn("Portão", [x["nome"] for x in com_portao["componentes"]])
        self.assertNotIn("Portão", [x["nome"] for x in sem_portao["componentes"]])
        self.assertEqual(sum(x["valor_centavos"] for x in com_portao["componentes"]), 10000)
        self.assertEqual(sum(x["valor_centavos"] for x in sem_portao["componentes"]), 10000)

    def test_arredondamento_percentual(self):
        config = {
            "versao": 1,
            "componentes": [
                {"id": "a", "nome": "A", "modo": "percentual", "valor": 33.33,
                 "ordem": 1, "ativo": True},
                {"id": "b", "nome": "B", "modo": "percentual", "valor": 33.33,
                 "ordem": 2, "ativo": True},
                {"id": "c", "nome": "C", "modo": "percentual", "valor": 33.34,
                 "ordem": 3, "ativo": True},
            ],
        }
        composicao.salvar(config)
        comp = composicao.calcular(total_centavos=10000, materiais_centavos=0, horas=0)
        self.assertEqual(sum(x["valor_centavos"] for x in comp["componentes"]), 10000)

    def test_json_ida_e_volta(self):
        comp = composicao.calcular(total_centavos=20000, materiais_centavos=0, horas=1)
        texto = composicao.para_json(comp)
        self.assertEqual(composicao.de_json(texto), comp)
        self.assertEqual(composicao.de_json("inválido"), None)

    def test_validacao_rejeita_componente_vazio(self):
        with self.assertRaises(ValueError):
            composicao.salvar({"versao": 1, "componentes": []})


class ComposicaoBancoTest(unittest.TestCase):
    def setUp(self):
        self.anterior = os.environ.get("AUTOSEG_BASE")
        self.pasta = tempfile.TemporaryDirectory()
        os.environ["AUTOSEG_BASE"] = self.pasta.name
        composicao.instalar()
        self.db = Path(self.pasta.name) / "teste.db"
        import banco
        import prestadores_ext as ext
        import catalogo_servicos as catalogo
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        catalogo.instalar(self.db)
        composicao.instalar_banco(self.db)
        self.catalogo = catalogo

    def tearDown(self):
        if self.anterior is None:
            os.environ.pop("AUTOSEG_BASE", None)
        else:
            os.environ["AUTOSEG_BASE"] = self.anterior
        self.pasta.cleanup()

    def test_servico_persiste_composicao(self):
        identificador = self.catalogo.salvar(self.db, {
            "nome": "Portão automático",
            "descricao": "Ajuste",
            "preco_servico": "200,00",
            "tempo_horas": "1",
            "materiais": "",
        })
        servico = self.catalogo.obter(self.db, identificador)
        comp = json.loads(servico["composicao_json"])
        self.assertEqual(comp["total_centavos"], 20000)
        self.assertEqual(sum(x["valor_centavos"] for x in comp["componentes"]), 20000)
        with sqlite3.connect(self.db) as conexao:
            self.assertEqual(
                conexao.execute("SELECT tempo_horas FROM catalogo_servicos WHERE id=?",
                                (identificador,)).fetchone()[0], 1.0)

    def test_recalcular_tudo_apos_mudanca_de_configuracao(self):
        identificador = self.catalogo.salvar(self.db, {
            "nome": "Portão automático",
            "descricao": "Ajuste",
            "preco_servico": "200,00",
            "tempo_horas": "1",
            "materiais": "",
        })
        config = composicao.carregar()
        for componente in config["componentes"]:
            if componente["id"] == "visita":
                componente["ativo"] = False
        composicao.salvar(config)
        totais = composicao.recalcular_tudo(self.db)
        self.assertEqual(totais["servicos"], 1)
        servico = self.catalogo.obter(self.db, identificador)
        comp = json.loads(servico["composicao_json"])
        self.assertNotIn("Taxa mínima de visita",
                         [item["nome"] for item in comp["componentes"]])
        self.assertEqual(comp["total_centavos"], 20000)
        self.assertEqual(sum(item["valor_centavos"] for item in comp["componentes"]), 20000)


if __name__ == "__main__":
    unittest.main()
