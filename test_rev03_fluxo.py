"""Regressão REV03: cadastro e OS no mesmo POST, sem poderes administrativos automáticos."""
import tempfile
import unittest
from pathlib import Path
import sqlite3
import json
from banco import criar_banco
import cadastros_v9 as cad
import prestadores_ext as ext
import atendimento_os as aten
import catalogo_servicos as catalogo


class Rev03Test(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='autoseg_rev03_')
        self.db=str(Path(self.tmp.name)/'teste.db')
        criar_banco(self.db);ext.instalar(self.db);aten.instalar(self.db);cad.instalar(self.db);catalogo.instalar(self.db)
        self.uid=cad.cadastrar_usuario(self.db,'Usuário de Teste','52998224725','51999999999','senha-bem-longa-2026')
        self.form={'nome':'Residencial Aurora Fictício','tipo':'Condomínio','cnpj':'','cidade':'Porto Alegre',
                   'bairro':'Centro','endereco':'Rua das Flores 123','telefone':'(51) 99999-0000',
                   'papel':'Morador','unidade':'Apartamento 201','descricao':'Portão não abre pelo controle remoto.',
                   'urgencia':'Normal','solicitante_nome':'Usuário de Teste','solicitante_telefone':'51999998888'}
    def tearDown(self):self.tmp.cleanup()

    def test_acao_unica_cadastra_cliente_organizacao_e_os(self):
        res=cad.criar_organizacao_e_os(self.db,self.uid,self.form)
        with ext.db(self.db) as c:
            cl=c.execute('SELECT * FROM clientes WHERE id=?',(res['cliente_id'],)).fetchone()
            org=c.execute('SELECT * FROM v9_organizacoes WHERE id=?',(res['organizacao_id'],)).fetchone()
            ch=c.execute('SELECT * FROM v9_chamados WHERE id=?',(res['chamado_id'],)).fetchone()
            os_=c.execute('SELECT * FROM ordens_servico WHERE id=?',(res['os_id'],)).fetchone()
            self.assertEqual(cl['status'],'Ativo')
            self.assertEqual(cl['telefone'],'51999990000')
            self.assertEqual(org['cliente_id'],cl['id'])
            self.assertEqual(org['situacao'],'Cadastrado')
            self.assertEqual(org['telefone'],cl['telefone'])
            self.assertEqual(ch['os_id'],os_['id'])
            self.assertEqual(os_['cliente_id'],cl['id'])
            self.assertEqual(os_['status'],'Aberta')
            self.assertEqual(len(cad.listar_os_organizacao(self.db,res['organizacao_id'],self.uid)['os']) if cad.responsavel_ativo(c,self.uid,org['id']) else 0,0)
            self.assertIsNone(cad.responsavel_ativo(c,self.uid,org['id']))

    def test_rejeita_telefone_ruim_sem_salvar(self):
        self.form['telefone']='123'
        with self.assertRaises(ValueError):cad.criar_organizacao_e_os(self.db,self.uid,self.form)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM clientes').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM v9_organizacoes').fetchone()[0],0)

    def test_sem_duplicidade_repeticao_nao_cria_outra_os(self):
        cad.criar_organizacao_e_os(self.db,self.uid,self.form)
        with self.assertRaises(ValueError):cad.criar_organizacao_e_os(self.db,self.uid,self.form)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM clientes').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ordens_servico').fetchone()[0],1)

    def test_usuario_nao_ganha_acesso_geral(self):
        r=cad.criar_organizacao_e_os(self.db,self.uid,self.form)
        with self.assertRaises(PermissionError):cad.listar_os_organizacao(self.db,r['organizacao_id'],self.uid)
        cad.atribuir_responsavel(self.db,r['organizacao_id'],self.uid,'Prestador autorizado')
        itens=cad.listar_os_organizacao(self.db,r['organizacao_id'],self.uid)
        self.assertEqual(len(itens['os']),1)
        cad.remover_responsavel(self.db,r['organizacao_id'],'Prestador autorizado')
        with self.assertRaises(PermissionError):cad.listar_os_organizacao(self.db,r['organizacao_id'],self.uid)

    def test_catalogo_valores_e_pdf(self):
        sid=catalogo.salvar(self.db,{'nome':'Manutenção de Portão','descricao':'Inspeção e ajuste',
            'preco_servico':'200,50','materiais':'Sensor teste | 2 | 30,25',
            'relatorio_padrao':'Inspecionado, ajustado e testado.'})
        res=catalogo.valores_orcamento(self.db,sid,3)
        self.assertEqual(res['total'],3*(20050+6050))
        self.assertEqual(res['servico']['relatorio_padrao'],'Inspecionado, ajustado e testado.')
        pdf=catalogo.pdf_orcamento(self.db,sid,3,'Usuário de Teste')
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertGreater(len(pdf),1500)

    def test_catalogo_nao_confia_em_precos_do_cliente(self):
        sid=catalogo.salvar(self.db,{'nome':'Manutenção de Portão','preco_servico':'100','materiais':''})
        with self.assertRaises(ValueError):catalogo.valores_orcamento(self.db,sid,100000)
        catalogo.arquivar(self.db,sid)
        with self.assertRaises(ValueError):catalogo.valores_orcamento(self.db,sid,1)

    def test_formato_documento(self):
        self.assertEqual(cad.formatar_documento('52998224725'),'529.982.247-25')
        self.assertEqual(cad.formatar_documento('11222333000181'),'11.222.333/0001-81')


if __name__=='__main__':unittest.main(verbosity=2)
