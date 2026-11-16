"""Prevent fields hidden from an editor from being reset or overwritten."""

def safe_customer_edit(banco, principal, current, submitted):
    """Merge submitted fields with current rows; ignore forbidden edits.

    Called *inside* the service's BEGIN IMMEDIATE and authorization boundary.
    """
    from officina.core.portal_negocios import CLIENTE_CAMPOS
    if principal is None:
        raise PermissionError('Identidade obrigatória.')
    if principal.role == 'admin':
        allowed = frozenset(CLIENTE_CAMPOS)
    else:
        from officina.application.work_item_access import involved_customer_field_scopes
        scoped = involved_customer_field_scopes(principal)
        allowed = frozenset({'status'} | set(scoped) | ({'cidade'} if 'endereco' in scoped else set()))
    return {field: submitted[field] if field in allowed and field in submitted else current[field]
            for field in CLIENTE_CAMPOS}

