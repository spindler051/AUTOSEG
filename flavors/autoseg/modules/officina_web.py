"""AUTOSEG adapter for the single Officina Web shell, preserving portal CSS."""
from __future__ import annotations
from html import escape
from officina.application.policy import load_policy
from officina.web import Brand, PageContext, ShellPage, render_shell
from flavors.autoseg.modules.autoseg_web_navigation import navigation_for, canonical_client_path, client_path_allowed

BRAND = Brand(product_name='Officina Web', provider_label='Portal do prestador',
              client_label='Portal do cliente')

def context_for(session, csrf: str = '') -> PageContext:
    if session is None:
        return PageContext(BRAND, 'anonymous', '', 'Acesso à plataforma')
    if isinstance(session, dict):
        kind, name = 'provider', session.get('nome', '')
        role = 'admin' if session.get('admin') else 'employee'
        csrf = csrf or session.get('csrf', '')
        permissions = load_policy().roles.get(role, frozenset())
    else:
        shared = getattr(session, 'context', None)
        kind = shared.identity_kind if shared is not None else session.identity.kind
        name = shared.display_name if shared is not None else session.identity.display_name
        role = shared.role if shared is not None else session.principal.role
        csrf = csrf or session.csrf
        permissions = (shared.permissions if shared is not None
                       else load_policy().roles.get(role, frozenset()))
    ctx = PageContext(BRAND, kind, name,
                      BRAND.client_label if kind == 'client' else BRAND.provider_label,
                      csrf=csrf, role=role, permissions=frozenset(permissions))
    from dataclasses import replace
    return replace(ctx, navigation=navigation_for(ctx))



def render_chrome(page: ShellPage) -> str:
    """AUTOSEG owns layout_app, styles, and brand substitutions."""
    from flavors.autoseg.modules.portal_prestador import layout_app
    ctx = page.context
    user = page.user if ctx.kind == 'provider' and page.user is not None else (None if ctx.kind == 'anonymous' else {
        'nome': ctx.display_name, 'csrf': ctx.csrf,
        'admin': ctx.role == 'admin',
        'pid': getattr(ctx, 'provider_id', None),
    })
    html = layout_app(page.title, page.content, user, path=page.path,
                      cliente=ctx.kind == 'client', banco=page.banco,
                      page_context=ctx, navigation=page.navigation)
    html = html.replace(' · AUTOSEG</title>', ' · Officina Web</title>', 1)
    html = html.replace('>Gestão de Serviços</span>', '>Officina Web</span>', 1)
    if ctx.kind == 'provider':
        html = html.replace('AUTOMAÇÃO E SEGURANÇA · Portal de Serviços',
                            'Officina Web · Portal do prestador', 1)
    return html


def render_page(page: ShellPage) -> str:
    """Only AUTOSEG binds a concrete renderer to the generic shell."""
    return render_shell(page, render_chrome)


def page(handler, title: str, body: str, session=None, status: int = 200) -> None:
    # No client-specific layout or nav. The handler's pagina is the ONE renderer.
    if status == 200:
        return handler.pagina(title, body, session)
    return handler.pagina(title, body, session, status=status)

def login_page(handler, error: str = '', identifier: str = '') -> None:
    identifier = escape(str(identifier or '')[:180], quote=True)
    if error == 'rate':
        message = 'Muitas tentativas. Aguarde dez minutos.'
    elif error:
        message = 'Credenciais inválidas.'
    else:
        message = ''
    alert = (f'<p class="bad login-erro" id="login-erro" role="alert">{message}</p>'
             if message else
             '<p class="bad login-erro" id="login-erro" role="alert" hidden></p>')
    form_html = ('<form class="login-form" method="post" action="/login" data-login-form="1">'
                 + alert +
                 '<label for="c_identificador">E-mail, CPF ou telefone</label>'
                 f'<input id="c_identificador" type="text" name="identificador" '
                 f'value="{identifier}" autocomplete="username" required>'
                 '<label for="c_senha">Senha</label>'
                 '<input id="c_senha" type="password" name="senha" '
                 'autocomplete="current-password" required>'
                 '<button type="submit">Entrar</button></form>')
    from flavors.autoseg.modules.portal_prestador import login_shell_markup
    body = login_shell_markup(
        form_html=form_html,
        lede='Use seu e-mail, CPF ou telefone e senha.',
        note='Prestadores e clientes usam a mesma entrada. O cadastro de prestadores '
             'é feito pelo aplicativo desktop.',
    )
    return page(handler, 'Entrar', body)
