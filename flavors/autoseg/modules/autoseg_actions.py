"""Canonical per-section actions for the provider web/GTK adapters.

The service resolves these descriptions using current server-side grants and
object links. Clients never send or choose their authorization context.
"""
from __future__ import annotations

from dataclasses import asdict
from importlib import import_module

from flavors.autoseg.modules.autoseg_web_navigation import ITEMS
from officina.application.policy import load_policy
from officina.application import work_item_access as access
from officina.core import prestadores_ext as ext


def _all_actions():
    actions = []
    for item in ITEMS:
        module = import_module('flavors.autoseg.modules.action_sections.'
                               + item.id.replace('-', '_'))
        actions.extend(module.ACTIONS)
    return tuple(actions)


ACTIONS = _all_actions()
ACTION_BY_ID = {action.id: action for action in ACTIONS}


def _object_permitted(banco, principal, action, object_id):
    if action.object_action in ('list', 'create'):
        if action.section == 'work' and action.object_action == 'create':
            access.require_create(banco, principal)
        if action.section == 'customers' and action.object_action == 'create':
            access.require_customer_create(principal)
        return True
    if object_id is None:
        return False
    if action.section == 'work':
        if action.object_action == 'assume':
            with ext.db(banco) as connection:
                return bool(principal.provider_id and
                            ext.pode_assumir(connection, int(object_id),
                                             principal.provider_id))
        access.require_work_item(banco, principal, int(object_id),
                                 action.object_action)
        return True
    if action.section == 'customers':
        if action.object_action == 'view':
            access.require_customer_read(banco, principal, int(object_id))
        else:
            access.require_customer_write(banco, principal, int(object_id))
        return True
    return True


def resolved_actions(banco, principal, section, *, object_id=None, surface=None):
    """Server-authoritative action list; object grants cannot be inferred by UI."""
    if principal is None or not principal.active:
        raise PermissionError('Sessão indisponível.')
    canonical = next((item for item in ITEMS if item.id == section), None)
    if canonical is None or (surface and surface not in canonical.surfaces):
        return ()
    if 'provider' in canonical.contexts and principal.provider_id is None:
        return ()
    if 'client' in canonical.contexts and principal.provider_id is not None:
        return ()
    policy = load_policy()
    visible = []
    for action in ACTIONS:
        if action.section != section or (surface and surface not in action.surfaces):
            continue
        if not policy.allows(principal.role,
                             'provider.manage.all' if action.permission == '*'
                             else action.permission):
            continue
        try:
            if not _object_permitted(banco, principal, action, object_id):
                continue
        except (PermissionError, ValueError, TypeError):
            continue
        visible.append(action)
    order = {'primary': 0, 'secondary': 1, 'menu': 2}
    return tuple(sorted(visible, key=lambda action: (order[action.priority],
                                                     ACTIONS.index(action))))


def action_payload(banco, principal, section, *, object_id=None, surface=None):
    return [asdict(action) for action in resolved_actions(
        banco, principal, section, object_id=object_id, surface=surface)]
