"""Generic navigation filtering; data is supplied by an application's flavor."""
from .context import NavItem


def _allows(permissions: frozenset[str], permission: str) -> bool:
    return ('*' in permissions or permission in permissions
            or any(grant.startswith(permission + '.') for grant in permissions))


def navigation_for(context, items: tuple[NavItem, ...]) -> tuple[NavItem, ...]:
    """Filter a flavor-provided item table by identity context and grants."""
    kind = getattr(context, 'identity_kind', getattr(context, 'kind', 'anonymous'))
    permissions = frozenset(getattr(context, 'permissions', ()) or ())
    return tuple(item for item in items if kind in item.contexts
                 and (not item.permission or _allows(permissions, item.permission)))


def active_for(path: str, navigation: tuple[NavItem, ...]) -> str:
    matches = (item for item in navigation if item.href == path
               or (item.href != '/' and path.startswith(item.href + '/')))
    return next((item.id for item in matches), '')
