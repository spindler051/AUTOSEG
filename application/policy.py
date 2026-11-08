"""Declarative permission policy with atomic runtime reload.

The policy is data, not code. Roles, permissions and field scopes live in
``policy.yaml`` (or ``AUTOSEG_BASE/policy.yaml``). ``PolicyStore.reload()``
swaps the active policy atomically so an administrator can change a rule at
runtime without restarting the process.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PASTA_APP = Path(__file__).resolve().parent.parent
SCOPES = ('none', 'own', 'involved', 'all')
RELATIONSHIPS = ('none', 'own', 'involved', 'other', 'all')

PADRAO = {
    'versao': 1,
    'roles': {
        'admin': {'permissions': ['*']},
        'employee': {'permissions': [
            'work_item.view.own', 'work_item.view.involved',
            'work_item.create', 'work_item.edit.own',
            'work_item.edit.involved', 'work_item.close.own',
            'report.publish.own', 'finance.view.own', 'stock.view',
            'customer.view.involved', 'customer.pii.view.involved',
            'customer.contact.view.involved',
        ]},
        'customer': {'permissions': [
            'work_item.create.request', 'work_item.view.own',
            'report.view.own', 'document.view.own', 'customer.view.own',
            'customer.pii.view.own', 'customer.contact.view.own',
        ]},
    },
    'campos': {
        'customer.nome': {'admin': 'all', 'employee': 'involved', 'customer': 'own'},
        'customer.telefone': {'admin': 'all', 'employee': 'involved', 'customer': 'own'},
        'customer.endereco': {'admin': 'all', 'employee': 'involved', 'customer': 'own'},
        'customer.email': {'admin': 'all', 'employee': 'involved', 'customer': 'own'},
        'customer.documento': {'admin': 'all', 'employee': 'involved', 'customer': 'own'},
    },
}


class PolicyError(ValueError):
    """Invalid policy configuration."""


@dataclass(frozen=True)
class Policy:
    version: int
    roles: Mapping[str, frozenset[str]]
    fields: Mapping[str, Mapping[str, str]]

    def allows(self, role: str, permission: str) -> bool:
        granted = self.roles.get(str(role))
        if granted is None:
            return False
        if '*' in granted or permission in granted:
            return True
        return any(item.endswith('.*') and permission.startswith(item[:-1])
                   for item in granted)

    def field_scope(self, role: str, field: str) -> str:
        return self.fields.get(str(field), {}).get(str(role), 'none')

    def can_view_field(self, role: str, field: str, relationship: str) -> bool:
        if relationship not in RELATIONSHIPS:
            raise ValueError(f'Relação inválida: {relationship}')
        scope = self.field_scope(role, field)
        if scope == 'all':
            return True
        return scope == relationship


class PolicyStore:
    """Holds the active policy and reloads it atomically on request."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else _default_path()
        self._policy = load_policy(self.path)
        self.revision = 1

    @property
    def policy(self) -> Policy:
        return self._policy

    def reload(self) -> Policy:
        novo = load_policy(self.path)
        self._policy = novo
        self.revision += 1
        return novo


def _default_path() -> Path | None:
    base = os.environ.get('AUTOSEG_BASE')
    if base:
        candidato = Path(base).expanduser() / 'policy.yaml'
        if candidato.is_file():
            return candidato
    candidato = PASTA_APP / 'flavors' / 'autoseg' / 'config' / 'policy.yaml'
    return candidato if candidato.is_file() else None


def load_policy(path: str | Path | None = None) -> Policy:
    destino = Path(path) if path is not None else _default_path()
    if destino is None or not destino.is_file():
        return _policy_from_dict(PADRAO)
    try:
        import yaml
        dados = yaml.safe_load(destino.read_text(encoding='utf-8'))
    except Exception as erro:
        raise PolicyError(f'policy.yaml inválido ({destino}): {erro}') from erro
    return _policy_from_dict(dados)


def _policy_from_dict(dados) -> Policy:
    if not isinstance(dados, dict) or dados.get('versao') != 1:
        raise PolicyError('policy.yaml precisa de versao: 1')
    roles_raw = dados.get('roles')
    if not isinstance(roles_raw, dict) or not roles_raw:
        raise PolicyError('policy.yaml precisa de roles')
    roles = {}
    for nome, config in roles_raw.items():
        if not isinstance(nome, str) or not nome.strip():
            raise PolicyError('nome de papel inválido')
        if not isinstance(config, dict):
            raise PolicyError(f'papel {nome} inválido')
        perms = config.get('permissions', [])
        if not isinstance(perms, list) or not all(isinstance(x, str) and x.strip()
                                                   for x in perms):
            raise PolicyError(f'permissões inválidas no papel {nome}')
        roles[nome] = frozenset(x.strip() for x in perms)

    campos_raw = dados.get('campos', {})
    if not isinstance(campos_raw, dict):
        raise PolicyError('campos inválido')
    fields = {}
    for campo, regras in campos_raw.items():
        if not isinstance(campo, str) or '.' not in campo:
            raise PolicyError(f'campo inválido: {campo}')
        if not isinstance(regras, dict):
            raise PolicyError(f'regras inválidas para {campo}')
        normalizado = {}
        for papel, escopo in regras.items():
            if papel not in roles:
                raise PolicyError(f'campo {campo} usa papel inexistente: {papel}')
            if escopo not in SCOPES:
                raise PolicyError(f'escopo inválido para {campo}/{papel}: {escopo}')
            normalizado[papel] = escopo
        fields[campo] = normalizado
    return Policy(version=1, roles=roles, fields=fields)
