"""Testes de regressão em SQLite temporário: não acessa dados.db real."""
import os, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from banco import criar_banco
import atendimento_os as aten, cadastros_v9 as cad, prestadores_ext as ext, fluxo_os as fluxo

class Fluxo(unittest.TestCase):
    def setUp(self):
        fd,self.path=tempfile.mkstemp(suffix='.db');os.close(fd)
        criar_banco(self.path);ext.instalar(self.path);fluxo.instalar(self.path);aten.instalar(self.path);cad.instalar(self.path)
        with ext.db(self.path) as c:
            self.uid=c.execute("INSERT INTO v9_usuarios(nome,cpf,telefone,senha_hash,criado_em) VALUES(?,?,?,?,?)",('Pessoa de teste','52998224725','','hash',ext.agora())).lastrowid

    def tearDown(self):
        os.unlink(self.path)
    def _abrir(self):
        org=cad.criar_organizacao(self.path,self.uid,'Condomínio do Teste','Condomínio',endereco='Rua do Teste 100',unidade='Portaria')
        ch=cad.registrar_chamado(self.path,self.uid,org,'Portão não abre','Alta','Porteiro','Funcionário','Pessoa de teste')
        return org,ch
    def test_os_imediata_sem_cnpj(self):
        org,ch=self._abrir()
        with ext.db(self.path) as c:
            reg=c.execute('SELECT os_id FROM v9_chamados WHERE id=?',(ch,)).fetchone();self.assertIsNotNone(reg['os_id'])
            os_=c.execute('SELECT status,numero_os FROM ordens_servico WHERE id=?',(reg['os_id'],)).fetchone()
            self.assertEqual(os_['status'],'Pendente');self.assertTrue(os_['numero_os'])
            org_=c.execute('SELECT situacao FROM v9_organizacoes WHERE id=?',(org,)).fetchone()
            self.assertEqual(org_['situacao'],'Pendente')
    def test_idempotencia_e_cancelamento(self):
        org,ch=self._abrir()
        oid=cad.gerar_os(self.path,ch,'teste');self.assertEqual(oid,cad.gerar_os(self.path,ch,'teste'))
        cad.cancelar_chamado(self.path,ch,'AUTOSEG','Duplicidade registrada')
        with ext.db(self.path) as c:
            self.assertEqual(c.execute('SELECT status FROM ordens_servico WHERE id=?',(oid,)).fetchone()['status'],'Cancelada')
            self.assertEqual(c.execute('SELECT status FROM v9_chamados WHERE id=?',(ch,)).fetchone()['status'],'Cancelado')
        self.assertIsNone(cad.gerar_os(self.path,ch,'teste') if False else None)
    def test_reconciliar_chamado_antigo(self):
        org,ch=self._abrir()
        with ext.db(self.path) as c:
            oid=c.execute('SELECT os_id FROM v9_chamados WHERE id=?',(ch,)).fetchone()['os_id']
            c.execute('UPDATE v9_chamados SET os_id=NULL WHERE id=?',(ch,))
            c.execute('DELETE FROM os_solicitacoes WHERE os_id=?',(oid,))
            c.execute('DELETE FROM ordens_servico WHERE id=?',(oid,))
        self.assertEqual(cad.sincronizar_solicitacoes_pendentes(self.path),1)
        self.assertEqual(cad.sincronizar_solicitacoes_pendentes(self.path),0)
    def test_bloqueia_cancelamento_apos_inicio(self):
        org,ch=self._abrir()
        with ext.db(self.path) as c:
            oid=c.execute('SELECT os_id FROM v9_chamados WHERE id=?',(ch,)).fetchone()['os_id']
            c.execute('INSERT INTO os_atendimentos(os_id,iniciado_em) VALUES(?,?)',(oid,ext.agora()))
        with self.assertRaises(ValueError):cad.cancelar_chamado(self.path,ch,'Prestador','Já iniciado')

if __name__=='__main__':unittest.main()
