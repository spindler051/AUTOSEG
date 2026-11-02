"""E2E v9 (portais HTTP locais, banco temporário, sem dados reais)."""
import os,shutil,tempfile,sys,types,http.cookiejar,urllib.request,urllib.parse,urllib.error,re
from pathlib import Path
from test_portal_v4 import schema
import prestadores_ext as ext
import cadastros_v9 as cad
import fluxo_os, atendimento_os
from portal_prestador import PortalPrestador

def cpf(n):
    a=[int(i) for i in f'{n:09d}']
    for k in (9,10):
        d=sum(a[i]*(k+1-i) for i in range(k))*10%11;a.append(0 if d==10 else d)
    return ''.join(map(str,a))

def cnpj():
    a=[int(i) for i in '123456780001']
    for pesos in [[5,4,3,2,9,8,7,6,5,4,3,2],[6,5,4,3,2,9,8,7,6,5,4,3,2]]:
        d=sum(x*y for x,y in zip(a,pesos))%11;a.append(0 if d<2 else 11-d)
    return ''.join(map(str,a))

def get(opener,base,path,data=None):
    if data is None:r=urllib.request.Request(base+path)
    else:r=urllib.request.Request(base+path,urllib.parse.urlencode(data).encode())
    try:
        with opener.open(r,timeout=10) as x:return x.status,x.read()
    except urllib.error.HTTPError as e:return e.code,e.read()

def csrf(data):
    v=re.search(rb'name="csrf" value="([^"]+)"',data)
    assert v,data[:500]
    return v.group(1).decode()

def main():
    with tempfile.TemporaryDirectory() as t:
        tmp=Path(t);db=str(tmp/'teste.sqlite')
        ext.RELATORIOS=tmp/'relatorios';ext.ANEXOS=tmp/'anexos';ext.RASCUNHOS=tmp/'rascunhos'
        for p in (ext.RELATORIOS,ext.ANEXOS,ext.RASCUNHOS):p.mkdir()
        schema(db)
        mod=types.ModuleType('banco')
        mod.proximo_numero_os=lambda cu:'OS-'+str(cu.execute('SELECT COALESCE(MAX(id),0)+1 FROM ordens_servico').fetchone()[0]).zfill(4)
        sys.modules['banco']=mod
        ext.instalar(db);fluxo_os.instalar(db);atendimento_os.instalar(db);cad.instalar(db)
        with ext.db(db) as c:
            org=c.execute("SELECT id FROM v9_organizacoes WHERE nome='Condomínio Alfa'").fetchone()['id']
        admin=ext.cadastrar(db,'Admin','admin@teste.local','Senha-de-teste-2026')
        worker=ext.cadastrar(db,'Operador','operador@teste.local','Senha-de-teste-2026')
        cad.definir_admin(db,admin,True)
        sind=cad.cadastrar_usuario(db,'Sindico de Teste',cpf(123456789),'51999999999','Senha-de-teste-2026')
        mor=cad.cadastrar_usuario(db,'Morador de Teste',cpf(223456789),'51988888888','Senha-de-teste-2026')
        cad.vincular(db,mor,org,'Morador')
        cad.atribuir_responsavel(db,org,sind,'Admin teste')
        h=cad.registrar_chamado(db,mor,org,'Portão não abre pela manhã','Alta','Bloco A','Morador','Pessoa Teste','51999998888')
        cad.analisar(db,h,'Admin teste','Aguardando síndico')
        cad.confirmar(db,h,'Síndico de teste',True,uid=sind)
        oid=cad.gerar_os(db,h,'Admin teste')
        with ext.db(db) as c:
            assert c.execute('SELECT status,os_id FROM v9_chamados WHERE id=?',(h,)).fetchone()['os_id']==oid
            assert c.execute('SELECT descricao_original FROM os_solicitacoes WHERE os_id=?',(oid,)).fetchone()[0]=='Portão não abre pela manhã'
        portal=PortalPrestador(db,'127.0.0.1',0);portal.iniciar()
        base='http://127.0.0.1:'+str(portal.servidor.server_port)
        try:
            opp=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            status,login=get(opp,base,'/pj');assert status==200 and b'PF / PJ' in login
            status,form=get(opp,base,'/pj/cadastro');assert status==200 and b'Nome completo' in form
            status,html=get(opp,base,'/pj/entrar',{'cpf':cpf(123456789),'senha':'Senha-de-teste-2026'})
            assert status==200 and b'Painel de acionamentos' in html,(status,html[:900])
            status,html=get(opp,base,f'/pj/sindico?org={org}');assert status==200 and b'Morador de Teste' in html
            # CPF/CNPJ must not appear publicly
            assert cpf(223456789).encode() not in html
            user2=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            status,html=get(user2,base,'/pj/entrar',{'cpf':cpf(223456789),'senha':'Senha-de-teste-2026'})
            status,html=get(user2,base,f'/pj/sindico?org={org}');assert status==403,(status,html[:400])
            # Provider non-admin cannot review
            op_tec=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            status,html=get(op_tec,base,'/login',{'email':'operador@teste.local','senha':'Senha-de-teste-2026'})
            status,html=get(op_tec,base,'/chamados');assert status==403
            opa=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            status,html=get(opa,base,'/login',{'email':'admin@teste.local','senha':'Senha-de-teste-2026'})
            status,html=get(opa,base,'/chamados');assert status==200 and b'An' in html
            status,html=get(opa,base,'/organizacoes');assert status==200
            # PDF no longer contains raw logs
            with ext.db(db) as c:
                c.execute("UPDATE ordens_servico SET status='Concluída' WHERE id=?",(oid,))
                c.execute("INSERT INTO os_encerramentos(os_id,situacao,relatorio,ator,encerrado_em) VALUES(?,?,?,?,?)",
                         (oid,'Concluída','Manutenção efetuada','Operador',ext.agora()))
            cad.salvar_detalhes(db,oid,'Falha no módulo','Conexões reparadas','Portão testado')
            path=ext.gerar_pdf(db,oid)
            if os.getenv('AUTOSEG_PDF_EXEMPLO'):shutil.copyfile(path,os.getenv('AUTOSEG_PDF_EXEMPLO'))
            assert Path(path).read_bytes()[:5]==b'%PDF-'
            try:
                from pypdf import PdfReader
            except ImportError:
                print('INFO: para verificar o texto completo do PDF instale pypdf no ambiente de testes.')
            else:
                txt='\n'.join(p.extract_text() for p in PdfReader(path).pages)
                assert 'Conexões reparadas' in txt
                assert 'HISTÓRICO DE ATIVIDADES' not in txt
            print('PASSOU: PJ, síndico, administração, OS autorizada, PDF cliente e permissões v9')
        finally:portal.parar()

if __name__=='__main__':main()
