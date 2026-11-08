"""One-time migration from legacy OS numbers to the configured numbering."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from officina.core.numeracao import ErroNumeracao, Politica, carregar


class ErroMigracao(ErroNumeracao):
    pass


def _momento(criado_em, data_abertura, fuso: str) -> datetime:
    texto = str(criado_em or '').strip()
    valor = None
    if texto:
        try:
            valor = datetime.fromisoformat(texto.replace('Z', '+00:00'))
        except ValueError:
            valor = None
    if valor is None:
        texto = str(data_abertura or '').strip()
        for formato in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
                        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M'):
            try:
                valor = datetime.strptime(texto[:19], formato)
                break
            except ValueError:
                continue
    if valor is None:
        raise ErroMigracao(f'data inválida: criado_em={criado_em!r} data_abertura={data_abertura!r}')
    if valor.tzinfo is None:
        return valor.replace(tzinfo=ZoneInfo(fuso))
    return valor.astimezone(ZoneInfo(fuso))


def _tabela_existe(cursor, nome: str) -> bool:
    return bool(cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nome,)).fetchone())


def _colunas(cursor, tabela: str) -> set[str]:
    return {linha[1] for linha in cursor.execute(f'PRAGMA table_info({tabela})')}


def planejar(banco, politica: Politica | None = None) -> dict:
    p = politica or carregar()
    caminho = Path(banco).expanduser()
    conexao = sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)
    conexao.row_factory = sqlite3.Row
    try:
        if _tabela_existe(conexao, 'numeracao_estado'):
            linha = conexao.execute(
                "SELECT valor FROM numeracao_estado WHERE chave='ativo'").fetchone()
            if linha and str(linha[0]) == '1':
                return {'db': str(caminho), 'ja_migrado': True, 'plano': [],
                        'erros': [], 'duplicados': []}
        linhas = conexao.execute(
            'SELECT id,numero_os,criado_em,data_abertura '
            'FROM ordens_servico ORDER BY id').fetchall()
    finally:
        conexao.close()

    legados = []
    erros = []
    for linha in linhas:
        numero = str(linha['numero_os'] or '')
        if not numero.startswith('OS-'):
            erros.append(
                f"id {linha['id']}: número não legado ({numero!r}); migração abortada")
            continue
        try:
            momento = _momento(linha['criado_em'], linha['data_abertura'], p.fuso)
        except ErroMigracao as erro:
            erros.append(f"id {linha['id']}: {erro}")
            continue
        legados.append((linha, momento))
    if erros:
        return {'db': str(caminho), 'ja_migrado': False, 'plano': [],
                'erros': erros, 'duplicados': []}

    legados.sort(key=lambda item: (str(item[0]['criado_em'] or ''), int(item[0]['id'])))
    por_dia = defaultdict(list)
    for linha, momento in legados:
        por_dia[momento.date().isoformat()].append((linha, momento))

    plano = []
    duplicados = []
    for dia in sorted(por_dia):
        registros = por_dia[dia]
        if len(registros) > p.maximo_por_dia:
            erros.append(f'{dia}: {len(registros)} OS excedem {p.maximo_por_dia}')
            continue
        for sequencia, (linha, momento) in enumerate(registros, start=1):
            periodo = (p.data_texto(momento)
                       if p.modo != 'sequential' else 'global')
            novo = p.compor(momento, sequencia)
            plano.append({
                'id': int(linha['id']),
                'antigo': str(linha['numero_os']),
                'novo': novo,
                'dia': dia,
                'periodo': periodo,
                'sequencia': sequencia,
                'criado_em': str(linha['criado_em'] or ''),
            })
    vistos = set()
    for item in plano:
        if item['novo'] in vistos:
            duplicados.append(item['novo'])
        vistos.add(item['novo'])
    return {'db': str(caminho), 'ja_migrado': False, 'plano': plano,
            'erros': erros, 'duplicados': duplicados}


def migrar(banco, politica: Politica | None = None, backup=True,
           dry_run=True) -> dict:
    caminho = Path(banco).expanduser()
    relatorio = planejar(caminho, politica)
    if relatorio['erros'] or relatorio['duplicados']:
        raise ErroMigracao('; '.join(relatorio['erros'] or relatorio['duplicados']))
    if relatorio['ja_migrado'] or dry_run:
        return relatorio

    backup_path = None
    if backup:
        carimbo = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = caminho.with_name(f'{caminho.name}.bak.{carimbo}')
        origem = sqlite3.connect(caminho)
        destino = sqlite3.connect(backup_path)
        try:
            origem.backup(destino)
        finally:
            destino.close()
            origem.close()

    p = politica or carregar()
    conexao = sqlite3.connect(caminho, timeout=20)
    conexao.row_factory = sqlite3.Row
    try:
        conexao.execute('PRAGMA foreign_keys = ON')
        conexao.execute('BEGIN IMMEDIATE')
        if _tabela_existe(conexao, 'numeracao_estado'):
            linha = conexao.execute(
                "SELECT valor FROM numeracao_estado WHERE chave='ativo'").fetchone()
            if linha and str(linha[0]) == '1':
                conexao.rollback()
                relatorio['ja_migrado'] = True
                relatorio['backup'] = str(backup_path) if backup_path else ''
                return relatorio
        _garantir_schema(conexao)
        agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for item in relatorio['plano']:
            alterou = conexao.execute(
                'UPDATE ordens_servico SET numero_os=?, numero_os_legado=?, '
                'numero_os_emitido_em=? WHERE id=? AND numero_os=?',
                (item['novo'], item['antigo'], item['criado_em'] or agora,
                 item['id'], item['antigo'])).rowcount
            if alterou != 1:
                raise ErroMigracao(
                    f"OS {item['id']} mudou durante a migração; rollback")
            conexao.execute(
                'INSERT OR IGNORE INTO os_numero_alias(alias,os_id,criado_em,origem) '
                'VALUES(?,?,?,?)',
                (item['antigo'], item['id'], agora, 'migracao'))

        if p.modo != 'uuid':
            ultimos = {}
            for item in relatorio['plano']:
                ultimos[item['periodo']] = max(
                    ultimos.get(item['periodo'], 0), item['sequencia'])
            for periodo, sequencia in ultimos.items():
                conexao.execute(
                    'INSERT OR REPLACE INTO numeracao_sequencias'
                    '(escopo,periodo,proximo,atualizado_em) VALUES(?,?,?,?)',
                    ('os', periodo, sequencia + 1, agora))
            ultimo = relatorio['plano'][-1]
            conexao.execute(
                '''INSERT INTO numeracao_meta(escopo,ultimo_dia,ultimo_valor,atualizado_em)
                   VALUES('os',?,?,?)
                   ON CONFLICT(escopo) DO UPDATE SET
                     ultimo_dia=excluded.ultimo_dia,
                     ultimo_valor=excluded.ultimo_valor,
                     atualizado_em=excluded.atualizado_em''',
                (ultimo['dia'], ultimo['sequencia'], agora))

        conexao.execute(
            "INSERT OR REPLACE INTO numeracao_estado(chave,valor) VALUES('ativo','1')")
        conexao.execute(
            "INSERT OR REPLACE INTO numeracao_estado(chave,valor) VALUES('migrado_em',?)",
            (agora,))
        conexao.execute(
            "INSERT OR REPLACE INTO numeracao_estado(chave,valor) VALUES('politica_modo',?)",
            (p.modo,))

        total = conexao.execute('SELECT COUNT(*) FROM ordens_servico').fetchone()[0]
        distintos = conexao.execute(
            'SELECT COUNT(DISTINCT numero_os) FROM ordens_servico').fetchone()[0]
        legados = conexao.execute(
            'SELECT COUNT(*) FROM ordens_servico WHERE numero_os_legado IS NOT NULL').fetchone()[0]
        aliases = conexao.execute('SELECT COUNT(*) FROM os_numero_alias').fetchone()[0]
        if not (total == distintos == len(relatorio['plano'])
                == legados == aliases):
            raise ErroMigracao(
                f'validação falhou: total={total} distintos={distintos} '
                f'plano={len(relatorio["plano"])} legados={legados} aliases={aliases}')
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()
    relatorio['backup'] = str(backup_path) if backup_path else ''
    return relatorio


def _garantir_schema(conexao) -> None:
    for coluna, definicao in (
        ('numero_os_legado', 'TEXT'),
        ('numero_os_emitido_em', 'TEXT'),
        ('numero_policy_id', 'INTEGER'),
    ):
        if coluna not in _colunas(conexao, 'ordens_servico'):
            conexao.execute(
                f'ALTER TABLE ordens_servico ADD COLUMN {coluna} {definicao}')
    conexao.execute('''CREATE TABLE IF NOT EXISTS os_numero_alias(
        alias TEXT PRIMARY KEY, os_id INTEGER NOT NULL,
        criado_em TEXT NOT NULL, origem TEXT NOT NULL DEFAULT 'migracao')''')
    conexao.execute('''CREATE TABLE IF NOT EXISTS numeracao_sequencias(
        escopo TEXT NOT NULL, periodo TEXT NOT NULL, proximo INTEGER NOT NULL,
        atualizado_em TEXT NOT NULL, PRIMARY KEY(escopo, periodo))''')
    conexao.execute('''CREATE TABLE IF NOT EXISTS numeracao_meta(
        escopo TEXT PRIMARY KEY, ultimo_dia TEXT, ultimo_valor INTEGER,
        atualizado_em TEXT NOT NULL)''')
    conexao.execute('''CREATE TABLE IF NOT EXISTS numeracao_estado(
        chave TEXT PRIMARY KEY, valor TEXT NOT NULL)''')
