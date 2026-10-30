"""Teste de integração HTTP usando um SQLite temporário; dados reais nunca são alterados."""
import http.cookiejar
import io
import os
import re
import sqlite3
import sys
import tempfile
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from PIL import Image

sys.path.insert(0,str(Path(__file__).parent))
import prestadores_ext as ext
from portal_prestador import PortalPrestador


def schema(db):
    with ext.db(db) as c:
        c.executescript('''
        CREATE TABLE clientes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,tipo_pessoa TEXT DEFAULT 'Jurídica',documento TEXT,
        nome TEXT NOT NULL,nome_fantasia TEXT,endereco TEXT,numero TEXT,complemento TEXT,
        bairro TEXT,cep TEXT,cidade TEXT,uf TEXT,telefone TEXT,email TEXT,sindico_nome TEXT,
        sindico_telefone TEXT,sindico_email TEXT,administradora TEXT,administradora_email TEXT,
        administradora_telefone TEXT,observacoes TEXT,status TEXT DEFAULT 'Ativo',criado_em TEXT);
        CREATE TABLE ordens_servico(
        id INTEGER PRIMARY KEY AUTOINCREMENT,numero_os TEXT,cliente_id INTEGER,data_abertura TEXT,
        tecnico TEXT,descricao TEXT,valor_mao_obra REAL,valor_materiais REAL,valor_total REAL,
        forma_pagamento TEXT,status TEXT,observacoes TEXT,criado_em TEXT,atualizado_em TEXT,
        data_conclusao TEXT,origem TEXT DEFAULT 'App');
        CREATE TABLE materiais_os(id INTEGER PRIMARY KEY AUTOINCREMENT,os_id INTEGER,item TEXT,quantidade REAL,valor_unitario REAL,valor_total REAL);
        CREATE TABLE financeiro(id INTEGER PRIMARY KEY AUTOINCREMENT,os_id INTEGER,cliente_id INTEGER,descricao TEXT,valor REAL,forma_pagamento TEXT,status TEXT,data_lancamento TEXT,data_pagamento TEXT,vencimento TEXT);
        INSERT INTO clientes(nome,email,documento,status,cidade) VALUES('Condomínio Alfa','alfa@example.com','123','Ativo','Porto Alegre');
        INSERT INTO ordens_servico(numero_os,cliente_id,data_abertura,descricao,valor_mao_obra,valor_materiais,valor_total,forma_pagamento,status,observacoes) VALUES
         ('OS-001',1,'hoje','Interfone',200,0,200,'PIX','Aberta',''),
         ('OS-002',1,'hoje','CFTV',100,0,100,'PIX','Pendente',''),
         ('OS-003',1,'hoje','Redes',100,0,100,'PIX','Aberta',''),
         ('OS-004',1,'ontem','Antiga',100,0,100,'PIX','Concluída','');
        ''')


def run():
    with tempfile.TemporaryDirectory(prefix='autosseg_v4_') as tmp:
        banco=str(Path(tmp)/'teste.db')
        schema(banco)
        fake=types.ModuleType('banco')
        fake.proximo_numero_os=lambda cursor: f"OS-{cursor.execute('SELECT COALESCE(MAX(id),0)+1 FROM ordens_servico').fetchone()[0]:03d}"
        sys.modules['banco']=fake
        ext.instalar(banco)
        joao=ext.cadastrar(banco,'João','joao@example.com','senha-bem-segura-2026')
        ana=ext.cadastrar(banco,'Ana','ana@example.com','senha-bem-segura-2026')
        ext.atribuir(banco,3,ana)
        portal=PortalPrestador(banco,host='127.0.0.1',porta=0)
        portal.iniciar()
        url='http://127.0.0.1:'+str(portal.servidor.server_port)
        jar=http.cookiejar.CookieJar()
        openr=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        def requisitar(path,params=None,opener=openr,expect=200):
            if params is not None:
                data=urllib.parse.urlencode(params,doseq=True).encode()
                req=urllib.request.Request(url+path,data,{'Content-Type':'application/x-www-form-urlencoded'})
            else:req=urllib.request.Request(url+path)
            try:
                with opener.open(req,timeout=10) as r:
                    raw=r.read();status=r.status;headers=r.headers
            except urllib.error.HTTPError as e:
                raw=e.read();status=e.code;headers=e.headers
            assert status==expect,(path,status,raw[:800])
            return raw,headers
        try:
            raw,_=requisitar('/');assert b'Entrar' in raw
            raw,_=requisitar('/login',{'email':'joao@example.com','senha':'senha-bem-segura-2026'})
            html=raw.decode();assert 'Painel principal' in html
            csrf=re.search('name="csrf" value="([^"]+)"',html).group(1)
            for path in ['/os','/historico','/clientes','/clientes/1','/clientes/novo','/financeiro','/relatorios','/emails','/notas','/portal-cliente','/os/1','/os/nova']:
                raw,_=requisitar(path)
                assert len(raw)>500,(path,len(raw))
            oslist,_=requisitar('/os');oslist=oslist.decode()
            assert all(x in oslist for x in ('OS-001','OS-002','OS-003','Ana'))
            page,_=requisitar('/os/3');assert b'Finalizar OS' in page
            # CSRF é obrigatório.
            requisitar('/os/1/salvar',{'descricao':'Falhou'},expect=403)
            # Atualização integral, com materiais.
            base={'csrf':csrf,'cliente_id':'1','tecnico':'João','forma_pagamento':'PIX',
                  'descricao':'Manutenção interfone','observacoes':'Teste',
                  'valor_mao_obra':'200,00','relatorio_tecnico':'Troca de cabo e testes concluídos',
                  'material_item[]':['Cabo','Fonte',''],
                  'material_qtd[]':['2','1',''],
                  'material_unit[]':['5,00','25,00',''],'acao_status':'Pendente'}
            raw,_=requisitar('/os/1/salvar',base)
            with ext.db(banco) as c:
                r=c.execute('SELECT status,valor_total FROM ordens_servico WHERE id=1').fetchone()
                assert r['status']=='Pendente' and r['valor_total']==235,dict(r)
                assert c.execute('SELECT COUNT(*) FROM materiais_os WHERE os_id=1').fetchone()[0]==2
            # Sem responsável, pode pendenciar/finalizar via portal. PIX não recebido automaticamente.
            base['acao_status']='Concluída'
            raw,_=requisitar('/os/1/salvar',base)
            with ext.db(banco) as c:
                r=c.execute('SELECT status FROM ordens_servico WHERE id=1').fetchone()
                f=c.execute('SELECT status,valor FROM financeiro WHERE os_id=1').fetchone()
                assert r['status']=='Concluída' and f['status']=='Aguardando pagamento' and f['valor']==235
            pdf,h=requisitar('/os/1/pdf');assert pdf.startswith(b'%PDF-') and h['Content-Type'].startswith('application/pdf')
            eml,_=requisitar('/os/1/email');assert b'Content-Type: application/pdf' in eml
            nf,_=requisitar('/os/1/nota');assert json_load(nf)['status']=='RASCUNHO_NAO_EMITIDO'
            # Responsável de outra pessoa: não pode encerrar sem transferência.
            base['acao_status']='Concluída'
            requisitar('/os/3/salvar',base,expect=403)
            # Transferência, painel disponível a todos.
            requisitar('/os/3/atribuir',{'csrf':csrf,'prestador_id':str(joao)})
            with ext.db(banco) as c:assert ext.responsavel_atual(c,3)==joao
            # Upload imagem por um prestador ativo: registra identidade e aparece no PDF.
            img=io.BytesIO();Image.new('RGB',(55,40),'red').save(img,format='PNG')
            blob=img.getvalue();boundary='autossegtestboundary'
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{csrf}\r\n'
                  f'--{boundary}\r\nContent-Disposition: form-data; name="foto"; filename="teste.png"\r\nContent-Type: image/png\r\n\r\n').encode()+blob+(f'\r\n--{boundary}--\r\n').encode()
            req=urllib.request.Request(url+'/os/3/foto',body,{'Content-Type':'multipart/form-data; boundary='+boundary})
            with openr.open(req,timeout=10) as r:assert r.status==200
            with ext.db(banco) as c:
                pic=c.execute('SELECT id,prestador_id FROM os_anexos WHERE os_id=3').fetchone()
                assert pic and pic['prestador_id']==joao
            imgdata,_=requisitar('/arquivos/anexo/'+str(pic['id']));assert imgdata==blob
            # Cadastro e atualização cliente.
            cd={'csrf':csrf,**{k:'' for k in __import__('portal_negocios').CLIENTE_CAMPOS}}
            cd.update({'nome':'Condomínio Beta','status':'Ativo','tipo_pessoa':'Jurídica','email':'beta@example.com'})
            requisitar('/clientes/novo/salvar',cd)
            with ext.db(banco) as c: cid=c.execute("SELECT id FROM clientes WHERE nome='Condomínio Beta'").fetchone()[0]
            cd['nome']='Condomínio Beta Atualizado'
            requisitar(f'/clientes/{cid}/salvar',cd)
            with ext.db(banco) as c:assert c.execute('SELECT nome FROM clientes WHERE id=?',(cid,)).fetchone()[0]=='Condomínio Beta Atualizado'
            # Nova OS, mantendo numeração do banco.
            nova={**base,'csrf':csrf,'cliente_id':str(cid),'acao_status':'salvar'}
            requisitar('/os/nova/salvar',nova)
            with ext.db(banco) as c: oid=c.execute('SELECT MAX(id) FROM ordens_servico').fetchone()[0]
            assert oid==5
            with ext.db(banco) as c:fid=c.execute('SELECT id FROM financeiro WHERE os_id=1').fetchone()[0]
            requisitar(f'/financeiro/{fid}/receber',{'csrf':csrf})
            with ext.db(banco) as c:
                assert c.execute('SELECT status FROM financeiro WHERE id=?',(fid,)).fetchone()[0]=='Recebido'
                n=c.execute('SELECT COUNT(*) FROM portal_auditoria').fetchone()[0]
                assert n>=8,n
            # Sem cadastro de prestador no portal.
            requisitar('/prestadores/novo',expect=404)
            print('OK: login, CSRF, menus web, clientes, OS compartilhadas, materiais, pendência, conclusão, PDF, EML, NFS-e rascunho, transferência, fotos, financeiro e auditoria.')
        finally:
            portal.parar()


def json_load(data):
    import json
    return json.loads(data)

if __name__=='__main__':run()
