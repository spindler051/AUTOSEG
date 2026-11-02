#!/usr/bin/env python3
"""Separa o banco misto em uma base de produção limpa.

Uso:
  python3 scripts/limpar_banco_misto.py --origem dados_misto.db \
      --destino dados_producao_limpa.db --aplicar [--mover-arquivos]

A origem NUNCA é alterada. O destino é uma cópia. Antes de apagar, confira o
relatório e mantenha o backup bruto.

Classificação desta limpeza (revisar antes de rodar em outro banco):
- clientes de teste: 2 (Cond. Palermo) e 4 (pessoa da silva)
- OS de teste: 1-9, 13, 14; reais preservadas: 10, 11, 12
- usuários V9 de teste: 1, 3, 4; Pricila (2) preservada
- organizações V9 de teste: 2 (Palermo) e 444 (Gibraltar duplicada)
- chamados V9 de teste: 1, 2, 3, 4, 6, 7; chamado 5 preservado
"""
import argparse
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

CLIENTES_TESTE = (2, 4)
OS_TESTE = (1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 14)
USUARIOS_TESTE = (1, 3, 4)
ORGS_TESTE = (2, 444)
CHAMADOS_TESTE = (1, 2, 3, 4, 6, 7)
VINCULOS_TESTE = (1, 2, 3)
PRODUTOS_TESTE = (1, 2, 3)

TABELAS_OS = (
    "materiais_os", "financeiro", "os_anexos", "os_atendimentos",
    "os_conclusoes", "os_deslocamentos", "os_documentos", "os_encerramentos",
    "os_entregas", "os_eventos", "os_prestadores", "os_rascunhos_web",
    "os_responsaveis", "os_solicitacoes", "produtividade_deslocamentos",
    "produtividade_email", "produtividade_etapas", "produtividade_rateios",
    "produtividade_repasses", "v9_detalhes_os",
)


def marcar(valores):
    return ",".join(str(int(x)) for x in valores)


def tabela_existe(c, nome):
    return bool(c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)
    ).fetchone())


def contar(c, nome, where="1=1"):
    return c.execute(f"SELECT COUNT(*) FROM {nome} WHERE {where}").fetchone()[0]


def validar(c):
    regras = (
        ("clientes", 2, "palermo"),
        ("clientes", 4, "pessoa da silva"),
    )
    for tabela, ident, trecho in regras:
        row = c.execute(f"SELECT nome FROM {tabela} WHERE id=?", (ident,)).fetchone()
        if not row or trecho not in (row[0] or "").casefold():
            raise SystemExit(f"Abortado: {tabela} id={ident} não confere com '{trecho}'.")
    for ident, trecho in ((1, "cadastro"), (3, "haddad"), (4, "cadastro")):
        row = c.execute("SELECT nome FROM v9_usuarios WHERE id=?", (ident,)).fetchone()
        if not row or trecho not in (row[0] or "").casefold():
            raise SystemExit(f"Abortado: v9_usuarios id={ident} não confere.")


def aplicar(c, mover_arquivos, quarentena):
    ids_os = marcar(OS_TESTE)
    ids_clientes = marcar(CLIENTES_TESTE)
    ids_usuarios = marcar(USUARIOS_TESTE)
    ids_orgs = marcar(ORGS_TESTE)
    ids_chamados = marcar(CHAMADOS_TESTE)
    ids_vinculos = marcar(VINCULOS_TESTE)

    anexos = []
    documentos = []
    if tabela_existe(c, "os_anexos"):
        anexos = [r[0] for r in c.execute(
            f"SELECT id FROM os_anexos WHERE os_id IN ({ids_os})")]
    if tabela_existe(c, "os_documentos"):
        documentos = [r[0] for r in c.execute(
            f"SELECT id FROM os_documentos WHERE os_id IN ({ids_os})")]

    caminhos = []
    if tabela_existe(c, "os_anexos"):
        caminhos += [r[0] for r in c.execute(
            f"SELECT caminho FROM os_anexos WHERE os_id IN ({ids_os})")]
    if tabela_existe(c, "os_documentos"):
        caminhos += [r[0] for r in c.execute(
            f"SELECT caminho FROM os_documentos WHERE os_id IN ({ids_os})")]

    removidos = {}
    c.execute("BEGIN IMMEDIATE")
    try:
        for tabela in TABELAS_OS:
            if tabela_existe(c, tabela):
                removidos[tabela] = c.execute(
                    f"DELETE FROM {tabela} WHERE os_id IN ({ids_os})").rowcount

        if tabela_existe(c, "v9_anexos_visiveis") and anexos:
            removidos["v9_anexos_visiveis"] = c.execute(
                f"DELETE FROM v9_anexos_visiveis WHERE anexo_id IN ({marcar(anexos)})"
            ).rowcount

        if tabela_existe(c, "materiais_os"):
            removidos["materiais_os (placeholder)"] = c.execute(
                "DELETE FROM materiais_os WHERE item='sem uso de material'"
            ).rowcount
        if tabela_existe(c, "estoque_os_aplicacoes"):
            removidos["estoque_os_aplicacoes"] = c.execute(
                f"DELETE FROM estoque_os_aplicacoes WHERE os_id IN ({ids_os}) "
                f"OR produto_id IN ({marcar(PRODUTOS_TESTE)})"
            ).rowcount
        if tabela_existe(c, "estoque_movimentos"):
            removidos["estoque_movimentos"] = c.execute(
                f"DELETE FROM estoque_movimentos WHERE os_id IN ({ids_os})"
            ).rowcount
        if tabela_existe(c, "estoque_produtos") and PRODUTOS_TESTE:
            removidos["estoque_produtos"] = c.execute(
                f"DELETE FROM estoque_produtos WHERE id IN ({marcar(PRODUTOS_TESTE)})"
            ).rowcount

        if tabela_existe(c, "v9_eventos"):
            removidos["v9_eventos"] = c.execute(
                f"DELETE FROM v9_eventos WHERE chamado_id IN ({ids_chamados})"
            ).rowcount
        if tabela_existe(c, "v9_notificacoes"):
            removidos["v9_notificacoes"] = c.execute(
                f"DELETE FROM v9_notificacoes WHERE usuario_id IN ({ids_usuarios}) "
                f"OR chamado_id IN ({ids_chamados})"
            ).rowcount
        if tabela_existe(c, "v9_vinculos"):
            removidos["v9_vinculos"] = c.execute(
                f"DELETE FROM v9_vinculos WHERE id IN ({ids_vinculos})"
            ).rowcount
        if tabela_existe(c, "v9_chamados"):
            removidos["v9_chamados"] = c.execute(
                f"DELETE FROM v9_chamados WHERE id IN ({ids_chamados})"
            ).rowcount
        if tabela_existe(c, "v9_responsaveis"):
            removidos["v9_responsaveis"] = c.execute(
                f"DELETE FROM v9_responsaveis WHERE organizacao_id IN ({ids_orgs})"
            ).rowcount
        if tabela_existe(c, "v9_usuarios"):
            removidos["v9_usuarios"] = c.execute(
                f"DELETE FROM v9_usuarios WHERE id IN ({ids_usuarios})"
            ).rowcount
        if tabela_existe(c, "v9_organizacoes"):
            removidos["v9_organizacoes"] = c.execute(
                f"DELETE FROM v9_organizacoes WHERE id IN ({ids_orgs})"
            ).rowcount
        if tabela_existe(c, "v9_historico_clientes"):
            removidos["v9_historico_clientes"] = c.execute(
                f"DELETE FROM v9_historico_clientes WHERE cliente_id IN ({ids_clientes}) "
                f"OR origem_id IN ({ids_orgs}) "
                "OR descricao IN ('Vínculo 1','Vínculo 2','Vínculo 3')"
            ).rowcount
        if tabela_existe(c, "cliente_acessos"):
            removidos["cliente_acessos"] = c.execute(
                f"DELETE FROM cliente_acessos WHERE cliente_id IN ({ids_clientes})"
            ).rowcount
        if tabela_existe(c, "portal_auditoria"):
            removidos["portal_auditoria"] = c.execute(
                f"DELETE FROM portal_auditoria WHERE referencia IN ({ids_os})"
            ).rowcount
        removidos["ordens_servico"] = c.execute(
            f"DELETE FROM ordens_servico WHERE id IN ({ids_os})").rowcount
        removidos["clientes"] = c.execute(
            f"DELETE FROM clientes WHERE id IN ({ids_clientes})").rowcount
        c.execute("COMMIT")
    except Exception:
        c.execute("ROLLBACK")
        raise

    if mover_arquivos:
        quarentena.mkdir(parents=True, exist_ok=True)
        for caminho in caminhos:
            origem = Path(caminho)
            if not origem.is_file():
                continue
            destino = quarentena / f"{origem.stem}_{datetime.now():%Y%m%d%H%M%S}{origem.suffix}"
            try:
                shutil.move(str(origem), str(destino))
            except OSError as erro:
                print(f"AVISO: não movi {origem}: {erro}")
    return removidos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--origem", required=True)
    parser.add_argument("--destino", required=True)
    parser.add_argument("--quarentena", default="backups/quarentena_limpeza")
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--mover-arquivos", action="store_true")
    args = parser.parse_args()

    origem = Path(args.origem).resolve()
    destino = Path(args.destino).resolve()
    if not origem.is_file():
        raise SystemExit(f"Origem não encontrada: {origem}")
    if destino.exists():
        raise SystemExit(f"Destino já existe: {destino}")
    if not args.aplicar:
        raise SystemExit("Modo seguro: informe --aplicar para criar o destino limpo.")

    shutil.copy2(origem, destino)
    c = sqlite3.connect(destino)
    c.row_factory = sqlite3.Row
    try:
        validar(c)
        removidos = aplicar(
            c, args.mover_arquivos,
            Path(args.quarentena).resolve())
        print("Removidos:")
        for tabela, quantidade in removidos.items():
            if quantidade:
                print(f"  {tabela}: {quantidade}")
        print("\nContagens no destino:")
        for tabela in ("clientes", "ordens_servico", "financeiro", "prestadores",
                       "v9_usuarios", "v9_organizacoes", "v9_chamados",
                       "os_documentos", "os_anexos", "estoque_produtos"):
            if tabela_existe(c, tabela):
                print(f"  {tabela}: {contar(c, tabela)}")
        print(f"\nProdução limpa: {destino}")
        print(f"Origem intacta: {origem}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
