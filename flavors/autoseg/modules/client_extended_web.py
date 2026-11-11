"""Unified-shell presentation for authenticated customer profile/PJ/quotes.

Only renders content fragments; business rules and SQL remain in services.
"""
from __future__ import annotations
from html import escape
from urllib.parse import parse_qs, urlsplit, urlencode

from flavors.autoseg.modules import client_features as features, client_service, officina_web
from flavors.autoseg.modules import web_cookie, web_session


def _e(value):
    return escape(str(value if value is not None else ''), quote=True)


def _field(label, name, value='', required=False, typ='text'):
    return (f'<label for="{_e(name)}">{_e(label)}</label>'
            f'<input id="{_e(name)}" name="{_e(name)}" type="{_e(typ)}" '
            f'value="{_e(value)}" {"required" if required else ""}>')


def _select(label, name, values):
    return f'<label for="{_e(name)}">{_e(label)}</label><select id="{_e(name)}" name="{_e(name)}">' + ''.join(
        f'<option value="{_e(a)}">{_e(b)}</option>' for a,b in values) + '</select>'


def _form(session, action, fields, button):
    return (f'<form method="post" action="{_e(action)}">{web_cookie.csrf_input(session)}'
            + fields + f'<button type="submit">{_e(button)}</button></form>')


def _page(handler, session, title, body, error=''):
    notice = f'<p role="alert" class="bad">{_e(error)}</p>' if error else ''
    return officina_web.page(handler, title, '<section class="card">'+notice+body+'</section>', session)


def _params(handler):
    return parse_qs(urlsplit(handler.path).query)


def _param(handler, name, default=''):
    return _params(handler).get(name,[default])[0]


def profile(handler, banco, session, error=''):
    data=features.profile(banco, session)
    columns=(('Nome completo','nome',True),('Telefone com DDD','telefone',True),
             ('E-mail','email',True),('Rua / avenida / endereço','endereco',True),
             ('Número (ou S/N)','numero',True),('Bairro (opcional)','bairro',False),
             ('Cidade','cidade',True),('UF','uf',True),('CEP (opcional)','cep',False))
    inputs=''.join(_field(label,key,data.get(key,''),required,
                          'email' if key=='email' else 'text')
                   for label,key,required in columns)
    return _page(handler,session,'Meus dados para atendimento particular',
        '<h2>Complete o perfil PF</h2><p>Antes de abrir uma OS particular, informe telefone, e-mail e endereço. '
        'Para chamados de condomínios e empresas, basta entrar com CPF e senha.</p>'
        +_form(session,'/cliente/perfil',inputs,'Salvar meus dados')
        +'<p><a href="/cliente/senha">Alterar minha senha</a></p>',error)


def password(handler, banco, session, error=''):
    fields=''.join(_field(label,key,required=True,typ='password') for label,key in (
        ('Senha atual','senha_atual'),
        ('Nova senha (mínimo 10 caracteres, com letras e números)','nova_senha'),
        ('Confirmar nova senha','confirmar_senha')))
    return _page(handler,session,'Alterar minha senha',
        '<h2>Segurança da conta</h2><p>Você só pode alterar a senha da própria conta. '
        'As demais sessões serão encerradas após a mudança.</p>'
        +_form(session,'/cliente/senha',fields,'Alterar minha senha'),error)


def organization_search(handler, banco, session):
    q=str(_param(handler,'q'))[:120]
    try:page=int(_param(handler,'page','1'))
    except ValueError:page=1
    rows,total=features.search_organizations(banco,session,q,page)
    links=''.join('<article class="card"><h3>'+_e(r['nome'])+'</h3>'
                  '<p>'+_e(r['tipo'])+' · '+_e(r['bairro'])+' · '+_e(r['cidade'])+'</p>'
                  f'<a class="btn" href="/cliente/chamado/novo?org={r["id"]}">Pedir serviço neste local</a></article>'
                  for r in rows)
    pager=f'<p>{total} local(is) encontrado(s) · Página {page}</p>'
    if page>1:pager+=f'<a href="/cliente/organizacoes?{_e(urlencode({"q":q,"page":page-1}))}">Voltar uma página</a> '
    if page*20<total:pager+=f'<a href="/cliente/organizacoes?{_e(urlencode({"q":q,"page":page+1}))}">Ver mais resultados</a>'
    return _page(handler,session,'Escolha seu condomínio ou empresa',
        '<h2>1. Encontre o local</h2><p>Procure pelo nome. Não é preciso saber o CNPJ ou ser síndico.</p>'
        '<form method="get" action="/cliente/organizacoes">'+_field('Nome do condomínio ou empresa','q',q)
        +'<button type="submit">Buscar</button></form>'
        '<h2>2. Escolha e peça o atendimento</h2>'+pager+(links or '<p>Nenhum resultado com esse nome.</p>')
        +'<p><a href="/cliente/nova-organizacao">Cadastrar local e solicitar OS</a></p>')


def organization_create(handler,banco,session):
    features.uid(session)
    fields=(_select('Tipo de local','tipo',((x,x) for x in ('Condomínio','Empresa')))
       +''.join(_field(label,key,required=req) for label,key,req in (
        ('Nome do condomínio ou empresa','nome',True),('Endereço completo','endereco',True),
        ('Cidade','cidade',True),('Bairro','bairro',False),
        ('Telefone de contato do local (DDD)','telefone',True),('CNPJ (opcional)','cnpj',False)))
       +_select('Você é','papel',(('Morador','Morador'),('Funcionário','Funcionário / porteiro')))
       +''.join(_field(label,key,required=True) for label,key in (
         ('Seu nome completo para contato','solicitante_nome'),('Seu telefone com DDD','solicitante_telefone'),
         ('Apartamento ou cargo','unidade')))
       +_select('Urgência','urgencia',((x,x) for x in ('Normal','Alta','Baixa')))
       +'<label for="descricao">Descreva o serviço solicitado</label><textarea id="descricao" name="descricao" required></textarea>')
    return _page(handler,session,'Cadastrar local e solicitar OS',
        '<h2>Condomínio ou empresa</h2><p>Cadastro e solicitação em uma única página</p>'
        +_form(session,'/cliente/nova-organizacao',fields,'Cadastrar local e solicitar OS'))


def manage_organization(handler,banco,session):
    features.uid(session)
    return _page(handler,session,'Solicitação de gestão',
         '<h2>Acesso como síndico ou gestor</h2>'
         '<p>O síndico ou gestor é nomeado somente pelo prestador ou pelo desktop, '
         'a partir de uma conta PF existente.</p>')


def link_request(handler,banco,session):
    org_id=int(_param(handler,'org','0'))
    org=features.organization(banco,session,org_id)
    fields=(f'<input type="hidden" name="org_id" value="{org_id}">'
        +_select('Minha função na organização','funcao',((x,x) for x in
         ('Síndico','Proprietário','Representante legal','Administrador')))
        +_field('CNPJ','cnpj',required=bool(org.get('cnpj'))))
    return _page(handler,session,'Responsável pelo condomínio / empresa',
        '<h2>Solicitar gestão — '+_e(org['nome'])+'</h2>'
        '<p>O vínculo será analisado pela AUTOSEG. Isso não concede acesso de síndico imediatamente.</p>'
        +_form(session,'/cliente/vinculo/novo',fields,'Solicitar vínculo de responsável'))


def call_new(handler,banco,session):
    org_id=int(_param(handler,'org','0'))
    org=features.organization(banco,session,org_id)
    p=features.profile(banco,session)
    fields=(f'<input type="hidden" name="org_id" value="{org_id}">'
        +_select('Meu papel neste local','papel',(('Morador','Morador'),('Funcionário','Funcionário / porteiro')))
        +_field('Seu nome completo (para contato)','solicitante_nome',p.get('nome',''),True)
        +_field('Seu telefone com DDD (para contato)','solicitante_telefone',p.get('telefone',''),True)
        +_field('Apartamento ou cargo / função','unidade',_param(handler,'unidade'),True)
        +_select('Urgência','urgencia',((x,x) for x in ('Normal','Alta','Baixa')))
        +'<label for="descricao">Conte o que aconteceu e onde precisa do serviço</label>'
         '<textarea id="descricao" name="descricao" required></textarea>')
    return _page(handler,session,'Solicitar serviço — '+org['nome'],
        '<h2>Etapa final: descreva o problema</h2>'
        '<p>Você pode solicitar mesmo sem ser síndico ou administrador.</p>'
        +_form(session,'/cliente/chamado/novo',fields,'Enviar pedido de atendimento'))


def quote(handler,banco,session):
    services=features.quote_services(banco,session)
    if not services:return _page(handler,session,'Solicitar orçamento',
        '<h2>Serviços disponíveis</h2><p>Ainda não há serviços com valores cadastrados. Consulte a AUTOSEG.</p>')
    rows=''.join('<li>'+_e(s['nome'])+' — '+_e(v)+' (estimado por unidade)</li>'
                 for s,v in services)
    fields=(_select('Serviço','servico_id',((s['id'],s['nome']) for s,v in services))
       +_field('Quantidade (de 1 a 20)','quantidade','1',True))
    return _page(handler,session,'Orçamento estimativo',
        '<h2>Serviços e valores</h2><ul>'+rows+'</ul>'
        '<p>O valor é calculado com base no catálogo e pode mudar após vistoria.</p>'
        +_form(session,'/cliente/orcamento/pdf',fields,'Gerar orçamento em PDF'))


def responsible_history(handler,banco,session):
    org=int(_param(handler,'org','0'))
    data=features.organization_history(banco,session,org)
    rows=''.join('<tr><td>'+_e(item['numero_os'])+'</td><td>'+_e(item['descricao'])+
         '</td><td>'+_e(item['status'])+'</td><td>'+_e(item['solicitante'] or 'Abertura administrativa / prestador')+
         '</td><td><a href="/cliente/organizacao/'+str(org)+'/os/'+str(item['id'])+
         '/pdf">Relatório PDF</a></td></tr>' for item in data['os'])
    return _page(handler,session,'Histórico da organização',
        '<h2>Todas as ordens de serviço — '+_e(data['organizacao']['nome'])+'</h2>'
        '<p>Inclui solicitações do síndico, dos condôminos, dos funcionários e OS criadas pelo prestador.</p>'
        '<table><thead><tr><th>OS</th><th>Descrição</th><th>Situação</th><th>Solicitante</th><th>PDF</th></tr></thead><tbody>'+rows+'</tbody></table>')


def extra_home(banco,session):
    p=features.profile(banco,session)
    orgs=features.linked_organizations(banco,session)
    responsible=features.approved_organizations(banco,session)
    body='<section class="card"><h2>Minha conta e organizações</h2>'
    body+='<p>'+_e(p.get('nome') or 'Você está conectado(a)')+'</p>'
    for name,url in (('Editar meus dados','/cliente/perfil'),('Alterar minha senha','/cliente/senha'),
                     ('Pedir serviço para condomínio ou empresa','/cliente/organizacoes'),
                     ('Orçamento estimativo em PDF','/cliente/orcamento')):
        body+=f'<p><a href="{url}">{_e(name)}</a></p>'
    for org in orgs:
        body+='<p>'+_e(org['nome'])+' · '+_e(org['situacao'])+' '
        body+=f'<a href="/cliente/chamado/novo?org={org["id"]}">Solicitar serviço</a></p>'
    for org in responsible:
        body+=f'<p><a href="/cliente/sindico?org={org["id"]}">Consultar todas as OS — {_e(org["nome"])}</a></p>'
    return body+'</section>'


_GET = {'/cliente/perfil': profile, '/cliente/senha': password,
        '/cliente/organizacoes':organization_search,
        '/cliente/nova-organizacao':organization_create,
        '/cliente/administrar-organizacao':manage_organization,
        '/cliente/vinculo/novo':link_request,
        '/cliente/chamado/novo':call_new,
        '/cliente/orcamento':quote,
        '/cliente/sindico':responsible_history,
        '/cliente/os/nova':lambda h,b,s: _page(h,s,'Nova OS particular',
              '<p>Para solicitar atendimento particular, complete primeiro seu perfil.</p>'
              '<p><a href="/solicitar">Solicitar serviço</a></p>')}


def dispatch_get(handler,banco,session,path):
    if path in _GET:
        return _GET[path](handler,banco,session)
    parts=path.strip('/').split('/')
    try:
        if len(parts)==4 and parts[:2]==['cliente','os'] and parts[2].isdigit() and parts[3]=='pdf':
            return _download(handler, features.report_for_work(banco,session,int(parts[2])))
        if len(parts)==3 and parts[:2]==['cliente','nota'] and parts[2].isdigit():
            return _download(handler, features.invoice_by_id(banco,session,int(parts[2])))
        if len(parts)==4 and parts[:2]==['cliente','chamado'] and parts[2].isdigit() and parts[3]=='pdf':
            return _download(handler, features.report_for_call(banco,session,int(parts[2])))
        if (len(parts)==6 and parts[:2]==['cliente','organizacao'] and parts[2].isdigit()
                and parts[3]=='os' and parts[4].isdigit() and parts[5]=='pdf'):
            return _download(handler, features.report_for_organization(banco,session,int(parts[2]),int(parts[4])))
    except (PermissionError,ValueError,TypeError):
        return handler.erro('Documento indisponível.',404)
    return handler.erro('Página indisponível.',404)


def _download(handler, result):
    content,mime,filename=result
    return handler.send_bytes(content,mime,filename=filename)


def dispatch_post(handler,banco,session,path,data):
    if not web_cookie.csrf_valid(session,str(data.get('csrf',''))):
        return handler.erro('Formulário expirado ou sessão inválida.',403)
    try:
        if path=='/cliente/perfil':
            features.update_profile(banco,session,data)
            return handler.redir('/cliente/perfil')
        if path=='/cliente/senha':
            features.change_password(banco,session,data)
            # Sessions are invalidated by credential fingerprint on next use;
            # revoke the current token now for immediate consistency.
            web_session.revoke(banco,web_cookie.token_from_headers(handler.headers))
            return handler.redir('/login',web_cookie.clear_cookie(secure=web_cookie.secure_request(handler.headers)))
        if path=='/cliente/administrar-organizacao':
            raise PermissionError('A nomeação de síndico/gestor só pode ser feita pelo prestador ou desktop.')
        if path=='/cliente/nova-organizacao':
            item=features.create_organization_request(banco,session,data)
            return handler.redir('/chamado/'+str(item['chamado_id']))
        if path=='/cliente/chamado/novo':
            item=features.create_call(banco,session,data)
            return handler.redir('/chamado/'+str(item))
        if path=='/cliente/vinculo/novo':
            features.request_link(banco,session,data)
            return handler.redir('/cliente/organizacoes')
        if path=='/cliente/orcamento/pdf':
            return _download(handler,features.quote_pdf(banco,session,data))
        if path=='/cliente/os/nova':
            from flavors.autoseg.modules import client_web
            return client_web.request_submit(handler,banco,session,data)
    except ValueError as error:
        return handler.erro(str(error),409)
    except PermissionError:
        return handler.erro('Recurso indisponível.',403)
    return handler.erro('Página indisponível.',404)
