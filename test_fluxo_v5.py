"""Teste de integração HTTP da versão 5; não usa o dados.db real."""
import http.cookiejar
import hashlib
import json
import re
import sys
import tempfile
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import prestadores_ext as ext
import fluxo_os as fluxo
import cliente_fluxo_v94 as fluxo_pf
import cadastros_v9 as cad
from portal_prestador import PortalPrestador
from servidor_web import ServidorPortal
from test_portal_v4 import schema
from test_v9 import cpf


def navegar(opener,base,path,params=None):
    req=urllib.request.Request(base+path)
    if params is not None:
        req=urllib.request.Request(base+path,urllib.parse.urlencode(params,doseq=True).encode(),
                                   {'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with opener.open(req,timeout=15) as res: return res.status,res.read(),res.headers
    except urllib.error.HTTPError as e:return e.code,e.read(),e.headers


def token(html):
    return re.search(r'name="csrf" value="([^"]+)"',html.decode()).group(1)


def main():
    with tempfile.TemporaryDirectory(prefix='autosseg_v5_') as tmp:
        p=Path(tmp)
        banco=str(p/'teste.db')
        ext.ANEXOS=p/'anexos';ext.RELATORIOS=p/'relatorios';ext.RASCUNHOS=p/'rascunhos'
        for path in (ext.ANEXOS,ext.RELATORIOS,ext.RASCUNHOS):path.mkdir()
        schema(banco)
        fake=types.ModuleType('banco')
        fake.proximo_numero_os=lambda cursor: f"OS-{cursor.execute('SELECT COALESCE(MAX(id),0)+1 FROM ordens_servico').fetchone()[0]:03d}"
        sys.modules['banco']=fake
        ext.instalar(banco);fluxo.instalar(banco);cad.instalar(banco)
        p1=ext.cadastrar(banco,'João','joao@example.com','senha-bem-segura-2026')
        ext.atribuir(banco,1,p1)
        ext.atribuir(banco,2,p1)
        with ext.db(banco) as c:
            c.execute("INSERT INTO clientes(nome,email,documento,status,tipo_pessoa) VALUES('Condomínio Beta','beta@example.com','222','Ativo','Física')")
            c.execute("UPDATE clientes SET tipo_pessoa='Física' WHERE id=1")
            c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,data_abertura,descricao,status,valor_total,forma_pagamento) VALUES('OS-005',2,'hoje','Portão','Aberta',50,'PIX')")
        senha1=fluxo.definir_senha_cliente(banco,1)
        senha2=fluxo.definir_senha_cliente(banco,2)
        senha_moderna='Senha-Cliente-123'
        cpf_alfa=cpf(111222333); cpf_beta=cpf(222333444)
        uid_alfa=fluxo_pf.criar_conta(banco,cpf_alfa,senha_moderna)
        uid_beta=fluxo_pf.criar_conta(banco,cpf_beta,senha_moderna)
        with ext.db(banco) as c:
            c.execute('UPDATE v9_usuarios SET cliente_pf_id=1 WHERE id=?',(uid_alfa,))
            c.execute('UPDATE v9_usuarios SET cliente_pf_id=2 WHERE id=?',(uid_beta,))
        fluxo_pf.atualizar_perfil(banco,uid_alfa,{
            'nome':'Cliente Alfa Teste','telefone':'51999998888','email':'alfa@example.com',
            'endereco':'Rua Alfa','numero':'100','bairro':'Centro','cidade':'Porto Alegre',
            'uf':'RS','cep':'90000000'})
        portal=PortalPrestador(banco,host='127.0.0.1',porta=0)
        portal.iniciar()
        base='http://127.0.0.1:'+str(portal.servidor.server_port)
        portal_cliente=ServidorPortal(caminho_banco=banco,host='127.0.0.1',porta=0)
        portal_cliente.iniciar()
        base_cliente='http://127.0.0.1:'+str(portal_cliente.porta)
        staff=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        alfa=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        beta=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        anon=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            status,html,_=navegar(staff,base,'/login',{'email':'joao@example.com','senha':'senha-bem-segura-2026'})
            assert status==200
            csrf=token(html)
            # OS cancelada, com relatório e motivo; publica PDF e não cria cobrança.
            base_form={'csrf':csrf,'cliente_id':'1','tecnico':'João','forma_pagamento':'PIX',
                'descricao':'Manutenção de interfone','observacoes':'teste','valor_mao_obra':'200',
                'sem_nota_fiscal':'1',
                'valor_materiais_manual':'0','relatorio_tecnico':'Diagnóstico realizado; serviço cancelado.',
                'motivo_encerramento':'Cliente desistiu do serviço','material_item[]':['Cabo',''],
                'material_qtd[]':['1',''],'material_unit[]':['15',''],'acao_status':'Cancelada'}
            st,html,_=navegar(staff,base,'/os/1/salvar',base_form)
            assert st==200,(st,html[-600:])
            with ext.db(banco) as c:
                assert c.execute('SELECT status FROM ordens_servico WHERE id=1').fetchone()[0]=='Cancelada'
                assert c.execute('SELECT COUNT(*) FROM financeiro WHERE os_id=1').fetchone()[0]==0
                assert c.execute('SELECT motivo FROM os_encerramentos WHERE os_id=1').fetchone()[0]=='Cliente desistiu do serviço'
                entrega=c.execute('SELECT email_status,nf_status FROM os_entregas WHERE os_id=1').fetchone()
                assert entrega['email_status']=='aguardando_api' and entrega['nf_status']=='nao_aplicavel'
            st,web_pdf,h=navegar(staff,base,'/os/1/pdf');assert st==200 and web_pdf.startswith(b'%PDF')
            assert h['Content-Type']=='application/pdf'
            # Login de dois clientes separados, sem leitura cruzada.
            st,html,_=navegar(alfa,base_cliente,'/cliente/entrar-pf',{'cpf':cpf_alfa,'senha':senha_moderna})
            assert st==200 and b'OS-001' in html
            csrf1=token(html)
            st,html,_=navegar(beta,base_cliente,'/cliente/entrar-pf',{'cpf':cpf_beta,'senha':senha_moderna})
            assert st==200 and b'OS-005' in html and b'OS-001' not in html
            csrf2=token(html)
            st,html,_=navegar(beta,base_cliente,'/cliente/os/1/pdf')
            assert st in (403,404) and not html.startswith(b'%PDF')
            st,html,_=navegar(anon,base_cliente,'/cliente/os/1/pdf')
            assert not html.startswith(b'%PDF')
            st,cliente_pdf,h=navegar(alfa,base_cliente,'/cliente/os/1/pdf')
            assert st==200 and cliente_pdf==web_pdf
            assert hashlib.sha256(cliente_pdf).hexdigest()==fluxo.ultimo_documento(banco,1)['sha256']
            # OS não realizada não gera cobrança automática.
            base_form.update({'descricao':'CFTV','acao_status':'Cancelada','motivo_encerramento':'Sem acesso ao equipamento'})
            st,html,_=navegar(staff,base,'/os/2/salvar',base_form)
            assert st==200,(st,html[-400:])
            with ext.db(banco) as c:
                assert c.execute('SELECT status FROM ordens_servico WHERE id=2').fetchone()[0]=='Cancelada'
                assert c.execute('SELECT COUNT(*) FROM financeiro WHERE os_id=2').fetchone()[0]==0
            st,pdf,_=navegar(alfa,base_cliente,'/cliente/os/2/pdf');assert st==200 and pdf.startswith(b'%PDF')
            # Conclusão: gera pendência financeira real, não confirma PIX.
            ext.atribuir(banco,3,p1)
            base_form.update({'descricao':'Redes','acao_status':'Concluída','motivo_encerramento':''})
            st,html,_=navegar(staff,base,'/os/3/salvar',base_form)
            assert st==200,(st,html[-400:])
            with ext.db(banco) as c:
                f=c.execute('SELECT status,valor FROM financeiro WHERE os_id=3').fetchone()
                assert f['status']=='Aguardando pagamento' and f['valor']==215
            st,pdf,_=navegar(alfa,base_cliente,'/cliente/os/3/pdf');assert st==200 and pdf.startswith(b'%PDF')
            # Requisitar abertura pelo cliente: aparece na lista compartilhada do prestador.
            st,html,_=navegar(alfa,base_cliente,'/cliente/os/nova',{'csrf':csrf1,'descricao':'Solicito revisão do motor do portão','urgencia':'Alta'})
            assert st==200,(st,html[-500:])
            with ext.db(banco) as c:
                o=c.execute("SELECT id,origem,status FROM ordens_servico WHERE descricao='Solicito revisão do motor do portão'").fetchone()
                assert o['status']=='Aberta' and o['origem']=='Portal'
            st,html,_=navegar(staff,base,'/os')
            assert st==200 and f'OS-{o["id"]:03d}'.encode() in html
            st,html,_=navegar(alfa,base_cliente,f'/cliente/os/{o["id"]}/pdf')
            assert st in (400,404,409) and not html.startswith(b'%PDF')
            # Publicação de versão nova exige POST + CSRF.
            st,html,_=navegar(staff,base,'/os/1/publicar',{'csrf':'falso'})
            assert st==403
            st,html,_=navegar(staff,base,'/os/1/publicar',{'csrf':csrf})
            assert st==200
            assert fluxo.ultimo_documento(banco,1)['versao']==2
            # Rascunhos continuam pendentes de API.
            st,eml,_=navegar(staff,base,'/os/1/email');assert st==200 and b'Content-Type: application/pdf' in eml
            st,nf,_=navegar(staff,base,'/os/1/nota');assert st in (400,409)
            st,nf,_=navegar(staff,base,'/os/3/nota');assert st==200 and json.loads(nf)['status']=='RASCUNHO_NAO_EMITIDO'
            # Reset de senha invalidando a antiga; sessão anterior ainda válida até logout, teste apenas reautenticação.
            nova=fluxo.definir_senha_cliente(banco,2)
            assert fluxo.autenticar_cliente(banco,2,senha2) is None
            assert fluxo.autenticar_cliente(banco,2,nova) is not None
            visitante=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            st,apos_reset,_=navegar(visitante,base_cliente,'/cliente')
            assert b'name="cpf"' in apos_reset
            st,apos_reset,_=navegar(visitante,base_cliente,'/legado/entrar',{'cliente_id':'2','senha':nova})
            assert st==200 and b'OS-005' in apos_reset and b'OS-001' not in apos_reset
            print('PASSOU: cliente e prestador, 3 tipos de encerramento, relatório idêntico, isolamento por cliente, PDF versionado, OS em tempo real, pendência PIX, rascunhos e reset de senha.')
        finally:
            portal_cliente.parar()
            portal.parar()

if __name__=='__main__': main()
