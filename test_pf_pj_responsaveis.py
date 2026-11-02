"""PF/PJ: permissões negativas e histórico completo, sempre SQLite temporário."""
import tempfile
import unittest
from pathlib import Path

from banco import criar_banco, proximo_numero_os
import atendimento_os
import fluxo_os
import cadastros_v9 as cad
import prestadores_ext as ext
import portal_v9
import portal_cliente_v94
from CRIAR_CADASTROS_FICTICIOS_DEV import cpf_ficticio, cnpj_ficticio


class PF_PJ(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='autosseg_pf_pj_')
        self.db=str(Path(self.tmp.name)/'base.db')
        criar_banco(self.db);ext.instalar(self.db);fluxo_os.instalar(self.db)
        atendimento_os.instalar(self.db);cad.instalar(self.db)
        self.pfs=[]
        for nome,base in (('Pessoa Responsável A','987611120'),('Pessoa Moradora B','987611121'),
                          ('Pessoa Gestora C','987611122')):
            cpf=cpf_ficticio(base)
            self.pfs.append(cad.cadastrar_usuario(self.db,nome,cpf,'51999999999','TESTE-SEGURANCA-12345'))
        self.orgs=[];self.cids=[]
        for nome,tipo,base in (('Condomínio A','Condomínio','976620110001'),
                               ('Empresa B','Empresa','976620110002')):
            doc=cnpj_ficticio(base)
            with ext.db(self.db) as c:
                cid=c.execute('''INSERT INTO clientes(nome,tipo_pessoa,documento,status)
                       VALUES(?,'Jurídica',?,'Ativo')''',(nome,doc)).lastrowid
                org=cad.sincronizar_cliente_pj(c,cid)
                c.execute('UPDATE v9_organizacoes SET tipo=?,situacao=? WHERE id=?',
                          (tipo,'Validado',org))
            self.orgs.append(org);self.cids.append(cid)
        with ext.db(self.db) as c:
            for index,desc in ((0,'OS do prestador no condomínio A'),(1,'OS da empresa B')):
                c.execute('''INSERT INTO ordens_servico(numero_os,cliente_id,descricao,status,data_abertura)
                             VALUES(?,?,?,'Aberta',?)''',
                          (proximo_numero_os(c.cursor()),self.cids[index],desc,ext.agora()))
        self.ids=[]
        with ext.db(self.db) as c:
            self.ids=[r['id'] for r in c.execute('SELECT id FROM ordens_servico ORDER BY id')]

    def tearDown(self):self.tmp.cleanup()

    def test_pf_so_recebe_acesso_apos_nomeacao_explicita(self):
        a,b=self.orgs;gestor,morador,_=self.pfs
        with self.assertRaises(PermissionError):cad.listar_os_organizacao(self.db,a,gestor)
        vid=cad.solicitar_vinculo(self.db,morador,a,'Síndico')
        with ext.db(self.db) as c:
            vinc=c.execute('SELECT id FROM v9_vinculos WHERE usuario_id=? AND organizacao_id=?',(morador,a)).fetchone()['id']
        with self.assertRaisesRegex(ValueError,'Nomear responsável'):
            cad.alterar_vinculo(self.db,vinc,True,'Prestador')
        with ext.db(self.db) as c:
            c.execute("UPDATE v9_vinculos SET situacao='Aprovado' WHERE id=?",(vinc,))
        self.assertFalse(cad.vinculo_aprovado(self.db,morador,a,('Síndico','Administrador')))
        with self.assertRaises(PermissionError):cad.listar_os_organizacao(self.db,a,morador)
        self.assertEqual(cad.atribuir_responsavel(self.db,a,gestor,'Prestador autenticado'),'Síndico')
        self.assertTrue(cad.vinculo_aprovado(self.db,gestor,a,('Síndico','Administrador')))
        self.assertEqual(len(cad.listar_os_organizacao(self.db,a,gestor)['os']),1)

    def test_os_de_morador_e_prestador_sao_visiveis_ao_sindico(self):
        org=self.orgs[0];sindico,morador,_=self.pfs
        cad.atribuir_responsavel(self.db,org,sindico,'desktop')
        cad.registrar_chamado(self.db,morador,org,'Portão de entrada apresentou defeito em teste.',
                             'Normal','Apto 203','Morador','Pessoa Teste','51999998888')
        regs=cad.listar_os_organizacao(self.db,org,sindico)['os']
        self.assertEqual(len(regs),2)
        self.assertTrue(any('prestador' in x['descricao'] for x in regs))
        self.assertTrue(any(x['solicitante']=='Pessoa Moradora B' for x in regs))
        self.assertTrue(all(x['status'] in ('Aberta','Pendente') for x in regs))
        with self.assertRaises(PermissionError):cad.listar_os_organizacao(self.db,org,morador)

    def test_empresa_funciona_com_mesma_regra_e_bloqueia_acesso_cruzado(self):
        a,b=self.orgs;gestor,morador,gestora=self.pfs
        self.assertEqual(cad.atribuir_responsavel(self.db,b,gestora,'desktop'),'Gestor')
        self.assertEqual(len(cad.listar_os_organizacao(self.db,b,gestora)['os']),1)
        with self.assertRaises(PermissionError):cad.listar_os_organizacao(self.db,a,gestora)
        with self.assertRaises(PermissionError):cad.autorizar_pdf_os_organizacao(self.db,a,gestora,self.ids[0])
        with self.assertRaises(PermissionError):cad.autorizar_pdf_os_organizacao(self.db,b,gestora,self.ids[0])
        self.assertTrue(cad.autorizar_pdf_os_organizacao(self.db,b,gestora,self.ids[1]))

    def test_trocar_ou_revogar_sindico_revoga_acesso_imediatamente(self):
        org=self.orgs[0];antigo,novo,_=self.pfs
        cad.atribuir_responsavel(self.db,org,antigo,'desktop')
        cad.atribuir_responsavel(self.db,org,novo,'desktop')
        with self.assertRaises(PermissionError):cad.listar_os_organizacao(self.db,org,antigo)
        self.assertEqual(len(cad.listar_os_organizacao(self.db,org,novo)['os']),1)
        cad.remover_responsavel(self.db,org,'desktop')
        with self.assertRaises(PermissionError):cad.listar_os_organizacao(self.db,org,novo)
        with ext.db(self.db) as c:
            hist=[r['acao'] for r in c.execute('SELECT acao FROM v9_historico_clientes')]
        self.assertIn('Responsável nomeado',hist)
        self.assertIn('Responsável removido',hist)

    def test_impede_os_alheia_em_cadastro_legado_ambiguo(self):
        org=self.orgs[0];uid=self.pfs[0]
        cad.atribuir_responsavel(self.db,org,uid,'desktop')
        with ext.db(self.db) as c:
            c.execute('''INSERT INTO v9_organizacoes(cliente_id,nome,tipo,criado_em)
                         VALUES(?,'Duplicado legado','Condomínio',?)''',(self.cids[0],ext.agora()))
        dados=cad.listar_os_organizacao(self.db,org,uid)
        self.assertTrue(dados['cadastro_ambiguo'])
        self.assertEqual(dados['os'],[])
        with self.assertRaises(PermissionError):cad.autorizar_pdf_os_organizacao(self.db,org,uid,self.ids[0])

    def test_empresa_associada_ao_cnpj_errado_nao_expoe_os(self):
        org=self.orgs[0];uid=self.pfs[0]
        cad.atribuir_responsavel(self.db,org,uid,'desktop')
        with ext.db(self.db) as c:
            c.execute('UPDATE v9_organizacoes SET cnpj=? WHERE id=?',
                      (cnpj_ficticio('975510450011'),org))
        dados=cad.listar_os_organizacao(self.db,org,uid)
        self.assertTrue(dados['cadastro_ambiguo'])
        self.assertFalse(dados['os'])

    def test_portal_prestador_tem_pagina_de_nomeacao_e_cliente_nao_tem_form(self):
        class H:
            path='/organizacoes/responsaveis'
            def responder(self,html,status=200):self.html=html;self.status=status
            def redir(self,url):self.destino=url
        h=H()
        portal_v9.get(h,'/organizacoes/responsaveis',self.db,{'csrf':'teste','nome':'Prestador','pid':1})
        self.assertIn('/organizacoes/responsavel/atribuir',h.html)
        self.assertIn('Pessoa física com login CPF ativo',h.html)
        self.assertNotIn('senha_hash',h.html)
        with self.assertRaises(PermissionError):
            portal_v9.post(h,'/organizacoes/responsavel/atribuir',
                           {'csrf':'errado','org_id':str(self.orgs[0]),'usuario_id':str(self.pfs[0])},
                           self.db,{'csrf':'teste','nome':'Prestador'})

    def test_cadastro_pf_prestador_redefinicao_senha(self):
        pid=ext.cadastrar(self.db,'Prestador Fictício','prestador-ficticio@example.invalid',
                           'Senha-Original-2026')
        self.assertIsNotNone(ext.autenticar(self.db,'prestador-ficticio@example.invalid','Senha-Original-2026'))
        ext.redefinir_senha_prestador_desktop(self.db,pid,'Senha-Nova-2026-Segura')
        self.assertIsNone(ext.autenticar(self.db,'prestador-ficticio@example.invalid','Senha-Original-2026'))
        self.assertIsNotNone(ext.autenticar(self.db,'prestador-ficticio@example.invalid','Senha-Nova-2026-Segura'))


if __name__=='__main__':unittest.main(verbosity=2)
