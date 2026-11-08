"""Regressão REV04: modelos YAML, catálogo visual e estoque transacional."""
import json
import tempfile
import unittest
from pathlib import Path
from banco import criar_banco
import prestadores_ext as ext
import catalogo_servicos as cat
import estoque_materiais as est
import importacao_yaml as imp
import atendimento_os as aten
import fluxo_os as fluxo
import portal_negocios as neg


class Operacoes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='rev04_ops_')
        self.db=str(Path(self.tmp.name)/'teste.db')
        criar_banco(self.db);ext.instalar(self.db);aten.instalar(self.db);fluxo.instalar(self.db)
        cat.instalar(self.db);est.instalar(self.db)
        self.pid=ext.cadastrar(self.db,'Prestador de Teste','rev04@example.invalid','Senha-ficticia-2026')
        with ext.db(self.db) as c:
            self.cid=c.execute("INSERT INTO clientes(nome,tipo_pessoa,status) VALUES('Cliente fictício','Jurídica','Ativo')").lastrowid
    def tearDown(self):self.tmp.cleanup()

    def os_fake(self,numero='OS-0040',status='Aberta'):
        with ext.db(self.db) as c:
            return c.execute('INSERT INTO ordens_servico(numero_os,cliente_id,descricao,status,forma_pagamento) VALUES(?,?,?,?,?)',
                             (numero,self.cid,'Revisão de portão',status,'PIX')).lastrowid

    def def_mat(self,c,oid,itens):
        c.execute('DELETE FROM materiais_os WHERE os_id=?',(oid,))
        for nome,qtd,preco in itens:
            c.execute('INSERT INTO materiais_os(os_id,item,quantidade,valor_unitario,valor_total) VALUES(?,?,?,?,?)',
                (oid,nome,qtd,preco,qtd*preco))
        est.reconciliar_os_conexao(c,oid,'Prestador DEV')

    def test_yml_relatorio_reutilizavel_em_qualquer_os(self):
        modelo=(Path(__file__).parent / 'flavors/autoseg/templates/modelo_relatorio_os.yaml').read_bytes()
        # O modelo oficial atual é um formulário em branco; a importação não
        # inventa diagnóstico nem materiais.
        self.assertEqual(imp.relatorio('modelo.yaml',modelo),{})
        preenchido=('versao: 1\nos:\n  diagnostico: Inspeção do automatizador.\n  materiais: []\n').encode('utf-8')
        report=imp.relatorio('preenchido.yaml',preenchido)
        self.assertEqual(report['v9_diagnostico'],'Inspeção do automatizador.')
        self.assertEqual(report['material_yaml'],[])
        self.assertNotIn('numero',report)
        # antigo modelo numérico é aceito como conteúdo, sem tentar alterar a OS
        outro=imp.relatorio('arquivo.yaml',b'versao: 1\nos:\n  numero: OS-99999\n  resultado: OK\n', 'OS-0001')
        self.assertEqual(outro,{'v9_resultado':'OK'})

    def test_yml_servico_valida_sem_gravar(self):
        pre=imp.servico('modelo_servico.yaml',(Path(__file__).parent / 'flavors/autoseg/templates/modelo_servico.yaml').read_bytes())
        self.assertEqual(pre['nome'],'Cadastro de controle remoto PPA — DEMO')
        self.assertEqual(len(pre['materiais_lista']),2)
        self.assertEqual(cat.listar(self.db),[])
        data={'nome':pre['nome'],'descricao':pre['descricao'],'preco_servico':pre['preco_servico'],'relatorio_padrao':pre['relatorio_padrao'],
              'material_nome[]':[x['nome'] for x in pre['materiais_lista']],
              'material_qtd[]':[x['quantidade'] for x in pre['materiais_lista']],
              'material_valor[]':[x['valor_unitario'] for x in pre['materiais_lista']]}
        sid=cat.salvar(self.db,data)
        self.assertEqual(len(json.loads(cat.obter(self.db,sid)['materiais_json'])),2)
        self.assertEqual(cat.valores_orcamento(self.db,sid)['total'],13350)
        self.assertTrue(cat.pdf_orcamento(self.db,sid).startswith(b'%PDF'))

    def test_form_catalogo_zero_material_e_linhas_incompletas(self):
        sid=cat.salvar(self.db,{'nome':'Inspeção de Teste','preco_servico':'20',
                                'material_nome[]':[''],'material_qtd[]':[''],'material_valor[]':['']})
        self.assertEqual(json.loads(cat.obter(self.db,sid)['materiais_json']),[])
        with self.assertRaisesRegex(ValueError,'Preencha nome'):
            cat.salvar(self.db,{'nome':'Inspeção de Teste','preco_servico':'20','material_nome[]':['Sensor'],
                                'material_qtd[]':['1'],'material_valor[]':['']})
        self.assertEqual(len(cat.listar(self.db)),1)

    def test_estoque_material_novo_saldo_negativo_sem_baixa_dupla(self):
        oid=self.os_fake()
        with ext.db(self.db) as c:self.def_mat(c,oid,[('Sensor demo',2,50)])
        produto=next(x for x in est.listar(self.db) if x['nome']=='Sensor demo')
        self.assertEqual(produto['saldo'],-2)
        with ext.db(self.db) as c:self.def_mat(c,oid,[('Sensor demo',2,50)])
        self.assertEqual(est.listar(self.db)[0]['saldo'],-2)
        self.assertEqual(len(est.movimentos(self.db)),1)
        with ext.db(self.db) as c:self.def_mat(c,oid,[('Sensor demo',3,50)])
        self.assertEqual(est.listar(self.db)[0]['saldo'],-3)
        with ext.db(self.db) as c:self.def_mat(c,oid,[])
        self.assertEqual(est.listar(self.db)[0]['saldo'],0)
        self.assertEqual([x['delta'] for x in est.movimentos(self.db)],[3,-1,-2])

    def test_estoque_entrada_e_cancelamento_preserva_consumo(self):
        oid=self.os_fake()
        pid=est.cadastrar(self.db,'Sensor DEV',venda='20,00',minimo='2')
        est.ajuste(self.db,pid,'5','Compra fictícia')
        with ext.db(self.db) as c:self.def_mat(c,oid,[('Sensor DEV',2,20)])
        self.assertEqual(est.listar(self.db)[0]['saldo'],3)
        with ext.db(self.db) as c:
            fluxo.aplicar_encerramento(c,oid,'Cancelada','Serviço não realizado.','Pedido cancelado.')
        self.assertEqual(est.listar(self.db)[0]['saldo'],3)
        self.assertEqual(sum(x['delta'] for x in est.movimentos(self.db,pid)),3)

    def test_historico_preexistente_nao_baixa_retroativo(self):
        with tempfile.TemporaryDirectory(prefix='rev04_legado_') as tmp:
            b=str(Path(tmp)/'velho.db')
            criar_banco(b);ext.instalar(b)
            with ext.db(b) as c:
                cid=c.execute("INSERT INTO clientes(nome) VALUES('Cliente demo')").lastrowid
                oid=c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status) VALUES('OS-0999',?,'Concluída')",(cid,)).lastrowid
                c.execute("INSERT INTO materiais_os(os_id,item,quantidade,valor_unitario,valor_total) VALUES(?,'Cabo de teste',4,2,8)",(oid,))
            est.instalar(b)
            self.assertEqual(est.listar(b)[0]['saldo'],0)
            with ext.db(b) as c:est.reconciliar_os_conexao(c,oid)
            self.assertEqual(est.listar(b)[0]['saldo'],0)
            self.assertEqual(len(est.movimentos(b)),0)

    def test_estoque_possui_endpoint_administrativo_web(self):
        src=Path(__file__).with_name('portal_prestador.py').read_text()
        self.assertIn("if path=='/estoque':return self.estoque_admin(s)",src)
        self.assertIn("Somente administradores podem gerenciar o estoque.",src)


if __name__=='__main__':unittest.main(verbosity=2)
