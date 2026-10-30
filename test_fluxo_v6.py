"""Teste de integração HTTP da versão 6; não usa o dados.db real."""
import http.cookiejar
import hashlib
import io
import uuid
from PIL import Image
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
from portal_prestador import PortalPrestador
from test_portal_v4 import schema


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


def navegar_multipart(opener, base, path, data, arquivo_nome='teste.png'):
    """Envia seleção de situação e imagem em um único POST (como um celular)."""
    fronteira='AUTOSSEG'+uuid.uuid4().hex
    partes=[]
    for nome,val in data.items():
        valores=val if isinstance(val,list) else [val]
        for item in valores:
            partes.append((f'--{fronteira}\r\nContent-Disposition: form-data; name="{nome}"\r\n\r\n{item}\r\n').encode('utf-8'))
    img=Image.new('RGB',(24,24),'yellow')
    buffer=io.BytesIO();img.save(buffer,format='PNG')
    partes.append((f'--{fronteira}\r\nContent-Disposition: form-data; name="imagem_encerramento"; filename="{arquivo_nome}"\r\nContent-Type: image/png\r\n\r\n').encode())
    partes.append(buffer.getvalue());partes.append(b'\r\n')
    partes.append(f'--{fronteira}--\r\n'.encode())
    req=urllib.request.Request(base+path,b''.join(partes),
        {'Content-Type':f'multipart/form-data; boundary={fronteira}'})
    try:
        with opener.open(req,timeout=15) as r: return r.status,r.read(),r.headers
    except urllib.error.HTTPError as e:return e.code,e.read(),e.headers


def main():
    with tempfile.TemporaryDirectory(prefix='autosseg_v6_') as tmp:
        p=Path(tmp)
        banco=str(p/'teste.db')
        ext.ANEXOS=p/'anexos';ext.RELATORIOS=p/'relatorios';ext.RASCUNHOS=p/'rascunhos'
        for path in (ext.ANEXOS,ext.RELATORIOS,ext.RASCUNHOS):path.mkdir()
        schema(banco)
        fake=types.ModuleType('banco')
        fake.proximo_numero_os=lambda cursor: f"OS-{cursor.execute('SELECT COALESCE(MAX(id),0)+1 FROM ordens_servico').fetchone()[0]:03d}"
        sys.modules['banco']=fake
        ext.instalar(banco);fluxo.instalar(banco)
        p1=ext.cadastrar(banco,'João','joao@example.com','senha-bem-segura-2026')
        with ext.db(banco) as c:
            c.execute("INSERT INTO clientes(nome,email,documento,status) VALUES('Condomínio Beta','beta@example.com','222','Ativo')")
            c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,data_abertura,descricao,status,valor_total,forma_pagamento) VALUES('OS-005',2,'hoje','Portão','Aberta',50,'PIX')")
        senha1=fluxo.definir_senha_cliente(banco,1)
        senha2=fluxo.definir_senha_cliente(banco,2)
        portal=PortalPrestador(banco,host='127.0.0.1',porta=0)
        portal.iniciar()
        base='http://127.0.0.1:'+str(portal.servidor.server_port)
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
                'valor_materiais_manual':'0','relatorio_tecnico':'Diagnóstico realizado; serviço cancelado.',
                'motivo_encerramento':'Cliente desistiu do serviço','material_item[]':['Cabo',''],
                'material_qtd[]':['1',''],'material_unit[]':['15',''],'acao_status':'Cancelada','modo_envio':'encerrar'}
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
            st,html,_=navegar(alfa,base,'/cliente/entrar',{'cliente_id':'1','senha':senha1})
            assert st==200 and b'OS-001' in html
            csrf1=token(html)
            st,html,_=navegar(beta,base,'/cliente/entrar',{'cliente_id':'2','senha':senha2})
            assert st==200 and b'OS-005' in html and b'OS-001' not in html
            csrf2=token(html)
            st,html,_=navegar(beta,base,'/cliente/os/1/pdf')
            assert st==404 and not html.startswith(b'%PDF')
            st,html,_=navegar(anon,base,'/cliente/os/1/pdf')
            assert not html.startswith(b'%PDF')
            st,cliente_pdf,h=navegar(alfa,base,'/cliente/os/1/pdf')
            assert st==200 and cliente_pdf==web_pdf
            assert hashlib.sha256(cliente_pdf).hexdigest()==fluxo.ultimo_documento(banco,1)['sha256']
            # Cancelamento com justificativa não gera cobrança automática.
            base_form.update({'descricao':'CFTV','acao_status':'Cancelada','motivo_encerramento':'Sem acesso ao equipamento'})
            st,html,_=navegar(staff,base,'/os/2/salvar',base_form)
            assert st==200,(st,html[-400:])
            with ext.db(banco) as c:
                assert c.execute('SELECT status FROM ordens_servico WHERE id=2').fetchone()[0]=='Cancelada'
                assert c.execute('SELECT COUNT(*) FROM financeiro WHERE os_id=2').fetchone()[0]==0
            st,pdf,_=navegar(alfa,base,'/cliente/os/2/pdf');assert st==200 and pdf.startswith(b'%PDF')
            # Conclusão: gera pendência financeira real, não confirma PIX.
            ext.atribuir(banco,3,p1)
            base_form.update({'descricao':'Redes','acao_status':'Concluída','motivo_encerramento':''})
            st,html,_=navegar(staff,base,'/os/3/salvar',base_form)
            assert st==200,(st,html[-400:])
            with ext.db(banco) as c:
                f=c.execute('SELECT status,valor FROM financeiro WHERE os_id=3').fetchone()
                assert f['status']=='Aguardando pagamento' and f['valor']==215
            st,pdf,_=navegar(alfa,base,'/cliente/os/3/pdf');assert st==200 and pdf.startswith(b'%PDF')
            # Requisitar abertura pelo cliente: aparece na lista compartilhada do prestador.
            st,html,_=navegar(alfa,base,'/cliente/nova',{'csrf':csrf1,'descricao':'Solicito revisão do motor do portão','urgencia':'Alta'})
            assert st==200,(st,html[-500:])
            with ext.db(banco) as c:
                o=c.execute("SELECT id,origem,status FROM ordens_servico WHERE descricao='Solicito revisão do motor do portão'").fetchone()
                assert o['status']=='Aberta' and o['origem']=='Portal'
            st,html,_=navegar(staff,base,'/os')
            assert st==200 and f'OS-{o["id"]:03d}'.encode() in html
            st,html,_=navegar(alfa,base,f'/cliente/os/{o["id"]}/pdf')
            assert st==409 and not html.startswith(b'%PDF')
            # Pendência é o único status não final deste formulário e não publica PDF.
            base_form.update({'descricao':'Portão auxiliar','cliente_id':'1',
                'acao_status':'Pendente','modo_envio':'encerrar','motivo_encerramento':''})
            st,html,_=navegar(staff,base,f'/os/{o["id"]}/salvar',base_form)
            assert st==200,(st,html[-400:])
            with ext.db(banco) as c:
                assert c.execute('SELECT status FROM ordens_servico WHERE id=?',(o['id'],)).fetchone()[0]=='Pendente'
            assert fluxo.ultimo_documento(banco,o['id']) is None
            # Fechamento final com imagem (multipart) deve anexar ANTES de publicar.
            base_form.update({'acao_status':'Concluída','relatorio_tecnico':'Instalado novo módulo e realizado teste final.'})
            st,html,_=navegar_multipart(staff,base,f'/os/{o["id"]}/salvar',base_form)
            assert st==200,(st,html[-800:])
            with ext.db(banco) as c:
                assert c.execute('SELECT status FROM ordens_servico WHERE id=?',(o['id'],)).fetchone()[0]=='Concluída'
                assert c.execute('SELECT COUNT(*) FROM os_anexos WHERE os_id=?',(o['id'],)).fetchone()[0]==1
            st,img_pdf,_=navegar(alfa,base,f'/cliente/os/{o["id"]}/pdf')
            assert st==200 and img_pdf.startswith(b'%PDF')
            st,prestador_pdf,_=navegar(staff,base,f'/os/{o["id"]}/pdf')
            assert st==200 and prestador_pdf==img_pdf
            st,html,_=navegar(staff,base,'/historico')
            assert st==200 and b'Vers' in html and b'Baixar PDF' in html
            # Publicação de versão nova exige POST + CSRF.
            st,html,_=navegar(staff,base,'/os/1/publicar',{'csrf':'falso'})
            assert st==403
            st,html,_=navegar(staff,base,'/os/1/publicar',{'csrf':csrf})
            assert st==200
            assert fluxo.ultimo_documento(banco,1)['versao']==2
            # Rascunhos continuam pendentes de API.
            st,eml,_=navegar(staff,base,'/os/1/email');assert st==200 and b'Content-Type: application/pdf' in eml
            st,nf,_=navegar(staff,base,'/os/1/nota');assert st==409
            st,nf,_=navegar(staff,base,'/os/3/nota');assert st==200 and json.loads(nf)['status']=='RASCUNHO_NAO_EMITIDO'
            # Reset de senha invalidando a antiga; sessão anterior ainda válida até logout, teste apenas reautenticação.
            nova=fluxo.definir_senha_cliente(banco,2)
            assert fluxo.autenticar_cliente(banco,2,senha2) is None
            assert fluxo.autenticar_cliente(banco,2,nova) is not None
            st,apos_reset,_=navegar(beta,base,'/cliente')
            assert b'OS-005' not in apos_reset and b'Acesso do cliente' in apos_reset
            print('PASSOU: cliente e prestador, 2 tipos de encerramento e pendência, relatório idêntico, isolamento por cliente, PDF versionado, OS em tempo real, pendência PIX, rascunhos e reset de senha.')
        finally:portal.parar()

if __name__=='__main__': main()
