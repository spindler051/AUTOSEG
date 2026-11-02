"""Testes da fatia de clientes sobre o núcleo Workaholic."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import banco
import cadastros_v9 as cad9
import prestadores_ext as ext
from integracao import clientes
from integracao.clientes import RepositorioClientes
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
