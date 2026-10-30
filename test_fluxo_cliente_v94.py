"""Testes HTTP reais do portal v9.4 com banco temporário, sem CPF/OS reais."""
import http.cookiejar
import re
import tempfile
import types
import urllib.error
import urllib.parse
import urllib.request
import sys
from pathlib import Path

import prestadores_ext as ext
import atendimento_os as aten
import fluxo_os
import cadastros_v9 as cad
from portal_prestador import PortalPrestador
from test_portal_v4 import schema
from test_v9 import cpf, cnpj


def browser():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def req(client,base,path,d=None):
    b=urllib.parse.urlencode(d).encode() if d is not None else None
    r=urllib.request.Request(base+path,b)
    try:
        with client.open(r,timeout=10) as x:return x.status,x.read().decode('utf-8','replace'),x.geturl()
    except urllib.error.HTTPError as x:return x.code,x.read().decode('utf-8','replace'),x.geturl()


def csrf(html):
    m=re.search('name="csrf" value="([^"]+)"',html)
    assert m,'CSRF não encontrado'
    return m.group(1)


def check(test,cond):
    assert cond,test
    print('OK:',test)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);db=str(tmp/'teste.db')
        schema(db)
        for a,b in [('ANEXOS','anexos'),('RELATORIOS','relatorios'),('RASCUNHOS','rascunhos')]:
            setattr(ext,a,tmp/b);(tmp/b).mkdir()
        sys.modules['banco']=types.SimpleNamespace(
            proximo_numero_os=lambda cursor: 'OS-'+str(cursor.execute('SELECT COALESCE(MAX(id),0)+1 FROM ordens_servico').fetchone()[0]).zfill(4))
        ext.instalar(db);fluxo_os.instalar(db);aten.instalar(db);cad.instalar(db)
        # migração aditiva/idempotente
        cad.instalar(db)
        with ext.db(db) as c:
            campos={r['name'] for r in c.execute('PRAGMA table_info(v9_usuarios)')}
            check('schema aditivo',{'perfil_completo','endereco','cliente_pf_id'}.issubset(campos))
        server=PortalPrestador(db,'127.0.0.1',0);server.iniciar()
        base='http://127.0.0.1:'+str(server.servidor.server_port)
        try:
            c=browser();st,body,_=req(c,base,'/cliente')
            check('login principal CPF/senha',st==200 and 'name="cpf"' in body and 'name="senha"' in body)
            st,body,_=req(c,base,'/cliente/cadastro')
            check('registro inicial sem telefone obrigatório',st==200 and 'confirmar_senha' in body and 'name="telefone"' not in body)
            doc=cpf(345678901)
            st,body,_=req(c,base,'/cliente/cadastrar',{'cpf':doc,'senha':'Senha-Boa-123456','confirmar_senha':'Senha-Boa-123456'})
            check('cadastro mínimo autentica imediatamente',st==200 and 'Meu painel' in body)
            st,body,_=req(c,base,'/cliente/nova')
            check('OS particular bloqueada sem perfil',st==200 and 'Complete seu cadastro' in body and 'action="/cliente/os/nova"' not in body)
            st,body,_=req(c,base,'/cliente/perfil')
            csrf0=csrf(body)
            st,body,_=req(c,base,'/cliente/perfil',{'csrf':csrf0,'nome':'Cliente Particular Teste','telefone':'51999998888',
                      'email':'cliente@teste.local','endereco':'Rua das Flores','numero':'123',
                      'bairro':'Centro','cidade':'Porto Alegre','uf':'RS','cep':'90000000'})
            check('salvar perfil PF',st==200 and 'Meu painel' in body)
            st,body,_=req(c,base,'/cliente/nova')
            check('formulário PF liberado',st==200 and 'action="/cliente/os/nova"' in body)
            st,body,_=req(c,base,'/cliente/os/nova',{'csrf':csrf(body),'descricao':'Revisar o portão de garagem particular','urgencia':'Normal'})
            check('OS PF aberta',st==200 and 'Revisar o portão de garagem particular' in body)
            with ext.db(db) as dbconn:
                o=dbconn.execute("SELECT id FROM ordens_servico WHERE descricao LIKE '%garagem particular%'").fetchone()
                check('registro OS PF no banco',o is not None)
                pfid=dbconn.execute('SELECT cliente_pf_id FROM v9_usuarios WHERE cpf=?',(doc,)).fetchone()[0]
                check('cliente PF ligado só ao seu perfil',pfid is not None)
            # Outra pessoa cadastra-se sem perfil e consegue solicitar para condomínio.
            user2=browser(); doc2=cpf(445678901)
            st,body,_=req(user2,base,'/cliente/cadastrar',{'cpf':doc2,'senha':'Senha-Boa-123456','confirmar_senha':'Senha-Boa-123456'})
            check('segundo usuário sem perfil completo',st==200)
            st,body,_=req(user2,base,'/cliente/nova-organizacao')
            check('pré-cadastro com apartamento/cargo e endereço',st==200 and 'name="unidade"' in body and 'name="endereco"' in body)
            st,body,_=req(user2,base,'/cliente/nova-organizacao',{'csrf':csrf(body),'nome':'Condomínio Teste Azul','tipo':'Condomínio',
                'cnpj':'','endereco':'Av Teste 100, Cidade/RS','unidade':'Apto 303','papel':'Morador','cidade':'Porto Alegre'})
            check('pré-cadastro seguido de chamado',st==200 and 'Apto 303' in body and 'Registrar solicitação' in body)
            st,body,_=req(user2,base,'/cliente/chamado/novo',{'csrf':csrf(body),'org_id':str(1 if False else 0),
                    'papel':'Morador','unidade':'Apto 303','descricao':'Portão com problema de abertura','urgencia':'Alta'})
            # Descobrir organização criada e repetir após chamada sem org_id, que deve ser rejeitada.
            check('chamado sem organização rejeitado',st in (400,409,500))
            with ext.db(db) as conn:
                org=conn.execute("SELECT id FROM v9_organizacoes WHERE nome='Condomínio Teste Azul'").fetchone()['id']
            st,body,_=req(user2,base,f'/cliente/chamado/novo?org={org}')
            st,body,_=req(user2,base,'/cliente/chamado/novo',{'csrf':csrf(body),'org_id':str(org),
                    'papel':'Morador','unidade':'Apto 303','descricao':'Portão com problema de abertura','urgencia':'Alta'})
            check('morador abre chamado sem perfil completo',st==200 and 'Portão com problema' in body)
            with ext.db(db) as conn:
                r=conn.execute('SELECT status,unidade FROM v9_chamados ORDER BY id DESC LIMIT 1').fetchone()
                check('status de análise e unidade',r['status']=='Aguardando AUTOSEG' and r['unidade']=='Apto 303')
            st,body,_=req(user2,base,'/cliente/organizacoes?q='+urllib.parse.quote('Condomínio Teste'))
            check('pesquisa por nome',st==200 and 'Condomínio Teste Azul' in body)
            # cadastrar outra organização como responsável: CNPJ obrigatório, vínculo não é aprovado automaticamente.
            st,body,_=req(user2,base,'/cliente/administrar-organizacao')
            check('cadastro PJ após login',st==200 and 'name="cnpj"' in body)
            st,body,_=req(user2,base,'/cliente/administrar-organizacao',{'csrf':csrf(body),'nome':'Empresa Nova','tipo':'Empresa',
                'cnpj':cnpj(),'endereco':'Rua Industrial 80'})
            check('criação de PJ como administrador pendente',st==200 and 'Empresa Nova' in body)
            with ext.db(db) as conn:
                r=conn.execute("SELECT v.papel,v.situacao FROM v9_vinculos v JOIN v9_organizacoes o ON o.id=v.organizacao_id WHERE o.nome='Empresa Nova'").fetchone()
                check('autorização admin não é automática',r['papel']=='Administrador' and r['situacao']=='Pendente')
            st,body,_=req(user2,base,'/cliente/organizacoes?q='+cnpj())
            check('CNPJ busca exata sem vazamento',st==200 and 'Empresa Nova' in body and cnpj() not in body)
            # Um outro usuário pode pedir vínculo em PJ existente, sem ganhar privilégio.
            terceiro=browser();doc3=cpf(545678901)
            st,body,_=req(terceiro,base,'/cliente/cadastrar',{'cpf':doc3,'senha':'Senha-Boa-123456','confirmar_senha':'Senha-Boa-123456'})
            with ext.db(db) as conn:
                empresaid=conn.execute("SELECT id FROM v9_organizacoes WHERE nome='Empresa Nova'").fetchone()['id']
            st,body,_=req(terceiro,base,f'/cliente/vinculo/novo?org={empresaid}')
            check('vínculo com PJ existente disponível',st==200 and 'name="cnpj"' in body)
            st,body,_=req(terceiro,base,'/cliente/vinculo/novo',{'csrf':csrf(body),'org_id':str(empresaid),'cnpj':cnpj()})
            check('solicitação de responsável para PJ existente',st==200)
            with ext.db(db) as conn:
                r=conn.execute('SELECT papel,situacao FROM v9_vinculos WHERE organizacao_id=? AND usuario_id=(SELECT id FROM v9_usuarios WHERE cpf=?)',(empresaid,doc3)).fetchone()
                check('responsável novo permanece pendente',r['papel']=='Administrador' and r['situacao']=='Pendente')
            st,body,_=req(terceiro,base,f'/cliente/sindico?org={empresaid}')
            check('não concede visão de síndico sem validação',st==403)
            # Acesso ID/senha antigo continua disponível.
            st,body,_=req(browser(),base,'/cliente/legado')
            check('portal legado preservado',st==200 and 'cliente_id' in body)
        finally:server.parar()
    print('PASSOU: fluxo de clientes AUTOSEG v9.4')


if __name__=='__main__':main()
