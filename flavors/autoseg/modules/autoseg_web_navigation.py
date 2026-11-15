"""AUTOSEG-specific navigation, route registry, and legacy URL aliases.

The generic officina.web package knows none of these names or endpoints.
"""
from officina.web import NavItem, WebRoute
from officina.web.navigation import navigation_for as filter_navigation, active_for

ITEMS = (
    NavItem("home", "Início", "/", contexts=("provider",), group="Operação", icon="home", top=True, top_order=0),
    NavItem("work", "Ordens de serviço", "/os", contexts=("provider",), group="Operação", icon="clipboard", top=True, top_order=2),
    NavItem("customers", "Clientes", "/clientes", contexts=("provider",), group="Operação", icon="users", top=True, top_order=1),
    NavItem("services", "Serviços e valores", "/servicos", contexts=("provider",), group="Gestão", icon="wrench", top=True, top_order=3),
    NavItem("finance", "Financeiro", "/financeiro", contexts=("provider",), group="Gestão", icon="wallet", top=True, top_order=4),
    NavItem("invoices", "Notas fiscais", "/notas", contexts=("provider",), group="Gestão", icon="receipt", top=True, top_order=6),
    NavItem("email", "E-mails", "/emails", contexts=("provider",), group="Gestão", icon="mail", top=True, top_order=7),
    NavItem("providers", "Prestadores", "/prestadores", permission="*", contexts=("provider",), group="Gestão", icon="users", top=True, top_order=9),
    NavItem("stock", "Estoque", "/estoque", permission="*", contexts=("provider",), group="Gestão", icon="wrench", top=True, top_order=10),
    NavItem("composition", "Composição de valores", "/composicao", permission="*", contexts=("provider",), group="Gestão", icon="layout", top=True, top_order=11),
    NavItem("history", "Histórico e relatórios", "/historico", contexts=("provider",), group="Registros", icon="history", top=True, top_order=8),
    NavItem("public", "Solicitações PJ", "/pj-publicas", contexts=("provider",), group="Registros", icon="building", top=True, top_order=5),
    NavItem("settings", "Configurações", "/configuracoes", contexts=("provider",), group="Registros", icon="settings"),
    NavItem("feedback", "Feedbacks", "/feedback/recebidos", permission="*", contexts=("provider",), group="Registros", icon="message", top=True, top_order=12),
    NavItem("client-home", "Painel", "/", contexts=("client",), group="Minha conta", icon="home", top=True, top_order=0),
    NavItem("client-work", "Minhas OS", "/os", permission="work_item.view", contexts=("client",), group="Minha conta", icon="clipboard", top=True, top_order=1),
    NavItem("client-documents", "Documentos", "/documentos", permission="document.view", contexts=("client",), group="Minha conta", icon="file", top=True, top_order=2),
    NavItem("client-request", "Solicitar serviço", "/solicitar", permission="work_item.create.request", contexts=("client",), group="Minha conta", icon="plus", top=True, top_order=3),
    NavItem("client-route", "Em rota", "/em-rota", permission="work_item.view", contexts=("client",), group="Minha conta", icon="arrow-right", top=True, top_order=4),
    NavItem("client-profile", "Meu perfil", "/cliente/perfil", contexts=("client",), group="Minha conta", icon="user"),
    NavItem("client-organizations", "Organizações", "/cliente/organizacoes", contexts=("client",), group="Minha conta", icon="building"),
    NavItem("client-quote", "Orçamento", "/cliente/orcamento", contexts=("client",), group="Minha conta", icon="receipt"),
)

def navigation_for(context):
    return filter_navigation(context, ITEMS)


def top_navigation_for(context, navigation=None):
    """Same NavItem objects as sidebar, selected by presentation metadata.

    The optional navigation is already permission/context filtered. It permits
    renderers to use the *same* snapshot for both navigation surfaces.
    """
    visible = navigation if navigation is not None else navigation_for(context)
    return tuple(sorted((item for item in visible if item.top),
                        key=lambda item: item.top_order))


# All client-only module handlers are injected explicitly by client_web.
def client_routes(*, home, list_items, documents, request_form, en_route):
    return (
        WebRoute('/', None, ('client',), home),
        WebRoute('/os', 'work_item.view', ('client',), list_items),
        WebRoute('/documentos', 'document.view', ('client',), documents),
        WebRoute('/solicitar', 'work_item.create.request', ('client',), request_form),
        WebRoute('/em-rota', 'work_item.view', ('client',), en_route),
    )


# Public contractual redirects only. Never infer aliases by prefix.
ALIASES = {
    '/cliente': '/', '/cliente/painel': '/', '/cliente/os': '/os',
    '/cliente/documentos': '/documentos',
    '/cliente/solicitar': '/solicitar', '/cliente/nova': '/solicitar',
    '/cliente/em-rota': '/em-rota',
    '/cliente/entrar-pf': '/login', '/cliente/sair-pf': '/sair',
}

# These are actual customer-only features, not URL aliases or a second portal.
MIGRATED_GET = frozenset({
    '/cliente/perfil', '/cliente/senha', '/cliente/os/nova', '/cliente/organizacoes',
    '/cliente/nova-organizacao', '/cliente/administrar-organizacao',
    '/cliente/vinculo/novo', '/cliente/chamado/novo', '/cliente/orcamento',
    '/cliente/sindico',
})
MIGRATED_POST = frozenset({
    '/cliente/perfil', '/cliente/senha', '/cliente/os/nova',
    '/cliente/nova-organizacao', '/cliente/vinculo/novo',
    '/cliente/administrar-organizacao', '/cliente/chamado/novo',
    '/cliente/orcamento/pdf',
})


def canonical_client_path(path: str) -> str | None:
    """Closed allowlist; an arbitrary /cliente/<path> is NEVER a redirect."""
    if path in ALIASES:
        return ALIASES[path]
    segments=path.strip('/').split('/')
    if len(segments)==3 and segments[:2]==['cliente','os'] and segments[2].isdigit():
        return '/os/'+segments[2]
    if len(segments)==3 and segments[:2]==['cliente','chamado'] and segments[2].isdigit():
        return '/chamado/'+segments[2]
    return None


def retired_client_path(path: str) -> bool:
    """Explicit product withdrawals B1/B2/B3 (410 Gone)."""
    return (path in ('/legado','/pj-rapido','/cliente/pj-rapido',
                    '/cliente/cadastro','/cliente/cadastrar','/cliente/cadastro-pj')
            or path.startswith('/legado/')
            or path.startswith('/pj-rapido/')
            or path.startswith('/cliente/pj-rapido/')
            or path.startswith('/cliente/cadastro/'))


CLIENT_PATHS = frozenset(('/', '/os', '/documentos', '/solicitar', '/em-rota'))


def client_path_allowed(path: str) -> bool:
    if path in CLIENT_PATHS or path in MIGRATED_GET:
        return True
    parts=path.strip('/').split('/')
    return ((len(parts)==2 and parts[0] in ('os','chamado') and parts[1].isdigit())
            or (len(parts)==4 and parts[0] in ('os','chamado')
                and parts[1].isdigit() and parts[2]=='documento'
                and parts[3].lstrip('-').isdigit())
            or (len(parts)==4 and parts[:2]==['cliente','os']
                and parts[2].isdigit() and parts[3]=='pdf')
            or (len(parts)==3 and parts[:2]==['cliente','nota'] and parts[2].isdigit())
            or (len(parts)==4 and parts[:2]==['cliente','chamado']
                and parts[2].isdigit() and parts[3]=='pdf')
            or (len(parts)==6 and parts[:2]==['cliente','organizacao']
                and parts[2].isdigit() and parts[3]=='os'
                and parts[4].isdigit() and parts[5]=='pdf'))
