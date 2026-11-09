"""Provider authentication and revocable desktop sessions."""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from datetime import datetime, timedelta

from officina.core import cadastros_v9 as cad9
from officina.core import prestadores_ext as ext
TOKEN_PREFIX = 'autoseg_desk_'
SESSAO_CURTA = timedelta(hours=12)
SESSAO_LEMBRADA = timedelta(days=30)
MAX_FALHAS = 10
JANELA_FALHAS = 600

_FALHAS: dict[str, list[float]] = {}
_LOCK = threading.Lock()


class MuitasTentativasError(ValueError):
    """Raised when the same origin fails login too many times."""


def instalar(banco) -> None:
    with ext.db(banco) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS desktop_sessoes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prestador_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            criado_em TEXT NOT NULL,
            expira_em TEXT NOT NULL,
            ultimo_uso_em TEXT,
            revogado_em TEXT,
            lembrar INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(prestador_id) REFERENCES prestadores(id)
        );
        CREATE INDEX IF NOT EXISTS idx_desktop_sessoes_token
            ON desktop_sessoes(token_hash, id);
        ''')


TEMAS = ('auto', 'claro', 'escuro')
ACENTOS = ('ambar', 'azul', 'verde', 'vermelho', 'roxo', 'ciano', 'laranja')


def _instalar_preferencias(banco) -> None:
    with ext.db(banco) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS portal_preferencias(
            prestador_id INTEGER PRIMARY KEY,
            tema TEXT NOT NULL DEFAULT 'auto',
            acento TEXT NOT NULL DEFAULT 'ambar',
            atualizado_em TEXT NOT NULL
        )""")


def obter_preferencias(banco, prestador_id) -> dict:
    _instalar_preferencias(banco)
    with ext.db(banco) as c:
        linha = c.execute(
            'SELECT tema,acento FROM portal_preferencias WHERE prestador_id=?',
            (int(prestador_id),)).fetchone()
    if not linha:
        return {'tema': 'auto', 'acento': 'ambar'}
    return {
        'tema': linha['tema'] if linha['tema'] in TEMAS else 'auto',
        'acento': linha['acento'] if linha['acento'] in ACENTOS else 'ambar',
    }


def salvar_preferencias(banco, prestador_id, tema, acento) -> dict:
    tema = str(tema or 'auto').strip()
    acento = str(acento or 'ambar').strip()
    if tema not in TEMAS:
        tema = 'auto'
    if acento not in ACENTOS:
        acento = 'ambar'
    _instalar_preferencias(banco)
    with ext.db(banco) as c:
        c.execute("""INSERT INTO portal_preferencias(prestador_id,tema,acento,atualizado_em)
            VALUES(?,?,?,?) ON CONFLICT(prestador_id) DO UPDATE SET
            tema=excluded.tema,acento=excluded.acento,atualizado_em=excluded.atualizado_em""",
            (int(prestador_id), tema, acento, ext.agora()))
    return {'tema': tema, 'acento': acento}


def _agora() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _hash(token: str) -> str:
    return hashlib.sha256(str(token).encode('utf-8')).hexdigest()


def autenticar_local(banco, email: str, senha: str) -> dict | None:
    """Validate one provider against the local/server database."""
    pessoa = ext.autenticar(banco, str(email or ''), str(senha or ''))
    if not pessoa or pessoa.get('excluido'):
        return None
    return {
        'id': int(pessoa['id']),
        'nome': str(pessoa['nome'] or ''),
        'email': str(pessoa['email'] or ''),
        'admin': bool(cad9.prestador_admin(banco, pessoa['id'])),
    }


def criar_primeiro_admin(banco, nome: str, email: str, senha: str) -> dict:
    with ext.db(banco) as c:
        if c.execute('SELECT 1 FROM prestadores WHERE excluido=0 LIMIT 1').fetchone():
            raise ValueError('Já existe prestador cadastrado neste banco.')
    pid = ext.cadastrar(banco, nome=nome, email=email, senha=senha)
    cad9.definir_admin(banco, pid, True)
    pessoa = autenticar_local(banco, email, senha)
    if not pessoa:
        raise ValueError('Não foi possível validar o administrador criado.')
    return pessoa


def _podar_falhas() -> None:
    agora = time.time()
    for chave, marcas in list(_FALHAS.items()):
        recentes = [t for t in marcas if agora - t < JANELA_FALHAS]
        if recentes:
            _FALHAS[chave] = recentes
        else:
            _FALHAS.pop(chave, None)


def _falhas(chave: str) -> list[float]:
    agora = time.time()
    return [t for t in _FALHAS.get(chave, []) if agora - t < JANELA_FALHAS]


def login(banco, email: str, senha: str, lembrar: bool = False,
          origem: str = '') -> dict:
    """Authenticate and issue a revocable session token."""
    email = str(email or '').strip().lower()
    chave = f'{origem}:{email}'
    with _LOCK:
        falhas = _falhas(chave)
        if len(falhas) >= MAX_FALHAS:
            raise MuitasTentativasError(
                'Muitas tentativas. Aguarde alguns minutos.')
    pessoa = autenticar_local(banco, email, senha)
    if not pessoa:
        with _LOCK:
            _FALHAS[chave] = falhas + [time.time()]
            if len(_FALHAS) > 2000:
                _podar_falhas()
        return None
    with _LOCK:
        _FALHAS.pop(chave, None)
    token = TOKEN_PREFIX + secrets.token_urlsafe(36)
    validade = SESSAO_LEMBRADA if lembrar else SESSAO_CURTA
    expira = (datetime.now() + validade).strftime('%Y-%m-%d %H:%M:%S')
    with ext.db(banco) as c:
        c.execute(
            '''INSERT INTO desktop_sessoes
               (prestador_id,token_hash,criado_em,expira_em,lembrar)
               VALUES(?,?,?,?,?)''',
            (pessoa['id'], _hash(token), _agora(), expira, 1 if lembrar else 0))
    return {'token': token, 'expira_em': expira, 'prestador': pessoa}


def _token_bearer(authorization: str) -> str:
    texto = str(authorization or '').strip()
    if not texto.lower().startswith('bearer '):
        return ''
    token = texto[7:].strip()
    return token if token.startswith(TOKEN_PREFIX) else ''


def validar_sessao(banco, authorization: str) -> dict | None:
    token = _token_bearer(authorization)
    if not token:
        return None
    token_hash = _hash(token)
    with ext.db(banco) as c:
        row = c.execute(
            '''SELECT s.id,s.prestador_id,s.expira_em,p.nome,p.email
               FROM desktop_sessoes s
               JOIN prestadores p ON p.id=s.prestador_id
               WHERE s.token_hash=? AND s.revogado_em IS NULL
                 AND s.expira_em>? AND p.ativo=1 AND p.excluido=0''',
            (token_hash, _agora())).fetchone()
        if not row:
            return None
        c.execute('UPDATE desktop_sessoes SET ultimo_uso_em=? WHERE id=?',
                  (_agora(), row['id']))
    return {
        'id': int(row['prestador_id']),
        'nome': str(row['nome'] or ''),
        'email': str(row['email'] or ''),
        'admin': bool(cad9.prestador_admin(banco, row['prestador_id'])),
        'sessao_id': int(row['id']),
        'expira_em': str(row['expira_em'] or ''),
    }


def revogar_sessao(banco, authorization: str) -> bool:
    token = _token_bearer(authorization)
    if not token:
        return False
    with ext.db(banco) as c:
        cur = c.execute(
            'UPDATE desktop_sessoes SET revogado_em=? '
            'WHERE token_hash=? AND revogado_em IS NULL',
            (_agora(), _hash(token)))
        return cur.rowcount > 0
