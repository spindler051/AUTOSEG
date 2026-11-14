"""Desktop application API.

This module exposes the same ``AppService`` contract used by the GTK shell,
over JSON, so the desktop can run in server mode without opening the local
SQLite database.

The API is intentionally separate from the read-only finance API. It requires
either a loopback client or ``AUTOSEG_DESKTOP_TOKEN`` when the server listens on
a non-loopback address.
"""
from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import sqlite3
from dataclasses import asdict, is_dataclass, replace
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from officina.application.contracts import (
    AppError,
    ConflitoError,
    NaoEncontradoError,
    OSInput,
    ServicoIndisponivelError,
    ValidacaoError,
)
from officina.application.local_service import LocalService
from flavors.autoseg.modules import prestador_auth, identity
from officina.application.contracts import SessionContext, ClienteResumo, Cliente, ClienteOpcao
from officina.application import work_item_access as access
from officina.application.object_policy import ObjectPolicy, Resource, PermissionDenied
from officina.core import prestadores_ext as ext
from officina.integration import clientes as clientes_core
from officina.repositories import ordens as ordens_repo
LOG = logging.getLogger('autoseg.api_desktop')
PREFIX = '/api/v1/desktop'
MAX_BODY = 32 * 1024 * 1024
PREAUTH_BODY = 64 * 1024


def _jsonable(valor: Any) -> Any:
    if is_dataclass(valor):
        return _jsonable(asdict(valor))
    if isinstance(valor, Mapping):
        return {str(chave): _jsonable(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_jsonable(item) for item in valor]
    if isinstance(valor, Path):
        return str(valor)
    if isinstance(valor, bytes):
        return base64.b64encode(valor).decode('ascii')
    return valor


def _enviar(handler, status: int, payload: Mapping[str, Any]):
    corpo = json.dumps({'data': _jsonable(payload)},
                       ensure_ascii=False).encode('utf-8')
    handler.send_response(int(status))
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(corpo)))
    handler.send_header('Cache-Control', 'no-store, max-age=0')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('X-AUTOSEG-API-Version', 'v1')
    handler.end_headers()
    handler.wfile.write(corpo)


def _erro(handler, status: int, codigo: str, mensagem: str):
    corpo = json.dumps({'error': {'code': codigo, 'message': mensagem}},
                       ensure_ascii=False).encode('utf-8')
    handler.send_response(int(status))
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(corpo)))
    handler.send_header('Cache-Control', 'no-store, max-age=0')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    if int(status) == 401:
        handler.send_header('WWW-Authenticate',
                            'Bearer realm="AUTOSEG Desktop"')
    handler.end_headers()
    handler.wfile.write(corpo)


def _corpo(handler, limite: int = MAX_BODY) -> dict:
    try:
        tamanho = int(handler.headers.get('Content-Length', '0') or 0)
    except ValueError:
        raise ValidacaoError('Tamanho de requisição inválido.')
    if tamanho > int(limite):
        raise ValidacaoError('Requisição grande demais.')
    if tamanho <= 0:
        return {}
    bruto = handler.rfile.read(tamanho)
    try:
        dados = json.loads(bruto.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as erro:
        raise ValidacaoError('Corpo JSON inválido.') from erro
    if not isinstance(dados, dict):
        raise ValidacaoError('O corpo da requisição deve ser um objeto JSON.')
    return dados


def instalar(banco) -> None:
    prestador_auth.instalar(banco)


def _ip(handler) -> str:
    from flavors.autoseg.modules import feedback_portal
    return feedback_portal.ip_requisicao(
        str(handler.client_address[0] if handler.client_address else ''),
        handler.headers)


def _exigir_admin(info: dict) -> None:
    if not info or not info.get('admin'):
        raise PermissionError('Somente administradores podem executar esta ação.')


def _portao_desktop(handler) -> bool:
    try:
        endereco = str(handler.server.server_address[0])
    except (AttributeError, TypeError, IndexError):
        endereco = ''
    if endereco in ('127.0.0.1', '::1', 'localhost'):
        return True
    esperado = os.environ.get('AUTOSEG_DESKTOP_TOKEN', '')
    recebido = handler.headers.get('X-AUTOSEG-Desktop-Token', '')
    if esperado and recebido and hmac.compare_digest(str(esperado), str(recebido)):
        return True
    _erro(handler, 403, 'forbidden',
          'A API desktop em endereço não-local exige AUTOSEG_DESKTOP_TOKEN.')
    return False


def _status_de_erro(erro: AppError) -> int:
    if isinstance(erro, NaoEncontradoError):
        return HTTPStatus.NOT_FOUND
    if isinstance(erro, ConflitoError):
        return HTTPStatus.CONFLICT
    if isinstance(erro, ValidacaoError):
        return HTTPStatus.BAD_REQUEST
    if isinstance(erro, ServicoIndisponivelError):
        return HTTPStatus.SERVICE_UNAVAILABLE
    return HTTPStatus.BAD_REQUEST


def _codigo_de_erro(erro: AppError) -> str:
    if isinstance(erro, NaoEncontradoError):
        return 'not_found'
    if isinstance(erro, ConflitoError):
        return 'conflict'
    if isinstance(erro, ValidacaoError):
        return 'validation'
    if isinstance(erro, ServicoIndisponivelError):
        return 'unavailable'
    return 'error'


def _int(valor, padrao=None) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def _os_input(dados: Mapping[str, Any]) -> OSInput:
    campos = dict(dados)
    imagens = []
    for item in campos.pop('imagens', []) or []:
        if not isinstance(item, Mapping):
            continue
        nome = str(item.get('nome') or 'imagem')
        conteudo = item.get('conteudo') or ''
        try:
            imagens.append((nome, base64.b64decode(conteudo, validate=True)))
        except (ValueError, TypeError) as erro:
            raise ValidacaoError(f'Imagem inválida: {nome}.') from erro
    try:
        return OSInput(**campos, imagens=tuple(imagens))
    except TypeError as erro:
        raise ValidacaoError('Dados da OS inválidos.') from erro


def _hidden_resource():
    raise NaoEncontradoError('Recurso não encontrado.')


def _require_object(banco, principal, os_id, action='view'):
    """The API gate authenticates transport, not access to a service order.

    Preflight is read-only. The legacy LocalService writers use separate
    transactions, so relationship changes between authorization and a write
    remain a TOCTOU risk until they accept a transaction-local guard.
    """
    if type(os_id) is not int or os_id <= 0:
        _hidden_resource()
    try:
        access.require_read_work_item(banco, principal, os_id)
        if action not in ('view', 'download'):
            access.require_work_item(banco, principal, os_id, action)
        elif action == 'download':
            work = access.resource_for_work_item(banco, os_id)
            doc = Resource('document', os_id, work.organization_id,
                           work.owner_id, work.client_id,
                           work.participant_ids, work.attributes,
                           work.client_org_id)
            ObjectPolicy().require(principal, 'download', doc)
    except PermissionDenied as error:
        if error.decision.relationship == 'other':
            _hidden_resource()
        raise
    except PermissionError:
        _hidden_resource()


def _require_customer(banco, principal, customer_id):
    try:
        access.require_customer_read(banco, principal, customer_id)
    except PermissionError:
        _hidden_resource()


def _scoped_os_rows(banco, principal, *, recent=False, termo='', limite=250):
    """Full involved rows and safe shared rows are separate SQL projections."""
    if access.can_read_all(principal):
        service = LocalService(banco)
        return (service.listar_os_recentes(limite) if recent
                else service.listar_os_ativas(termo))
    pid = principal.provider_id
    if pid is None or not principal.active or principal.organization_id != 'autoseg':
        raise PermissionError('Contexto indisponível.')
    involved = """(EXISTS (SELECT 1 FROM os_responsaveis r WHERE r.os_id=os.id
                 AND r.prestador_id=?) OR EXISTS (SELECT 1 FROM os_prestadores op
                 WHERE op.os_id=os.id AND op.prestador_id=? AND op.ativo=1))"""
    active = "os.status IN ('Aberta','Iniciada','Pendente') AND COALESCE(os.arquivada,0)=0"
    service = LocalService(banco)
    safe_sql = """SELECT os.id,os.numero_os,c.nome AS cliente,os.status,
           os.data_abertura,COALESCE(os.atualizado_em,os.data_abertura) AS atualizado_em,
           p.nome AS responsavel,
           (SELECT GROUP_CONCAT(nome, ', ') FROM (
              SELECT DISTINCT pp.nome AS nome FROM os_prestadores op
              JOIN prestadores pp ON pp.id=op.prestador_id
              WHERE op.os_id=os.id AND op.ativo=1 ORDER BY pp.nome
           )) AS participantes
           FROM ordens_servico os JOIN clientes c ON c.id=os.cliente_id
           LEFT JOIN os_responsaveis r ON r.os_id=os.id
           LEFT JOIN prestadores p ON p.id=r.prestador_id"""
    bound = max(1, min(int(limite), 500))
    limit_sql = ' LIMIT ?' if recent else ''
    params = (pid, pid, bound) if recent else (pid, pid)
    with ext.db(banco) as c:
        full = c.execute(service._SQL_OS_RESUMO + ' WHERE ' + involved +
             ((' AND '+ active) if not recent else '') +
             ' ORDER BY os.id DESC' + limit_sql, params).fetchall()
        safe = c.execute(safe_sql + ' WHERE NOT '+involved+' AND '+active+
             ' ORDER BY os.id DESC' + limit_sql, params).fetchall()
    full_rows = [asdict(item) for item in service._mapear_os(full)]
    safe_rows = [dict(item) for item in safe]
    if termo:
        search = str(termo).casefold().strip()
        safe_rows = [item for item in safe_rows if search in
                     ' '.join(str(v or '') for v in item.values()).casefold()]
    merged = sorted(full_rows + safe_rows, key=lambda item:int(item['id']),reverse=True)
    return merged[:bound] if recent else merged


def _minimal_customer_picker(banco, termo=''):
    pattern = '%' + str(termo or '').strip()[:100].replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
    with ext.db(banco) as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id,nome FROM clientes WHERE status NOT IN ('Inativo','A definir')"
            " AND nome LIKE ? ESCAPE '!' ORDER BY nome LIMIT 250", (pattern,))]


def _minimal_providers(banco):
    with ext.db(banco) as connection:
        return [dict(row) for row in connection.execute(
            'SELECT id,nome FROM prestadores WHERE ativo=1 AND excluido=0 ORDER BY nome')]


def _scoped_customer_list(banco, principal, termo=''):
    if access.can_read_all(principal, 'customer'):
        return LocalService(banco).listar_clientes(termo)
    allowed = access.involved_customer_field_scopes(principal)
    _, rows = clientes_core.listar_paginado(termo, limite=1000, banco=banco,
                  provider_id=principal.provider_id, allowed_fields=allowed)
    return [ClienteResumo(id=int(row['id']), nome=str(row['nome'] or ''),
              documento=str(row['documento'] or ''), cidade=str(row['cidade'] or ''),
              telefone=str(row['telefone'] or ''), status=str(row['status'] or ''),
              incompleto=bool(row['dados_incompletos'])) for row in rows]


def _scoped_customer_os_count(banco, principal, customer_id):
    if access.can_read_all(principal, 'work_item'):
        return LocalService(banco).contar_os_cliente(customer_id)
    with ext.db(banco) as connection:
        return int(connection.execute('''SELECT COUNT(*) FROM ordens_servico os
            WHERE os.cliente_id=? AND (EXISTS (
                SELECT 1 FROM os_responsaveis r WHERE r.os_id=os.id AND r.prestador_id=?)
                OR EXISTS (SELECT 1 FROM os_prestadores p WHERE p.os_id=os.id
                           AND p.prestador_id=? AND p.ativo=1))''',
                (customer_id, principal.provider_id, principal.provider_id)).fetchone()[0])


def _scoped_customer_detail(banco, principal, customer_id):
    _require_customer(banco, principal, customer_id)
    if access.can_read_all(principal, 'customer'):
        return LocalService(banco).obter_cliente(customer_id)
    allowed = access.involved_customer_field_scopes(principal)
    with ext.db(banco) as c:
        columns = ['id', 'nome', 'status', 'versao', 'dados_incompletos'] + [field for field in
                   ('documento','telefone','email','cidade','endereco')
                   if (field if field != 'cidade' else 'endereco') in allowed]
        row = c.execute('SELECT '+','.join(columns)+""" FROM clientes WHERE id=? AND EXISTS (
            SELECT 1 FROM ordens_servico os WHERE os.cliente_id=clientes.id
              AND (EXISTS (SELECT 1 FROM os_responsaveis r WHERE r.os_id=os.id AND r.prestador_id=?)
                OR EXISTS (SELECT 1 FROM os_prestadores p WHERE p.os_id=os.id AND p.prestador_id=? AND p.ativo=1)))""",
            (customer_id, principal.provider_id,principal.provider_id)).fetchone()
    if row is None:
        _hidden_resource()
    return Cliente(id=int(row['id']), versao=int(row['versao'] or 1),
                  campos={key:row[key] for key in row.keys()
                          if key not in ('id','versao','dados_incompletos')},
                  incompleto=bool(row['dados_incompletos']))


def _rota(handler, partes: list[str], query: dict, banco: str, metodo: str,
          info: dict | None = None, principal=None):
    servico = LocalService(banco)
    admin = bool(principal and principal.role == 'admin')
    if not partes:
        return _enviar(handler, 200, {
            'name': 'desktop',
            'version': 'v1',
            'capabilities': list(servico.health().capabilities),
        })
    recurso = partes[0]
    if recurso == 'health':
        info = servico.health()
        return _enviar(handler, 200, {
            'status': info.status,
            'version': info.version,
            'capabilities': list(info.capabilities),
            'detail': info.detail,
        })
    if recurso == 'resumo' and metodo == 'GET':
        if admin:
            return _enviar(handler, 200, servico.resumo_inicio())
        counts = ordens_repo.resumo_scoped(banco, principal.provider_id)
        finance = ordens_repo.financeiro_resumo_scoped(banco, principal.provider_id)
        return _enviar(handler, 200, {
            'clientes_ativos': ordens_repo.clientes_ativos_scoped(banco, principal.provider_id),
            'os_abertas': counts['abertas'], 'os_iniciadas': counts['iniciadas'],
            'os_pendentes': counts['pendentes'],
            'financeiro_recebido': finance['recebido'],
            'financeiro_a_receber': finance['a_receber']})
    if recurso in ('prestadores', 'estoque', 'empresa', 'composicao') and not admin:
        raise PermissionError('Somente administradores podem acessar esta área.')
    if recurso == 'clientes':
        return _rota_clientes(handler, partes, query, servico, metodo, info, principal)
    if recurso == 'os':
        return _rota_os(handler, partes, query, servico, metodo, banco, info, principal)
    if recurso == 'prestadores':
        return _rota_prestadores(handler, partes, servico, metodo)
    if recurso == 'organizacoes':
        _exigir_admin(info)
        return _rota_organizacoes(handler, partes, servico, metodo)
    if recurso == 'relatorios':
        _exigir_admin(info)
        if metodo == 'GET' and partes == ['relatorios']:
            return _enviar(handler, 200, servico.listar_relatorios(
                str(query.get('termo', [''])[0])))
        raise NaoEncontradoError('Rota não encontrada.')
    if recurso == 'historico':
        _exigir_admin(info)
        return _rota_historico(handler, partes, query, servico, metodo)
    if recurso == 'pj':
        _exigir_admin(info)
        return _rota_pj(handler, partes, query, servico, metodo)
    if recurso == 'financeiro':
        _exigir_admin(info)
        return _rota_financeiro(handler, partes, query, servico, metodo)
    if recurso == 'portal':
        _exigir_admin(info)
        return _rota_portal(handler, partes, query, servico, metodo)
    if recurso == 'catalogo':
        if metodo != 'GET':
            _exigir_admin(info)
        return _rota_catalogo(handler, partes, query, servico, metodo)
    if recurso == 'estoque':
        return _rota_estoque(handler, partes, query, servico, metodo)
    if recurso == 'empresa':
        return _rota_empresa(handler, partes, servico, metodo)
    if recurso == 'composicao':
        return _rota_composicao(handler, partes, servico, metodo)
    if recurso == 'contexto':
        if partes == ['contexto','os-rapida'] and metodo == 'GET' and not admin:
            return _enviar(handler, 200, {
                'clientes': _minimal_customer_picker(banco),
                'prestadores': _minimal_providers(banco)})
        _exigir_admin(info)
        return _rota_contexto(handler, partes, servico, metodo)
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_clientes(handler, partes, query, servico, metodo, info=None, principal=None):
    if partes == ['clientes','busca'] and metodo == 'GET':
        return _enviar(handler, 200, _minimal_customer_picker(servico.banco,
                      str(query.get('termo', [''])[0])))
    if len(partes) == 1:
        if metodo == 'GET':
            return _enviar(handler, 200, _scoped_customer_list(servico.banco, principal,
                str(query.get('termo', [''])[0])))
        if metodo == 'POST':
            dados = _corpo(handler)
            existing = _int(dados.get('cliente_id', dados.get('id')))
            if existing is not None:
                _require_customer(servico.banco, principal, existing)
            return _enviar(handler, 200, servico.salvar_cliente(
                existing,
                dict(dados.get('dados') or {})))
    if partes == ['clientes', 'ativo'] and metodo == 'GET':
        _exigir_admin(info)
        return _enviar(handler, 200, servico.obter_cliente_ativo_por_documento(
            str(query.get('documento', [''])[0])))
    if partes == ['clientes', 'ativos', 'contar'] and metodo == 'GET':
        return _enviar(handler, 200, {
            'total': (servico.contar_clientes_ativos() if info.get('admin') else
                      ordens_repo.clientes_ativos_scoped(servico.banco, principal.provider_id))})
    if len(partes) >= 2:
        cliente_id = _int(partes[1])
        if cliente_id is None:
            raise NaoEncontradoError('Cliente não encontrado.')
        return _rota_cliente_id(handler, cliente_id, partes[2:],
                                servico, metodo, info, principal)
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_cliente_id(handler, cliente_id, resto, servico, metodo, info=None, principal=None):
    _require_customer(servico.banco, principal, cliente_id)
    if not resto and metodo == 'GET':
        registro = _scoped_customer_detail(servico.banco, principal, cliente_id)
        if registro is None:
            raise NaoEncontradoError('Cliente não encontrado.')
        return _enviar(handler, 200, registro)
    if not resto and metodo == 'PUT':
        dados = _corpo(handler)
        return _enviar(handler, 200, servico.salvar_cliente(
            cliente_id, dict(dados.get('dados') or dados)))
    if resto == ['ativo'] and metodo == 'GET':
        registro = _scoped_customer_detail(servico.banco, principal, cliente_id)
        if str(registro.campos.get('status') or '') == 'Inativo':
            raise NaoEncontradoError('Cliente não encontrado.')
        return _enviar(handler, 200, ClienteOpcao(id=cliente_id,
                           nome=str(registro.campos.get('nome') or '')))
    if resto == ['os', 'contar'] and metodo == 'GET':
        return _enviar(handler, 200, {
            'total': _scoped_customer_os_count(servico.banco, principal, cliente_id)})
    if resto == ['desativar'] and metodo == 'POST':
        _exigir_admin(info)
        servico.desativar_cliente(
            cliente_id, str(_corpo(handler).get('motivo') or ''))
        return _enviar(handler, 200, {'ok': True})
    if resto == ['excluir'] and metodo == 'POST':
        _exigir_admin(info)
        servico.excluir_cliente(cliente_id)
        return _enviar(handler, 200, {'ok': True})
    if resto == ['senha'] and metodo == 'POST':
        _exigir_admin(info)
        servico.definir_senha_cliente(
            cliente_id, _corpo(handler).get('senha'))
        return _enviar(handler, 200, {'ok': True})
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_os(handler, partes, query, servico, metodo, banco=None, info=None, principal=None):
    if partes == ['os'] and metodo == 'POST':
        payload = _os_input(_corpo(handler))
        if payload.os_id:
            _require_object(banco, principal, int(payload.os_id), 'edit')
        else:
            access.require_create(banco, principal)
        return _enviar(handler, 200, servico.salvar_os(payload))
    if partes == ['os', 'ativas'] and metodo == 'GET':
        return _enviar(handler, 200, _scoped_os_rows(banco, principal,
            termo=str(query.get('termo', [''])[0])))
    if partes == ['os', 'recentes'] and metodo == 'GET':
        limite = _int(query.get('limite', ['6'])[0], 6) or 6
        return _enviar(handler, 200, _scoped_os_rows(banco, principal,
            recent=True, limite=limite))
    if partes == ['os', 'escolha'] and metodo == 'GET':
        _exigir_admin(info)
        limite = _int(query.get('limite', ['250'])[0], 250) or 250
        return _enviar(handler, 200, servico.listar_os_para_escolha(limite))
    if partes == ['os', 'atribuicao'] and metodo == 'GET':
        _exigir_admin(info)
        return _enviar(handler, 200, servico.listar_os_para_atribuicao())
    if partes == ['os', 'contexto'] and metodo == 'GET':
        os_id = _int(query.get('os_id', [None])[0])
        _require_object(banco, principal, os_id)
        return _enviar(handler, 200, servico.contexto_os(os_id))
    if len(partes) >= 3:
        os_id = _int(partes[1])
        if os_id is None:
            raise NaoEncontradoError('OS não encontrada.')
        return _rota_os_id(handler, os_id, partes[2:], servico, metodo,
                           banco, info, principal)
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_os_id(handler, os_id, resto, servico, metodo, banco=None, info=None, principal=None):
    actions = {
        ('GET', ('contexto',)): 'view',
        ('GET', ('contexto-atribuicao',)): 'assign',
        ('GET', ('anexos','contar')): 'view',
        ('GET', ('pdf','arquivo')): 'download',
        ('POST', ('atribuir',)): 'assign',
        ('POST', ('desatribuir',)): 'assign',
        ('POST', ('iniciar',)): 'start',
        ('POST', ('pdf','publicar')): 'publish',
        ('POST', ('email','preparar')): 'send',
        ('POST', ('nota','preparar')): 'send',
    }
    action = actions.get((metodo,tuple(resto)))
    if action is None:
        raise NaoEncontradoError('Rota não encontrada.')
    _require_object(banco, principal, os_id, action)
    if resto == ['contexto'] and metodo == 'GET':
        return _enviar(handler, 200, servico.contexto_os(os_id))
    if resto == ['anexos', 'contar'] and metodo == 'GET':
        return _enviar(handler, 200, {
            'total': servico.contar_anexos_os(os_id)})
    if resto == ['contexto-atribuicao'] and metodo == 'GET':
        return _enviar(handler, 200, servico.contexto_atribuicao(os_id))
    if resto == ['atribuir'] and metodo == 'POST':
        prestador_id = _int(_corpo(handler).get('prestador_id'))
        if prestador_id is None:
            raise ValidacaoError('Informe o prestador.')
        return _enviar(handler, 200, {
            'mudou': servico.atribuir_os(os_id, prestador_id)})
    if resto == ['desatribuir'] and metodo == 'POST':
        return _enviar(handler, 200, {
            'mudou': servico.desatribuir_os(os_id)})
    if resto == ['iniciar'] and metodo == 'POST':
        servico.iniciar_os(os_id)
        return _enviar(handler, 200, {'ok': True})
    if resto == ['pdf', 'arquivo'] and metodo == 'GET':
        return _enviar(handler, 200, {
            'arquivo': servico.pdf_publicado(os_id)})
    if resto == ['pdf', 'publicar'] and metodo == 'POST':
        return _enviar(handler, 200, {
            'arquivo': servico.publicar_pdf(os_id)})
    if resto == ['email', 'preparar'] and metodo == 'POST':
        return _enviar(handler, 200, {
            'arquivo': servico.preparar_email(os_id)})
    if resto == ['nota', 'preparar'] and metodo == 'POST':
        return _enviar(handler, 200, {
            'arquivo': servico.preparar_nota(os_id)})
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_prestadores(handler, partes, servico, metodo):
    if len(partes) == 1:
        if metodo == 'GET':
            return _enviar(handler, 200, servico.listar_prestadores())
        if metodo == 'POST':
            return _enviar(handler, 200, {
                'id': servico.criar_prestador(_corpo(handler))})
    if len(partes) != 3:
        raise NaoEncontradoError('Rota não encontrada.')
    prestador_id = _int(partes[1])
    if prestador_id is None:
        raise NaoEncontradoError('Prestador não encontrado.')
    acao = partes[2]
    if acao == 'config':
        if metodo == 'GET':
            return _enviar(handler, 200,
                           servico.obter_config_prestador(prestador_id))
        if metodo in ('POST', 'PUT'):
            servico.salvar_config_prestador(prestador_id, _corpo(handler))
            return _enviar(handler, 200, {'ok': True})
    if acao == 'documento':
        if metodo == 'GET':
            return _enviar(handler, 200, {
                'documento': servico.documento_prestador(prestador_id)})
        if metodo in ('POST', 'PUT'):
            return _enviar(handler, 200, {
                'documento': servico.definir_documento_prestador(
                    prestador_id,
                    str(_corpo(handler).get('documento') or ''))})
    if acao == 'admin':
        if metodo == 'GET':
            return _enviar(handler, 200, {
                'admin': servico.prestador_admin(prestador_id)})
        if metodo == 'POST':
            servico.definir_admin(
                prestador_id, bool(_corpo(handler).get('ativo')))
            return _enviar(handler, 200, {'ok': True})
    if metodo != 'POST':
        raise NaoEncontradoError('Rota não encontrada.')
    if acao == 'alternar':
        servico.alternar_prestador(prestador_id)
    elif acao == 'arquivar':
        servico.arquivar_prestador(prestador_id)
    elif acao == 'senha':
        servico.redefinir_senha_prestador(
            prestador_id, str(_corpo(handler).get('senha') or ''))
    else:
        raise NaoEncontradoError('Rota não encontrada.')
    return _enviar(handler, 200, {'ok': True})


def _rota_organizacoes(handler, partes, servico, metodo):
    if len(partes) != 3:
        raise NaoEncontradoError('Rota não encontrada.')
    org_id = _int(partes[1])
    if org_id is None:
        raise NaoEncontradoError('Organização não encontrada.')
    if partes[2] == 'sindico' and metodo == 'GET':
        return _enviar(handler, 200, servico.obter_contato_sindico(org_id))
    if partes[2] == 'responsavel' and metodo == 'POST':
        usuario_id = _int(_corpo(handler).get('usuario_id'))
        if usuario_id is None:
            raise ValidacaoError('Informe a pessoa física.')
        return _enviar(handler, 200, {
            'papel': servico.atribuir_responsavel(org_id, usuario_id)})
    if partes[2] == 'responsavel' and metodo == 'DELETE':
        servico.remover_responsavel(org_id)
        return _enviar(handler, 200, {'ok': True})
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_historico(handler, partes, query, servico, metodo):
    if partes == ['historico'] and metodo == 'GET':
        return _enviar(handler, 200, servico.listar_historico(
            str(query.get('termo', [''])[0])))
    if partes == ['historico', 'resumo'] and metodo == 'GET':
        return _enviar(handler, 200, servico.resumo_historico())
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_pj(handler, partes, query, servico, metodo):
    if partes == ['pj', 'painel'] and metodo == 'GET':
        chamados, organizacoes, vinculos = servico.painel_pj()
        return _enviar(handler, 200, {
            'chamados': chamados, 'organizacoes': organizacoes,
            'vinculos': vinculos})
    if partes[:2] == ['pj', 'chamados']:
        return _rota_pj_chamados(handler, partes, query, servico, metodo)
    if partes[:2] == ['pj', 'organizacoes']:
        return _rota_pj_organizacoes(handler, partes, servico, metodo)
    if partes[:2] == ['pj', 'vinculos']:
        return _rota_pj_vinculos(handler, partes, servico, metodo)
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_pj_chamados(handler, partes, query, servico, metodo):
    if len(partes) != 4:
        raise NaoEncontradoError('Rota não encontrada.')
    chamado_id = _int(partes[2])
    if chamado_id is None:
        raise NaoEncontradoError('Chamado não encontrado.')
    if partes[3] == 'whatsapp' and metodo == 'GET':
        return _enviar(handler, 200, servico.url_whatsapp_chamado(
            chamado_id, str(query.get('link', [''])[0])))
    if metodo != 'POST':
        raise NaoEncontradoError('Rota não encontrada.')
    dados = _corpo(handler)
    if partes[3] == 'analisar':
        servico.analisar_chamado(
            chamado_id, str(dados.get('decisao') or ''),
            str(dados.get('observacao') or ''))
    elif partes[3] == 'confirmar':
        servico.confirmar_chamado(
            chamado_id, str(dados.get('confirmacao') or ''))
    elif partes[3] == 'gerar-os':
        return _enviar(handler, 200, {
            'os_id': servico.gerar_os_chamado(chamado_id)})
    else:
        raise NaoEncontradoError('Rota não encontrada.')
    return _enviar(handler, 200, {'ok': True})


def _rota_pj_organizacoes(handler, partes, servico, metodo):
    if partes == ['pj', 'organizacoes', 'mesclar'] and metodo == 'POST':
        dados = _corpo(handler)
        origem = _int(dados.get('origem'))
        destino = _int(dados.get('destino'))
        if origem is None or destino is None:
            raise ValidacaoError('Informe origem e destino.')
        servico.mesclar_organizacoes(origem, destino)
        return _enviar(handler, 200, {'ok': True})
    if len(partes) != 4:
        raise NaoEncontradoError('Rota não encontrada.')
    org_id = _int(partes[2])
    if org_id is None:
        raise NaoEncontradoError('Organização não encontrada.')
    dados = _corpo(handler)
    if partes[3] == 'validar' and metodo == 'POST':
        cliente_id = _int(dados.get('cliente_id'))
        if cliente_id is None:
            raise ValidacaoError('Informe o cliente.')
        servico.validar_organizacao(org_id, cliente_id)
        return _enviar(handler, 200, {'ok': True})
    if partes[3] == 'sindico' and metodo == 'POST':
        servico.atualizar_sindico(
            org_id, str(dados.get('nome') or ''),
            str(dados.get('telefone') or ''))
        return _enviar(handler, 200, {'ok': True})
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_pj_vinculos(handler, partes, servico, metodo):
    if len(partes) != 4 or partes[3] != 'alterar' or metodo != 'POST':
        raise NaoEncontradoError('Rota não encontrada.')
    vinculo_id = _int(partes[2])
    if vinculo_id is None:
        raise NaoEncontradoError('Vínculo não encontrado.')
    servico.alterar_vinculo(
        vinculo_id, bool(_corpo(handler).get('aprovar')))
    return _enviar(handler, 200, {'ok': True})


def _rota_financeiro(handler, partes, query, servico, metodo):
    if partes == ['financeiro'] and metodo == 'GET':
        return _enviar(handler, 200, servico.listar_financeiro(
            str(query.get('termo', [''])[0])))
    if partes == ['financeiro', 'resumo'] and metodo == 'GET':
        return _enviar(handler, 200, servico.resumo_financeiro())
    if len(partes) == 3 and partes[2] == 'receber' and metodo == 'POST':
        lancamento_id = _int(partes[1])
        if lancamento_id is None:
            raise NaoEncontradoError('Lançamento não encontrado.')
        servico.marcar_recebido(lancamento_id)
        return _enviar(handler, 200, {'ok': True})
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_portal(handler, partes, query, servico, metodo):
    if partes == ['portal', 'resumo'] and metodo == 'GET':
        return _enviar(handler, 200, servico.resumo_portal())
    if partes == ['portal', 'solicitacoes'] and metodo == 'GET':
        limite = _int(query.get('limite', ['50'])[0], 50) or 50
        return _enviar(handler, 200,
                       servico.listar_solicitacoes_portal(limite))
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_catalogo(handler, partes, query, servico, metodo):
    if partes == ['catalogo', 'servicos']:
        if metodo == 'GET':
            ativos = str(query.get('ativos', ['0'])[0]).lower() in (
                '1', 'true', 'sim')
            return _enviar(handler, 200,
                           servico.catalogo_listar(ativos=ativos))
        if metodo == 'POST':
            dados = _corpo(handler)
            return _enviar(handler, 200, {
                'id': servico.catalogo_salvar(
                    dict(dados.get('dados') or {}), _int(dados.get('id')))})
    if len(partes) == 3 and partes[1] == 'servicos':
        servico_id = _int(partes[2])
        if servico_id is None:
            raise NaoEncontradoError('Serviço não encontrado.')
        if metodo == 'GET':
            registro = servico.catalogo_obter(servico_id)
            if registro is None:
                raise NaoEncontradoError('Serviço não encontrado.')
            return _enviar(handler, 200, registro)
        if metodo == 'PUT':
            dados = _corpo(handler)
            return _enviar(handler, 200, {
                'id': servico.catalogo_salvar(
                    dict(dados.get('dados') or dados), servico_id)})
    if len(partes) == 4 and partes[1] == 'servicos' and metodo == 'POST':
        servico_id = _int(partes[2])
        if servico_id is None:
            raise NaoEncontradoError('Serviço não encontrado.')
        if partes[3] == 'excluir':
            servico.catalogo_excluir(servico_id)
        elif partes[3] in ('arquivar', 'reativar'):
            servico.catalogo_definir_ativo(
                servico_id, partes[3] == 'reativar')
        else:
            raise NaoEncontradoError('Rota não encontrada.')
        return _enviar(handler, 200, {'ok': True})
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_estoque(handler, partes, query, servico, metodo):
    if partes == ['estoque', 'materiais'] and metodo == 'GET':
        ativos = str(query.get('ativos', ['0'])[0]).lower() in (
            '1', 'true', 'sim')
        return _enviar(handler, 200,
                       servico.listar_materiais_estoque(ativos=ativos))
    if partes == ['estoque', 'importar'] and metodo == 'POST':
        return _enviar(handler, 200, servico.estoque_importar_lote(
            list(_corpo(handler).get('materiais') or [])))
    if partes == ['estoque', 'produtos']:
        if metodo == 'GET':
            ativos = str(query.get('ativos', ['0'])[0]).lower() in (
                '1', 'true', 'sim')
            return _enviar(handler, 200,
                           servico.listar_materiais_estoque(ativos=ativos))
        if metodo == 'POST':
            dados = _corpo(handler)
            return _enviar(handler, 200, {
                'id': servico.estoque_cadastrar(
                    dict(dados.get('dados') or {}), _int(dados.get('id')))})
    if len(partes) == 3 and partes[1] == 'produtos':
        produto_id = _int(partes[2])
        if produto_id is None:
            raise NaoEncontradoError('Material não encontrado.')
        if metodo == 'GET':
            registro = servico.estoque_obter(produto_id)
            if registro is None:
                raise NaoEncontradoError('Material não encontrado.')
            return _enviar(handler, 200, registro)
        if metodo == 'PUT':
            dados = _corpo(handler)
            return _enviar(handler, 200, {
                'id': servico.estoque_cadastrar(
                    dict(dados.get('dados') or dados), produto_id)})
    if len(partes) == 4 and partes[1] == 'produtos':
        produto_id = _int(partes[2])
        if produto_id is None:
            raise NaoEncontradoError('Material não encontrado.')
        if partes[3] == 'movimentos' and metodo == 'GET':
            limite = _int(query.get('limite', ['300'])[0], 300) or 300
            return _enviar(handler, 200,
                           servico.estoque_movimentos(produto_id, limite))
        if metodo != 'POST':
            raise NaoEncontradoError('Rota não encontrada.')
        dados = _corpo(handler)
        if partes[3] == 'ajuste':
            servico.estoque_ajuste(
                produto_id, dados.get('delta'),
                str(dados.get('motivo') or ''))
            return _enviar(handler, 200, {'ok': True})
        if partes[3] == 'excluir':
            return _enviar(handler, 200, {
                'resultado': servico.estoque_excluir(produto_id)})
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_empresa(handler, partes, servico, metodo):
    if partes == ['empresa', 'resumo'] and metodo == 'GET':
        return _enviar(handler, 200, servico.empresa_resumo())
    if partes == ['empresa', 'movimentos']:
        if metodo == 'GET':
            return _enviar(handler, 200, servico.empresa_listar())
        if metodo == 'POST':
            return _enviar(handler, 200, {
                'id': servico.empresa_registrar(_corpo(handler))})
    if len(partes) == 4 and partes[1] == 'movimentos'             and partes[3] == 'arquivar' and metodo == 'POST':
        movimento_id = _int(partes[2])
        if movimento_id is None:
            raise NaoEncontradoError('Lançamento não encontrado.')
        servico.empresa_arquivar(movimento_id)
        return _enviar(handler, 200, {'ok': True})
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_composicao(handler, partes, servico, metodo):
    if partes == ['composicao', 'config']:
        if metodo == 'GET':
            return _enviar(handler, 200, servico.composicao_config())
        if metodo in ('PUT', 'POST'):
            servico.composicao_salvar(_corpo(handler))
            return _enviar(handler, 200, {'ok': True})
    if partes == ['composicao', 'recalcular'] and metodo == 'POST':
        return _enviar(handler, 200, servico.composicao_recalcular())
    raise NaoEncontradoError('Rota não encontrada.')


def _rota_contexto(handler, partes, servico, metodo):
    if metodo != 'GET':
        raise NaoEncontradoError('Rota não encontrada.')
    if partes == ['contexto', 'responsavel']:
        return _enviar(handler, 200, servico.contexto_responsavel())
    if partes == ['contexto', 'os-rapida']:
        return _enviar(handler, 200, servico.contexto_os_rapida())
    if partes == ['contexto', 'movimento']:
        return _enviar(handler, 200, servico.contexto_movimento_empresa())
    raise NaoEncontradoError('Rota não encontrada.')


def _login(handler, banco) -> bool:
    dados = _corpo(handler, PREAUTH_BODY)
    resultado = prestador_auth.login(
        banco, str(dados.get('email') or ''),
        str(dados.get('senha') or ''),
        bool(dados.get('lembrar')),
        _ip(handler))
    if not resultado:
        _erro(handler, 401, 'unauthorized', 'E-mail ou senha incorretos.')
    else:
        _enviar(handler, 200, resultado)
    return True


def _desktop_session_context(banco, info):
    """Shared service mapping; desktop_sessoes authentication is unchanged."""
    ident = identity.load_identity(banco, 'provider', int(info['id']))
    memberships = identity.memberships(banco, ident) if ident else ()
    if len(memberships) != 1:
        raise PermissionError('Contexto do prestador indisponível.')
    membership = memberships[0]
    principal = replace(identity.to_principal(ident, membership),
                        organization_id='autoseg')
    return SessionContext.from_identity(ident, membership, principal), principal


def _context_api(context):
    return {
        'role': context.role,
        'context_label': context.context_label,
        'permissions': sorted(context.permissions),
        'account_id': context.account_id,
        'identity_kind': context.identity_kind,
        'identity_id': context.identity_id,
        'display_name': context.display_name,
        'provider_org_id': context.provider_org_id,
        'provider_id': context.provider_id,
        'client_id': context.client_id,
        'client_org_ids': sorted(context.client_org_ids),
    }


def handle(handler, path: str, banco: str, method: str = 'GET') -> bool:
    """Handle desktop API requests. Returns True when the prefix matched."""
    if path != PREFIX and not path.startswith(PREFIX + '/'):
        return False
    if method == 'OPTIONS':
        handler.send_response(204)
        handler.send_header('Content-Length', '0')
        handler.end_headers()
        return True
    caminho = path.rstrip('/') or PREFIX
    partes = caminho[len(PREFIX):].strip('/').split('/') if caminho != PREFIX else []
    partes = [parte for parte in partes if parte]
    query = parse_qs(urlparse(handler.path).query)
    try:
        if not _portao_desktop(handler):
            return True
        if caminho == PREFIX + '/health' and method == 'GET':
            return _rota(handler, partes, query, banco, method)
        if caminho == PREFIX + '/login' and method == 'POST':
            return _login(handler, banco)
        info = prestador_auth.validar_sessao(
            banco, handler.headers.get('Authorization', ''))
        if not info:
            _erro(handler, 401, 'unauthorized',
                  'Sessão expirada ou não autenticada.')
            return True
        if caminho == PREFIX + '/me' and method == 'GET':
            context, principal = _desktop_session_context(banco, info)
            _enviar(handler, 200, {**info, **_context_api(context)})
            return True
        if caminho == PREFIX + '/logout' and method == 'POST':
            prestador_auth.revogar_sessao(
                banco, handler.headers.get('Authorization', ''))
            _enviar(handler, 200, {'ok': True})
            return True
        context, principal = _desktop_session_context(banco, info)
        info = {**info, 'admin': principal.role == 'admin'}
        _rota(handler, partes, query, banco, method, info, principal)
    except prestador_auth.MuitasTentativasError as erro:
        _erro(handler, 429, 'rate_limited', str(erro))
    except AppError as erro:
        _erro(handler, _status_de_erro(erro), _codigo_de_erro(erro),
              erro.mensagem)
    except ValueError as erro:
        _erro(handler, 400, 'validation', str(erro))
    except PermissionDenied as erro:
        if erro.decision.relationship == 'other':
            _erro(handler, 404, 'not_found', 'Recurso não encontrado.')
        else:
            _erro(handler, 403, 'forbidden', 'Operação não permitida.')
    except PermissionError:
        _erro(handler, 403, 'forbidden', 'Operação não permitida.')
    except sqlite3.Error:
        LOG.exception('Falha de banco na API desktop')
        _erro(handler, 500, 'internal_error',
              'Falha interna ao acessar os dados.')
    except OSError:
        LOG.exception('Falha de sistema na API desktop')
        _erro(handler, 500, 'internal_error',
              'Falha interna ao acessar os dados.')
    return True
