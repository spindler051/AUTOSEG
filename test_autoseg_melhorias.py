"""Regressões novas — sempre SQLite temporário, sem rede externa ou dados reais."""
import os
import tempfile
import unittest
from pathlib import Path

import atendimento_os as aten
import cadastros_v9 as cad
import fluxo_os
import importacao_yaml as iy
import portal_negocios as neg
import prestadores_ext as ext
from banco import criar_banco


class AutoSegMelhorias(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_regressao_')
        self.db = str(Path(self.tmp.name)/'teste.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        fluxo_os.instalar(self.db)
        aten.instalar(self.db)
        cad.instalar(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def dados_cliente(nome, documento='', tipo='Jurídica'):
        d = {k:'' for k in neg.CLIENTE_CAMPOS}
        d.update(nome=nome, documento=documento, tipo_pessoa=tipo,
                 status='Ativo', cidade='Porto Alegre')
        return d

    def test_cliente_pj_sincroniza_no_mesmo_banco_sem_reiniciar(self):
        doc='12345678000195'
        self.assertTrue(cad.cnpj_valido(doc))
        cid=neg.cliente_salvar(self.db,self.dados_cliente('Condomínio Teste Um',doc),0)
        with ext.db(self.db) as c:
            org=c.execute('SELECT id,cliente_id,cnpj FROM v9_organizacoes WHERE cliente_id=?',(cid,)).fetchone()
            self.assertIsNotNone(org)
            self.assertEqual(org['cnpj'],doc)
        self.assertEqual(cad.organizacao_por_cnpj(self.db,doc)['id'],org['id'])
        d=self.dados_cliente('Condomínio Teste Atualizado',doc)
        neg.cliente_salvar(self.db,d,0,cid)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM v9_organizacoes WHERE cliente_id=?',(cid,)).fetchone()[0],1)
            self.assertEqual(c.execute('SELECT nome FROM v9_organizacoes WHERE cliente_id=?',(cid,)).fetchone()[0],d['nome'])

    def test_bloqueia_vinculo_com_cnpjs_diferentes(self):
        doc='12345678000195'
        doc2='11222333000181'
        self.assertTrue(cad.cnpj_valido(doc2))
        cid=neg.cliente_salvar(self.db,self.dados_cliente('Condomínio Alfa',doc),0)
        with ext.db(self.db) as c:
            org=c.execute('INSERT INTO v9_organizacoes(nome,tipo,cnpj,criado_em) VALUES(?,?,?,?)',
                          ('Condomínio Beta','Condomínio',doc2,ext.agora())).lastrowid
        with self.assertRaisesRegex(ValueError,'CNPJs diferentes'):
            cad.validar_organizacao(self.db,org,cid,'Teste')
        with ext.db(self.db) as c:
            self.assertIsNone(c.execute('SELECT cliente_id FROM v9_organizacoes WHERE id=?',(org,)).fetchone()[0])

    def test_exclusao_sem_os_e_protecao_de_historico(self):
        cid=neg.cliente_salvar(self.db,self.dados_cliente('Condomínio Provisório'),0)
        neg.cliente_excluir(self.db,cid,0)
        with ext.db(self.db) as c:
            self.assertFalse(c.execute('SELECT 1 FROM clientes WHERE id=?',(cid,)).fetchone())
            self.assertFalse(c.execute('SELECT 1 FROM v9_organizacoes WHERE cliente_id=?',(cid,)).fetchone())
        cid=neg.cliente_salvar(self.db,self.dados_cliente('Condomínio com OS'),0)
        with ext.db(self.db) as c:
            c.execute("INSERT INTO ordens_servico(numero_os,cliente_id,status) VALUES('OS-0001',?,'Pendente')",(cid,))
        with self.assertRaisesRegex(ValueError,'OS vinculada'):
            neg.cliente_excluir(self.db,cid,0)

    def test_solicitacao_cliente_vira_os_pendente_idempotente(self):
        uid=0
        with ext.db(self.db) as c:
            uid=c.execute('''INSERT INTO v9_usuarios(nome,cpf,telefone,senha_hash,criado_em)
                             VALUES(?,?,?,?,?)''',('Teste Usuário','52998224725','','hash',ext.agora())).lastrowid
        cid=neg.cliente_salvar(self.db,self.dados_cliente('Condomínio Portal','12345678000195'),0)
        with ext.db(self.db) as c:
            org=c.execute('SELECT id FROM v9_organizacoes WHERE cliente_id=?',(cid,)).fetchone()['id']
        ch=cad.registrar_chamado(self.db,uid,org,'Interfone não está funcionando','Normal','Portaria','Funcionário','Teste Usuário','51999998888')
        with ext.db(self.db) as c:
            chamada=c.execute('SELECT os_id FROM v9_chamados WHERE id=?',(ch,)).fetchone()
            self.assertTrue(chamada['os_id'])
            oid=chamada['os_id']
            os_=c.execute('SELECT status,cliente_id,origem FROM ordens_servico WHERE id=?',(oid,)).fetchone()
            self.assertEqual(os_['status'],'Aberta')
            self.assertEqual(os_['cliente_id'],cid)
            self.assertEqual(os_['origem'],'Portal')
        self.assertIn(oid,[x['id'] for x in ext.listar_os_compartilhadas(self.db)])
        self.assertEqual(cad.gerar_os(self.db,ch,'teste'),oid)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ordens_servico WHERE id=?',(oid,)).fetchone()[0],1)

    def test_ordem_das_os_ativas(self):
        with ext.db(self.db) as c:
            cliente_a = c.execute(
                "INSERT INTO clientes(nome) VALUES('Alfa')").lastrowid
            cliente_z = c.execute(
                "INSERT INTO clientes(nome) VALUES('Zulu')").lastrowid
            c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,data_abertura) "
                "VALUES('OS-0002',?,'Aberta','2026-11-02')", (cliente_a,))
            c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,data_abertura) "
                "VALUES('OS-0003',?,'Iniciada','2026-11-01')", (cliente_z,))
            c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,status,data_abertura) "
                "VALUES('OS-0001',?,'Pendente','2026-11-03')", (cliente_a,))
        padrao = [x['status'] for x in ext.listar_os_compartilhadas(self.db)]
        self.assertEqual(padrao, ['Iniciada', 'Pendente', 'Aberta'])
        por_cliente = [x['cliente'] for x in ext.listar_os_compartilhadas(
            self.db, 'cliente')]
        self.assertEqual(por_cliente, ['Alfa', 'Alfa', 'Zulu'])
        por_data = [x['numero_os'] for x in ext.listar_os_compartilhadas(
            self.db, 'data')]
        self.assertEqual(por_data, ['OS-0001', 'OS-0002', 'OS-0003'])
        por_numero = [x['numero_os'] for x in ext.listar_os_compartilhadas(
            self.db, 'os')]
        self.assertEqual(por_numero, ['OS-0001', 'OS-0002', 'OS-0003'])

    def test_importacao_yaml_valida_sem_gravar(self):
        texto=Path(__file__).with_name('modelo_cadastro_cliente.yaml').read_bytes()
        antes=[]
        with ext.db(self.db) as c:antes.append(c.execute('SELECT COUNT(*) FROM clientes').fetchone()[0])
        dados=iy.cliente('cadastro.yaml',texto)
        self.assertIn('Condomínio Exemplo Fictício',dados['nome'])
        with ext.db(self.db) as c:self.assertEqual(antes[0],c.execute('SELECT COUNT(*) FROM clientes').fetchone()[0])
        report=iy.relatorio('teste.yml',b'versao: 1\nos:\n  numero: OS-0001\n  diagnostico: Teste\n  materiais: []\n','OS-0001')
        self.assertEqual(report['material_yaml'],[])
        # REV04: número legado é ignorado, o YAML serve em qualquer OS.
        self.assertEqual(iy.relatorio('teste.yml',b'versao: 1\nos:\n  numero: OS-0001\n','OS-9999'),{})
        with self.assertRaises(ValueError):
            iy.cliente('bomba.yaml',b'versao: 1\ncliente:\n  nome: &x Outro\n  observacoes: *x\n')
        with self.assertRaises(ValueError):
            iy.cliente('bomba.yaml',b'versao: 1\ncliente:\n  nome: !!python/object/apply:os.system ["echo danger"]\n')

    def test_editar_os_sem_materiais_remove_linhas_antigas(self):
        pid=ext.cadastrar(self.db,'Técnico Teste','tec@example.org','senha-bem-segura-2026')
        cid=neg.cliente_salvar(self.db,self.dados_cliente('Cliente OS de Teste'),pid)
        d={'cliente_id':str(cid), 'descricao':'Troca de sensor', 'tecnico':'Técnico Teste',
           'forma_pagamento':'PIX','valor_mao_obra':'100', 'valor_materiais_manual':'0',
           'material_item[]':['Sensor'], 'material_qtd[]':['1'],
           'material_unit[]':['50'], 'acao_status':'salvar', 'materiais_presentes':'1'}
        oid=neg.os_salvar(self.db,d,pid)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM materiais_os WHERE os_id=?',(oid,)).fetchone()[0],1)
        sem_mat=dict(d)
        for k in ('material_item[]','material_qtd[]','material_unit[]'):
            del sem_mat[k]
        neg.os_salvar(self.db,sem_mat,pid,oid)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM materiais_os WHERE os_id=?',(oid,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT valor_materiais,valor_total FROM ordens_servico WHERE id=?',(oid,)).fetchone()['valor_total'],100)

    def test_rascunho_email_inclui_apenas_pix_do_prestador_atual(self):
        import email
        p1=ext.cadastrar(self.db,'Técnico Alfa','alfa@example.org','senha-bem-segura-2026')
        p2=ext.cadastrar(self.db,'Técnico Beta','beta@example.org','senha-bem-segura-2026')
        ext.salvar_config_prestador(self.db,p1,{'banco_titular':'Titular A','chave_pix':'pix-alfa'})
        ext.salvar_config_prestador(self.db,p2,{'banco_titular':'Titular B','chave_pix':'pix-beta'})
        dados=self.dados_cliente('Cliente Email')
        dados['email']='teste@example.org'
        cid=neg.cliente_salvar(self.db,dados,p1)
        d={'cliente_id':str(cid),'descricao':'Serviço fictício','forma_pagamento':'PIX',
           'valor_mao_obra':'0','valor_materiais_manual':'0','acao_status':'salvar'}
        oid=neg.os_salvar(self.db,d,p1)
        pdf=Path(self.tmp.name)/'relatorio.pdf'
        pdf.write_bytes(b'%PDF-1.4\n%%EOF')
        arq=Path(ext.criar_email_rascunho(self.db,oid,str(pdf),prestador_id=p2))
        msg=email.message_from_bytes(arq.read_bytes(),policy=email.policy.default)
        corpo=msg.get_body(preferencelist=('plain',)).get_content()
        self.assertIn('pix-beta',corpo)
        self.assertNotIn('pix-alfa',corpo)
        self.assertEqual(msg['To'],'teste@example.org')
        arq.unlink(missing_ok=True)

    def test_config_bancaria_separada_por_prestador(self):
        pid1=ext.cadastrar(self.db,'Prestador Fictício 1','p1@example.org','senha-bem-segura-2026')
        pid2=ext.cadastrar(self.db,'Prestador Fictício 2','p2@example.org','senha-bem-segura-2026')
        ext.salvar_config_prestador(self.db,pid1,{
            'provedor_email':'SMTP','email_remetente':'p1@example.org',
            'credencial_env':'AUTOSEG_P1_SMTP_TOKEN','banco_titular':'Empresa Fictícia 1',
            'chave_pix':'pix-ficticio-1'})
        self.assertEqual(ext.obter_config_prestador(self.db,pid1)['chave_pix'],'pix-ficticio-1')
        self.assertNotIn('pix-ficticio-1',str(ext.obter_config_prestador(self.db,pid2)))
        with self.assertRaises(ValueError):
            ext.salvar_config_prestador(self.db,pid1,{'credencial_env':'token-secreto-nao-deve-salvar'})

if __name__=='__main__':
    unittest.main(verbosity=2)
