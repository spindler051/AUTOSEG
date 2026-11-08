"""Configurable OS numbering: policy, daily sequence and clock guard.

The policy is data (``numeracao.yaml``), not code. The default for AUTOSEG is
``YYMMDD`` plus a 3-digit daily sequence in ``America/Sao_Paulo``. The engine
does not rewrite existing OS numbers; migration is a separate, reviewed step.
"""
from __future__ import annotations

import os
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PASTA_APP = Path(__file__).resolve().parents[2]
from officina.paths import AUTOSEG_DIR
MODOS = ('date_sequence', 'sequential', 'uuid', 'custom')
ESTILOS = ('numeric', 'letters')
GUARDAS = ('rejeitar', 'avisar')

PADRAO = {
    'versao': 1,
    'modo': 'date_sequence',
    'fuso': 'America/Sao_Paulo',
    'prefixo': '',
    'sufixo': '',
    'separador': '',
    'data': {'formato': '%y%m%d'},
    'sequencia': {'estilo': 'numeric', 'largura': 3, 'maximo_por_dia': 999},
    'custom': {'template': '{data}{sequencia}'},
    'guardas': {'relogio': 'rejeitar'},
}


class ErroNumeracao(ValueError):
    """Invalid policy or impossible number."""


class RelogioInconsistenteError(ErroNumeracao):
    """The machine clock moved backwards relative to the last issued OS."""


class NumeroEsgotadoError(ErroNumeracao):
    """The daily/global sequence reached its configured maximum."""


@dataclass(frozen=True)
class Politica:
    modo: str
    fuso: str
    prefixo: str
    sufixo: str
    separador: str
    formato_data: str
    estilo: str
    largura: int
    maximo_por_dia: int
    template: str
    relogio: str

    def agora(self) -> datetime:
        return datetime.now(ZoneInfo(self.fuso))

    def normalizar(self, quando: datetime | None = None) -> datetime:
        valor = quando or self.agora()
        if valor.tzinfo is None:
            return valor.replace(tzinfo=ZoneInfo(self.fuso))
        return valor.astimezone(ZoneInfo(self.fuso))

    def data_texto(self, quando: datetime | None = None) -> str:
        return self.normalizar(quando).strftime(self.formato_data)

    def compor(self, quando: datetime | None = None, sequencia: int = 1) -> str:
        data = self.data_texto(quando)
        numero_seq = _sequencia(sequencia, self.estilo, self.largura)
        if self.modo == 'date_sequence':
            return f'{self.prefixo}{data}{self.separador}{numero_seq}{self.sufixo}'
        if self.modo == 'sequential':
            return f'{self.prefixo}{numero_seq}{self.sufixo}'
        if self.modo == 'uuid':
            return f'{self.prefixo}{uuid.uuid4().hex}{self.sufixo}'
        return (f'{self.prefixo}'
                + self.template.format(data=data, sequencia=numero_seq,
                                       seq=numero_seq, uuid=uuid.uuid4().hex)
                + self.sufixo)


class PoliticaStore:
    """Keeps the active policy and swaps it atomically on reload."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else _arquivo()
        self._politica = carregar(self.path)
        self.revision = 1

    @property
    def politica(self) -> Politica:
        return self._politica

    def reload(self) -> Politica:
        nova = carregar(self.path)
        self._politica = nova
        self.revision += 1
        return nova


def _arquivo():
    base = os.environ.get('AUTOSEG_BASE')
    if base:
        candidato = Path(base).expanduser() / 'numeracao.yaml'
        if candidato.is_file():
            return candidato
    candidato = AUTOSEG_DIR / 'config' / 'numeracao.yaml'
    return candidato if candidato.is_file() else None


def carregar(path: str | Path | None = None) -> Politica:
    destino = Path(path) if path is not None else _arquivo()
    if destino is None or not destino.is_file():
        return _de_dict(PADRAO)
    try:
        import yaml
        dados = yaml.safe_load(destino.read_text(encoding='utf-8'))
    except Exception as erro:
        raise ErroNumeracao(f'numeracao.yaml inválido ({destino}): {erro}') from erro
    return _de_dict(dados)


def _de_dict(dados) -> Politica:
    if not isinstance(dados, dict) or dados.get('versao') != 1:
        raise ErroNumeracao('numeracao.yaml precisa de versao: 1')
    modo = str(dados.get('modo') or 'date_sequence')
    if modo not in MODOS:
        raise ErroNumeracao(f'modo inválido: {modo}')
    fuso = str(dados.get('fuso') or 'America/Sao_Paulo')
    try:
        ZoneInfo(fuso)
    except ZoneInfoNotFoundError as erro:
        raise ErroNumeracao(f'fuso inválido: {fuso}') from erro
    data_cfg = dados.get('data') or {}
    seq_cfg = dados.get('sequencia') or {}
    custom = dados.get('custom') or {}
    guardas = dados.get('guardas') or {}
    formato = str(data_cfg.get('formato') or '%y%m%d')
    estilo = str(seq_cfg.get('estilo') or 'numeric')
    if estilo not in ESTILOS:
        raise ErroNumeracao(f'estilo de sequência inválido: {estilo}')
    try:
        largura = int(seq_cfg.get('largura', 3))
        maximo = int(seq_cfg.get('maximo_por_dia', 999))
    except (TypeError, ValueError) as erro:
        raise ErroNumeracao('largura/maximo_por_dia inválidos') from erro
    if not 1 <= largura <= 12 or not 1 <= maximo <= 999999999:
        raise ErroNumeracao('largura/maximo_por_dia fora do intervalo')
    template = str(custom.get('template') or '{data}{sequencia}')
    if modo == 'custom' and not any(x in template for x in
                                    ('{data}', '{sequencia}', '{seq}', '{uuid}')):
        raise ErroNumeracao('template custom não contém marcador')
    relogio = str(guardas.get('relogio') or 'rejeitar')
    if relogio not in GUARDAS:
        raise ErroNumeracao(f'guarda de relógio inválida: {relogio}')
    return Politica(
        modo=modo,
        fuso=fuso,
        prefixo=str(dados.get('prefixo') or ''),
        sufixo=str(dados.get('sufixo') or ''),
        separador=str(dados.get('separador') or ''),
        formato_data=formato,
        estilo=estilo,
        largura=largura,
        maximo_por_dia=maximo,
        template=template,
        relogio=relogio,
    )


def _sequencia(valor: int, estilo: str, largura: int) -> str:
    if estilo == 'numeric':
        return str(int(valor)).zfill(largura)
    return _letras(int(valor))


def _letras(valor: int) -> str:
    if valor <= 0:
        return 'A'
    saida = ''
    while valor:
        valor, resto = divmod(valor - 1, 26)
        saida = chr(65 + resto) + saida
    return saida


def estado_ativo(cursor) -> bool:
    """True when a migrated database has the new numbering enabled."""
    tabela = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='numeracao_estado'"
    ).fetchone()
    if not tabela:
        return False
    linha = cursor.execute(
        "SELECT valor FROM numeracao_estado WHERE chave='ativo'").fetchone()
    return bool(linha and str(linha[0]) == '1')


def preview(politica: Politica | None = None,
            quando: datetime | None = None, sequencia: int = 1) -> str:
    return (politica or carregar()).compor(quando, sequencia)


def proximo_numero(cursor, politica: Politica | None = None,
                   quando: datetime | None = None) -> str:
    """Reserve and format the next number using the caller's transaction.

    The caller must already be inside a transaction. This function never uses
    ``MAX(numero_os)+1``; it updates ``numeracao_sequencias`` under SQLite's
    write lock.
    """
    p = politica or carregar()
    momento = p.normalizar(quando)
    cursor.execute('''CREATE TABLE IF NOT EXISTS numeracao_sequencias(
        escopo TEXT NOT NULL, periodo TEXT NOT NULL, proximo INTEGER NOT NULL,
        atualizado_em TEXT NOT NULL, PRIMARY KEY(escopo, periodo))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS numeracao_meta(
        escopo TEXT PRIMARY KEY, ultimo_dia TEXT, ultimo_valor INTEGER,
        atualizado_em TEXT NOT NULL)''')

    if p.modo == 'uuid':
        return p.compor(momento)

    data_iso = momento.date().isoformat()
    meta = cursor.execute(
        "SELECT ultimo_dia FROM numeracao_meta WHERE escopo='os'").fetchone()
    if meta and meta[0] and data_iso < str(meta[0]):
        mensagem = (
            'O relógio do computador está atrasado em relação à última OS '
            'emitida. Corrija data/hora antes de emitir. Em modo local com '
            'sincronização, use o horário confiável do servidor.')
        if p.relogio == 'rejeitar':
            raise RelogioInconsistenteError(mensagem)
        warnings.warn(mensagem, RuntimeWarning)

    periodo = p.data_texto(momento) if p.modo != 'sequential' else 'global'
    linha = cursor.execute(
        'SELECT proximo FROM numeracao_sequencias WHERE escopo=? AND periodo=?',
        ('os', periodo)).fetchone()
    sequencia = int(linha[0]) if linha else 1
    if p.modo != 'uuid' and sequencia > p.maximo_por_dia:
        raise NumeroEsgotadoError(
            f'Limite de {p.maximo_por_dia} OS por dia atingido em {periodo}.')
    numero = p.compor(momento, sequencia)
    agora = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    if linha:
        cursor.execute(
            'UPDATE numeracao_sequencias SET proximo=?, atualizado_em=? '
            'WHERE escopo=? AND periodo=?',
            (sequencia + 1, agora, 'os', periodo))
    else:
        cursor.execute(
            'INSERT INTO numeracao_sequencias(escopo,periodo,proximo,atualizado_em) '
            'VALUES(?,?,?,?)', ('os', periodo, 2, agora))
    cursor.execute(
        '''INSERT INTO numeracao_meta(escopo,ultimo_dia,ultimo_valor,atualizado_em)
           VALUES('os',?,?,?)
           ON CONFLICT(escopo) DO UPDATE SET
             ultimo_dia=CASE
               WHEN excluded.ultimo_dia > COALESCE(numeracao_meta.ultimo_dia,'')
               THEN excluded.ultimo_dia ELSE numeracao_meta.ultimo_dia END,
             ultimo_valor=excluded.ultimo_valor,
             atualizado_em=excluded.atualizado_em''',
        (data_iso, sequencia, agora))
    return numero
