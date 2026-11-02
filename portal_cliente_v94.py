"""Portal do cliente v9.4 — camada HTTP separada do backend AUTOSEG.

Conta de pessoa física única, reutilizada para solicitação particular, pré-cadastro
PJ e solicitação para organizações. Não interfere no portal do prestador/legado.
"""
import secrets
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit, urlencode

import cadastros_v9 as cad
import cliente_fluxo_v94 as fluxo_pf
import portal_v9 as v9
import prestadores_ext as ext
import catalogo_servicos as catalogo

VERSAO_PORTAL = '9.6.0'
_CSS_ACESSIVEL = '\n/* AUTOSEG 9.6 — Cliente: legibilidade e navegação inclusiva */\nbody{font-size:18px;line-height:1.65}\nmain{max-width:880px;margin:18px auto;padding:0 17px 65px}\nmain h1{font-size:clamp(24px,5vw,35px);line-height:1.2;margin:18px 0 24px}\n.card{padding:clamp(19px,4vw,30px);margin:19px 0;border-radius:16px}\n.card h2{font-size:clamp(20px,4vw,26px);line-height:1.35}\nlabel{font-size:18px;margin-top:18px}\ninput,textarea,select{min-height:54px;font-size:18px;border:2px solid #aaa;border-radius:11px;padding:13px}\nbutton,.btn{min-height:54px;min-width:150px;font-size:17px;padding:13px 20px;border-radius:11px;line-height:1.35}\nbutton:focus-visible,.btn:focus-visible,a:focus-visible,summary:focus-visible{outline:4px solid #fff;outline-offset:4px}\ninput:focus-visible,textarea:focus-visible,select:focus-visible{outline:3px solid var(--yellow);outline-offset:2px}\n.acao-principal .btn,.acao-principal button{display:block;text-align:center;width:100%;margin:12px 0}\n.passo{color:#ffe577;font-weight:800;letter-spacing:.01em;margin-bottom:6px}\n.ajuda{background:#242424;border:1px solid #777;border-radius:12px;padding:16px 19px;margin:16px 0}\n.ajuda summary{font-size:18px;font-weight:750;cursor:pointer}\n.ajuda p{margin-bottom:0}\n.resultado-organizacao{border:1px solid #666;border-radius:13px;padding:18px 20px;margin:14px 0;background:#202020}\n.resultado-organizacao h3{margin:0 0 5px;font-size:21px}\n.resultado-organizacao p{margin:4px 0 12px;color:#ddd}\n.resultado-organizacao .btn{width:100%;text-align:center;margin:0}\n.aviso-claro{border-left:5px solid var(--yellow);padding:15px 18px;background:#2a2617;border-radius:8px}\n.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}\n.skip-to-content{position:absolute;top:-120px;left:12px;padding:13px;background:var(--yellow);color:#000;z-index:9000;font-weight:bold}\n.skip-to-content:focus{top:12px}\n.table-scroll{overflow-x:auto;max-width:100%}\n.table-scroll table{min-width:640px} .table-scroll td:nth-child(3){min-width:160px;word-break:normal;overflow-wrap:normal} .table-scroll th:nth-child(3){min-width:160px}\n@media(max-width:630px){main{padding:0 14px 65px} .top{padding:10px 16px} .brand{font-size:25px} .tagline{font-size:12px} .card{padding:18px} .btn,button{width:100%;margin:7px 0} .nav{display:none} input,textarea,select{font-size:18px}}\n@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation-duration:.001ms!important;transition-duration:.001ms!important;scroll-behavior:auto!important}}\n'
FUNCOES_RESPONSAVEL = ('Síndico', 'Proprietário', 'Representante legal', 'Administrador')


def u():
    return v9.ui()


def cabecalho():
    return ''  # Link público exibido discretamente no rodapé, após o login.


def pagina_texto(titulo,corpo):
    """HTML completo do portal, sem escrever na resposta (usado pelo servidor 8765)."""
    _,layout,*_=u()
    html=layout(titulo,corpo).replace('<a class="brand" href="/">','<a class="brand" href="/cliente">',1)
    html=html.replace('</style>',_CSS_ACESSIVEL+'</style>',1)
    html=html.replace('<body><header>', '<body><a class="skip-to-content" href="#conteudo">Pular para o conteúdo</a><header>',1)
    html=html.replace('<main>', '<main id="conteudo" tabindex="-1">',1)
    return html.replace('</main>',v9.barra_links('cliente')+f'<p class="muted" style="text-align:center">AUTOSEG v{VERSAO_PORTAL} · portal do cliente · login por CPF e senha</p></main>',1)


def pagina(h,titulo,corpo,status=200):
    return h.responder(pagina_texto(titulo,corpo),status)


def login(h,aviso=''):
    card,_,campos,_,_,esc,botao,_=u()
    mensagem=('<p class="notice" role="alert">'+esc(aviso)+'</p>') if aviso else ''
    form=('<form method="post" action="/cliente/entrar-pf">'
          +campos('Seu CPF (somente números ou com pontos)','cpf',required=True)
          +campos('Sua senha','senha',kind='password',required=True)
          +'<button type="submit" style="width:100%">Entrar no portal</button></form>')
    corpo=card('Entre na sua conta',
        '<p>Use seu CPF e sua senha para solicitar um serviço ou acompanhar um pedido.</p>'
        +mensagem+form+'<p>Primeira vez aqui?</p>'
        +'<div class="acao-principal">'+botao('Criar minha conta','/cliente/cadastro','secondary')+'</div>')
    corpo+='<details class="ajuda"><summary>Preciso de ajuda para entrar</summary>'
    corpo+='<p>Se esqueceu a senha, fale com a AUTOSEG. Nunca informe sua senha no WhatsApp.</p>'
    corpo+=botao('Pedir ajuda pelo WhatsApp','https://wa.me/'+cad.WHATSAPP_AUTOSEG,'secondary')
    corpo+='</details>'
    corpo+='<details class="ajuda"><summary>Sou morador ou porteiro. Posso solicitar serviço?</summary>'
    corpo+='<p>Sim. Crie uma conta com seu CPF. Depois procure seu condomínio pelo nome e descreva o problema. Não precisa ter o CNPJ ou ser síndico.</p></details>'
    return pagina(h,'Portal do Cliente',corpo)


def cadastro(h):
    card,_,campos,_,_,_,botao,_=u()
    form=('<p class="passo">Etapa única: criar seu acesso</p>'
          '<p>Você precisa apenas de um CPF e uma senha. Para pedir serviço ao condomínio, não precisa informar seu endereço residencial.</p>'
          '<form method="post" action="/cliente/cadastrar">'
          +campos('Seu CPF','cpf',required=True)
          +campos('Crie uma senha (pelo menos 10 caracteres)','senha',kind='password',required=True)
          +campos('Digite sua senha novamente','confirmar_senha',kind='password',required=True)
          +'<button type="submit" style="width:100%">Criar conta e continuar</button></form>'
          '<p class="muted">A senha é pessoal. Não compartilhe com porteiros, vizinhos ou administradores.</p>')
    return pagina(h,'Criar conta',card('Meu primeiro acesso',form)+botao('Voltar ao login','/cliente','secondary'))



def cadastro_pj(h,s):
    card,_,_,_,_,_,botao,_=u()
    if not s:
        return pagina(h,'Cadastro PJ',card('Primeiro crie ou acesse sua conta pessoal',
            '<p>O login do responsável por condomínio ou empresa utiliza CPF e senha. '
            'Depois de entrar, cadastre o CNPJ sob seu perfil como síndico ou proprietário. '
            'Não existe uma segunda senha para a empresa.</p>'
            +botao('Entrar com CPF e senha','/cliente')+botao('Criar conta CPF','/cliente/cadastro','secondary')))
    return h.redir('/cliente/administrar-organizacao')


def token_sessao(h,usuario):
    token=secrets.token_urlsafe(32)
    v9.SESSOES[token]={'uid':usuario['id'],'nome':usuario['nome'],
                       'cred':usuario['senha_hash'],'csrf':secrets.token_urlsafe(24),
                       'exp':time.time()+28800}
    return v9.cookie(h,token)


def nome_solicitante(banco,uid):
    """Nome usado na mensagem do WhatsApp; perfil completo tem prioridade."""
    p=fluxo_pf.obter_perfil(banco,uid)
    return p['nome'] if fluxo_pf.perfil_pronto(p) else ''


def link_whatsapp_os(banco,s,os_registro):
    nome=nome_solicitante(banco,s['uid']) or 'Cliente do portal'
    return cad.url_whatsapp_cliente(os_registro['numero_os'] or '#'+str(os_registro['id']),nome,'Particular')


def link_whatsapp_chamado(banco,s,ch):
    nome=ch['solicitante_nome'] or nome_solicitante(banco,s['uid']) or 'Cliente do portal'
    protocolo=('OS '+str(ch['numero_os'])) if ch['numero_os'] else ('Chamado #'+str(ch['id']))
    return cad.url_whatsapp_cliente(protocolo,nome,ch['tipo'],ch['organizacao'])


def _abrir_whatsapp_apos_gravar(url,ident):
    from html import escape
    return ('<div id="whatsapp-automatico" data-id="'+escape(str(ident),quote=True)+'" data-url="'+escape(url,quote=True)+'"></div>'
            '<script src="/static/cliente_whatsapp.js" defer></script>')

def os_detalhe(h,banco,s,oid):
    card,_,_,_,_,esc,botao,_=u()
    x=fluxo_pf.obter_os_pf(banco,s['uid'],oid)
    if not x:
        return pagina(h,'OS não encontrada','<p>Esta ordem de serviço não pertence à sua conta.</p>',404)
    status_txt = x['status']
    try:
        with ext.db(banco) as c:
            if ext.em_rota_atual(c, x['id']): status_txt = 'Em rota'
    except Exception:
        pass
    corpo=card('Solicitação salva',
        '<p class="good">Sua OS particular foi registrada com o protocolo <b>'+esc(x['numero_os'] or '#'+str(x['id']))+'</b>.</p>'
        +'<p>'+esc(x['descricao'])+'</p><p><span class="tag">'+esc(status_txt)+'</span></p>')
    corpo+=card('Avisar a AUTOSEG pelo WhatsApp',
        '<p>O botão abaixo abre o WhatsApp com a mensagem pronta. O envio só acontece quando <b>você</b> confirmar no aplicativo. '
        'Sua OS já está salva e permanece válida mesmo que você não envie a mensagem.</p>'
        +botao('Avisar AUTOSEG pelo WhatsApp',link_whatsapp_os(banco,s,x))
        +(_abrir_whatsapp_apos_gravar(link_whatsapp_os(banco,s,x),'pf-'+str(oid)) if 'whatsapp=1' in h.path else ''))
    return pagina(h,'OS '+str(x['numero_os'] or x['id'])+' registrada',corpo+botao('Ver minhas solicitações','/cliente/painel','secondary'))


def chamado_detalhe(h,banco,s,chamado_id):
    card,_,_,_,_,esc,botao,_=u()
    ch=fluxo_pf.obter_chamado(banco,s['uid'],chamado_id)
    if not ch:
        return pagina(h,'Chamado não encontrado','<p>Este chamado não pertence à sua conta.</p>',404)
    protocolo=('OS '+str(ch['numero_os'])) if ch['numero_os'] else ('Chamado #'+str(ch['id']))
    status_txt = ch['status']
    try:
        if ch['os_id']:
            with ext.db(banco) as c:
                if ext.em_rota_atual(c, ch['os_id']): status_txt = 'Em rota'
    except Exception:
        pass
    corpo=card('Chamado salvo',
        '<p class="good">Sua solicitação foi registrada com o protocolo <b>'+esc(protocolo)+'</b>.</p>'
        f'<p><b>{esc(ch["organizacao"])}</b> · {esc(ch["unidade"])} · {esc(ch["papel"] or "Solicitante")}</p>'
        +'<p>'+esc(ch['descricao'])+'</p><p><span class="tag">'+esc(status_txt)+'</span></p>')
    corpo+=card('Avisar a AUTOSEG pelo WhatsApp',
        '<p>O botão abaixo abre o WhatsApp com a mensagem pronta. O envio só acontece quando <b>você</b> confirmar no aplicativo. '
        'O chamado já está salvo e continua valendo mesmo que você não envie a mensagem.</p>'
        +botao('Avisar AUTOSEG pelo WhatsApp',link_whatsapp_chamado(banco,s,ch))
        +(_abrir_whatsapp_apos_gravar(link_whatsapp_chamado(banco,s,ch),'org-'+str(chamado_id)) if 'whatsapp=1' in h.path else ''))
    return pagina(h,'Solicitação registrada',corpo+botao('Acompanhar minhas solicitações','/cliente/painel','secondary'))


def perfil(h,banco,s):
    card,_,campos,_,_,esc,botao,_=u()
    p=fluxo_pf.obter_perfil(banco,s['uid'])
    form=f'<form method="post" action="/cliente/perfil">{v9.formulario_csrf(s)}'
    form+=campos('Nome completo','nome',p['nome'] if p['perfil_completo'] else '',required=True)
    form+=campos('Telefone com DDD','telefone',p['telefone'],required=True)
    form+=campos('E-mail','email',p['email'],required=True,kind='email')
    form+=campos('Rua / avenida / endereço','endereco',p['endereco'],required=True)
    form+=campos('Número (ou S/N)','numero',p['numero'],required=True)
    form+=campos('Bairro (opcional)','bairro',p['bairro'])
    form+=campos('Cidade','cidade',p['cidade'],required=True)
    form+=campos('UF','uf',p['uf'],required=True)
    form+=campos('CEP (opcional)','cep',p['cep'])
    form+='<button>Salvar meus dados</button></form>'
    return pagina(h,'Meus dados para atendimento particular',
        card('Complete o perfil PF',
        '<p>Antes de abrir uma OS particular, informe telefone, e-mail e endereço. '
        'Para chamados de condomínios e empresas, basta entrar com CPF e senha.</p>'+form)
        +botao('Voltar ao painel','/cliente/painel','secondary'))


def painel(h,banco,s):
    card,_,_,_,_,esc,botao,tabela=u()
    p=fluxo_pf.obter_perfil(banco,s['uid'])
    apelido=p['nome'] if p['perfil_completo'] else 'Você está conectado(a)'
    abertura=card('O que você precisa fazer?',
        '<p>Bem-vindo(a)! Escolha uma opção:</p>'
        '<div class="acao-principal">'
        +botao('Pedir serviço para condomínio ou empresa','/cliente/organizacoes')
        +botao('Pedir serviço particular','/cliente/nova','secondary')
        +botao('Orçamento estimativo em PDF','/cliente/orcamento','secondary')
        +'</div>')
    with ext.db(banco) as c:
        chamados=c.execute('''SELECT h.id,h.status,h.descricao,h.criado_em,h.os_id,o.nome organizacao,
            so.status status_os
            FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id
            LEFT JOIN ordens_servico so ON so.id=h.os_id
            WHERE h.usuario_id=? ORDER BY h.id DESC LIMIT 30''',(s['uid'],)).fetchall()
        orgs=c.execute('''SELECT o.id,o.nome,o.tipo,v.papel,v.situacao
           FROM v9_vinculos v JOIN v9_organizacoes o ON o.id=v.organizacao_id
           WHERE v.usuario_id=? AND o.mesclado_em IS NULL ORDER BY o.nome''',(s['uid'],)).fetchall()
        responsaveis=c.execute('''SELECT o.id,o.nome,o.tipo,r.papel
             FROM v9_responsaveis r JOIN v9_organizacoes o ON o.id=r.organizacao_id
             WHERE r.usuario_id=? AND o.mesclado_em IS NULL ORDER BY o.nome''',(s['uid'],)).fetchall()
    particulares=fluxo_pf.listar_os_pf(banco,s['uid'])
    lista=[]
    for x in chamados:
        st = 'OS '+str(x['status_os']) if x['status_os'] else x['status']
        try:
            if x['status_os']:
                with ext.db(banco) as c:
                    if ext.em_rota_atual(c, x['os_id']): st = 'Em rota'
        except Exception:
            pass
        lista.append((esc(x['organizacao']),esc(x['descricao'][:100]),esc(st),
                     botao('Acompanhar',f'/cliente/chamado/{x["id"]}','secondary')))
    for x in particulares:
        st = x['status']
        try:
            with ext.db(banco) as c:
                if ext.em_rota_atual(c, x['id']): st = 'Em rota'
        except Exception:
            pass
        lista.append((esc(x['numero_os']),esc(x['descricao'][:100]),esc(st),
                     botao('Acompanhar',f'/cliente/os/{x["id"]}','secondary')))
    if lista:
        abertura+=card('Acompanhe seus pedidos',tabela(['Local / OS','Serviço','Situação','Ação'],lista))
    else:
        abertura+=card('Seus pedidos','<p>Você ainda não fez solicitações por este acesso. Para começar, use um dos botões acima.</p>')
    mais='<div class="acao-principal">'+botao('Editar meus dados','/cliente/perfil','secondary')
    mais+='</div>'
    if orgs:
        linhas=[]
        for o in orgs:
            ac=botao('Solicitar serviço',f'/cliente/chamado/novo?org={o["id"]}','secondary')
            if any(r['id']==o['id'] for r in responsaveis):
                ac+=botao('Ver todas as OS da organização',f'/cliente/sindico?org={o["id"]}','secondary')
            estado=o['situacao']
            if o['papel'] in ('Síndico','Administrador','Gestor') and not any(r['id']==o['id'] for r in responsaveis):
                estado='Aguardando nomeação da AUTOSEG (sem acesso geral)'
            linhas.append((esc(o['nome']),esc(estado),ac))
        mais+=tabela(['Organização','Vínculo','Ações'],linhas)
    abertura+='<details class="ajuda"><summary>Meus dados e opções de responsável</summary>'+mais+'</details>'
    if responsaveis:
        linhas=[(esc(r['nome']),esc(r['tipo']),esc(r['papel']),
                 botao('Consultar todas as OS',f'/cliente/sindico?org={r["id"]}')) for r in responsaveis]
        abertura+=card('Organizações sob sua responsabilidade',
            '<p>Você tem acesso ao histórico de OS destes locais, inclusive pedidos abertos por moradores, funcionários ou prestadores.</p>'
            +tabela(['Organização','Tipo','Atribuição','Ação'],linhas))
    abertura+=f'<form method="post" action="/cliente/sair-pf">{v9.formulario_csrf(s)}<button class="secondary" type="submit">Sair da minha conta</button></form>'
    return pagina(h,'Meu painel', '<p class="muted">'+esc(apelido)+'</p>'+abertura)


def os_pf_form(h,banco,s):
    card,_,_,textarea,select,_,botao,_=u()
    p=fluxo_pf.obter_perfil(banco,s['uid'])
    if not fluxo_pf.perfil_pronto(p):
        return pagina(h,'Antes de solicitar sua OS',
            card('Complete seu cadastro',
            '<p>Para solicitar atendimento particular é obrigatório informar nome, telefone, e-mail e endereço.</p>'
            +botao('Completar meu perfil','/cliente/perfil')))
    form=f'<form method="post" action="/cliente/os/nova">{v9.formulario_csrf(s)}'
    form+=textarea('Descreva o serviço necessário','descricao',required=True)
    form+=select('Urgência','urgencia',[(x,x) for x in ('Normal','Alta','Baixa')])
    form+='<button>Enviar solicitação particular</button></form>'
    return pagina(h,'Nova OS particular',card('Atendimento pessoa física',form)
                  +botao('Voltar','/cliente/painel','secondary'))


def pesquisar(h,banco,s):
    card,_,campos,_,_,esc,botao,tabela=u()
    params=parse_qs(urlsplit(h.path).query)
    q=params.get('q',[''])[0].strip()[:120]
    try: page=max(1,min(100000,int(params.get('page',['1'])[0])))
    except (ValueError,TypeError): page=1
    limite=20
    offset=(page-1)*limite
    cnpj=cad.digitos(q)
    busca_documento=bool(q and len(cnpj)==14 and all(x.isdigit() or x in './- ' for x in q))
    with ext.db(banco) as c:
        if busca_documento:
            rows=c.execute('''SELECT id,nome,tipo,cidade,bairro FROM v9_organizacoes
                WHERE cnpj=? AND mesclado_em IS NULL ORDER BY nome LIMIT 20 OFFSET ?''',(cnpj,offset)).fetchall()
            total=c.execute('SELECT COUNT(*) FROM v9_organizacoes WHERE cnpj=? AND mesclado_em IS NULL',(cnpj,)).fetchone()[0]
        elif q:
            esc_like=q.replace('!','!!').replace('%','!%').replace('_','!_')
            rows=c.execute("""SELECT id,nome,tipo,cidade,bairro FROM v9_organizacoes
                WHERE nome LIKE ? ESCAPE '!' AND mesclado_em IS NULL ORDER BY nome LIMIT 20 OFFSET ?""",
                ('%'+esc_like+'%',offset)).fetchall()
            total=c.execute("SELECT COUNT(*) FROM v9_organizacoes WHERE nome LIKE ? ESCAPE '!' AND mesclado_em IS NULL",('%'+esc_like+'%',)).fetchone()[0]
        else:
            rows=c.execute('''SELECT id,nome,tipo,cidade,bairro FROM v9_organizacoes
                WHERE mesclado_em IS NULL ORDER BY nome LIMIT 20 OFFSET ?''',(offset,)).fetchall()
            total=c.execute('SELECT COUNT(*) FROM v9_organizacoes WHERE mesclado_em IS NULL').fetchone()[0]
    resultados=''
    for r in rows:
        localidade=' · '.join(x for x in (r['bairro'],r['cidade']) if x)
        resultados+=('<article class="resultado-organizacao"><h3>'+esc(r['nome'])+'</h3>'
                    +'<p>'+esc(r['tipo'])+(' · '+esc(localidade) if localidade else '')+'</p>'
                    +botao('Pedir serviço neste local',f'/cliente/chamado/novo?org={r["id"]}')+'</article>')
    if not resultados:
        resultados='<p class="aviso-claro">Nenhum resultado com esse nome. Você pode cadastrar o local sem CNPJ.</p>'
    busca='<form method="get" action="/cliente/organizacoes">'+campos('Nome do condomínio ou empresa','q','' if busca_documento else q,placeholder='Ex.: Edifício Primavera')+'<button type="submit">Buscar</button></form>'
    paginacao='<p class="muted">'+str(total)+' local(is) encontrado(s) · Página '+str(page)+'</p>'
    if page>1:
        paginacao+=botao('Voltar uma página','/cliente/organizacoes?'+urlencode({'q':q,'page':page-1}),'secondary')
    if offset+len(rows)<total:
        paginacao+=botao('Ver mais resultados','/cliente/organizacoes?'+urlencode({'q':q,'page':page+1}),'secondary')
    return pagina(h,'Escolha seu condomínio ou empresa',
        card('1. Encontre o local',
          '<p>Procure pelo nome. Não é preciso saber o CNPJ ou ser síndico.</p>'+busca)
        +card('2. Escolha e peça o atendimento',paginacao+resultados)
        +'<div class="acao-principal">'+botao('Cadastrar local e solicitar OS','/cliente/nova-organizacao','secondary')+'</div>'
        +'<p class="muted">Para administrar todas as OS da empresa ou condomínio, peça a nomeação ao prestador.</p>')


def solicitar_vinculo_form(h,banco,s):
    card,_,campos,_,select,esc,botao,_=u()
    qs=parse_qs(urlsplit(h.path).query)
    org_id=int(qs.get('org',['0'])[0])
    with ext.db(banco) as c:
        org=c.execute('SELECT nome,tipo,cnpj FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(org_id,)).fetchone()
    if not org:raise ValueError('Organização não encontrada.')
    form=f'<form method="post" action="/cliente/vinculo/novo">{v9.formulario_csrf(s)}'
    form+=f'<input type="hidden" name="org_id" value="{org_id}">'
    form+=select('Minha função na organização','funcao',[(v,v) for v in FUNCOES_RESPONSAVEL])
    aviso_cnpj=('O CNPJ informado será conferido com o cadastro da organização.' if org['cnpj']
                else 'Esta organização ainda não tem CNPJ confirmado. Você pode informá-lo agora, se souber.')
    form+=campos('CNPJ'+('' if org['cnpj'] else ' (opcional)'),'cnpj',required=bool(org['cnpj']))
    form+=f'<p class="muted">{esc(aviso_cnpj)}</p>'
    form+='<p class="notice">O vínculo será analisado pela AUTOSEG. Isso não concede acesso de síndico ou administrador imediatamente.</p>'
    form+='<button>Solicitar vínculo de responsável</button></form>'
    return pagina(h,'Responsável pelo condomínio / empresa',card('Solicitar gestão — '+esc(org['nome']),form)
                 +botao('Voltar','/cliente/organizacoes','secondary'))


def formulario_org(h,s,administrador=False):
    card,_,campos,textarea,select,esc,botao,_=u()
    if administrador:
        return pagina(h,'Solicitação de gestão',card('Acesso como síndico ou gestor',
            '<p>O síndico ou gestor é nomeado somente pelo prestador ou pelo desktop, a partir de uma conta PF existente.</p>'
            +botao('Voltar ao painel','/cliente/painel','secondary')))
    form=f'<form method="post" action="/cliente/nova-organizacao">{v9.formulario_csrf(s)}'
    form+='<p class="passo">Cadastro e solicitação em uma única página</p>'
    form+=select('Tipo de local','tipo',[(v,v) for v in ('Condomínio','Empresa')])
    form+=campos('Nome do condomínio ou empresa','nome',required=True)
    form+=campos('Endereço completo','endereco',required=True)
    form+=campos('Cidade','cidade',required=True)+campos('Bairro','bairro')
    form+=campos('Telefone de contato do local (DDD)','telefone',required=True,placeholder='(51) 99999-9999')
    form+=campos('CNPJ (opcional)','cnpj',placeholder='00.000.000/0000-00')
    form+=select('Você é','papel',[('Morador','Morador'),('Funcionário','Funcionário / porteiro')])
    form+=campos('Seu nome para contato','solicitante_nome',s.get('nome',''),required=True)
    form+=campos('Apartamento ou cargo','unidade',required=True,placeholder='Apartamento 203 ou Porteiro')
    form+=select('Urgência','urgencia',[(x,x) for x in ('Normal','Alta','Baixa')])
    form+=textarea('Descreva o serviço solicitado','descricao',required=True)
    form+=('<p class="notice">Ao enviar, o condomínio entra na lista principal de clientes e a OS aparece em Pendentes. '
           'O cadastro poderá ser complementado pelo prestador. Isso não concede acesso de síndico.</p>'
           '<button type="submit" style="width:100%;white-space:normal">Cadastrar local e solicitar OS</button></form>')
    return pagina(h,'Cadastrar local e solicitar OS',card('Condomínio ou empresa',form)
                  +botao('Voltar','/cliente/organizacoes','secondary'))


def chamado_form(h,banco,s):
    card,_,campos,textarea,select,esc,botao,_=u()
    qs=parse_qs(urlsplit(h.path).query)
    try:org=int(qs.get('org',['0'])[0])
    except ValueError:raise ValueError('Selecione uma organização.')
    unidade=qs.get('unidade',[''])[0][:100]
    with ext.db(banco) as c:
        o=c.execute('SELECT nome,tipo FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(org,)).fetchone()
    if not o:raise ValueError('Condomínio ou empresa inexistente.')
    p=fluxo_pf.obter_perfil(banco,s['uid'])
    nome_padrao=p['nome'] if fluxo_pf.perfil_pronto(p) else ''
    form=f'<form method="post" action="/cliente/chamado/novo">{v9.formulario_csrf(s)}<input type="hidden" name="org_id" value="{org}">'
    form+=select('Meu papel neste local','papel',[
        ('Morador','Morador'),('Funcionário','Funcionário / porteiro')])
    form+=campos('Seu nome (para contato)','solicitante_nome',nome_padrao,required=True)
    form+=campos('Apartamento ou cargo / função','unidade',unidade,required=True,
                 placeholder='Ex.: Apartamento 203, Porteiro, Zelador, Recepcionista, Auxiliar administrativo')
    form+=select('Urgência','urgencia',[(x,x) for x in ('Normal','Alta','Baixa')])
    form+=textarea('Conte o que aconteceu e onde precisa do serviço','descricao',required=True)
    form+=('<p class="notice">Você pode solicitar mesmo sem ser síndico ou administrador. '
           'A AUTOSEG entrará em contato com o responsável para confirmar os detalhes.</p>'
           '<button type="submit" style="width:100%">Enviar pedido de atendimento</button></form>')
    return pagina(h,'Solicitar serviço — '+o['nome'],card('Etapa final: descreva o problema', '<p class="passo">Seu pedido será registrado como OS pendente para atendimento.</p>'+form)
                  +botao('Voltar às organizações','/cliente/organizacoes','secondary'))


def orcamento_form(h,banco,s):
    card,_,campos,_,select,esc,botao,_=u()
    servicos=catalogo.listar(banco,ativos=True)
    if not servicos:
        return pagina(h,'Solicitar orçamento',card('Serviços disponíveis',
            '<p>Ainda não há serviços com valores cadastrados. Consulte a AUTOSEG.</p>'
            +botao('Voltar','/cliente/painel','secondary')))
    detalhes=[]
    for x in servicos:
        v=catalogo.valores_orcamento(banco,x['id'])
        detalhes.append('<li>'+esc(x['nome'])+' — '+esc(catalogo.reais(v['total']))+' (estimado por unidade)</li>')
    form=(f'<form method="post" action="/cliente/orcamento/pdf">{v9.formulario_csrf(s)}'
          +select('Serviço','servico_id',[(x['id'],x['nome']) for x in servicos],required=True)
          +campos('Quantidade (de 1 a 20)','quantidade','1',required=True)
          +'<p class="muted">O valor é calculado com base no catálogo e pode mudar após vistoria.</p>'
          +'<button>Gerar orçamento em PDF</button></form>')
    return pagina(h,'Orçamento estimativo',card('Serviços e valores',
        '<ul>'+''.join(detalhes)+'</ul>'+form)
        +botao('Voltar ao painel','/cliente/painel','secondary'))


def pdf_pf(h,banco,s,oid):
    from pathlib import Path
    import fluxo_os as fluxo
    p=fluxo_pf.obter_perfil(banco,s['uid'])
    if not p.get('cliente_pf_id'):raise PermissionError('Documento não autorizado.')
    with ext.db(banco) as c:
        o=c.execute('SELECT status FROM ordens_servico WHERE id=? AND cliente_id=?',
                    (oid,p['cliente_pf_id'])).fetchone()
    if not o:raise PermissionError('Este documento não pertence à sua conta.')
    if o['status'] not in fluxo.FIM:raise ValueError('A OS ainda não foi encerrada.')
    documento=fluxo.ultimo_documento(banco,oid)
    if not documento:raise ValueError('O relatório ainda não foi publicado.')
    arquivo=Path(fluxo.validar_pdf_publicado(documento))
    return h.send_bytes(arquivo.read_bytes(),'application/pdf',filename=arquivo.name)


def sindico(h,banco,s,org):
    """Histórico de OS da empresa/condomínio — apenas PF explicitamente nomeada."""
    card,_,_,_,_,esc,botao,tabela=u()
    dados=cad.listar_os_organizacao(banco,org,s['uid'])
    organizacao=dados['organizacao']
    linhas=[]
    for x in dados['os']:
        origem=x['solicitante'] or 'Abertura administrativa / prestador'
        linhas.append((esc(x['numero_os'] or '#'+str(x['id'])),esc(x['descricao'] or ''),
            esc(x['status']),esc(origem),esc(x['data_abertura'] or ''),
            botao('Relatório PDF',f'/cliente/organizacao/{org}/os/{x["id"]}/pdf','secondary')))
    aviso='<p class="notice">Há mais de uma organização para o mesmo cadastro. Por segurança, exibimos somente OS explicitamente vinculadas. Peça revisão cadastral à AUTOSEG.</p>' if dados['cadastro_ambiguo'] else ''
    corpo=card('Todas as ordens de serviço — '+esc(organizacao['nome']),
        '<p>Inclui solicitações do síndico, dos condôminos, dos funcionários e OS criadas pelo prestador.</p>'
        +aviso+tabela(['OS','Descrição','Situação','Solicitante / Origem','Abertura','PDF'],linhas))
    return pagina(h,'Histórico do '+organização_rotulo(organizacao['tipo']),corpo+
                  botao('Voltar ao meu painel','/cliente/painel','secondary'))


def organização_rotulo(tipo):
    return 'condomínio' if tipo=='Condomínio' else 'empresa'


def pdf_os_organizacao(h,banco,s,org,oid):
    from pathlib import Path
    import fluxo_os as fluxo
    cad.autorizar_pdf_os_organizacao(banco,org,s['uid'],oid)
    registro=fluxo.ultimo_documento(banco,oid)
    if not registro:raise ValueError('Ainda não há relatório PDF publicado para esta OS.')
    arquivo=Path(fluxo.validar_pdf_publicado(registro))
    return h.send_bytes(arquivo.read_bytes(),'application/pdf',filename=arquivo.name)


def pdf_chamado(h,banco,s,chamado_id):
    """PDF do chamado para o próprio solicitante ou síndico validado da organização."""
    from pathlib import Path
    import fluxo_os as fluxo
    with ext.db(banco) as c:
        chamado=c.execute('SELECT organizacao_id,usuario_id,os_id FROM v9_chamados WHERE id=?',
                          (chamado_id,)).fetchone()
    if not chamado:
        raise ValueError('Chamado não encontrado.')
    if chamado['usuario_id']!=s['uid'] and not cad.vinculo_aprovado(
            banco,s['uid'],chamado['organizacao_id'],('Síndico','Administrador')):
        raise PermissionError('Documento restrito ao solicitante ou síndico validado.')
    if not chamado['os_id']:
        raise ValueError('A solicitação ainda não foi convertida em OS.')
    registro=fluxo.ultimo_documento(banco,chamado['os_id'])
    if not registro:
        raise ValueError('Relatório ainda não publicado.')
    arquivo=Path(fluxo.validar_pdf_publicado(registro))
    return h.send_bytes(arquivo.read_bytes(),'application/pdf',filename=arquivo.name)


def get(h,path,banco):
    if path=='/cliente/cadastro':return cadastro(h)
    s=v9.sessao(h,banco)
    if path=='/cliente/cadastro-pj':return cadastro_pj(h,s)
    if not s:return login(h,'Faça login para acessar essa área.' if path!='/cliente' else '')
    if path in ('/cliente','/cliente/painel'):return painel(h,banco,s)
    if path=='/cliente/perfil':return perfil(h,banco,s)
    if path=='/cliente/nova':return os_pf_form(h,banco,s)
    if path=='/cliente/organizacoes':return pesquisar(h,banco,s)
    if path=='/cliente/orcamento':return orcamento_form(h,banco,s)
    if path=='/cliente/nova-organizacao':return formulario_org(h,s)
    if path=='/cliente/administrar-organizacao':return formulario_org(h,s,administrador=True)
    if path=='/cliente/vinculo/novo':return solicitar_vinculo_form(h,banco,s)
    if path=='/cliente/chamado/novo':return chamado_form(h,banco,s)
    if path=='/cliente/sindico':
        qs=parse_qs(urlsplit(h.path).query)
        return sindico(h,banco,s,int(qs.get('org',['0'])[0]))
    parts=path.strip('/').split('/')
    if (len(parts)==6 and parts[0]=='cliente' and parts[1]=='organizacao'
            and parts[2].isdigit() and parts[3]=='os' and parts[4].isdigit() and parts[5]=='pdf'):
        return pdf_os_organizacao(h,banco,s,int(parts[2]),int(parts[4]))
    if len(parts)==3 and parts[0]=='cliente' and parts[1]=='os' and parts[2].isdigit():
        return os_detalhe(h,banco,s,int(parts[2]))
    if len(parts)==3 and parts[0]=='cliente' and parts[1]=='chamado' and parts[2].isdigit():
        return chamado_detalhe(h,banco,s,int(parts[2]))
    if len(parts)==4 and parts[1]=='chamado' and parts[2].isdigit() and parts[3]=='pdf':
        return pdf_chamado(h,banco,s,int(parts[2]))
    if len(parts)==4 and parts[1]=='os' and parts[2].isdigit() and parts[3]=='pdf':
        return pdf_pf(h,banco,s,int(parts[2]))
    return pagina(h,'Página não encontrada','<p>Endereço não encontrado.</p>',404)


def post(h,path,d,banco):
    if path=='/cliente/entrar-pf':
        cpf=cad.digitos(d.get('cpf',''))
        key='cliente-login:'+cpf+':'+h.client_address[0]
        now=time.time();events=[t for t in v9.FALHAS.get(key,[]) if now-t<600]
        if len(events)>=10:return pagina(h,'Acesso temporariamente bloqueado','<p>Aguarde dez minutos.</p>',429)
        usuario=cad.autenticar(banco,cpf,str(d.get('senha','')))
        if not usuario:
            v9.FALHAS[key]=events+[now]
            return login(h,'CPF ou senha incorretos.')
        v9.FALHAS.pop(key,None)
        return h.redir('/cliente/painel',token_sessao(h,usuario))
    if path=='/cliente/cadastrar':
        key='cliente-cadastro:'+h.client_address[0]
        now=time.time();events=[t for t in v9.FALHAS.get(key,[]) if now-t<3600]
        if len(events)>=6:return pagina(h,'Muitas tentativas','<p>Tente mais tarde.</p>',429)
        v9.FALHAS[key]=events+[now]
        senha=str(d.get('senha',''))
        if senha!=str(d.get('confirmar_senha','')):raise ValueError('As senhas não coincidem.')
        uid=fluxo_pf.criar_conta(banco,d.get('cpf',''),senha)
        usuario=fluxo_pf.obter_perfil(banco,uid)
        return h.redir('/cliente/painel',token_sessao(h,usuario))
    s=v9.sessao(h,banco)
    v9.verificar_csrf(s,d)
    uid=s['uid']
    if path=='/cliente/sair-pf':
        jar=SimpleCookie();jar.load(h.headers.get('Cookie',''))
        if 'autosseg_pj' in jar:v9.SESSOES.pop(jar['autosseg_pj'].value,None)
        return h.redir('/cliente',v9.cookie(h,'',True))
    if path=='/cliente/perfil':
        p=fluxo_pf.atualizar_perfil(banco,uid,d)
        s['nome']=p['nome']
        return h.redir('/cliente/painel')
    if path=='/cliente/os/nova':
        oid=fluxo_pf.registrar_os_pf(banco,uid,d.get('descricao',''),str(d.get('urgencia','Normal')))
        return h.redir('/cliente/os/'+str(oid)+'?whatsapp=1')
    if path=='/cliente/orcamento/pdf':
        perfil=fluxo_pf.obter_perfil(banco,uid)
        nome=perfil['nome'] if perfil and perfil.get('nome') else 'Cliente'
        pdf=catalogo.pdf_orcamento(banco,int(d.get('servico_id','0')),d.get('quantidade','1'),nome)
        return h.send_bytes(pdf,'application/pdf',filename='AUTOSEG_orcamento_estimativo.pdf')
    if path=='/cliente/nova-organizacao':
        resultado=cad.criar_organizacao_e_os(banco,uid,d)
        return h.redir('/cliente/chamado/'+str(resultado['chamado_id'])+'?whatsapp=1')
    if path=='/cliente/vinculo/novo':
        fluxo_pf.solicitar_administracao(banco,uid,int(d.get('org_id','0')),str(d.get('cnpj','')),
                                         str(d.get('funcao','')))
        return h.redir('/cliente/painel')
    if path=='/cliente/administrar-organizacao':
        raise PermissionError('A nomeação de síndico/gestor só pode ser feita pelo prestador ou desktop.')
        return h.redir('/cliente/painel')
    if path=='/cliente/chamado/novo':
        chid=fluxo_pf.registrar_chamado_org(banco,uid,d)
        return h.redir('/cliente/chamado/'+str(chid)+'?whatsapp=1')
    raise ValueError('Operação do cliente desconhecida.')
