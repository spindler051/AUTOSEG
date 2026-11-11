"""AUTOSEG branding and navigation for the generic Officina Web shell."""
from __future__ import annotations

from officina.web import Brand, NavItem, PageContext

BRAND = Brand(product_name="Officina Web",
              provider_label="Portal do prestador", client_label="Portal do cliente")


def provider_navigation(admin: bool) -> tuple[NavItem, ...]:
    nav = [NavItem("home", "Visão geral", "/"),
           NavItem("work", "Ordens de serviço ativas", "/os"),
           NavItem("customers", "Clientes", "/clientes"),
           NavItem("finance", "Financeiro", "/financeiro")]
    if admin:
        nav.append(NavItem("providers", "Prestadores", "/prestadores"))
    return tuple(nav)


def client_navigation() -> tuple[NavItem, ...]:
    return (NavItem("home", "Painel", "/cliente"),
            NavItem("work", "Minhas OS", "/cliente/os"),
            NavItem("documents", "Documentos", "/cliente/documentos"),
            NavItem("request", "Solicitar serviço", "/cliente/solicitar"))


def context_for(session, csrf: str = "") -> PageContext:
    if session is None:
        return PageContext(BRAND, "anonymous", "", "Acesso à plataforma")
    if isinstance(session, dict):
        kind = "provider"
        name = session.get("nome", "")
        role = "admin" if session.get("admin") else "employee"
        csrf = csrf or session.get("csrf", "")
    else:
        # Unified sessions provide the same DTO consumed by the desktop API.
        # Older presentation mocks and legacy contexts retain their shape.
        shared = getattr(session, 'context', None)
        kind = shared.identity_kind if shared is not None else session.identity.kind
        name = shared.display_name if shared is not None else session.identity.display_name
        role = shared.role if shared is not None else session.principal.role
        csrf = csrf or session.csrf
    if kind == "client":
        return PageContext(BRAND, "client", name, BRAND.client_label,
                           client_navigation(), csrf)
    if kind == "provider":
        return PageContext(BRAND, "provider", name, BRAND.provider_label,
                           provider_navigation(role == "admin"), csrf)
    return PageContext(BRAND, "anonymous", "", "Acesso à plataforma")


def page(handler, title: str, body: str, session=None, status: int = 200) -> None:
    """Render with the existing portal CSS; keep the shared context as data."""
    context = context_for(session)
    if context.kind == "client":
        from html import escape
        links = ''.join(
            f'<a href="{escape(item.href, quote=True)}">{escape(item.label)}</a>'
            for item in context.navigation)
        header = ('<section class="card"><strong>Officina Web · Portal do cliente</strong>'
                  f'<p>{escape(context.display_name)}</p>'
                  f'<nav class="nav">{links}</nav>'
                  f'<form method="post" action="/cliente/sair">'
                  f'<input type="hidden" name="csrf" value="{escape(context.csrf, quote=True)}">'
                  '<button class="subtle" type="submit">Sair</button></form></section>')
        return handler.pagina(title, header + body, None, status=status, cliente=True)
    return handler.pagina(title, body, session, status=status)


def login_page(handler, error: str = "", identifier: str = "") -> None:
    """Use the live portal login layout rather than an unused minimal HTML shell."""
    from html import escape
    identifier = escape(str(identifier or "")[:180], quote=True)
    alert = '<p class="bad" role="alert">Credenciais inválidas.</p>' if error else ''
    body = ('<section class="card"><h2>Entrar</h2>' + alert +
            '<form method="post" action="/entrar">'
            '<label for="unified_identifier">Identificador</label>'
            f'<input id="unified_identifier" name="identificador" '
            f'autocomplete="username" value="{identifier}" required>'
            '<label for="unified_password">Senha</label>'
            '<input id="unified_password" type="password" name="senha" '
            'autocomplete="current-password" required>'
            '<button type="submit">Entrar</button></form>'
            '<p><a href="/login">Usar login antigo</a></p></section>')
    return handler.pagina("Entrar", body, None)
