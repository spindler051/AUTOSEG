"""Módulos administrativos Tkinter aditivos para a versão 9."""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import webbrowser
import threading
import gerenciar_tuneis as tuneis_v91
import cadastros_v9 as cad
import prestadores_ext as ext
import links_publicos as links

PRETO='#000000';CINZA='#AAAAAA';AMARELO='#FFD400';VERDE='#20C878';ESCURO='#151515'

class DesktopV9Mixin:
    def iniciar_tuneis_v91(self, mostrar_avisos=True):
        if __import__("os").environ.get("AUTOSEG_DEV") == "1":
            print("AUTOSEG DEV: túneis Cloudflare bloqueados.")
            return
        """Integra o gerenciador ao desktop, sem travar a interface."""
        import shutil
        if not (shutil.which('cloudflared') or __import__('pathlib').Path('/usr/local/bin/cloudflared').is_file()):
            if mostrar_avisos:messagebox.showerror('Cloudflare','cloudflared não encontrado no Mac.')
            return
        def trabalho():
            try:tuneis_v91.iniciar()
            except Exception as e:print('Não foi possível iniciar os túneis:',e)
        threading.Thread(target=trabalho,daemon=True,name='AUTOSEG-Tuneis').start()

    def ativar_automatico_v91(self):
        import json
        config=links.TUNEIS/'auto_iniciar.json'
        config.parent.mkdir(parents=True,exist_ok=True)
        try:atual=bool(json.loads(config.read_text()).get('ativo'))
        except Exception:atual=False
        if atual:
            if messagebox.askyesno('Cloudflare','Desativar a abertura automática de túneis ao iniciar o AUTOSEG?'):
                config.write_text(json.dumps({'ativo':False}));messagebox.showinfo('Cloudflare','Início automático desativado.')
            return
        if messagebox.askyesno('Cloudflare — publicação na internet',
            'ATENÇÃO: os dois portais serão publicados na internet SEM uma camada Cloudflare Access. '+
            'Não utilize dados reais até que login e permissões sejam revisados.\n\n'+
            'Ativar início automático dos dois túneis de TESTE?'):
            config.write_text(json.dumps({'ativo':True}))
            self.iniciar_tuneis_v91()
            messagebox.showinfo('Túneis','Inicialização solicitada. Os novos links aparecerão automaticamente no visor.')

    def agendar_tuneis_v91(self):
        """Após os servidores locais iniciarem, configura auto-início somente se autorizado."""
        import json
        try:
            cfg=json.loads((links.TUNEIS/'auto_iniciar.json').read_text())
            if cfg.get('ativo'):self.iniciar_tuneis_v91(False)
        except (OSError,ValueError):pass
        self.after(30000,self.verificar_tuneis_v91)

    def verificar_tuneis_v91(self):
        import json
        try:
            cfg=json.loads((links.TUNEIS/'auto_iniciar.json').read_text())
            if cfg.get('ativo') and len(links.estado())<2:self.iniciar_tuneis_v91(False)
        except (OSError,ValueError):pass
        self.after(30000,self.verificar_tuneis_v91)

    def atualizar_links_v9(self):
        if not getattr(self,'v9_links',None):return
        info=links.estado_com_manuais()
        for porta,rot in self.v9_links.items():
            try:
                if rot.winfo_exists():
                    u=info.get(porta,{}).get('url','')
                    rot.config(text=f'Porta {porta}: '+(u or 'sem link gerenciado ativo'),fg=VERDE if u else CINZA)
            except tk.TclError:pass
        if self.tela_atual==self.mostrar_inicio:self.after(5000,self.atualizar_links_v9)

    def abrir_link_publico_v9(self,porta):
        u=links.estado_com_manuais().get(porta,{}).get('url')
        if u:webbrowser.open(u)
        else:messagebox.showinfo('Túnel','Nenhum túnel v9 gerenciado ativo. Execute INICIAR_TUNEIS_TESTE.command.')

    def administrador_prestador_v9(self,tree):
        i=tree.selection()
        if not i:return messagebox.showwarning('Prestador','Selecione um prestador.')
        pid=int(tree.item(i[0])['values'][0])
        atual=cad.prestador_admin(self.BANCO_V9,pid)
        texto='Revogar a permissão ADMINISTRADOR?' if atual else 'Conceder acesso ADMINISTRADOR? Permite analisar, autorizar chamados e acessar cadastros/financeiro.'
        if not messagebox.askyesno('Administrador AUTOSEG',texto):return
        try:
            cad.definir_admin(self.BANCO_V9,pid,not atual)
            messagebox.showinfo('Permissão','Perfil administrador '+('revogado' if atual else 'ativado')+'.')
        except Exception as e:messagebox.showerror('Administrador',str(e))

    def mostrar_gestao_pj_v9(self):
        self.limpar_tela();self.tela_atual=self.mostrar_gestao_pj_v9
        self.criar_cabecalho('CHAMADOS E CONDOMÍNIOS • V9')
        barra=tk.Frame(self,bg=PRETO);barra.pack(fill='x',padx=25,pady=8)
        self.criar_botao(barra,'PORTAL DO CLIENTE (CPF)',lambda:webbrowser.open('http://127.0.0.1:8765/')).pack(side='left',padx=5)
        self.criar_botao(barra,'GESTÃO WEB',lambda:webbrowser.open('http://127.0.0.1:8766/chamados')).pack(side='left',padx=5)
        self.criar_botao(barra,'RECARREGAR',self.mostrar_gestao_pj_v9).pack(side='left',padx=5)
        tk.Label(self,text='Chamados só viram OS após análise AUTOSEG, confirmação do síndico e vínculo com cliente.',bg=PRETO,fg=CINZA).pack(pady=8)
        campos=[('id',65),('org',210),('solicitante',175),('status',165),('descricao',400)]
        tb=ttk.Treeview(self,columns=[a for a,_ in campos],show='headings',height=9)
        for a,w in campos:tb.heading(a,text=a.upper());tb.column(a,width=w)
        tb.pack(fill='both',expand=True,padx=25,pady=5)
        with ext.db(self.BANCO_V9) as c:
            rows=c.execute('''SELECT h.id,o.nome org,u.nome solicitante,h.status,h.descricao
                FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id
                JOIN v9_usuarios u ON u.id=h.usuario_id ORDER BY h.id DESC LIMIT 300''').fetchall()
        for r in rows:tb.insert('','end',values=(r['id'],r['org'],r['solicitante'],r['status'],r['descricao'][:140]))
        def escolha():
            itens=tb.selection()
            if not itens:messagebox.showwarning('Chamado','Selecione um chamado.');return None
            return int(tb.item(itens[0])['values'][0])
        def acao(nome):
            ch=escolha()
            if ch is None:return
            try:
                if nome=='analisar':cad.analisar(self.BANCO_V9,ch,'AUTOSEG desktop','Aguardando síndico')
                elif nome=='confirmar':
                    dado=simpledialog.askstring('Confirmação','Nome do síndico e meio de confirmação:')
                    if not dado or len(dado.strip())<8:return
                    cad.confirmar(self.BANCO_V9,ch,'AUTOSEG desktop — '+dado,True)
                elif nome=='recusar':cad.analisar(self.BANCO_V9,ch,'AUTOSEG desktop','Recusado','Rejeitado na análise')
                elif nome=='os':cad.gerar_os(self.BANCO_V9,ch,'AUTOSEG desktop')
                elif nome=='whatsapp':
                    link,_=cad.url_whatsapp(self.BANCO_V9,ch,links.estado_com_manuais().get('8766',{}).get('url',''))
                    webbrowser.open(link);return
                self.mostrar_gestao_pj_v9()
            except Exception as e:messagebox.showerror('Chamados PJ',str(e))
        botoes=tk.Frame(self,bg=PRETO);botoes.pack(pady=8)
        for nome,operacao in [('ABRIR WHATSAPP','whatsapp'),('ENCAMINHAR AO SÍNDICO','analisar'),('REGISTRAR CONFIRMAÇÃO','confirmar'),('GERAR OS AUTORIZADA','os'),('RECUSAR','recusar')]:
            self.criar_botao(botoes,nome,lambda op=operacao:acao(op),largura=23).pack(side='left',padx=4)
        self.criar_botao(self,'CONDOMÍNIOS E VÍNCULOS',self.mostrar_organizacoes_v9).pack(pady=6)

    def mostrar_organizacoes_v9(self):
        self.limpar_tela();self.tela_atual=self.mostrar_organizacoes_v9
        self.criar_cabecalho('ORGANIZAÇÕES E VÍNCULOS')
        with ext.db(self.BANCO_V9) as c:
            orgs=c.execute('SELECT id,nome,tipo,situacao,cliente_id FROM v9_organizacoes WHERE mesclado_em IS NULL ORDER BY nome').fetchall()
            pend=c.execute('''SELECT v.id,o.nome org,u.nome pessoa,v.papel FROM v9_vinculos v
                 JOIN v9_organizacoes o ON o.id=v.organizacao_id JOIN v9_usuarios u ON u.id=v.usuario_id
                 WHERE v.situacao='Pendente' ORDER BY v.id DESC''').fetchall()
        tb=ttk.Treeview(self,columns=('id','nome','tipo','situacao','cliente'),show='headings',height=8)
        for k,w in [('id',50),('nome',300),('tipo',130),('situacao',120),('cliente',100)]:tb.heading(k,text=k.upper());tb.column(k,width=w)
        tb.pack(fill='both',expand=True,padx=25,pady=5)
        for x in orgs:tb.insert('','end',values=(x['id'],x['nome'],x['tipo'],x['situacao'],x['cliente_id'] or '—'))
        def validar():
            i=tb.selection()
            if not i:return messagebox.showwarning('Organização','Selecione a organização.')
            oid=int(tb.item(i[0])['values'][0]);cliente=simpledialog.askinteger('Vincular cliente','ID do cliente contratante no desktop:')
            if not cliente:return
            try:cad.validar_organizacao(self.BANCO_V9,oid,cliente,'AUTOSEG desktop');self.mostrar_organizacoes_v9()
            except Exception as e:messagebox.showerror('Cadastro PJ',str(e))
        self.criar_botao(self,'VALIDAR / VINCULAR AO CLIENTE',validar).pack(pady=5)
        def atualizar_contato():
            i=tb.selection()
            if not i:return messagebox.showwarning('Síndico','Selecione um condomínio.')
            org=int(tb.item(i[0])['values'][0])
            with ext.db(self.BANCO_V9) as c:
                x=c.execute('SELECT sindico_nome,sindico_telefone FROM v9_organizacoes WHERE id=?',(org,)).fetchone()
            nome=simpledialog.askstring('Nome do síndico','Responsável:',initialvalue=x['sindico_nome'] or '')
            if nome is None:return
            fone=simpledialog.askstring('WhatsApp do síndico','Telefone com DDD:',initialvalue=x['sindico_telefone'] or '')
            if fone is None:return
            try:cad.atualizar_sindico(self.BANCO_V9,org,nome,fone,'AUTOSEG desktop');self.mostrar_organizacoes_v9()
            except Exception as erro:messagebox.showerror('WhatsApp',str(erro))
        self.criar_botao(self,'EDITAR WHATSAPP DO SÍNDICO',atualizar_contato).pack(pady=5)
        def mesclar():
            origem=simpledialog.askinteger('Mesclar organizações','ID do cadastro duplicado (origem):')
            if origem is None:return
            destino=simpledialog.askinteger('Mesclar organizações','ID do cadastro principal (destino):')
            if destino is None:return
            if not messagebox.askyesno('Confirmação de mesclagem',f'Mesclar organização {origem} dentro de {destino}? Esta operação é auditada e protege histórico.'):
                return
            try:cad.mesclar_organizacoes(self.BANCO_V9,origem,destino,'AUTOSEG desktop');self.mostrar_organizacoes_v9()
            except Exception as e:messagebox.showerror('Mesclagem',str(e))
        self.criar_botao(self,'MESCLAR CADASTROS DUPLICADOS',mesclar).pack(pady=4)

        tk.Label(self,text='Vínculos pendentes: confira identidade e representação antes de aprovar.',bg=PRETO,fg=CINZA).pack(pady=5)
        vtb=ttk.Treeview(self,columns=('id','org','pessoa','papel'),show='headings',height=5)
        for k,w in [('id',60),('org',300),('pessoa',270),('papel',130)]:vtb.heading(k,text=k.upper());vtb.column(k,width=w)
        vtb.pack(fill='both',expand=True,padx=25,pady=5)
        for x in pend:vtb.insert('','end',values=(x['id'],x['org'],x['pessoa'],x['papel']))
        def vinculo(aprovado):
            i=vtb.selection()
            if not i:return messagebox.showwarning('Vínculo','Selecione um vínculo.')
            vid=int(vtb.item(i[0])['values'][0])
            if not messagebox.askyesno('Verificação','O vínculo foi realmente conferido?'):return
            try:cad.alterar_vinculo(self.BANCO_V9,vid,aprovado,'AUTOSEG desktop');self.mostrar_organizacoes_v9()
            except Exception as e:messagebox.showerror('Vínculos',str(e))
        barra=tk.Frame(self,bg=PRETO);barra.pack(pady=8)
        self.criar_botao(barra,'APROVAR VÍNCULO',lambda:vinculo(True)).pack(side='left',padx=5)
        self.criar_botao(barra,'RECUSAR VÍNCULO',lambda:vinculo(False)).pack(side='left',padx=5)
        self.criar_botao(barra,'VOLTAR',self.mostrar_gestao_pj_v9).pack(side='left',padx=5)
