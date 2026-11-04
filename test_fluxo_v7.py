"""Teste de regressão v7 (banco temporário, servidor localhost)."""
import http.cookiejar, tempfile, types, sys, urllib.request
from pathlib import Path
from test_portal_v4 import schema
from test_fluxo_v6 import navegar, token
import prestadores_ext as ext
import atendimento_os as aten
import fluxo_os as fluxo
from portal_prestador import PortalPrestador


def main():
    with tempfile.TemporaryDirectory(prefix='autosseg_v7_') as tmp:
        p=Path(tmp); banco=str(p/'teste.db')
        ext.RELATORIOS=p/'relatorios';ext.ANEXOS=p/'anexos';ext.RASCUNHOS=p/'rascunhos'
        for item in (ext.RELATORIOS,ext.ANEXOS,ext.RASCUNHOS):item.mkdir()
        schema(banco)
        fake=types.ModuleType('banco')
        fake.proximo_numero_os=lambda cursor:f"OS-{cursor.execute('SELECT COALESCE(MAX(id),0)+1 FROM ordens_servico').fetchone()[0]:03d}"
        sys.modules['banco']=fake
        ext.instalar(banco);fluxo.instalar(banco);aten.instalar(banco)
        pid=ext.cadastrar(banco,'João','joao@example.com','senha-bem-segura-2026')
        portal=PortalPrestador(banco,'127.0.0.1',0);portal.iniciar()
        base=f'http://127.0.0.1:{portal.servidor.server_port}'
        opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            st,html,_=navegar(opener,base,'/login',{'email':'joao@example.com','senha':'senha-bem-segura-2026'})
            assert st==200
            csrf=token(html)
            st,html,_=navegar(opener,base,'/os/1')
            assert st==200 and b'INICIAR OS' in html and b'Solicita' in html
            # Iniciar já assume automaticamente, sem etapa de assunção separada.
            st,_,_=navegar(opener,base,'/os/1/iniciar',{'csrf':csrf})
            assert st==200
            st,_,_=navegar(opener,base,'/os/1/iniciar',{'csrf':csrf})
            assert st==200
            with ext.db(banco) as c:
                assert c.execute('SELECT COUNT(*) FROM os_eventos WHERE os_id=1 AND acao="Atendimento iniciado"').fetchone()[0]==1
                assert c.execute('SELECT status FROM ordens_servico WHERE id=1').fetchone()[0]=='Iniciada'
                original=c.execute('SELECT descricao_original FROM os_solicitacoes WHERE os_id=1').fetchone()[0]
                assert original
            st,html,_=navegar(opener,base,'/')
            assert st==200 and b'OS iniciadas' in html
            st,html,_=navegar(opener,base,'/os')
            assert st==200 and b'Iniciada' in html
            body={'csrf':csrf,'cliente_id':'1','descricao':'TEXTO MALICIOSO',
                'tecnico':'Atendente','forma_pagamento':'PIX','observacoes':'Anotação nova',
                'valor_mao_obra':'100','valor_materiais_manual':'0','relatorio_tecnico':'Teste de rascunho persistente',
                'modo_envio':'salvar','acao_status':'Concluída'}
            st,html,_=navegar(opener,base,'/os/1/salvar',body)
            assert st==200,(st,html[-800:])
            st,html,_=navegar(opener,base,'/os/1')
            assert b'Teste de rascunho persistente' in html
            with ext.db(banco) as c:
                assert c.execute('SELECT status FROM ordens_servico WHERE id=1').fetchone()[0]=='Iniciada'
                assert c.execute('SELECT descricao FROM ordens_servico WHERE id=1').fetchone()[0]==original
                assert c.execute('SELECT rascunho FROM os_atendimentos WHERE os_id=1').fetchone()[0]=='Teste de rascunho persistente'
            # Encerra via portal e baixa o PDF publicado.
            body.update({'descricao':original,'modo_envio':'encerrar','acao_status':'Concluída','sem_nota_fiscal':'1'})
            st,html,_=navegar(opener,base,'/os/1/salvar',body)
            assert st==200,(st,html[-800:])
            st,pdf,_=navegar(opener,base,'/os/1/pdf')
            assert st==200 and pdf[:5]==b'%PDF-'
            with ext.db(banco) as c:
                assert c.execute('SELECT COUNT(*) FROM os_documentos WHERE os_id=1').fetchone()[0]==1
            print('PASSOU: atribuição, início idempotente, solicitação imutável, rascunho, encerramento e PDF pelo site')
        finally:portal.parar()
if __name__=='__main__':main()
