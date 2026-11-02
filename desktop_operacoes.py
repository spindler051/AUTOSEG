"""Interfaces Tkinter nativas: serviços e valores / materiais e estoque.

A administração de estoque NÃO possui endpoint web. O Portal do Prestador
pode apenas consumir materiais ao salvar uma OS, sem ver custo ou saldo.
"""
import json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import catalogo_servicos as catalogo
import estoque_materiais as estoque
import importacao_yaml
from banco import BANCO

FUNDO='#101010';PAINEL='#202020';BRANCO='#f7f7f7';AMARELO='#ffd400'


def campo(parent,rotulo,valor='',altura=0):
    frm=tk.Frame(parent,bg=FUNDO)
    frm.pack(fill='x',padx=12,pady=4)
    tk.Label(frm,text=rotulo,bg=FUNDO,fg=BRANCO,anchor='w').pack(anchor='w')
    if altura:
        w=tk.Text(frm,height=altura,wrap='word',bg=PAINEL,fg=BRANCO,insertbackground=BRANCO)
        w.insert('1.0',str(valor or ''))
    else:
        w=tk.Entry(frm,bg=PAINEL,fg=BRANCO,insertbackground=BRANCO)
        w.insert(0,str(valor or ''))
    w.pack(fill='x',pady=(2,2))
    return w


def ler(w):
    return w.get('1.0','end').strip() if isinstance(w,tk.Text) else w.get().strip()


def janela_dados(root,titulo,largura=800,altura=680):
    w=tk.Toplevel(root)
    w.title(titulo)
    w.geometry(f'{largura}x{altura}')
    w.minsize(610,450)
    w.configure(bg=FUNDO)
    cont=tk.Frame(w,bg=FUNDO);cont.pack(fill='both',expand=True)
    tela=tk.Canvas(cont,bg=FUNDO,highlightthickness=0)
    barra=ttk.Scrollbar(cont,orient='vertical',command=tela.yview)
    inner=tk.Frame(tela,bg=FUNDO)
    ident=tela.create_window((0,0),window=inner,anchor='nw')
    inner.bind('<Configure>',lambda _e:tela.configure(scrollregion=tela.bbox('all')))
    tela.bind('<Configure>',lambda e:tela.itemconfigure(ident,width=e.width))
    tela.configure(yscrollcommand=barra.set)
    tela.pack(side='left',fill='both',expand=True);barra.pack(side='right',fill='y')
    return w,inner


class DesktopOperacoesMixin:
    def abrir_catalogo_desktop(self):
        catalogo.instalar(BANCO)
        janela=tk.Toplevel(self);janela.title('AUTOSEG — Serviços e Valores')
        janela.geometry('1020x650');janela.minsize(740,450);janela.configure(bg=FUNDO)
        tk.Label(janela,text='SERVIÇOS E VALORES',fg=AMARELO,bg=FUNDO,font=('Arial',18,'bold')).pack(anchor='w',padx=16,pady=12)
        filtro=tk.StringVar()
        tk.Entry(janela,textvariable=filtro,bg=PAINEL,fg=BRANCO,insertbackground=BRANCO).pack(fill='x',padx=16)
        col=('id','nome','mao','ativo')
        tabela=ttk.Treeview(janela,columns=col,show='headings',height=16)
        for c,t,width in [('id','ID',60),('nome','Serviço',500),('mao','Mão de obra',140),('ativo','Situação',130)]:
            tabela.heading(c,text=t);tabela.column(c,width=width,stretch=(c=='nome'),anchor='w')
        # Tabela posicionada após as ações, para evitar corte dos botões.
        def atualizar(*_):
            busca=filtro.get().casefold().strip()
            tabela.delete(*tabela.get_children())
            for s in catalogo.listar(BANCO):
                if busca and busca not in (s['nome']+' '+s['descricao']).casefold():continue
                tabela.insert('', 'end',iid=str(s['id']),values=(s['id'],s['nome'],catalogo.reais(s['preco_servico_centavos']),'Ativo' if s['ativo'] else 'Arquivado'))
        filtro.trace_add('write',atualizar)
        def selecionado():
            val=tabela.selection()
            return int(val[0]) if val else None
        def editar(identificador=None,importado=None):
            registro=catalogo.obter(BANCO,identificador) if identificador else None
            info=importado or registro or {}
            itens=info.get('materiais_lista') if importado else json.loads(info.get('materiais_json') or '[]')
            tela,frm=janela_dados(janela,'AUTOSEG — Editar serviço' if identificador else 'AUTOSEG — Novo serviço')
            nome=campo(frm,'Nome do serviço',info.get('nome',''))
            desc=campo(frm,'Descrição ao cliente',info.get('descricao',''),4)
            preco=campo(frm,'Preço da mão de obra (R$)',info.get('preco_servico',str((info.get('preco_servico_centavos') or 0)/100).replace('.',',')))
            rel=campo(frm,'Relatório técnico padrão',info.get('relatorio_padrao',''),5)
            tk.Label(frm,text='Materiais do serviço (opcionais)',fg=AMARELO,bg=FUNDO,font=('Arial',12,'bold')).pack(anchor='w',padx=12,pady=9)
            linhas=[]
            area=tk.Frame(frm,bg=FUNDO);area.pack(fill='x',padx=12)
            def adicionar(d=None):
                d=d or {}
                linha=tk.Frame(area,bg=FUNDO);linha.pack(fill='x',pady=3)
                itens_texto=[]
                for key,largura in [('nome',28),('quantidade',8),('valor_unitario',13)]:
                    v=d.get(key, (str(d.get('preco_centavos',0)/100).replace('.',',') if key=='valor_unitario' else ''))
                    entrada=tk.Entry(linha,width=largura,bg=PAINEL,fg=BRANCO,insertbackground=BRANCO)
                    entrada.insert(0,str(v));entrada.pack(side='left',padx=3,fill='x',expand=(key=='nome'))
                    itens_texto.append(entrada)
                def excluir():linha.destroy();linhas.remove((linha,itens_texto))
                tk.Button(linha,text='Remover',command=excluir,bg='#522222',fg=BRANCO).pack(side='left',padx=3)
                linhas.append((linha,itens_texto))
            tk.Label(frm,text='Nome                          Quantidade                  Valor unitário',bg=FUNDO,fg=BRANCO).pack(anchor='w',padx=12)
            for d in itens:adicionar(d)
            tk.Button(frm,text='+ Adicionar material',command=adicionar,bg=PAINEL,fg=BRANCO).pack(anchor='w',padx=12,pady=8)
            def salvar():
                dados=dict(nome=ler(nome),descricao=ler(desc),preco_servico=ler(preco),relatorio_padrao=ler(rel))
                dados['material_nome[]']=[];dados['material_qtd[]']=[];dados['material_valor[]']=[]
                for _,fields in linhas:
                    val=[ler(x) for x in fields]
                    if not any(val):continue
                    dados['material_nome[]'].append(val[0]);dados['material_qtd[]'].append(val[1]);dados['material_valor[]'].append(val[2])
                try:catalogo.salvar(BANCO,dados,identificador)
                except Exception as e:messagebox.showerror('Verifique os campos',str(e),parent=tela);return
                atualizar();tela.destroy()
            tk.Button(frm,text='Salvar serviço',command=salvar,bg=AMARELO,fg='black',font=('Arial',12,'bold')).pack(fill='x',padx=12,pady=15)
        def importar():
            caminho=filedialog.askopenfilename(parent=janela,title='Importar serviço YAML',filetypes=[('YAML','*.yaml *.yml')])
            if not caminho:return
            try:
                from pathlib import Path
                pre=importacao_yaml.servico(Path(caminho).name,Path(caminho).read_bytes())
                editar(importado=pre)
            except Exception as e:messagebox.showerror('YAML inválido',str(e),parent=janela)
        def arquivar():
            sid=selecionado()
            if not sid:return messagebox.showwarning('Seleção','Selecione um serviço.',parent=janela)
            dados=catalogo.obter(BANCO,sid)
            if not messagebox.askyesno('Confirmar',('Arquivar' if dados['ativo'] else 'Reativar')+' este serviço?',parent=janela):return
            (catalogo.arquivar if dados['ativo'] else catalogo.reativar)(BANCO,sid);atualizar()
        acoes=tk.Frame(janela,bg=FUNDO);acoes.pack(fill='x',padx=12,pady=(0,14))
        for txt,cmd in [('Novo serviço',lambda:editar()),('Editar selecionado',lambda:editar(selecionado()) if selecionado() else messagebox.showwarning('Seleção','Selecione um serviço.',parent=janela)),('Importar YAML',importar),('Arquivar / Reativar',arquivar)]:
            tk.Button(acoes,text=txt,command=cmd,fg=BRANCO,bg=PAINEL,padx=10,pady=8).pack(side='left',padx=4)
        tabela.pack(fill='both',expand=True,padx=16,pady=12)
        tabela.bind('<Double-1>',lambda _e:editar(selecionado()) if selecionado() else None)
        atualizar()

    def abrir_estoque_desktop(self):
        estoque.instalar(BANCO)
        janela=tk.Toplevel(self);janela.title('AUTOSEG — Materiais e Estoque')
        janela.geometry('1100x690');janela.minsize(740,470);janela.configure(bg=FUNDO)
        tk.Label(janela,text='MATERIAIS E ESTOQUE • DESKTOP',fg=AMARELO,bg=FUNDO,font=('Arial',18,'bold')).pack(anchor='w',padx=16,pady=12)
        tk.Label(janela,text='Saldo negativo permitido e identificado. Entradas e estornos ficam no histórico.',bg=FUNDO,fg=BRANCO).pack(anchor='w',padx=16)
        tk.Label(janela,text='Buscar por nome ou código',bg=FUNDO,fg=BRANCO,
                 anchor='w').pack(fill='x',padx=16,pady=(10,1))
        busca=tk.StringVar();tk.Entry(janela,textvariable=busca,bg=PAINEL,fg=BRANCO,
                insertbackground=BRANCO).pack(fill='x',padx=16,pady=(2,9))
        cols=('id','nome','sku','unidade','saldo','minimo','venda')
        visual=ttk.Style(janela)
        visual.configure('AUTOSEG.Estoque.Treeview', background=PAINEL,
            fieldbackground=PAINEL, foreground=BRANCO, rowheight=29,
            borderwidth=0)
        visual.map('AUTOSEG.Estoque.Treeview',
            background=[('selected','#5a4700')], foreground=[('selected','#ffffff')])
        visual.configure('AUTOSEG.Estoque.Treeview.Heading',
            background='#292929',foreground=BRANCO,relief='flat',padding=7)
        tab=ttk.Treeview(janela,columns=cols,show='headings',height=14,
                         style='AUTOSEG.Estoque.Treeview')
        tab.configure(selectmode='browse')
        for c,t,w in [('id','ID',50),('nome','Material',360),('sku','Código',130),('unidade','Unid.',60),('saldo','Saldo',90),('minimo','Mínimo',90),('venda','Venda',130)]:
            tab.heading(c,text=t);tab.column(c,width=w,stretch=(c=='nome'))
        tab.tag_configure('negativo',foreground='#ffb5b5',background='#512222')
        tab.tag_configure('baixo',foreground='#ffdc8a',background='#483a19')
        tab.tag_configure('normal',foreground=BRANCO,background=PAINEL)
        resumo=tk.StringVar(value='Carregando materiais...')
        tk.Label(janela,textvariable=resumo,bg=FUNDO,fg=BRANCO,
                 anchor='w').pack(fill='x',padx=16,pady=(2,2))
        # Tabela posicionada após as ações para preservar botões mesmo em telas menores.
        def atualizar(*_):
            fil=estoque._chave(busca.get())
            tab.delete(*tab.get_children())
            total=0;alertas=0;negativos=0
            for x in estoque.listar(BANCO):
                if fil and fil not in estoque._chave(x['nome']+' '+x['sku']):continue
                total+=1
                if x['saldo']<0:negativos+=1
                elif x['saldo']<=x['minimo']:alertas+=1
                tag=('negativo',) if x['saldo']<0 else (('baixo',) if x['saldo']<=x['minimo'] else ('normal',))
                tab.insert('','end',iid=str(x['id']),values=(x['id'],x['nome'],x['sku'],x['unidade'],x['saldo'],x['minimo'],catalogo.reais(x['venda_centavos'])),tags=tag)
            resumo.set(f'{total} materiais exibidos  |  {negativos} negativos  |  {alertas} abaixo ou no mínimo')
        busca.trace_add('write',atualizar)
        def sel():
            itens=tab.selection();return int(itens[0]) if itens else None
        def ficha(pid=None):
            d=next((x for x in estoque.listar(BANCO) if x['id']==pid),{})
            janela2,frm=janela_dados(janela,'Cadastro de material',760,600)
            campos={}
            for chave,rotulo,valor in [('nome','Nome do material',d.get('nome','')),('sku','Código / SKU',d.get('sku','')),('unidade','Unidade de medida',d.get('unidade','un')),('custo','Custo de compra (R$)',str(d.get('custo_centavos',0)/100)),('venda','Preço de venda (R$)',str(d.get('venda_centavos',0)/100)),('minimo','Estoque mínimo',d.get('minimo',0))]:
                campos[chave]=campo(frm,rotulo,valor)
            def gravar():
                try:estoque.cadastrar(BANCO,**{k:ler(w) for k,w in campos.items()},identificador=pid)
                except Exception as e:messagebox.showerror('Material inválido',str(e),parent=janela2);return
                atualizar();janela2.destroy()
            tk.Button(frm,text='Salvar material',command=gravar,bg=AMARELO,fg='black').pack(fill='x',padx=12,pady=15)
        def movimento():
            pid=sel()
            if pid is None:return messagebox.showwarning('Seleção','Selecione um material.',parent=janela)
            quantidade=simpledialog.askstring('Movimentação','Digite a quantidade com sinal: +5 entrada, -2 saída.',parent=janela)
            if quantidade is None:return
            motivo=simpledialog.askstring('Movimentação','Motivo obrigatório:',parent=janela)
            if motivo is None:return
            try:estoque.ajuste(BANCO,pid,quantidade,motivo)
            except Exception as e:messagebox.showerror('Movimentação inválida',str(e),parent=janela);return
            atualizar()
        def historico():
            registros=estoque.movimentos(BANCO,sel(),200)
            w,frame=janela_dados(janela,'Histórico de movimentações',900,610)
            for r in registros:
                tk.Label(frame,text=f"{r['criado_em']}  |  {r['nome']}  |  {r['delta']:+g}  |  {r['tipo']}  |  OS {r['os_id'] or '—'}  |  {r['motivo']}",bg=FUNDO,fg=BRANCO,anchor='w',wraplength=820,justify='left').pack(fill='x',padx=12,pady=4)
        def importar_materiais():
            from pathlib import Path
            caminho=filedialog.askopenfilename(parent=janela,title='Importar materiais YAML',filetypes=[('YAML','*.yaml *.yml')])
            if not caminho:return
            try:
                pre=importacao_yaml.materiais(Path(caminho).name,Path(caminho).read_bytes())
                existentes={estoque._chave(x['nome']) for x in estoque.listar(BANCO)}
                repetidos=[x['nome'] for x in pre if estoque._chave(x['nome']) in existentes]
                if repetidos:raise ValueError('Já cadastrados: '+', '.join(repetidos[:10]))
                previa='\n'.join(f"• {x['nome']} ({x['unidade']})" for x in pre[:12])
                if len(pre)>12:previa+=f'\n... e mais {len(pre)-12} materiais.'
                if not messagebox.askyesno('Confirmar importação',
                    f'Importar {len(pre)} materiais após revisão?\n\n'+previa,parent=janela):return
                estoque.importar_lote(BANCO,pre)
                atualizar()
                messagebox.showinfo('Materiais',f'{len(pre)} materiais importados sem alterar saldos.',parent=janela)
            except Exception as ex:messagebox.showerror('Importação YAML',str(ex),parent=janela)
        linha=tk.Frame(janela,bg=FUNDO);linha.pack(fill='x',padx=12,pady=(4,13))
        for titulo,acao in [('Cadastrar produto',lambda:ficha()),('Editar produto',lambda:ficha(sel()) if sel() is not None else messagebox.showwarning('Seleção','Selecione um material.',parent=janela)),('Importar YAML',importar_materiais),('Entrada / Ajuste',movimento),('Histórico',historico)]:
            tk.Button(linha,text=titulo,command=acao,padx=9,pady=8,bg=PAINEL,fg=BRANCO).pack(side='left',padx=4)
        tab.pack(fill='both',expand=True,padx=16,pady=10)
        atualizar()

    def adicionar_material_do_estoque_os(self):
        """Seleciona material cadastrado sem precisar escrever nome e preço manualmente."""
        itens=estoque.listar(BANCO,ativos=True)
        if not itens:return messagebox.showinfo('Estoque','Nenhum produto cadastrado no estoque.',parent=self)
        janela=tk.Toplevel(self);janela.title('Selecionar material do estoque');janela.geometry('630x210');janela.configure(bg=FUNDO)
        nomes=[f"{p['id']} — {p['nome']}" for p in itens]
        cb=ttk.Combobox(janela,values=nomes,state='readonly',width=70)
        cb.pack(fill='x',padx=15,pady=12);cb.current(0)
        qtd=campo(janela,'Quantidade utilizada','1')
        def incluir():
            p=itens[cb.current()]
            try:q=estoque._q(ler(qtd))
            except ValueError as e:messagebox.showerror('Quantidade',str(e),parent=janela);return
            self.materiais_os.append({'item':p['nome'],'quantidade':float(q),'valor_unitario':p['venda_centavos']/100})
            self.atualizar_tabela_materiais();janela.destroy()
        tk.Button(janela,text='Adicionar à OS',command=incluir,bg=AMARELO,fg='black').pack(pady=8)
