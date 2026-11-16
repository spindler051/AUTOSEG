"""Prevent fields hidden from an editor from being reset or overwritten."""

def safe_customer_edit(banco, principal, current, submitted, *, connection=None):
    """Merge submitted fields with current rows; ignore forbidden edits.

    Called *inside* the service's BEGIN IMMEDIATE and authorization boundary.
    The admin decision is re-read from the database, never taken from a stale
    session role: a demoted administrator must not keep hidden-field access.
    """
    from contextlib import nullcontext
    from officina.core import prestadores_ext as ext
    from officina.core.portal_negocios import CLIENTE_CAMPOS
    if (principal is None or type(principal.provider_id) is not int
            or principal.provider_id <= 0):
        raise PermissionError('Identidade obrigatória.')
    with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
        live_admin = bool(ext.administrador(c, principal.provider_id))
    if live_admin:
        allowed = frozenset(CLIENTE_CAMPOS)
    else:
        from officina.application.work_item_access import involved_customer_field_scopes
        scoped = involved_customer_field_scopes(principal)
        allowed = frozenset({'status'} | set(scoped) | ({'cidade'} if 'endereco' in scoped else set()))
    return {field: submitted[field] if field in allowed and field in submitted else current[field]
            for field in CLIENTE_CAMPOS}

