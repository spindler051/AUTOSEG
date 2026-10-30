"""Rotas aditivas da v9. Contrato: get(handler,path,banco,prestador) / post(...)."""
import secrets, time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit
import prestadores_ext as ext
import cadastros_v9 as cad
import links_publicos as links

SESSOES = {}
FALHAS = {}

def ui():
    from portal_prestador import card, layout, campos_escuros, textarea, select, esc, botao, tabela
    return card, layout, campos_escuros, textarea, select, esc, botao, tabela

def sessao(h,banco):
    try:
        jar=SimpleCookie();jar.load(h.headers.get('Cookie',''))
        tok=jar['autosseg_pj'].value
    except (ValueError,KeyError):return None
    s=SESSOES.get(tok)
    if not s or s['exp']<time.time():
        SESSOES.pop(tok,None);return None
    with ext.db(banco) as c:
        u=c.execute('SELECT id,nome,senha_hash FROM v9_usuarios WHERE id=? AND ativo=1',(s['uid'],)).fetchone()
    if not u or not secrets.compare_digest(s['cred'],u['senha_hash']):
        SESSOES.pop(tok,None);return None
    return s

def cookie(h,tok,delete=False):
    # HTTP no Mac para testes; cookies Secure no tráfego Cloudflare HTTPS.
    secure=('Secure; ' if (h.headers.get('CF-Ray') or h.headers.get('X-Forwarded-Proto','').lower()=='https') else '')
    return f'autosseg_pj={tok}; Path=/; HttpOnly; SameSite=Strict; {secure}Max-Age={0 if delete else 28800}'

def barra_links(pagina='cliente'):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    d=links.estado_com_manuais()
    porta = '8765' if pagina == 'cliente' else '8766'
    url=d.get(porta,{}).get('url','')
    return '<details class="card" style="margin-top:30px"><summary style="cursor:pointer;color:#bbb">Link público deste portal</summary>'+(
        '<p><a rel="noopener noreferrer" href="'+esc(url)+'">'+esc(url)+'</a></p><small>Link registrado pelo gerenciador de túneis, ativo enquanto o túnel funcionar.</small>'
        if url else '<p class="muted">Sem link público gerenciado ativo. Acesso local: http://127.0.0.1:'+porta+'/</p>')+'</details>'

def pagina(h,titulo,conteudo,usuario=None,status=200):
    card,layout,*_=ui()
    h.responder(layout(titulo,conteudo,usuario),status)

def formulario_csrf(s):return f'<input type="hidden" name="csrf" value="{s["csrf"]}">'

def verificar_csrf(s,d):
    if not s or not secrets.compare_digest(s['csrf'],str(d.get('csrf',''))):raise PermissionError('Sessão ou formulário inválido.')

def publico(banco):
    with ext.db(banco) as c:
        return c.execute('SELECT id,nome,tipo,cidade,bairro FROM v9_organizacoes WHERE mesclado_em IS NULL ORDER BY nome LIMIT 500').fetchall()

def login(h,banco,aviso=''):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    corpo=barra_links('cliente')
    corpo+=card('Conta pessoal — pessoa física ou condomínio',
        '<p class="muted">Entre com CPF e senha para abrir um chamado particular ou para qualquer condomínio/empresa cadastrada. Não é necessário ser síndico nem possuir vínculo aprovado para solicitar.</p>'+
        ('<p class="notice">'+esc(aviso)+'</p>' if aviso else '')+
        '<form method="post" action="/pj/entrar">'+campos('CPF','cpf',required=True)+campos('Senha','senha',kind='password',required=True)+
        '<button>Entrar</button></form>'+botao('Criar minha conta','/pj/cadastro','secondary')+
        botao('Consultar minhas OS antigas (ID e senha)','/cliente/legado','secondary'))
    return pagina(h,'Acionamentos PF / PJ',corpo)

def cadastro(h,banco):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    formulario='<form method="post" action="/pj/cadastrar">'+campos('Nome completo','nome',required=True)+campos('CPF','cpf',required=True)+campos('Telefone com DDD','telefone',required=True)+campos('E-mail (opcional)','email',kind='email')+campos('Escolha sua senha (mínimo de 10 caracteres)','senha',kind='password',required=True)+campos('Repita sua senha','confirmar_senha',kind='password',required=True)+'<button>Criar minha conta pessoal</button></form>'
    return pagina(h,'Cadastro de usuário',barra_links('cliente')+card('Conta individual',formulario)+'<p>'+botao('Voltar ao login','/pj','secondary')+'</p>')

def painel(h,banco,s):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    with ext.db(banco) as c:
        vs=c.execute('''SELECT v.organizacao_id,v.papel,v.situacao,o.nome,o.tipo,o.situacao estado
                        FROM v9_vinculos v JOIN v9_organizacoes o ON o.id=v.organizacao_id
                        WHERE v.usuario_id=? AND o.mesclado_em IS NULL ORDER BY o.nome''',(s['uid'],)).fetchall()
        avisos=c.execute('SELECT id,texto,criado_em FROM v9_notificacoes WHERE usuario_id=? ORDER BY id DESC LIMIT 20',(s['uid'],)).fetchall()
        minhas=c.execute('''SELECT h.id,h.status,h.descricao,h.criado_em,o.nome organizacao,h.os_id
                         FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id
                         WHERE h.usuario_id=? ORDER BY h.id DESC LIMIT 100''',(s['uid'],)).fetchall()
    token=formulario_csrf(s)
    dados='Olá, <b>'+esc(s['nome'])+'</b>. '+botao('Abrir chamado para condomínio / empresa','/pj/organizacoes')+' '+botao('Cadastrar condomínio não encontrado','/pj/nova-organizacao')
    dados+=f'<form method="post" action="/pj/sair">{token}<button class="secondary">Sair</button></form>'
    orgs=[]
    for v in vs:
        acao=botao('Novo chamado',f'/pj/chamado/novo?org={v["organizacao_id"]}')
        if v['papel'] in ('Síndico','Administrador') and v['situacao']=='Aprovado':acao+=' '+botao('Chamados do condomínio',f'/pj/sindico?org={v["organizacao_id"]}','secondary')
        orgs.append((esc(v['nome']),esc(v['papel']),esc(v['situacao']),acao))
    chamados=[(f'#{x["id"]}',esc(x['organizacao']),esc(x['status']),esc(x['descricao'][:100]),esc(x['criado_em']),
               botao('Ver relatório PDF',f'/pj/chamado/{x["id"]}/pdf') if x['os_id'] else '—') for x in minhas]
    aviso_html=''.join('<p><small>'+esc(n['criado_em'])+'</small> · '+esc(n['texto'])+'</p>' for n in avisos) or '<p class="muted">Sem novas atualizações.</p>'
    return pagina(h,'Minha conta · PF / PJ',barra_links('cliente')+card('Minha conta pessoal',dados)+card('Notificações e atualizações',aviso_html)+card('Organizações vinculadas',tabela(['Organização','Meu papel','Vínculo','Ação'],orgs))+card('Meus chamados',tabela(['Nº','Condomínio / Empresa','Status','Descrição','Data','OS'],chamados)))

def organizacoes(h,banco,s):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    qs=parse_qs(urlsplit(h.path).query)
    busca=str(qs.get('q',[''])[0]).strip()[:120]
    termo=cad.digitos(busca)
    dados=[]
    with ext.db(banco) as c:
        if busca:
            if len(termo)==14 and termo==busca.replace('.','').replace('/','').replace('-',''):
                orgs=c.execute('SELECT id,nome,tipo,cidade,bairro FROM v9_organizacoes WHERE cnpj=? AND mesclado_em IS NULL ORDER BY nome LIMIT 80',(termo,)).fetchall()
            else:
                padrao='%'+busca.replace('!','!!').replace('%','!%').replace('_','!_')+'%'
                orgs=c.execute("SELECT id,nome,tipo,cidade,bairro FROM v9_organizacoes WHERE (nome LIKE ? ESCAPE '!' OR cidade LIKE ? ESCAPE '!') AND mesclado_em IS NULL ORDER BY nome LIMIT 80",(padrao,padrao)).fetchall()
        else:orgs=c.execute('SELECT id,nome,tipo,cidade,bairro FROM v9_organizacoes WHERE mesclado_em IS NULL ORDER BY nome LIMIT 150').fetchall()
    for o in orgs:
        dados.append((esc(o['nome']),esc(o['tipo']),esc(', '.join(x for x in (o['bairro'],o['cidade']) if x)),
            botao('Abrir chamado',f'/pj/chamado/novo?org={o["id"]}')+' '+
            f'<form method="post" action="/pj/vincular">{formulario_csrf(s)}<input type="hidden" name="org_id" value="{o["id"]}">'+
            select('Vincular meu perfil (opcional)','papel',[(x,x) for x in cad.PAPEIS])+'<button class="secondary">Solicitar vínculo</button></form>'))
    form='<form method="get" action="/pj/organizacoes">'+campos('Nome do condomínio, empresa ou CNPJ','q',busca,required=False)+'<button type="submit">Pesquisar</button></form>'
    return pagina(h,'Pesquisar organizações',barra_links('cliente')+card('Pesquisar condomínios e empresas',form+
        '<p class="muted">O CNPJ pode ser usado na pesquisa exata, mas nunca é exibido nos resultados.</p>')+
        card('Resultados — sem documentos pessoais ou CNPJ',tabela(['Nome','Tipo','Localidade','Ações'],dados))+
        botao('Não encontrou? Criar pré-cadastro','/pj/nova-organizacao')+botao('Voltar','/pj/painel','secondary'))

def nova_organizacao(h,banco,s):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    form='<form method="post" action="/pj/nova-organizacao">'+formulario_csrf(s)
    form+=campos('Nome do condomínio / empresa','nome',required=True)+select('Tipo','tipo',[(x,x) for x in ('Condomínio','Empresa')])
    form+=campos('CNPJ (se disponível)','cnpj')+campos('Cidade','cidade')+campos('Bairro','bairro')
    form+=select('Meu vínculo','papel',[(x,x) for x in cad.PAPEIS])
    form+='<p class="notice">Pré-cadastro não concede automaticamente permissões de síndico. A AUTOSEG verificará o vínculo.</p><button>Criar pré-cadastro</button></form>'
    return pagina(h,'Pré-cadastro de organização',card('Dados da organização',form))

def chamado_form(h,banco,s,org):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    with ext.db(banco) as c:o=c.execute('SELECT nome FROM v9_organizacoes WHERE id=? AND mesclado_em IS NULL',(org,)).fetchone()
    if not o:raise ValueError('Organização não encontrada.')
    form=f'<form method="post" action="/pj/chamado/novo">{formulario_csrf(s)}<input type="hidden" name="org_id" value="{int(org)}">'
    form+=campos('Bloco / unidade / setor (opcional)','unidade')+select('Urgência','urgencia',[(x,x) for x in ('Normal','Alta','Baixa')])
    form+=textarea('Problema e local do serviço','descricao',required=True)
    form+='<p class="notice">Qualquer pessoa identificada pode solicitar. A AUTOSEG contatará o síndico pelo WhatsApp para conferir o atendimento; você não precisa obter autorização antes de enviar.</p><button>Enviar chamado</button></form>'
    return pagina(h,'Novo chamado — '+o['nome'],card('Solicitação',form))

def sindico(h,banco,s,org):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    if not cad.vinculo_aprovado(banco,s['uid'],org,('Síndico','Administrador')):raise PermissionError('Acesso restrito ao síndico validado.')
    with ext.db(banco) as c:
        arr=c.execute('''SELECT h.*,u.nome solicitante FROM v9_chamados h JOIN v9_usuarios u ON u.id=h.usuario_id
             WHERE h.organizacao_id=? ORDER BY h.id DESC LIMIT 200''',(org,)).fetchall()
    linhas=[]
    for x in arr:
        documento=botao('Relatório PDF',f'/pj/chamado/{x["id"]}/pdf','secondary') if x['os_id'] else '—'
        linhas.append((f'#{x["id"]}',esc(x['solicitante']),esc(x['descricao']),esc(x['status']),esc(x['criado_em']),documento))
    return pagina(h,'Chamados do condomínio',barra_links('cliente')+card('Solicitações de moradores e funcionários',tabela(['Nº','Solicitante','Descrição','Status','Data','Documento'],linhas))+botao('Meu painel','/pj/painel','secondary'))

def administrar(h,banco,s):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    with ext.db(banco) as c:
        rows=c.execute('''SELECT h.*,o.nome org,u.nome solicitante
                          FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id
                          JOIN v9_usuarios u ON u.id=h.usuario_id ORDER BY h.id DESC LIMIT 300''').fetchall()
    dados=[]
    for r in rows:
        acao=''
        if r['status'] in ('Aguardando AUTOSEG','Mais informações'):
            acao=(f'<form method="post" action="/chamados/{r["id"]}/analisar">{formulario_csrf(s)}'
                  '<input name="observacao" placeholder="Observação da análise">'
                  '<button name="decisao" value="Aguardando síndico">Encaminhar ao síndico</button>'
                  '<button name="decisao" value="Mais informações" class="secondary">Pedir detalhes</button>'
                  '<button name="decisao" value="Recusado" class="danger">Recusar</button></form>')
        if r['status']=='Aguardando síndico':
            acao=(f'<form method="post" action="/chamados/{r["id"]}/confirmar">{formulario_csrf(s)}'
                  '<small>A AUTOSEG entra em contato pelo WhatsApp; depois registra a confirmação recebida.</small>'
                  '<input name="comprovacao" required placeholder="Nome do síndico e meio de confirmação">'
                  '<button name="decisao" value="aprovar">Registrar confirmação via WhatsApp</button>'
                  '<button name="decisao" value="recusar" class="danger">Registrar recusa</button></form>')
        if r['status']=='Autorizado' and not r['os_id']:
            acao=(f'<form method="post" action="/chamados/{r["id"]}/criar-os">{formulario_csrf(s)}'
                  '<button>Criar OS autorizada</button></form>')
        if r['os_id']:acao+=botao('Abrir OS',f'/os/{r["os_id"]}')
        if r['status'] not in ('Cancelado','Recusado'):
            acao+=(f'<form method="post" action="/chamados/{r["id"]}/cancelar">{formulario_csrf(s)}'
                   '<input name="motivo" required minlength="5" placeholder="Motivo do cancelamento">'
                   '<button class="danger" type="submit">Cancelar solicitação</button></form>')
        wurl,destino=cad.url_whatsapp(banco,r['id'],links.estado_com_manuais().get('8766',{}).get('url',''))
        acao+=' '+botao('WhatsApp: '+destino,wurl,'secondary')
        dados.append((f'#{r["id"]}',esc(r['org']),esc(r['solicitante']),esc(r['descricao']),esc(r['status']),acao))
    return pagina(h,'Análise de chamados',card('Caixa de entrada de acionamentos',tabela(['Nº','Organização','Solicitante','Descrição','Situação','Ações'],dados)),s)

def administrar_organizacoes(h,banco,s):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    with ext.db(banco) as c:
        orgs=c.execute('SELECT * FROM v9_organizacoes WHERE mesclado_em IS NULL ORDER BY id DESC LIMIT 500').fetchall()
        clientes=c.execute("SELECT id,nome FROM clientes WHERE status!='Inativo' ORDER BY nome").fetchall()
        vs=c.execute('''SELECT v.*,o.nome org,u.nome usuario FROM v9_vinculos v
                     JOIN v9_organizacoes o ON o.id=v.organizacao_id JOIN v9_usuarios u ON u.id=v.usuario_id
                     WHERE v.situacao='Pendente' ORDER BY v.id DESC''').fetchall()
    dados=[]
    for o in orgs:
        form=f'<form method="post" action="/organizacoes/{o["id"]}/validar">{formulario_csrf(s)}'
        if o['cliente_id']:
            form+='Cliente vinculado #'+str(o['cliente_id'])
            if o['situacao']!='Validado':
                form+=f'<input type="hidden" name="cliente_id" value="{o["cliente_id"]}"><button>Validar cadastro</button>'
        else:
            form+=select('Cliente contratante','cliente_id',[(x['id'],f'#{x["id"]} - {x["nome"]}') for x in clientes],required=True)
            form+='<button>Validar e vincular</button>'
        form+='</form>'
        form+=f'<form method="post" action="/organizacoes/{o["id"]}/sindico">{formulario_csrf(s)}'+campos('Nome do síndico','sindico_nome',o['sindico_nome'] or '')+campos('WhatsApp do síndico (DDD)','sindico_telefone',o['sindico_telefone'] or '')+'<button class="secondary">Salvar contato verificado</button></form>'
        dados.append((f'#{o["id"]}',esc(o['nome']),esc(o['tipo']),esc(o['situacao']),form))
    linhas=[]
    for x in vs:
        form=(f'<form method="post" action="/organizacoes/vinculos/{x["id"]}">{formulario_csrf(s)}'
              '<button name="decisao" value="aprovar">Validar</button><button name="decisao" value="recusar" class="danger">Recusar</button></form>')
        linhas.append((esc(x['org']),esc(x['usuario']),esc(x['papel']),form))
    mescla=(f'<form method="post" action="/organizacoes/mesclar">{formulario_csrf(s)}'
            +select('Origem (desativar)','origem',[(x['id'],f'#{x["id"]} {x["nome"]}') for x in orgs])
            +select('Destino (principal)','destino',[(x['id'],f'#{x["id"]} {x["nome"]}') for x in orgs])
            +'<p class="notice">Mesclagem preserva chamados e vínculos, e é bloqueada quando CNPJs ou clientes históricos divergem.</p><button class="danger">Mesclar após conferência</button></form>')
    return pagina(h,'Condomínios e vínculos',card('Vínculos pendentes',tabela(['Organização','Pessoa','Papel','Decisão'],linhas))+card('Organizações',tabela(['ID','Nome','Tipo','Situação','Vincular cliente'],dados))+card('Mesclagem controlada',mescla),s)

def pdf_pj(h,banco,s,chamado_id):
    import fluxo_os as fluxo
    from pathlib import Path
    with ext.db(banco) as c:
        chamado=c.execute('SELECT organizacao_id,usuario_id,os_id FROM v9_chamados WHERE id=?',(chamado_id,)).fetchone()
        if not chamado:raise ValueError('Chamado não encontrado.')
        if chamado['usuario_id']!=s['uid'] and not cad.vinculo_aprovado(banco,s['uid'],chamado['organizacao_id'],('Síndico','Administrador')):
            raise PermissionError('Documento restrito ao solicitante ou síndico validado.')
        if not chamado['os_id']:raise ValueError('A solicitação ainda não foi convertida em OS.')
        registro=fluxo.ultimo_documento(banco,chamado['os_id'])
        if not registro:raise ValueError('Relatório ainda não publicado.')
    arquivo=Path(fluxo.validar_pdf_publicado(registro))
    return h.send_bytes(arquivo.read_bytes(),'application/pdf',filename=arquivo.name)


def get(h,path,banco,prestador):
    card,layout,campos,textarea,select,esc,botao,tabela=ui()
    if path=='/pj':return login(h,banco)
    if path=='/pj/cadastro':return cadastro(h,banco)
    if path.startswith('/pj'):
        s=sessao(h,banco)
        if not s:return login(h,banco,'Entre para acessar condomínios e chamados.')
        parsed=urlsplit(h.path);params=parse_qs(parsed.query)
        if path=='/pj/painel':return painel(h,banco,s)
        if path=='/pj/organizacoes':return organizacoes(h,banco,s)
        if path=='/pj/nova-organizacao':return nova_organizacao(h,banco,s)
        if path=='/pj/chamado/novo':return chamado_form(h,banco,s,int(params.get('org',['0'])[0]))
        if path=='/pj/sindico':return sindico(h,banco,s,int(params.get('org',['0'])[0]))
        partes=path.strip('/').split('/')
        if len(partes)==4 and partes[1]=='chamado' and partes[2].isdigit() and partes[3]=='pdf':
            return pdf_pj(h,banco,s,int(partes[2]))
        return pagina(h,'Página inexistente',card('Aviso','Endereço não encontrado.'),status=404)
    if not prestador:return h.login()
    if path=='/chamados':return administrar(h,banco,prestador)
    if path=='/organizacoes':return administrar_organizacoes(h,banco,prestador)
    return None

def post(h,path,d,banco,prestador):
    if path=='/pj/entrar':
        cpf=cad.digitos(d.get('cpf',''));ip=h.client_address[0];key='pj:'+cpf+':'+ip
        eventos=[t for t in FALHAS.get(key,[]) if time.time()-t<600]
        if len(eventos)>=10:return pagina(h,'Acesso temporariamente bloqueado','<p>Aguarde dez minutos.</p>',status=429)
        u=cad.autenticar(banco,cpf,str(d.get('senha','')))
        if not u:
            FALHAS[key]=eventos+[time.time()]
            return login(h,banco,'CPF ou senha incorretos.')
        FALHAS.pop(key,None)
        token=secrets.token_urlsafe(32)
        SESSOES[token]={'uid':u['id'],'nome':u['nome'],'cred':u['senha_hash'],'csrf':secrets.token_urlsafe(24),'exp':time.time()+28800}
        return h.redir('/pj/painel',cookie(h,token))
    if path=='/pj/cadastrar':
        ip=h.client_address[0];key='cadastro:'+ip
        tentativas=[x for x in FALHAS.get(key,[]) if time.time()-x<3600]
        if len(tentativas)>=6:return pagina(h,'Cadastro temporariamente limitado','<p>Muitos cadastros. Tente mais tarde.</p>',status=429)
        FALHAS[key]=tentativas+[time.time()]
        if str(d.get('senha',''))!=str(d.get('confirmar_senha','')):raise ValueError('As senhas digitadas não coincidem.')
        cad.cadastrar_usuario(banco,str(d.get('nome','')),str(d.get('cpf','')),str(d.get('telefone','')),str(d.get('senha','')),str(d.get('email','')))
        return h.redir('/pj')
    if path.startswith('/pj'):
        s=sessao(h,banco)
        verificar_csrf(s,d)
        if path=='/pj/sair':
            jar=SimpleCookie();jar.load(h.headers.get('Cookie',''))
            if 'autosseg_pj' in jar:SESSOES.pop(jar['autosseg_pj'].value,None)
            return h.redir('/pj',cookie(h,'',True))
        if path=='/pj/vincular':
            cad.vincular(banco,s['uid'],int(d['org_id']),d['papel']);return h.redir('/pj/painel')
        if path=='/pj/nova-organizacao':
            cad.criar_organizacao(banco,s['uid'],str(d.get('nome','')),str(d.get('tipo','')),str(d.get('cnpj','')),str(d.get('cidade','')),str(d.get('bairro','')),str(d.get('papel','Morador')))
            return h.redir('/pj/painel')
        if path=='/pj/chamado/novo':
            cad.registrar_chamado(banco,s['uid'],int(d['org_id']),str(d.get('descricao','')),str(d.get('urgencia','Normal')),str(d.get('unidade','')))
            return h.redir('/pj/painel')
        partes=path.strip('/').split('/')
        if len(partes)==4 and partes[1]=='chamado' and partes[2].isdigit() and partes[3]=='confirmar':
            cad.confirmar(banco,int(partes[2]),'Síndico '+s['nome'],d.get('decisao')=='aprovar',uid=s['uid'])
            return h.redir('/pj/painel')
        raise ValueError('Operação desconhecida.')
    if not prestador:raise PermissionError('Área do prestador restrita.')
    verificar_csrf(prestador,d)
    partes=path.strip('/').split('/')
    if len(partes)==3 and partes[0]=='chamados' and partes[1].isdigit():
        ch=int(partes[1]);cmd=partes[2]
        if cmd=='analisar':cad.analisar(banco,ch,prestador['nome'],str(d.get('decisao','')),str(d.get('observacao','')))
        elif cmd=='confirmar':
            comprovacao=str(d.get('comprovacao','')).strip()
            if len(comprovacao)<8:raise ValueError('Registre nome do síndico e meio de confirmação.')
            cad.confirmar(banco,ch,'AUTOSEG '+prestador['nome']+' (confirmação: '+comprovacao[:150]+')',d.get('decisao')=='aprovar')
        elif cmd=='criar-os':cad.gerar_os(banco,ch,prestador['nome'])
        elif cmd=='cancelar':cad.cancelar_chamado(banco,ch,prestador['nome'],str(d.get('motivo','')))
        else:raise ValueError('Operação desconhecida.')
        return h.redir('/chamados')
    if len(partes)==3 and partes[0]=='organizacoes' and partes[1].isdigit() and partes[2]=='sindico':
        cad.atualizar_sindico(banco,int(partes[1]),str(d.get('sindico_nome','')),str(d.get('sindico_telefone','')),prestador['nome']);return h.redir('/organizacoes')
    if len(partes)==3 and partes[0]=='organizacoes' and partes[1].isdigit() and partes[2]=='validar':
        cad.validar_organizacao(banco,int(partes[1]),int(d['cliente_id']),prestador['nome']);return h.redir('/organizacoes')
    if len(partes)==3 and partes[0]=='organizacoes' and partes[1]=='vinculos' and partes[2].isdigit():
        cad.alterar_vinculo(banco,int(partes[2]),d.get('decisao')=='aprovar',prestador['nome']);return h.redir('/organizacoes')
    if path=='/organizacoes/mesclar':
        cad.mesclar_organizacoes(banco,int(d['origem']),int(d['destino']),prestador['nome']);return h.redir('/organizacoes')
    if len(partes)==3 and partes[0]=='clientes' and partes[1].isdigit() and partes[2]=='desativar':
        cad.desativar_cliente(banco,int(partes[1]),prestador['nome']);return h.redir('/clientes')
    raise ValueError('Operação desconhecida.')
