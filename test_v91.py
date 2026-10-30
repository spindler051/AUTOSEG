"""Testes de regressão v9.1 com banco fictício, sem dados do usuário."""
import os,sys,tempfile,types,re,io,shutil
from pathlib import Path
import urllib.request,urllib.error,urllib.parse,http.cookiejar
from PIL import Image
from test_portal_v4 import schema
from test_v9 import cpf,cnpj,csrf
import prestadores_ext as ext
import cadastros_v9 as cad
import fluxo_os,atendimento_os
from portal_prestador import PortalPrestador

def visit(client,base,path,d=None):
    request=urllib.request.Request(base+path,urllib.parse.urlencode(d).encode() if d is not None else None)
    try:
        with client.open(request,timeout=10) as r:return r.status,r.read().decode('utf-8','replace')
    except urllib.error.HTTPError as e:return e.code,e.read().decode('utf-8','replace')

def main():
  with tempfile.TemporaryDirectory() as td:
    td=Path(td); db=str(td/'test.db')
    ext.RELATORIOS=td/'relatorios';ext.ANEXOS=td/'anexos';ext.RASCUNHOS=td/'rascunhos'
    for x in (ext.RELATORIOS,ext.ANEXOS,ext.RASCUNHOS):x.mkdir()
    schema(db)
    with ext.db(db) as c:
        c.execute("UPDATE clientes SET documento=?,sindico_nome='Maria Síndica',sindico_telefone='51987654321' WHERE id=1",(cnpj(),))
    m=types.ModuleType('banco');m.proximo_numero_os=lambda cu: 'OS-'+str(cu.execute('SELECT COALESCE(MAX(id),0)+1 FROM ordens_servico').fetchone()[0]).zfill(4)
    sys.modules['banco']=m
    ext.instalar(db);fluxo_os.instalar(db);atendimento_os.instalar(db);cad.instalar(db)
    with ext.db(db) as c:
        org=c.execute('SELECT * FROM v9_organizacoes').fetchone()
        assert org['sindico_telefone']=='51987654321'
        orgid=org['id']
    u=cad.cadastrar_usuario(db,'Pessoa Física',cpf(456789123),'51999999999','Senhaforte-2026')
    assert cad.autenticar(db,cpf(456789123),'Senhaforte-2026')['id']==u
    ch=cad.registrar_chamado(db,u,orgid,'Meu interfone parou de funcionar','Normal','Apt 203')
    with ext.db(db) as c:
        assert c.execute('SELECT COUNT(*) FROM v9_vinculos WHERE usuario_id=?',(u,)).fetchone()[0]==0
    link,destino=cad.url_whatsapp(db,ch,'https://teste.trycloudflare.com')
    assert 'wa.me/5551987654321' in link and 'org%3D' in link and 'teste.trycloudflare.com' in link
    cad.atualizar_sindico(db,orgid,'', '', 'Teste')
    link,destino=cad.url_whatsapp(db,ch)
    assert 'wa.me/5551992692007' in link
    cad.atualizar_sindico(db,orgid,'Maria','51987654321','Teste')
    provider_id=ext.cadastrar(db,'Técnico de Teste','tec@teste.local','Senhaforte-2026')
    portal=PortalPrestador(db,'127.0.0.1',0);portal.iniciar()
    base='http://127.0.0.1:'+str(portal.servidor.server_port)
    try:
        pf=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        st,html=visit(pf,base,'/pj/cadastro');assert st==200 and 'Repita sua senha' in html
        st,html=visit(pf,base,'/pj/entrar',{'cpf':cpf(456789123),'senha':'Senhaforte-2026'});assert st==200
        st,html=visit(pf,base,'/pj/organizacoes?q='+cnpj())
        assert st==200 and 'Condomínio Alfa' in html
        # The CNPJ typed by the requester can remain in the query field, but never displayed in the results rows.
        res=html.split('Resultados — sem documentos pessoais ou CNPJ')[-1]
        assert cnpj() not in res
        st,html=visit(pf,base,'/pj/chamado/novo?org='+str(orgid));assert st==200 and 'Enviar chamado' in html
        csrfpf=re.search('name="csrf" value="([^"]+)"',html).group(1)
        st,html=visit(pf,base,'/pj/chamado/novo',{'csrf':csrfpf,'org_id':orgid,'descricao':'Há um vazamento no hall do bloco','urgencia':'Alta'})
        assert st==200 and 'Minha conta' in html
        with ext.db(db) as c:assert c.execute('SELECT COUNT(*) FROM v9_chamados WHERE usuario_id=?',(u,)).fetchone()[0]==2
        staff=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        st,html=visit(staff,base,'/login',{'email':'tec@teste.local','senha':'Senhaforte-2026'});assert st==200
        assert 'Clientes' in html and 'Financeiro' in html and 'Notas fiscais' in html and 'Prestadores' not in html
        assert 'Acionamento PJ' not in html
        for path in ('/clientes','/financeiro','/emails','/notas','/os/nova','/chamados','/organizacoes'):
            st,page=visit(staff,base,path);assert st==200,(path,st,page[-450:])
        # Creates and closes an OS with photo, then verifies new client PDF embeds image by default.
        cad.analisar(db,ch,'AUTOSEG','Aguardando síndico')
        cad.confirmar(db,ch,'Síndico confirmado por WhatsApp',True)
        oid=cad.gerar_os(db,ch,'AUTOSEG')
        with ext.db(db) as c:
            img=Image.new('RGB',(120,80),(200,30,30));buff=io.BytesIO();img.save(buff,'PNG')
            aid=ext.registrar_imagem_transacao(c,oid,provider_id,'registro.png',buff.getvalue(),permitir_colaboracao=True)
            c.execute("UPDATE ordens_servico SET status='Concluída' WHERE id=?",(oid,))
            c.execute("INSERT INTO os_encerramentos(os_id,situacao,relatorio,ator,encerrado_em) VALUES(?,?,?,?,?)",(oid,'Concluída','Serviço finalizado','Técnico',ext.agora()))
        from pypdf import PdfReader
        pdf=Path(ext.gerar_pdf(db,oid))
        if os.environ.get('AUTOSEG_PDF_EXEMPLO'):shutil.copy2(pdf,os.environ['AUTOSEG_PDF_EXEMPLO'])
        pages=PdfReader(pdf).pages
        count=0
        for page in pages:
            imgs=page.images
            count+=len(imgs)
        assert count>=1, f'Foto não foi incluída no PDF: {count} imagens'
        print('PASSOU v9.1: PF CPF/senha, busca CNPJ privativa, chamado sem vínculo, WhatsApp síndico/fallback, prestador completo, foto PDF')
    finally:portal.parar()

if __name__=='__main__':main()
