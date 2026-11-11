"""Customer role administration; SQL mutation and audit share one transaction."""
from __future__ import annotations

from html import escape

from flavors.autoseg.modules import accounts, web_session
from officina.application.object_policy import ObjectPolicy, Resource
from officina.core import portal_negocios as neg


def _authorize(principal):
    ObjectPolicy().require(principal, "manage",
                           Resource("account", organization_id="autoseg"))


def listing(banco, principal):
    _authorize(principal)
    return accounts.list_client_accounts(banco)


def change_role(banco, principal, account_id: int, role: str):
    _authorize(principal)
    previous = accounts.account_link(banco,account_id)
    if previous is None or previous.link_type != "client":
        raise PermissionError("Conta indisponível.")
    # Both operations use one SQLite transaction. The callback throws on audit
    # failure, rolling back the role change.
    result = accounts.set_client_role(banco, account_id, role, audit=lambda c: neg.audit(
        c,principal.provider_id,"Papel de cliente alterado",account_id,
        f"{previous.client_role} -> {role}"))
    # In-memory revocation cannot be part of SQLite transaction; it occurs
    # immediately after commit, before an HTTP response is emitted.
    web_session.revoke_account(account_id)
    if result.client_user_id is not None:
        web_session.revoke_identity("client", int(result.client_user_id))
    return result


def render_accounts(handler,banco,session,principal):
    rows=listing(banco,principal)
    body=['<section class="card"><h2>Contas de cliente</h2><table>'
          '<thead><tr><th>Conta</th><th>Nome</th><th>Status</th>'
          '<th>Papel</th></tr></thead><tbody>']
    for row in rows:
        opts=''.join(f'<option value="{role}" '
                     f'{"selected" if role==row.client_role else ""}>{role}</option>'
                     for role in accounts.CLIENT_ROLES)
        body.append(f'<tr><td>{row.account_id}</td>'
                    f'<td>{escape(row.display_name)}</td>'
                    f'<td>{"Ativa" if row.active else "Inativa"}</td><td>'
                    f'<form method="post" action="/contas/{row.account_id}/papel">'
                    f'<input type="hidden" name="csrf" value="{escape(session["csrf"])}">'
                    f'<select name="papel">{opts}</select>'
                    '<button type="submit">Atualizar</button></form></td></tr>')
    body.append('</tbody></table></section>')
    return handler.pagina('Contas de cliente',''.join(body),session)
