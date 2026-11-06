"""Read-only finance API for one AUTOSEG provider.

Unix-style contract: JSON in/out, integer cents, ISO dates, opaque cursors,
bearer tokens and small composable endpoints. Tokens are managed by the CLI in
this module and only their SHA-256 hashes are stored.

This API never writes to OS, finance, stock or feedback tables. It exposes only
the authenticated provider's own financial view.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import secrets
import sqlite3
import sys
import threading
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.cookies import SimpleCookie  # noqa: F401  (kept for test harness parity)
from urllib.parse import parse_qs, urlparse

import prestadores_ext as ext
import produtividade_os as prod
from versao_app import versao_local

LOG = logging.getLogger('autosseg.api')
API_PREFIX = '/api/v1'
TOKEN_PREFIX = 'autoseg_fin_'
MAX_LIMIT = 200
DEFAULT_LIMIT = 50
RATE_LIMIT = 120
SCOPES = ('financeiro:read',)

_RATE = {}
_RATE_LOCK = threading.Lock()


def instalar(banco):
    """Create token and access-audit tables; never changes existing tables."""
    with ext.db(banco) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS api_tokens(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prestador_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            escopos TEXT NOT NULL DEFAULT 'financeiro:read',
            criado_em TEXT NOT NULL,
            ultimo_uso_em TEXT,
            revogado_em TEXT,
            FOREIGN KEY(prestador_id) REFERENCES prestadores(id)
        );
        CREATE INDEX IF NOT EXISTS idx_api_tokens_prestador
            ON api_tokens(prestador_id,id);
        CREATE TABLE IF NOT EXISTS api_acessos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id INTEGER,
            prestador_id INTEGER,
            metodo TEXT NOT NULL,
            rota TEXT NOT NULL,
            status INTEGER NOT NULL,
            ip TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_api_acessos_token
            ON api_acessos(token_id,id);
        ''')


def _agora():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _centavos(valor):
    try:
        numero = Decimal(str(valor if valor is not None else 0))
        if not numero.is_finite():
            return 0
        return int((numero * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError, ValueError):
        return 0


def _data(valor):
    if not valor:
        return None
    return str(valor)[:10]


def _data_hora(valor):
    if not valor:
        return None
    texto = str(valor).strip().replace(' ', 'T')
    return texto[:19] if len(texto) >= 19 else texto


def _hash_token(token):
    return hashlib.sha256(str(token).encode('utf-8')).hexdigest()


def criar_token(banco, prestador_id, nome):
    """Create one token and return (id, raw_token). Raw token is shown once."""
    nome = str(nome or '').strip()
    if not 2 <= len(nome) <= 100:
        raise ValueError('O nome do token deve ter entre 2 e 100 caracteres.')
    with ext.db(banco) as c:
        pessoa = c.execute(
            'SELECT nome FROM prestadores WHERE id=? AND ativo=1 AND excluido=0',
            (int(prestador_id),)).fetchone()
        if not pessoa:
            raise ValueError('Prestador não encontrado ou inativo.')
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        token_hash = _hash_token(token)
        cur = c.execute(
            'INSERT INTO api_tokens(prestador_id,nome,token_hash,escopos,criado_em) '
            'VALUES(?,?,?,?,?)',
            (int(prestador_id), nome, token_hash, ','.join(SCOPES), _agora()))
        return int(cur.lastrowid), token


def listar_tokens(banco, prestador_id=None):
    with ext.db(banco) as c:
        sql = ('SELECT id,prestador_id,nome,escopos,criado_em,ultimo_uso_em,revogado_em '
               'FROM api_tokens')
        params = []
        if prestador_id is not None:
            sql += ' WHERE prestador_id=?'
            params.append(int(prestador_id))
        sql += ' ORDER BY id DESC'
        return [dict(r) for r in c.execute(sql, params)]


def revogar_token(banco, token_id, prestador_id=None):
    with ext.db(banco) as c:
        sql = 'SELECT id FROM api_tokens WHERE id=?'
        params = [int(token_id)]
        if prestador_id is not None:
            sql += ' AND prestador_id=?'
            params.append(int(prestador_id))
        if not c.execute(sql, params).fetchone():
            raise ValueError('Token não encontrado.')
        c.execute('UPDATE api_tokens SET revogado_em=? WHERE id=?',
                  (_agora(), int(token_id)))


def autenticar(banco, authorization):
    """Validate ``Authorization: Bearer <token>`` and return token metadata."""
    texto = str(authorization or '').strip()
    if not texto.lower().startswith('bearer '):
        return None
    token = texto[7:].strip()
    if not token.startswith(TOKEN_PREFIX) or len(token) < 30:
        return None
    token_hash = _hash_token(token)
    with ext.db(banco) as c:
        row = c.execute('''SELECT t.id,t.prestador_id,t.nome,t.escopos,
                                  p.nome prestador_nome
                           FROM api_tokens t
                           JOIN prestadores p ON p.id=t.prestador_id
                           WHERE t.token_hash=? AND t.revogado_em IS NULL
                             AND p.ativo=1 AND p.excluido=0''',
                        (token_hash,)).fetchone()
        if not row:
            return None
        c.execute('UPDATE api_tokens SET ultimo_uso_em=? WHERE id=?',
                  (_agora(), row['id']))
        dados = dict(row)
        dados['token_hash'] = token_hash
        return dados


def _rate_ok(chave):
    agora = time.time()
    with _RATE_LOCK:
        janela = [t for t in _RATE.get(chave, []) if agora - t < 60]
        if len(janela) >= RATE_LIMIT:
            return False
        janela.append(agora)
        _RATE[chave] = janela
    return True


def _request_id():
    return secrets.token_hex(8)


def _cors_headers(handler):
    origem = handler.headers.get('Origin', '')
    permitidas = {
        parte.strip() for parte in
        os.environ.get('AUTOSEG_API_ORIGINS', '').split(',') if parte.strip()
    }
    if origem and origem in permitidas:
        return {
            'Access-Control-Allow-Origin': origem,
            'Access-Control-Allow-Headers': 'Authorization, Content-Type',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Vary': 'Origin',
        }
    return {}


def _enviar(handler, status, payload, request_id):
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store, max-age=0')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('X-Frame-Options', 'DENY')
    handler.send_header('Referrer-Policy', 'no-referrer')
    handler.send_header('X-AUTOSEG-API-Version', 'v1')
    handler.send_header('X-Request-Id', request_id)
    if status == 401:
        handler.send_header('WWW-Authenticate', 'Bearer realm="AUTOSEG Finance API"')
    if status == 429:
        handler.send_header('Retry-After', '60')
    for chave, valor in _cors_headers(handler).items():
        handler.send_header(chave, valor)
    handler.end_headers()
    handler.wfile.write(body)


def _enviar_vazio(handler, status, request_id):
    handler.send_response(status)
    handler.send_header('Content-Length', '0')
    handler.send_header('Cache-Control', 'no-store, max-age=0')
    handler.send_header('X-Request-Id', request_id)
    for chave, valor in _cors_headers(handler).items():
        handler.send_header(chave, valor)
    handler.end_headers()


def _erro(handler, status, code, message, request_id):
    _enviar(handler, status, {
        'error': {'code': code, 'message': message},
        'request_id': request_id,
    }, request_id)


def _registrar_acesso(banco, info, handler, method, path, status):
    try:
        with ext.db(banco) as c:
            c.execute('''INSERT INTO api_acessos
                (token_id,prestador_id,metodo,rota,status,ip,criado_em)
                VALUES(?,?,?,?,?,?,?)''',
                (info.get('id'), info.get('prestador_id'), method,
                 str(path)[:300], int(status),
                 str(handler.client_address[0] if handler.client_address else '')[:100],
                 _agora()))
    except sqlite3.Error:
        pass


def _encode_cursor(valor):
    dados = json.dumps({'v': int(valor)}, separators=(',', ':')).encode('utf-8')
    return base64.urlsafe_b64encode(dados).decode('ascii').rstrip('=')


def _decode_cursor(valor):
    try:
        bruto = base64.urlsafe_b64decode(valor + '=' * (-len(valor) % 4))
        dados = json.loads(bruto.decode('utf-8'))
        numero = int(dados.get('v'))
        if numero <= 0:
            raise ValueError
        return numero
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as erro:
        raise ValueError('Cursor inválido.') from erro


def _parametros(handler):
    return parse_qs(urlparse(handler.path).query)


def _paginacao(query):
    try:
        limite = int(query.get('limit', [str(DEFAULT_LIMIT)])[0])
    except (TypeError, ValueError) as erro:
        raise ValueError('limit inválido.') from erro
    if not 1 <= limite <= MAX_LIMIT:
        raise ValueError(f'limit deve ficar entre 1 e {MAX_LIMIT}.')
    cursor_txt = str(query.get('cursor', [''])[0]).strip()
    cursor = _decode_cursor(cursor_txt) if cursor_txt else None
    return limite, cursor


def _data_filtro(query, chave):
    valor = str(query.get(chave, [''])[0]).strip()
    if not valor:
        return None
    try:
        return datetime.strptime(valor, '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError as erro:
        raise ValueError(f'{chave} deve estar no formato YYYY-MM-DD.') from erro


def _meta(limite, linhas, chave):
    tem_mais = len(linhas) > limite
    linhas = linhas[:limite]
    proximo = _encode_cursor(linhas[-1][chave]) if tem_mais and linhas else None
    return linhas, {
        'limit': limite,
        'has_more': tem_mais,
        'next_cursor': proximo,
        'generated_at': _data_hora(_agora()),
    }


def _lancamentos(banco, pid, query):
    limite, cursor = _paginacao(query)
    where = ['e.prestador_id=?','COALESCE(o.arquivada,0)=0']
    params = [int(pid)]
    status = str(query.get('status', [''])[0]).strip()[:40]
    if status:
        where.append('f.status=?')
        params.append(status)
    desde = _data_filtro(query, 'desde')
    ate = _data_filtro(query, 'ate')
    if desde:
        where.append('f.data_lancamento>=?')
        params.append(desde)
    if ate:
        where.append('f.data_lancamento<=?')
        params.append(ate)
    os_id = str(query.get('os_id', [''])[0]).strip()
    if os_id:
        if not os_id.isdigit():
            raise ValueError('os_id inválido.')
        where.append('f.os_id=?')
        params.append(int(os_id))
    if cursor:
        where.append('f.id<?')
        params.append(cursor)
    sql = f'''SELECT f.id,f.os_id,f.cliente_id,f.descricao,f.valor,f.status,
                     f.forma_pagamento,f.data_lancamento,f.vencimento,f.data_pagamento,
                     o.numero_os,c.nome cliente_nome,
                     COALESCE((SELECT SUM(r.valor_centavos)
                        FROM produtividade_rateios r
                        WHERE r.os_id=f.os_id),0) rateios_centavos
              FROM financeiro f
              JOIN ordens_servico o ON o.id=f.os_id
              JOIN clientes c ON c.id=f.cliente_id
              JOIN os_encerramentos e ON e.os_id=f.os_id
              WHERE {' AND '.join(where)}
              ORDER BY f.id DESC LIMIT ?'''
    params.append(limite + 1)
    with ext.db(banco) as c:
        linhas = c.execute(sql, params).fetchall()
    linhas, meta = _meta(limite, linhas, 'id')
    data = []
    for linha in linhas:
        valor = _centavos(linha['valor'])
        rateios = int(linha['rateios_centavos'] or 0)
        data.append({
            'id': int(linha['id']),
            'os': {'id': int(linha['os_id']), 'numero': linha['numero_os']},
            'cliente': {'id': int(linha['cliente_id']), 'nome': linha['cliente_nome']},
            'descricao': linha['descricao'] or '',
            'moeda': 'BRL',
            'valor_centavos': valor,
            'rateios_centavos': rateios,
            'minha_parcela_centavos': valor - rateios,
            'status': linha['status'],
            'forma_pagamento': linha['forma_pagamento'] or '',
            'data_lancamento': _data(linha['data_lancamento']),
            'vencimento': _data(linha['vencimento']),
            'data_pagamento': _data(linha['data_pagamento']),
        })
    return data, meta


def _rateios(banco, pid, query):
    limite, cursor = _paginacao(query)
    where = ['r.tecnico_id=?','COALESCE(o.arquivada,0)=0']
    params = [int(pid)]
    if cursor:
        where.append('r.os_id<?')
        params.append(cursor)
    sql = f'''SELECT r.os_id,r.valor_centavos,r.registrado_em,o.numero_os,
                     c.nome cliente_nome,e.prestador_id finalizador_id,
                     pf.nome finalizador_nome,
                     COALESCE(p.pago_centavos,0) pago_centavos,
                     COALESCE(p.enviado_centavos,0) enviado_centavos,
                     p.enviado_em,p.confirmado_em
              FROM produtividade_rateios r
              JOIN ordens_servico o ON o.id=r.os_id
              JOIN clientes c ON c.id=o.cliente_id
              JOIN os_encerramentos e ON e.os_id=r.os_id
              JOIN prestadores pf ON pf.id=e.prestador_id
              LEFT JOIN produtividade_repasses p
                ON p.os_id=r.os_id AND p.tecnico_id=r.tecnico_id
              WHERE {' AND '.join(where)}
              ORDER BY r.os_id DESC LIMIT ?'''
    params.append(limite + 1)
    with ext.db(banco) as c:
        linhas = c.execute(sql, params).fetchall()
    linhas, meta = _meta(limite, linhas, 'os_id')
    data = []
    for linha in linhas:
        valor = int(linha['valor_centavos'])
        pago = int(linha['pago_centavos'])
        enviado = int(linha['enviado_centavos'])
        if pago >= valor:
            status = 'recebido'
        elif enviado > pago:
            status = 'aguardando_confirmacao'
        else:
            status = 'a_receber'
        data.append({
            'os': {'id': int(linha['os_id']), 'numero': linha['numero_os']},
            'cliente': {'nome': linha['cliente_nome']},
            'finalizador': {'id': int(linha['finalizador_id']),
                            'nome': linha['finalizador_nome']},
            'moeda': 'BRL',
            'valor_centavos': valor,
            'pago_centavos': pago,
            'enviado_centavos': enviado,
            'aguardando_confirmacao_centavos': max(0, enviado - pago),
            'restante_centavos': max(0, valor - pago),
            'status': status,
            'registrado_em': _data_hora(linha['registrado_em']),
            'enviado_em': _data_hora(linha['enviado_em']),
            'confirmado_em': _data_hora(linha['confirmado_em']),
        })
    return data, meta


def _repasses(banco, pid, query):
    limite, cursor = _paginacao(query)
    where = ['e.prestador_id=?','COALESCE(o.arquivada,0)=0',
             "EXISTS (SELECT 1 FROM financeiro f WHERE f.os_id=r.os_id AND f.status='Recebido')"]
    params = [int(pid)]
    if cursor:
        where.append('r.os_id<?')
        params.append(cursor)
    sql = f'''SELECT r.os_id,r.tecnico_id,t.nome tecnico_nome,r.valor_centavos,
                     o.numero_os,c.nome cliente_nome,
                     COALESCE(p.pago_centavos,0) pago_centavos,
                     COALESCE(p.enviado_centavos,0) enviado_centavos,
                     p.enviado_em,p.confirmado_em
              FROM produtividade_rateios r
              JOIN ordens_servico o ON o.id=r.os_id
              JOIN clientes c ON c.id=o.cliente_id
              JOIN prestadores t ON t.id=r.tecnico_id
              JOIN os_encerramentos e ON e.os_id=r.os_id
              LEFT JOIN produtividade_repasses p
                ON p.os_id=r.os_id AND p.tecnico_id=r.tecnico_id
              WHERE {' AND '.join(where)}
              ORDER BY r.os_id DESC LIMIT ?'''
    params.append(limite + 1)
    with ext.db(banco) as c:
        linhas = c.execute(sql, params).fetchall()
    linhas, meta = _meta(limite, linhas, 'os_id')
    data = []
    for linha in linhas:
        valor = int(linha['valor_centavos'])
        pago = int(linha['pago_centavos'])
        enviado = int(linha['enviado_centavos'])
        a_enviar = max(0, valor - pago - enviado)
        if pago >= valor:
            status = 'confirmado'
        elif enviado > pago:
            status = 'aguardando_confirmacao'
        else:
            status = 'a_enviar'
        data.append({
            'os': {'id': int(linha['os_id']), 'numero': linha['numero_os']},
            'cliente': {'nome': linha['cliente_nome']},
            'tecnico': {'id': int(linha['tecnico_id']),
                        'nome': linha['tecnico_nome']},
            'moeda': 'BRL',
            'valor_centavos': valor,
            'pago_centavos': pago,
            'enviado_centavos': enviado,
            'aguardando_confirmacao_centavos': max(0, enviado - pago),
            'a_enviar_centavos': a_enviar,
            'status': status,
            'enviado_em': _data_hora(linha['enviado_em']),
            'confirmado_em': _data_hora(linha['confirmado_em']),
        })
    return data, meta


def _resumo(banco, pid):
    pessoal = prod.financeiro_pessoal(banco, pid)
    os_a_receber = 0
    os_recebido = 0
    for item in pessoal['brutos_proprios']:
        valor = _centavos(item['valor']) - int(item['partes_centavos'])
        if item['status'] == 'Recebido':
            os_recebido += valor
        elif item['status'] == 'Aguardando pagamento':
            os_a_receber += valor
    repasses_a_receber = 0
    repasses_recebidos = 0
    for item in pessoal['receber_de_colegas']:
        valor = int(item['valor_centavos'])
        pago = int(item['pago_centavos'])
        repasses_recebidos += pago
        repasses_a_receber += valor - pago
    repasses_a_pagar = 0
    repasses_aguardando = 0
    for item in pessoal['repassar_a_colegas']:
        valor = int(item['valor_centavos'])
        pago = int(item['pago_centavos'])
        enviado = int(item['enviado_centavos'])
        repasses_a_pagar += valor - pago
        repasses_aguardando += max(0, enviado - pago)
    return {
        'prestador_id': int(pid),
        'moeda': 'BRL',
        'gerado_em': _data_hora(_agora()),
        'os_a_receber_centavos': os_a_receber,
        'os_recebido_centavos': os_recebido,
        'repasses_a_receber_centavos': repasses_a_receber,
        'repasses_recebidos_centavos': repasses_recebidos,
        'repasses_a_pagar_centavos': repasses_a_pagar,
        'repasses_aguardando_confirmacao_centavos': repasses_aguardando,
        'total_a_receber_centavos': os_a_receber + repasses_a_receber,
        'total_recebido_centavos': os_recebido + repasses_recebidos,
    }


def _openapi():
    param_limit = {
        'name': 'limit', 'in': 'query', 'required': False,
        'schema': {'type': 'integer', 'minimum': 1, 'maximum': MAX_LIMIT,
                   'default': DEFAULT_LIMIT},
        'description': 'Itens por página.',
    }
    param_cursor = {
        'name': 'cursor', 'in': 'query', 'required': False,
        'schema': {'type': 'string'},
        'description': 'Cursor opaco retornado em meta.next_cursor.',
    }
    erro = {
        'type': 'object',
        'properties': {
            'error': {'type': 'object', 'properties': {
                'code': {'type': 'string'}, 'message': {'type': 'string'}}},
            'request_id': {'type': 'string'},
        },
    }
    paginado = {
        'type': 'object',
        'properties': {
            'data': {'type': 'array', 'items': {'type': 'object'}},
            'meta': {'type': 'object', 'properties': {
                'limit': {'type': 'integer'},
                'has_more': {'type': 'boolean'},
                'next_cursor': {'type': ['string', 'null']},
                'generated_at': {'type': 'string'},
            }},
        },
    }
    security = [{'BearerAuth': []}]
    return {
        'openapi': '3.1.0',
        'info': {
            'title': 'AUTOSEG Finance API',
            'version': '1.0.0',
            'description': 'API somente leitura do financeiro de um prestador. '
                           'Valores em centavos inteiros e moeda BRL. '
                           'Nenhum endpoint altera OS, financeiro ou estoque.',
        },
        'servers': [{'url': '/api/v1'}],
        'security': security,
        'components': {
            'securitySchemes': {
                'BearerAuth': {'type': 'http', 'scheme': 'bearer',
                               'bearerFormat': 'AUTOSEG provider token'},
            },
            'schemas': {'Error': erro, 'Paginated': paginado},
        },
        'paths': {
            '/health': {'get': {
                'summary': 'Verificação de saúde', 'security': [],
                'responses': {'200': {'description': 'API disponível'}},
            }},
            '/openapi.json': {'get': {
                'summary': 'Este contrato OpenAPI', 'security': [],
                'responses': {'200': {'description': 'Contrato'}},
            }},
            '/me': {'get': {
                'summary': 'Prestador autenticado',
                'responses': {'200': {'description': 'Identidade do prestador'}},
            }},
            '/financeiro/resumo': {'get': {
                'summary': 'Totais financeiros do prestador',
                'responses': {'200': {'description': 'Resumo em centavos'}},
            }},
            '/financeiro/lancamentos': {'get': {
                'summary': 'Lançamentos de OS em que o prestador é finalizador',
                'parameters': [
                    param_limit, param_cursor,
                    {'name': 'status', 'in': 'query', 'schema': {'type': 'string'}},
                    {'name': 'desde', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}},
                    {'name': 'ate', 'in': 'query', 'schema': {'type': 'string', 'format': 'date'}},
                    {'name': 'os_id', 'in': 'query', 'schema': {'type': 'integer'}},
                ],
                'responses': {'200': {'description': 'Lista paginada'}},
            }},
            '/financeiro/rateios': {'get': {
                'summary': 'Parcelas do prestador como técnico secundário',
                'parameters': [param_limit, param_cursor],
                'responses': {'200': {'description': 'Lista paginada'}},
            }},
            '/financeiro/repasses': {'get': {
                'summary': 'Repasses que o prestador deve a técnicos secundários',
                'parameters': [param_limit, param_cursor],
                'responses': {'200': {'description': 'Lista paginada'}},
            }},
        },
    }


def _rota(handler, path, banco, info, request_id):
    query = _parametros(handler)
    pid = int(info['prestador_id'])
    if path in (API_PREFIX, API_PREFIX + '/'):
        return 200, {'data': {
            'name': 'AUTOSEG Finance API', 'version': 'v1',
            'documentation': API_PREFIX + '/openapi.json',
            'endpoints': [
                '/me', '/financeiro/resumo', '/financeiro/lancamentos',
                '/financeiro/rateios', '/financeiro/repasses',
            ],
        }}
    if path == API_PREFIX + '/health':
        return 200, {'data': {'status': 'ok', 'version': versao_local(),
                              'time': _data_hora(_agora())}}
    if path == API_PREFIX + '/openapi.json':
        return 200, _openapi()
    if path == API_PREFIX + '/me':
        return 200, {'data': {
            'id': pid, 'nome': info['prestador_nome'], 'tipo': 'prestador',
        }}
    if path == API_PREFIX + '/financeiro/resumo':
        return 200, {'data': _resumo(banco, pid)}
    if path == API_PREFIX + '/financeiro/lancamentos':
        data, meta = _lancamentos(banco, pid, query)
        return 200, {'data': data, 'meta': meta}
    if path == API_PREFIX + '/financeiro/rateios':
        data, meta = _rateios(banco, pid, query)
        return 200, {'data': data, 'meta': meta}
    if path == API_PREFIX + '/financeiro/repasses':
        data, meta = _repasses(banco, pid, query)
        return 200, {'data': data, 'meta': meta}
    return 404, {'error': {'code': 'not_found', 'message': 'Rota não encontrada.'},
                 'request_id': request_id}


def handle(handler, path, banco, method='GET'):
    """Handle an API request. Returns True when the path belongs to the API."""
    request_id = _request_id()
    if method == 'OPTIONS':
        _enviar_vazio(handler, 204, request_id)
        return True
    if method != 'GET':
        _erro(handler, 405, 'method_not_allowed',
              'A API financeira é somente leitura.', request_id)
        return True
    if path == API_PREFIX + '/health' or path == API_PREFIX + '/openapi.json':
        status, payload = _rota(handler, path, banco, {'prestador_id': 0,
                                                      'prestador_nome': ''},
                                request_id)
        _enviar(handler, status, payload, request_id)
        return True
    if path in (API_PREFIX, API_PREFIX + '/'):
        status, payload = _rota(handler, path, banco, {'prestador_id': 0,
                                                      'prestador_nome': ''},
                                request_id)
        _enviar(handler, status, payload, request_id)
        return True

    info = autenticar(banco, handler.headers.get('Authorization', ''))
    if not info:
        _erro(handler, 401, 'unauthorized',
              'Informe um token Bearer válido em Authorization.', request_id)
        return True
    if not _rate_ok(info['token_hash']):
        _erro(handler, 429, 'rate_limited',
              'Limite temporário de requisições atingido.', request_id)
        return True
    escopos = {x.strip() for x in str(info.get('escopos', '')).split(',') if x.strip()}
    if 'financeiro:read' not in escopos:
        _erro(handler, 403, 'forbidden', 'Token sem escopo financeiro:read.', request_id)
        return True

    status = 500
    try:
        if path not in (
            API_PREFIX + '/me',
            API_PREFIX + '/financeiro/resumo',
            API_PREFIX + '/financeiro/lancamentos',
            API_PREFIX + '/financeiro/rateios',
            API_PREFIX + '/financeiro/repasses',
        ):
            status = 404
            _erro(handler, status, 'not_found', 'Rota não encontrada.', request_id)
            return True
        status, payload = _rota(handler, path, banco, info, request_id)
        _enviar(handler, status, payload, request_id)
    except ValueError as erro:
        status = 400
        _erro(handler, status, 'invalid_request', str(erro), request_id)
    except PermissionError as erro:
        status = 403
        _erro(handler, status, 'forbidden', str(erro), request_id)
    except (sqlite3.Error, OSError):
        LOG.exception('Falha na API financeira')
        status = 500
        _erro(handler, status, 'internal_error',
              'Falha interna ao consultar o financeiro.', request_id)
    finally:
        _registrar_acesso(banco, info, handler, method, path, status)
    return True


def _cli(banco):
    parser = argparse.ArgumentParser(
        prog='api_financeiro.py',
        description='API financeira somente leitura do AUTOSEG.')
    sub = parser.add_subparsers(dest='comando', required=True)
    token = sub.add_parser('token', help='gerenciar tokens de API')
    token_sub = token.add_subparsers(dest='acao', required=True)
    criar = token_sub.add_parser('criar', help='criar um token e imprimi-lo uma vez')
    criar.add_argument('--prestador-id', type=int, required=True)
    criar.add_argument('--nome', required=True)
    listar = token_sub.add_parser('listar', help='listar tokens sem revelar o segredo')
    listar.add_argument('--prestador-id', type=int)
    revogar = token_sub.add_parser('revogar', help='revogar um token pelo id')
    revogar.add_argument('--id', type=int, required=True)
    revogar.add_argument('--prestador-id', type=int)
    sub.add_parser('openapi', help='imprimir o contrato OpenAPI em JSON')
    args = parser.parse_args()

    instalar(banco)
    if args.comando == 'openapi':
        print(json.dumps(_openapi(), ensure_ascii=False, indent=2))
        return 0
    if args.acao == 'criar':
        token_id, raw = criar_token(banco, args.prestador_id, args.nome)
        print(raw)
        print(f'Token {token_id} criado. Guarde o segredo; ele não será exibido novamente.',
              file=sys.stderr)
        return 0
    if args.acao == 'listar':
        print(json.dumps(listar_tokens(banco, args.prestador_id),
                         ensure_ascii=False, indent=2))
        return 0
    if args.acao == 'revogar':
        revogar_token(banco, args.id, args.prestador_id)
        print(f'Token {args.id} revogado.', file=sys.stderr)
        return 0
    return 1


def main(argv=None):
    from banco import BANCO
    return _cli(BANCO)


if __name__ == '__main__':
    raise SystemExit(main())
