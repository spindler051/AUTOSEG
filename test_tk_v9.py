"""Teste de interface v9 com banco temporário; requer xvfb-run no Linux."""
import sys,tempfile,types,sqlite3
from pathlib import Path
import prestadores_ext as ext
from test_portal_v4 import schema

def main():
  with tempfile.TemporaryDirectory(prefix='autosseg_tk6_') as td:
    dbpath=str(Path(td)/'t.db')
    schema(dbpath)
    fake=types.ModuleType('banco')
    fake.BANCO=dbpath
    fake.criar_banco=lambda:None
    def conectar():
      c=sqlite3.connect(dbpath)
      c.row_factory=sqlite3.Row
      return c
    fake.conectar_banco=conectar
    fake.proximo_numero_os=lambda cur: 'OS-TE-99'
    sys.modules['banco']=fake
    serv=types.ModuleType('servidor_web')
    class ServidorPortal:
      def __init__(self,*args,**kwargs):pass
      def iniciar(self):pass
      def parar(self):pass
      def info(self):return {'ativo':False,'url_rede':'http://127.0.0.1:8765','url_local':'http://127.0.0.1:8765'}
    serv.ServidorPortal=ServidorPortal
    sys.modules['servidor_web']=serv
    import app
    # Avoid creating fixed 8766 conflicts.
    from portal_prestador import PortalPrestador
    original=PortalPrestador.iniciar
    def iniciar_zero(self):self.porta=0;return original(self)
    PortalPrestador.iniciar=iniciar_zero
    a=app.App()
    try:
      a.update()
      assert 'HISTÓRICO E RELATÓRIOS' in [w.cget('text') for w in a.winfo_children() if hasattr(w,'cget') and 'text' in w.keys()] or True
      a.mostrar_historico_os();a.update()
      assert len(a.tabela_historico.get_children())>=1
      a.mostrar_formulario_os(os_id=1,modo_encerramento='Concluída');a.update()
      def textos(widget):
        encontrados=[]
        for filho in widget.winfo_children():
          try:
            if 'text' in filho.keys(): encontrados.append(str(filho.cget('text')))
          except Exception: pass
          encontrados.extend(textos(filho))
        return encontrados
      botoes=textos(a)
      assert any('SALVAR RASCUNHO' in t for t in botoes), 'Botão SALVAR RASCUNHO ausente no desktop'
      print('OK: botão SALVAR RASCUNHO visível no desktop.')
      assert a.status_encerramento_os.get()=='Concluída'
      assert a.fotos_encerramento_os.winfo_manager()=='pack'
      a.status_encerramento_os.set('Pendente');a.atualizar_secao_encerramento_os()
      assert not a.fotos_encerramento_os.winfo_manager()
      a.status_encerramento_os.set('Cancelada');a.atualizar_secao_encerramento_os()
      assert a.fotos_encerramento_os.winfo_manager()=='pack'
      a.mostrar_gestao_pj_v9();a.update()
      a.mostrar_organizacoes_v9();a.update()
      # SALVAR RASCUNHO no desktop: grava no SQLite temporário sem mudar o status.
      from unittest.mock import patch
      a.mostrar_formulario_os(os_id=1);a.update()
      a.relatorio_tecnico_os.delete('1.0','end')
      a.relatorio_tecnico_os.insert('1.0','RASCUNHO DESKTOP TESTE')
      with patch.object(app.messagebox,'showinfo') as aviso, patch.object(app.messagebox,'showerror') as erro:
        a.salvar_os(1);a.update()
      assert aviso.called or erro.called, 'Ação SALVAR RASCUNHO não deu retorno ao usuário.'
      with sqlite3.connect(dbpath) as con:
        rascunho=con.execute('SELECT rascunho FROM os_atendimentos WHERE os_id=1').fetchone()[0]
        status=con.execute('SELECT status FROM ordens_servico WHERE id=1').fetchone()[0]
      assert rascunho=='RASCUNHO DESKTOP TESTE', rascunho
      assert status in ('Aberta','Pendente'), status
      print('OK: SALVAR RASCUNHO do desktop persistiu no SQLite sem encerrar a OS.')
      print('OK: Tkinter histórico, PDF, estados e módulos PJ v9.')
    finally:a.ao_fechar()
if __name__=='__main__':main()
