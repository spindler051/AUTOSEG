"""Testes locais e isolados. NUNCA utiliza o banco real do usuário."""
import http.cookiejar
import os
import re
import tempfile
import time
import unittest
import urllib.request
import urllib.parse
from pathlib import Path

from flavors.autoseg.modules import meu_auto_financeiro as maf
from officina.core import prestadores_ext as ext
from officina.core import produtividade_os as prod
from officina.core import fluxo_os
from officina.core.banco import criar_banco
from flavors.autoseg.modules.portal_prestador import PortalPrestador

os.environ['AUTOSEG_GMAIL_DESATIVADO']='1'

PDF_FICTICIO=b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n'


class Resposta:
    def __init__(self):self.path=None;self.cookie=None
    def redir(self,path,cookie=None):
        self.path=path;self.cookie=cookie
        return path


class FinanceiroTeste(unittest.TestCase):
    def setUp(self):
        self.pasta=tempfile.TemporaryDirectory(prefix='maf_teste_')
        self.addCleanup(self.pasta.cleanup)
        self.tmp=Path(self.pasta.name)
        self.original_db,self.original_docs=maf.DB,maf.DOCS
        self.original_base=ext.BASE
        maf.DB=self.tmp/'financeiro.db';maf.DOCS=self.tmp/'comprovantes'
        ext.BASE=self.tmp
        self.addCleanup(self.restaurar)
        maf.instalar()
        self.autoseg=self.tmp/'autoseg.db'
        criar_banco(str(self.autoseg))
        ext.instalar(str(self.autoseg))
        fluxo_os.instalar(str(self.autoseg))
        prod.instalar(str(self.autoseg))
        self.pid=ext.cadastrar(str(self.autoseg),'Técnico A','a@example.org','senha-segura-integra-1')
        self.pid_b=ext.cadastrar(str(self.autoseg),'Técnico B','b@example.org','senha-segura-integra-2')
        self.prestador={'pid':self.pid,'nome':'Técnico A','csrf':'token-csrf'}
        self.handler=Resposta()

    def restaurar(self):
        maf.DB,maf.DOCS= self.original_db,self.original_docs
        ext.BASE=self.original_base
        maf.SESSOES.clear()

    def acao(self,path,prestador=None,**dados):
        d={'csrf':'token-csrf',**dados}
        return maf.POST(self.handler,'/auto-financeiro/'+path,prestador or self.prestador,str(self.autoseg),d)

    def carregar(self):return maf.usuario_prestador(self.pid,'Técnico A')

    def os_ficticia(self):
        with ext.db(str(self.autoseg)) as c:
            c.execute("INSERT INTO clientes(nome) VALUES('Cliente fictício')")
            c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status) VALUES('OS-TESTE',1,'Concluída')")
            c.execute("INSERT INTO os_encerramentos(os_id,situacao,ator,prestador_id,encerrado_em) VALUES(1,'Concluída','Técnico',?,'2026-11-04')",(self.pid,))
            c.execute("INSERT INTO financeiro(os_id,cliente_id,valor,status) VALUES(1,1,1200,'Aguardando pagamento')")
            c.execute("INSERT INTO produtividade_rateios(os_id,tecnico_id,valor_centavos,definidor_id,registrado_em) VALUES(1,?,40000,?,'agora')",(self.pid_b,self.pid))
            c.execute("INSERT INTO produtividade_repasses(os_id,tecnico_id,pago_centavos,atualizado_em) VALUES(1,?,0,'agora')",(self.pid_b,))

    def test_conciliacao_com_valor_zero_nao_falha(self):
        self.assertEqual(maf.centavos(0), 0)
        self.assertEqual(maf.centavos(0.0), 0)
        self.os_ficticia()
        with ext.db(str(self.autoseg)) as c:
            c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status) "
                      "VALUES('OS-ZERO',1,'Concluída')")
            c.execute("INSERT INTO os_encerramentos(os_id,situacao,ator,prestador_id,"
                      "encerrado_em) VALUES(2,'Concluída','Técnico',?,'2026-11-04')",
                      (self.pid,))
            c.execute("INSERT INTO financeiro(os_id,cliente_id,valor,status) "
                      "VALUES(2,1,0,'Recebido')")
        u = self.carregar()
        self.assertEqual(maf.reconciliar_autoseg(str(self.autoseg), u), 0)
        with ext.db(str(self.autoseg)) as c:
            c.execute("UPDATE financeiro SET status='Recebido' WHERE os_id=1")
        self.assertEqual(maf.reconciliar_autoseg(str(self.autoseg), u), 1)
        with maf.conn() as c:
            self.assertEqual(maf.saldo(c, u['id']), 80000)

    def test_recebido_autoseg_sem_duplicacao_e_rateio(self):
        self.os_ficticia()
        u=self.carregar();ub=maf.usuario_prestador(self.pid_b,'Técnico B')
        self.assertEqual(maf.reconciliar_autoseg(str(self.autoseg),u),0)
        with maf.conn() as c:self.assertEqual(maf.saldo(c,u['id']),0)
        with ext.db(str(self.autoseg)) as c:c.execute("UPDATE financeiro SET status='Recebido' WHERE os_id=1")
        self.assertEqual(maf.reconciliar_autoseg(str(self.autoseg),u),1)
        self.assertEqual(maf.reconciliar_autoseg(str(self.autoseg),u),0)
        with maf.conn() as c:self.assertEqual(maf.saldo(c,u['id']),80000)
        with ext.db(str(self.autoseg)) as c:c.execute("UPDATE produtividade_repasses SET pago_centavos=15000 WHERE os_id=1 AND tecnico_id=?",(self.pid_b,))
        maf.reconciliar_autoseg(str(self.autoseg),ub)
        maf.reconciliar_autoseg(str(self.autoseg),ub)
        with maf.conn() as c:self.assertEqual(maf.saldo(c,ub['id']),15000)
        with ext.db(str(self.autoseg)) as c:c.execute("UPDATE produtividade_repasses SET pago_centavos=40000 WHERE os_id=1 AND tecnico_id=?",(self.pid_b,))
        maf.reconciliar_autoseg(str(self.autoseg),ub)
        with maf.conn() as c:self.assertEqual(maf.saldo(c,ub['id']),40000)
        # Mesmo se o valor cair e voltar (correção), o delta não pode desaparecer.
        with ext.db(str(self.autoseg)) as c:c.execute("UPDATE produtividade_repasses SET pago_centavos=15000 WHERE os_id=1 AND tecnico_id=?",(self.pid_b,))
        maf.reconciliar_autoseg(str(self.autoseg),ub)
        with ext.db(str(self.autoseg)) as c:c.execute("UPDATE produtividade_repasses SET pago_centavos=40000 WHERE os_id=1 AND tecnico_id=?",(self.pid_b,))
        maf.reconciliar_autoseg(str(self.autoseg),ub)
        with maf.conn() as c:self.assertEqual(maf.saldo(c,ub['id']),40000)

    def test_saldo_negativo_salario_manual_e_familia(self):
        u=self.carregar()
        self.acao('movimento',descricao='Despesa pessoal',valor='50,00',tipo='despesa')
        with maf.conn() as c:self.assertEqual(maf.saldo(c,u['id']),-5000)
        self.acao('familia/criar',nome='Família Teste')
        self.acao('familia/convidar')
        with maf.conn() as c:
            convite=c.execute('SELECT codigo FROM convites').fetchone()[0]
            familia_id=c.execute('SELECT familia_id FROM usuarios WHERE id=?',(u['id'],)).fetchone()[0]
        self.assertTrue(familia_id)
        maf._post_login(self.handler,'/auto-financeiro/cadastro',{'codigo':convite,'nome':'Pessoa B','email':'pessoa@example.org','senha':'senha-segura-123'})
        with maf.conn() as c:
            pessoa=dict(c.execute('SELECT * FROM usuarios WHERE email=?',('pessoa@example.org',)).fetchone())
            self.assertEqual(pessoa['familia_id'],familia_id)
        # Usar sessão individual do familiar, sem autenticação AUTOSEG
        maf.SESSOES['token_teste']={'uid':pessoa['id'],'csrf':'familiar-csrf','exp':time.time()+3600}
        from http.cookies import SimpleCookie
        class HandlerFamiliar(Resposta):
            def __init__(self):
                super().__init__()
                self.headers={'Cookie':'maf_session=token_teste'}
        h=HandlerFamiliar()
        maf.POST(h,'/auto-financeiro/salario/novo',None,str(self.autoseg),
                 {'csrf':'familiar-csrf','descricao':'Salário','dia':'5','valor':'3000,00'})
        with maf.conn() as c:self.assertEqual(maf.saldo(c,pessoa['id']),0)
        maf.POST(h,'/auto-financeiro/salario/confirmar',None,str(self.autoseg),
                 {'csrf':'familiar-csrf','id':'1'})
        maf.POST(h,'/auto-financeiro/salario/confirmar',None,str(self.autoseg),
                 {'csrf':'familiar-csrf','id':'1'})
        with maf.conn() as c:self.assertEqual(maf.saldo(c,pessoa['id']),300000)
        # Impede sair em empréstimo ativo, preserva saldo recebido.
        self.acao('emprestimo/criar',devedor=str(pessoa['id']),valor='100,00')
        with maf.conn() as c:lid=c.execute('SELECT id FROM emprestimos').fetchone()[0]
        self.acao(f'emprestimo/{lid}/enviar',comprovante=('pix.pdf',PDF_FICTICIO))
        with self.assertRaises(ValueError):
            maf.POST(h,'/auto-financeiro/familia/sair',None,str(self.autoseg),{'csrf':'familiar-csrf'})
        # A remoção administrativa mantém o empréstimo e os saldos do familiar.
        self.acao('familia/remover',uid=str(pessoa['id']),motivo='Saída administrativa solicitada')
        with maf.conn() as c:
            x=c.execute('SELECT familia_id FROM usuarios WHERE id=?',(pessoa['id'],)).fetchone()
            self.assertIsNone(x['familia_id'])
            self.assertEqual(maf.saldo(c,pessoa['id']),310000)

    def test_conta_compartilhada_contribuicao_nao_duplica(self):
        u=self.carregar()
        self.acao('familia/criar',nome='Família Compartilhada')
        with maf.conn() as c:
            f=c.execute('SELECT id FROM familias').fetchone()[0]
            c.execute('INSERT INTO usuarios(nome,email,senha_hash,familia_id,criado_em) VALUES(?,?,?,?,?)',
                ('Membro C','c@example.org',maf.senha_hash('senha-segura-abc'),f,maf.agora()))
            mid=c.execute('SELECT id FROM usuarios WHERE email=?',('c@example.org',)).fetchone()[0]
        self.acao('conta/criar',descricao='Energia',valor='200,00',vencimento='2026-11-30',
                  **{'participantes[]':[str(mid)],'divisao':'igual'})
        with maf.conn() as c:cid=c.execute('SELECT id FROM contas').fetchone()[0]
        self.acao(f'conta/{cid}/pagar',comprovante=('conta.pdf',PDF_FICTICIO))
        with maf.conn() as c:self.assertEqual(maf.saldo(c,u['id']),-20000)
        maf.SESSOES['token_c']={'uid':mid,'csrf':'csrf-c','exp':time.time()+3600}
        class HC(Resposta):
            def __init__(self):
                super().__init__(); self.headers={'Cookie':'maf_session=token_c'}
        h=HC()
        maf.POST(h,f'/auto-financeiro/conta/{cid}/enviar',None,str(self.autoseg),
                 {'csrf':'csrf-c','comprovante':('pix.pdf',PDF_FICTICIO)})
        self.acao(f'conta/{cid}/confirmar',uid=str(mid))
        with maf.conn() as c:
            self.assertEqual(maf.saldo(c,u['id']),-10000)
            self.assertEqual(maf.saldo(c,mid),-10000)
            self.assertEqual(maf.saldo(c,u['id'])+maf.saldo(c,mid),-20000)
        self.acao(f'conta/{cid}/cancelar',motivo='Conta de teste cancelada')
        with maf.conn() as c:
            x=c.execute('SELECT comprovante FROM cotas WHERE conta_id=? AND usuario_id=?',(cid,mid)).fetchone()
            self.assertTrue(x['comprovante'])

    def test_estorno_e_autorizacoes_familiares(self):
        u=self.carregar()
        self.acao('movimento',descricao='Compra fictícia',tipo='despesa',valor='45,00')
        with maf.conn() as c:
            mid=c.execute('SELECT id FROM movimentos WHERE usuario_id=?',(u['id'],)).fetchone()[0]
        self.acao('movimento/estornar',id=str(mid))
        with maf.conn() as c:self.assertEqual(maf.saldo(c,u['id']),0)
        with self.assertRaises(ValueError):self.acao('movimento/estornar',id=str(mid))
        self.acao('familia/criar',nome='Família Administrável')
        with maf.conn() as c:
            fid=c.execute('SELECT id FROM familias').fetchone()[0]
            c.execute('INSERT INTO usuarios(nome,email,senha_hash,familia_id,criado_em) VALUES(?,?,?,?,?)',
                ('Membro','membro@exemplo.org',maf.senha_hash('senha-segura-membro'),fid,maf.agora()))
            membro=c.execute('SELECT id FROM usuarios WHERE email=?',('membro@exemplo.org',)).fetchone()[0]
        maf.SESSOES['membro_teste']={'uid':membro,'csrf':'csrf-m','exp':time.time()+3600}
        class HM(Resposta):
            def __init__(self):
                super().__init__();self.headers={'Cookie':'maf_session=membro_teste'}
        h=HM()
        with self.assertRaises(PermissionError):
            maf.POST(h,'/auto-financeiro/familia/remover',None,str(self.autoseg),
                {'csrf':'csrf-m','uid':str(u['id']),'motivo':'não posso'})
        with self.assertRaises(PermissionError):
            maf.POST(h,'/auto-financeiro/salario/novo',None,str(self.autoseg),
                {'csrf':'falso','descricao':'Salário','valor':'200,00','dia':'10'})
        self.acao('familia/transferir',uid=str(membro))
        with maf.conn() as c:
            pedido=c.execute('SELECT id FROM transferencias_admin').fetchone()[0]
            self.assertEqual(c.execute('SELECT admin_id FROM familias').fetchone()[0],u['id'])
        maf.POST(h,'/auto-financeiro/familia/aceitar-admin',None,str(self.autoseg),
            {'csrf':'csrf-m','pedido_id':str(pedido)})
        with maf.conn() as c:
            self.assertEqual(c.execute('SELECT admin_id FROM familias').fetchone()[0],membro)
        self.acao('familia/sair')
        with maf.conn() as c:
            self.assertIsNone(c.execute('SELECT familia_id FROM usuarios WHERE id=?',(u['id'],)).fetchone()[0])

    def test_emprestimo_com_devolucoes_parciais(self):
        u=self.carregar()
        self.acao('familia/criar',nome='Família Empréstimo')
        with maf.conn() as c:
            fid=c.execute('SELECT id FROM familias').fetchone()[0]
            c.execute('INSERT INTO usuarios(nome,email,senha_hash,familia_id,criado_em) VALUES(?,?,?,?,?)',
                ('Pessoa D','d@exemplo.org',maf.senha_hash('senha-segura-pessoa'),fid,maf.agora()))
            m=c.execute('SELECT id FROM usuarios WHERE email=?',('d@exemplo.org',)).fetchone()[0]
        self.acao('emprestimo/criar',devedor=str(m),valor='200,00')
        with maf.conn() as c:lid=c.execute('SELECT id FROM emprestimos').fetchone()[0]
        self.acao(f'emprestimo/{lid}/enviar',comprovante=('pix.pdf',PDF_FICTICIO))
        maf.SESSOES['devedor']={'uid':m,'csrf':'csrf-d','exp':time.time()+3600}
        class HD(Resposta):
            def __init__(self):
                super().__init__();self.headers={'Cookie':'maf_session=devedor'}
        h=HD()
        maf.POST(h,f'/auto-financeiro/emprestimo/{lid}/devolver',None,str(self.autoseg),
            {'csrf':'csrf-d','valor':'80,00','comprovante':('devolucao.pdf',PDF_FICTICIO)})
        with maf.conn() as c:
            did=c.execute('SELECT id FROM devolucoes').fetchone()[0]
            # Não contabiliza devolução somente por upload.
            self.assertEqual(maf.saldo(c,u['id']),-20000)
            self.assertEqual(maf.saldo(c,m),20000)
        self.acao(f'emprestimo/{lid}/confirmar',devolucao=str(did))
        with maf.conn() as c:
            self.assertEqual(maf.saldo(c,u['id']),-12000)
            self.assertEqual(maf.saldo(c,m),12000)
            self.assertEqual(maf.saldo(c,u['id'])+maf.saldo(c,m),0)
        with self.assertRaises(ValueError):self.acao(f'emprestimo/{lid}/confirmar',devolucao=str(did))



if __name__=='__main__':
    import time
    unittest.main()
