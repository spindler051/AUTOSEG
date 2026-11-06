"""Testes de regressão REV07. Executar: python3 -m unittest -v test_produtividade_rev07
Usa somente SQLite temporário. Não envia Gmail nem acessa produção.
"""
import tempfile
import unittest
from pathlib import Path

from banco import criar_banco
import prestadores_ext as ext
import produtividade_os as prod


class ProdutividadeTestes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='autosseg_prod_')
        self.db=str(Path(self.tmp.name)/'teste.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        prod.instalar(self.db)
        self.a=ext.cadastrar(self.db,'Técnico A','a@example.org','senha-teste-a!')
        self.b=ext.cadastrar(self.db,'Técnico B','b@example.org','senha-teste-b!')

    def tearDown(self):
        self.tmp.cleanup()

    def nova_os(self,tipo='Física',email='titular@example.org',sindico=''):
        with ext.db(self.db) as c:
            cliente=c.execute('''INSERT INTO clientes
               (nome,tipo_pessoa,email,sindico_email)
               VALUES(?,?,?,?)''',('Cliente Teste',tipo,email,sindico)).lastrowid
            oid=c.execute('''INSERT INTO ordens_servico
               (numero_os,cliente_id,status,valor_total) VALUES(?,?,?,?)''',
               ('OS-TESTE-'+str(cliente),cliente,'Aberta',1000)).lastrowid
        return oid

    def test_atribuicao_e_concorrencia(self):
        osid=self.nova_os()
        self.assertTrue(ext.assumir(self.db,osid,self.a))
        with self.assertRaises(PermissionError):
            ext.assumir(self.db,osid,self.b)
        with ext.db(self.db) as c:
            self.assertEqual(ext.responsavel_atual(c,osid),self.a)
            c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?",(osid,))
        with self.assertRaises(PermissionError):
            ext.assumir(self.db,osid,self.b)
        ext.desatribuir(self.db,osid)
        self.assertTrue(ext.assumir(self.db,osid,self.b))
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM ordens_servico WHERE id=?',(osid,)).fetchone()[0],'Pendente')

    def test_rota_e_permissoes(self):
        osid=self.nova_os()
        with self.assertRaises(ValueError):
            prod.marcar_em_rota(self.db,osid,self.a,True)
        ext.assumir(self.db,osid,self.a)
        with self.assertRaises(PermissionError):
            prod.marcar_em_rota(self.db,osid,self.b,True)
        prod.marcar_em_rota(self.db,osid,self.a,True)
        self.assertEqual(prod.em_rota(self.db,osid)['em_rota'],1)
        prod.limpar_rota_ao_iniciar(self.db,osid)
        self.assertEqual(prod.em_rota(self.db,osid)['em_rota'],0)
        with ext.db(self.db) as c:
            c.execute("UPDATE ordens_servico SET status='Concluída' WHERE id=?",(osid,))
        with self.assertRaises(ValueError):
            prod.marcar_em_rota(self.db,osid,self.a,True)

    def test_rascunho_persistente_e_versao(self):
        osid=self.nova_os()
        ext.assumir(self.db,osid,self.a)
        campos={'v9_execucao':'Troca de fonte','material_item[]':['Fonte 12V'],
                'material_qtd[]':['1'],'material_unit[]':['90,00']}
        versao=prod.salvar_rascunho(self.db,osid,self.a,campos,0)
        self.assertEqual(versao,1)
        registro=prod.recuperar_rascunho(self.db,osid,self.a)
        self.assertEqual(registro['dados']['material_item[]'],['Fonte 12V'])
        self.assertEqual(registro['dados']['v9_execucao'],'Troca de fonte')
        self.assertEqual(prod.salvar_rascunho(self.db,osid,self.a,campos,1),2)
        with self.assertRaises(ValueError):
            prod.salvar_rascunho(self.db,osid,self.a,campos,1)
        with self.assertRaises(PermissionError):
            prod.recuperar_rascunho(self.db,osid,self.b)

    def test_etapas_nao_sao_duplicadas(self):
        osid=self.nova_os()
        ext.assumir(self.db,osid,self.a)
        dados={'relatorio_tecnico':'Primeira visita'}
        i=prod.registrar_etapa(self.db,osid,self.a,'Pendente',dados)
        self.assertEqual(prod.registrar_etapa(self.db,osid,self.a,'Pendente',dados),i)
        prod.registrar_etapa(self.db,osid,self.a,'Pendente',{'relatorio_tecnico':'Segunda visita'})
        self.assertEqual(len(prod.listar_etapas(self.db,osid)),2)

    def test_destinatarios_condominio_e_morador_ignorado(self):
        osid=self.nova_os('Jurídica','condominio@example.org','sindico@example.org')
        self.assertEqual(prod.destinatarios_conclusao(self.db,osid),
                         ['sindico@example.org','condominio@example.org'])
        self.assertEqual(len(prod.destinatarios_conclusao(self.db,osid,'sindico@example.org')),2)

    def test_email_obrigatorio_so_na_conclusao(self):
        osid=self.nova_os('Jurídica','','')
        with self.assertRaises(ValueError):
            prod.destinatarios_conclusao(self.db,osid)
        self.assertEqual(prod.destinatarios_conclusao(self.db,osid,'extra@example.org'),
                         ['extra@example.org'])
        with self.assertRaises(ValueError):
            prod.destinatarios_conclusao(self.db,osid,'invalido\r\nBCC:fake@example.org')

    def test_rateio_e_repasse_manual(self):
        oid=self.nova_os()
        ext.assumir(self.db,oid,self.a)
        with ext.db(self.db) as c:
            c.execute("UPDATE ordens_servico SET status='Concluída' WHERE id=?",(oid,))
            c.execute('CREATE TABLE IF NOT EXISTS os_encerramentos (os_id INTEGER PRIMARY KEY,prestador_id INTEGER)')
            c.execute('INSERT INTO os_encerramentos(os_id,prestador_id) VALUES(?,?)',(oid,self.a))
            liquido=prod.registrar_rateios_na_transacao(
                c,oid,self.a,1000,
                {'rateio_tecnico[]':[str(self.b)],'rateio_valor[]':['300,00']})
        self.assertEqual(liquido,70000)
        with self.assertRaises(ValueError):
            with ext.db(self.db) as c:
                prod.registrar_rateios_na_transacao(
                    c,oid,self.a,1000,
                    {'rateio_tecnico[]':[str(self.b)],'rateio_valor[]':['301,00']})
        with ext.db(self.db) as c:
            c.execute('''INSERT INTO financeiro(os_id,cliente_id,valor,status)
                         SELECT id,cliente_id,?,? FROM ordens_servico WHERE id=?''',
                      (1000,'Aguardando pagamento',oid))
        with self.assertRaisesRegex(ValueError,'Confirme o recebimento do cliente'):
            prod.confirmar_repasse(self.db,oid,self.a,self.b,'100,00')
        with ext.db(self.db) as c:
            c.execute("UPDATE financeiro SET status='Recebido' WHERE os_id=?",(oid,))
        self.assertEqual(prod.confirmar_repasse(self.db,oid,self.a,self.b,'100,00'),20000)
        self.assertEqual(prod.confirmar_repasse(self.db,oid,self.a,self.b,'200,00'),0)
        with self.assertRaises(ValueError):
            prod.confirmar_repasse(self.db,oid,self.a,self.b,'1,00')

    def test_rateio_sem_finalizacao_rejeitado(self):
        oid=self.nova_os()
        ext.assumir(self.db,oid,self.a)
        with self.assertRaises(PermissionError):
            with ext.db(self.db) as c:
                c.execute('CREATE TABLE IF NOT EXISTS os_encerramentos (os_id INTEGER PRIMARY KEY,prestador_id INTEGER)')
                prod.registrar_rateios_na_transacao(
                    c,oid,self.a,1000,
                    {'rateio_tecnico[]':[str(self.b)],'rateio_valor[]':['300,00']})

    def test_pdf_restrito_participantes(self):
        osid=self.nova_os()
        with self.assertRaises(PermissionError):
            prod.controlar_pdf(self.db,osid,self.a)
        ext.assumir(self.db,osid,self.a)
        prod.controlar_pdf(self.db,osid,self.a)
        with self.assertRaises(PermissionError):
            prod.controlar_pdf(self.db,osid,self.b)


if __name__=='__main__':
    unittest.main()
