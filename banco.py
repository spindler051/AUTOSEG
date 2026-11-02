"""
Camada de acesso ao banco de dados do Gestão de Serviços.

Centraliza a conexão, a criação/migração das tabelas e funções utilitárias
usadas tanto pelo aplicativo desktop quanto pelo portal web.
"""

import os
import re
import sqlite3
from datetime import datetime


PASTA_APP = os.path.abspath(os.environ.get("AUTOSEG_BASE") or os.path.dirname(os.path.abspath(__file__)))
BANCO = os.environ.get("GESTAO_BANCO", os.path.join(PASTA_APP, "dados.db"))


# ============================================================
# CONEXÃO
# ============================================================

def conectar_banco(caminho=None):
    conexao = sqlite3.connect(caminho or BANCO, timeout=20)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA busy_timeout = 20000")
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


# ============================================================
# CRIAÇÃO E MIGRAÇÃO
# ============================================================

def criar_banco(caminho=None):
    conexao = conectar_banco(caminho)
    cursor = conexao.cursor()

    # WAL permite que o app desktop e o portal web leiam/gravem ao mesmo
    # tempo com muito menos chance de bloqueio.
    try:
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.DatabaseError:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_pessoa TEXT NOT NULL DEFAULT 'Jurídica',
            documento TEXT,
            nome TEXT NOT NULL,
            nome_fantasia TEXT,
            endereco TEXT,
            numero TEXT,
            complemento TEXT,
            bairro TEXT,
            cep TEXT,
            cidade TEXT,
            uf TEXT,
            telefone TEXT,
            email TEXT,
            sindico_nome TEXT,
            sindico_telefone TEXT,
            sindico_email TEXT,
            administradora TEXT,
            administradora_email TEXT,
            administradora_telefone TEXT,
            observacoes TEXT,
            status TEXT NOT NULL DEFAULT 'Ativo',
            criado_em TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordens_servico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_os TEXT UNIQUE,
            cliente_id INTEGER NOT NULL,
            data_abertura TEXT,
            tecnico TEXT,
            descricao TEXT,
            valor_mao_obra REAL DEFAULT 0,
            valor_materiais REAL DEFAULT 0,
            valor_total REAL DEFAULT 0,
            forma_pagamento TEXT DEFAULT 'Outro',
            status TEXT DEFAULT 'Aberta',
            data_conclusao TEXT,
            observacoes TEXT,
            criado_em TEXT,
            origem TEXT NOT NULL DEFAULT 'App',
            urgencia TEXT DEFAULT 'Normal',
            contato_preferido TEXT,
            atualizado_em TEXT,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS materiais_os (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            os_id INTEGER NOT NULL,
            item TEXT NOT NULL,
            quantidade REAL DEFAULT 1,
            valor_unitario REAL DEFAULT 0,
            valor_total REAL DEFAULT 0,
            FOREIGN KEY (os_id) REFERENCES ordens_servico(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financeiro (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            os_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            descricao TEXT,
            valor REAL DEFAULT 0,
            forma_pagamento TEXT,
            status TEXT DEFAULT 'Aguardando pagamento',
            data_lancamento TEXT,
            vencimento TEXT,
            data_pagamento TEXT,
            numero_nota TEXT,
            observacoes TEXT,
            FOREIGN KEY (os_id) REFERENCES ordens_servico(id),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        )
    """)

    conexao.commit()

    # Migração simples para bancos criados em versões anteriores.
    adicionar_coluna_se_nao_existir(cursor, "clientes", "tipo_pessoa", "TEXT NOT NULL DEFAULT 'Jurídica'")
    adicionar_coluna_se_nao_existir(cursor, "clientes", "status", "TEXT NOT NULL DEFAULT 'Ativo'")
    adicionar_coluna_se_nao_existir(cursor, "clientes", "dados_incompletos", "INTEGER NOT NULL DEFAULT 0")
    adicionar_coluna_se_nao_existir(cursor, "ordens_servico", "forma_pagamento", "TEXT DEFAULT 'Outro'")
    adicionar_coluna_se_nao_existir(cursor, "ordens_servico", "data_conclusao", "TEXT")
    adicionar_coluna_se_nao_existir(cursor, "ordens_servico", "observacoes", "TEXT")
    adicionar_coluna_se_nao_existir(cursor, "ordens_servico", "origem", "TEXT NOT NULL DEFAULT 'App'")
    adicionar_coluna_se_nao_existir(cursor, "ordens_servico", "urgencia", "TEXT DEFAULT 'Normal'")
    adicionar_coluna_se_nao_existir(cursor, "ordens_servico", "contato_preferido", "TEXT")
    adicionar_coluna_se_nao_existir(cursor, "ordens_servico", "atualizado_em", "TEXT")
    adicionar_coluna_se_nao_existir(cursor, "ordens_servico", "dados_incompletos", "INTEGER NOT NULL DEFAULT 0")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_os_cliente ON ordens_servico(cliente_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_os_status ON ordens_servico(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_os_origem ON ordens_servico(origem)")

    conexao.commit()
    conexao.close()


def adicionar_coluna_se_nao_existir(cursor, tabela, coluna, definicao):
    cursor.execute(f"PRAGMA table_info({tabela})")
    colunas = [linha["name"] if isinstance(linha, sqlite3.Row) else linha[1] for linha in cursor.fetchall()]

    if coluna not in colunas:
        cursor.execute(
            f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}"
        )


# ============================================================
# NUMERAÇÃO E UTILITÁRIOS
# ============================================================

def proximo_numero_os(cursor):
    cursor.execute("""
        SELECT MAX(CAST(SUBSTR(numero_os, 4) AS INTEGER)) AS maior
        FROM ordens_servico
        WHERE numero_os LIKE 'OS-%'
    """)
    registro = cursor.fetchone()

    try:
        maior = int(registro["maior"] or 0)
    except (TypeError, ValueError, KeyError):
        maior = 0

    return f"OS-{maior + 1:04d}"


def somente_digitos(valor):
    return re.sub(r"\D", "", str(valor or ""))


def normalizar_documento(valor):
    return somente_digitos(valor)


def normalizar_telefone(valor):
    digitos = somente_digitos(valor)

    # Remove o código do país quando o número foi salvo como +55...
    if digitos.startswith("55") and len(digitos) > 11:
        digitos = digitos[2:]

    return digitos


def normalizar_email(valor):
    return str(valor or "").strip().lower()


def agora_banco():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def agora_br():
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def formatar_documento(valor):
    """Devolve CPF/CNPJ formatado quando possível, sem alterar outros valores."""
    digitos = somente_digitos(valor)

    if len(digitos) == 11:
        return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"

    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"

    return str(valor or "").strip()
