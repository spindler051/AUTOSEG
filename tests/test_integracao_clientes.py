"""Testes da fatia de clientes sobre o núcleo Workaholic."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from officina.core import banco
from officina.core import cadastros_v9 as cad9
from officina.core import prestadores_ext as ext
from officina.integration import clientes
from officina.integration.clientes import RepositorioClientes
from workaholic.domain.errors import ConflictError


class ClientesWorkaholicTest(unittest.TestCase):
    def setUp(self):
        os.environ.pop("AUTOSEG_BASE", None)
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "teste.db"
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        cad9.instalar(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def criar(self, **dados):
        base = {
            "tipo_pessoa": "Jurídica",
            "documento": "",
            "nome": "Condomínio Alfa",
            "status": "Ativo",
        }
        base.update(dados)
        return clientes.salvar(None, base, banco=self.db)

    def test_criar_e_obter(self):
        registro = self.criar()
        self.assertTrue(registro["id"].isdigit())
        self.assertEqual(registro["version"], 1)
        self.assertEqual(registro["fields"]["nome"], "Condomínio Alfa")
        self.assertFalse(registro["fields"]["dados_incompletos"])
        obtido = clientes.obter(registro["id"], banco=self.db)
        self.assertEqual(obtido["fields"]["nome"], "Condomínio Alfa")
        self.assertEqual(obtido["version"], 1)

    def test_incompleto_permitido(self):
        registro = self.criar(nome="")
        self.assertTrue(registro["fields"]["dados_incompletos"])

    def test_atualizar_incrementa_versao(self):
        registro = self.criar()
        atualizado = clientes.salvar(
            registro["id"],
            {"tipo_pessoa": "Jurídica", "documento": "",
             "nome": "Condomínio Beta", "status": "Ativo"},
            banco=self.db)
        self.assertEqual(atualizado["version"], 2)
        self.assertEqual(atualizado["fields"]["nome"], "Condomínio Beta")
        self.assertEqual(clientes.obter(registro["id"], banco=self.db)["version"], 2)

    def test_documento_invalido(self):
        with self.assertRaises(clientes.ErroCliente) as contexto:
            self.criar(tipo_pessoa="Física", documento="123")
        self.assertEqual(contexto.exception.titulo, "Documento inválido")

    def test_documento_duplicado(self):
        self.criar(tipo_pessoa="Física", documento="529.982.247-25")
        with self.assertRaises(clientes.ErroCliente) as contexto:
            self.criar(nome="Outro", tipo_pessoa="Física",
                       documento="52998224725")
        self.assertEqual(contexto.exception.titulo, "Documento duplicado")

    def test_listar_filtra_nome_documento_cidade(self):
        self.criar(nome="Alfa", cidade="Porto Alegre")
        self.criar(nome="Beta", cidade="Canoas")
        self.assertEqual([r["fields"]["nome"] for r in
                          clientes.listar("porto", banco=self.db)], ["Alfa"])
        self.assertEqual(len(clientes.listar(banco=self.db)), 2)

    def test_listar_paginado_preserva_busca_e_paginacao(self):
        self.criar(nome="Alfa", cidade="Porto Alegre", email="alfa@example.org")
        self.criar(nome="Beta", tipo_pessoa="Física",
                   documento="529.982.247-25", cidade="Canoas",
                   email="beta@example.org")
        self.criar(nome="Gama", cidade="Porto Alegre", status="Inativo")
        total, linhas = clientes.listar_paginado("porto", 1, 0, banco=self.db)
        self.assertEqual(total, 2)
        self.assertEqual([x["nome"] for x in linhas], ["Alfa"])
        total, linhas = clientes.listar_paginado("529982", 10, 0, banco=self.db)
        self.assertEqual([x["nome"] for x in linhas], ["Beta"])
        total, linhas = clientes.listar_paginado("beta@example", 10, 0, banco=self.db)
        self.assertEqual([x["nome"] for x in linhas], ["Beta"])
        total, linhas = clientes.listar_paginado("", 2, 0, banco=self.db)
        self.assertEqual(total, 3)
        self.assertEqual(len(linhas), 2)
        total, linhas = clientes.listar_paginado("", 2, 2, banco=self.db)
        self.assertEqual(len(linhas), 1)

    def test_contar_listas_e_obtencoes_legadas(self):
        self.criar(nome="Alfa", cidade="Porto Alegre", email="alfa@example.org",
                   observacoes="Observação de teste")
        beta = self.criar(nome="Beta", cidade="Canoas")
        self.criar(nome="Gama", status="Inativo")
        self.assertEqual(clientes.contar_ativos(banco=self.db), 2)
        selecao = clientes.listar_para_selecao(banco=self.db, limite=10)
        self.assertEqual([x["nome"] for x in selecao], ["Alfa", "Beta"])
        para_os = clientes.listar_para_os(banco=self.db)
        self.assertEqual([x["nome"] for x in para_os], ["Alfa", "Beta"])
        self.assertIn("endereco", para_os[0])
        linha = clientes.obter_linha(beta["id"], banco=self.db)
        self.assertEqual(linha["nome"], "Beta")
        self.assertIn("observacoes", linha)
        orcamento = clientes.obter_para_orcamento(beta["id"], banco=self.db)
        self.assertEqual(orcamento["nome"], "Beta")
        inativo = clientes.listar("Gama", banco=self.db)[0]
        self.assertIsNone(clientes.obter_para_orcamento(inativo["id"], banco=self.db))
        resumo = clientes.obter_resumo_ativo(beta["id"], banco=self.db)
        self.assertEqual(resumo["nome"], "Beta")
        self.assertIsNone(clientes.obter_resumo_ativo(inativo["id"], banco=self.db))
        rapida = clientes.buscar_rapida("canoas", banco=self.db, limite=10)
        self.assertEqual([x["nome"] for x in rapida], ["Beta"])
        todas = clientes.buscar_rapida("", banco=self.db, limite=10)
        self.assertEqual([x["nome"] for x in todas], ["Alfa", "Beta"])

    def test_cliente_pj_sincroniza_organizacao(self):
        self.criar(nome="Condomínio Central", tipo_pessoa="Jurídica",
                   documento="11.222.333/0001-81")
        conexao = sqlite3.connect(self.db)
        try:
            linha = conexao.execute(
                "SELECT cliente_id,cnpj FROM v9_organizacoes WHERE cliente_id=1"
            ).fetchone()
        finally:
            conexao.close()
        self.assertIsNotNone(linha)
        self.assertEqual(linha[1], "11222333000181")

    def test_bloqueio_otimista(self):
        registro = self.criar()
        repositorio = RepositorioClientes(self.db)
        antigo = repositorio.get("cliente", registro["id"])
        novo = repositorio.get("cliente", registro["id"])
        novo["fields"]["nome"] = "Primeira alteração"
        repositorio.put("cliente", novo, expected_version=1)
        with self.assertRaises(ConflictError):
            repositorio.put("cliente", antigo, expected_version=1)


if __name__ == "__main__":
    unittest.main()
