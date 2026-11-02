import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import os
import queue
import urllib.request
import urllib.error
import json
import threading
import webbrowser
from datetime import datetime

from banco import BANCO, conectar_banco, criar_banco, proximo_numero_os
from servidor_web import ServidorPortal
import prestadores_ext as ext
import fluxo_os as fluxo
import atendimento_os as aten
from portal_prestador import PortalPrestador
from desktop_v9 import DesktopV9Mixin
import cadastros_v9 as cad9
import links_publicos as links9
import estoque_materiais as estoque
from desktop_operacoes import DesktopOperacoesMixin
from versao_app import versao_local

VERSAO_APP = versao_local('9.6.0-dev.6')


# ============================================================
# CONFIGURAÇÕES
# ============================================================

APP_TITLE = "AUTOSEG — Gestão de Serviços"
WINDOW_WIDTH = 1150
WINDOW_HEIGHT = 720

BLACK = "#000000"
DARK = "#151515"
DARKER = "#0A0A0A"
YELLOW = "#FFD400"
WHITE = "#FFFFFF"
GRAY = "#AAAAAA"
GREEN = "#20C878"
RED = "#E53935"
ORANGE = "#FFB000"

PASTA_APP = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(PASTA_APP, "logo.png")


# ============================================================
# APLICAÇÃO
# ============================================================

class App(DesktopV9Mixin,DesktopOperacoesMixin,tk.Tk):

    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(980, 640)
        self.configure(bg=BLACK)

        criar_banco()
        ext.instalar(BANCO)
        fluxo.instalar(BANCO)
        aten.instalar(BANCO)
        cad9.instalar(BANCO)
        estoque.instalar(BANCO)
        self.BANCO_V9=BANCO
        try:
            importados = fluxo.recuperar_relatorios_antigos(BANCO)
            if importados:
                print(f'PDFs anteriores vinculados ao histórico: {len(importados)}')
        except Exception as erro:
            print('Aviso: recuperação de PDFs anteriores:', erro)
        # Somente para teste na mesma rede local. Não configura publicação na internet.
        self.portal_prestador = PortalPrestador(BANCO,host=os.environ.get('PRESTADOR_BIND','0.0.0.0'))
        self.url_prestador = ""
        self.aviso_prestador = ""
        try:
            self.url_prestador = self.portal_prestador.iniciar()
        except Exception as erro:
            self.aviso_prestador = str(erro)
            print("Portal do prestador/cliente indisponível:", erro)
            try:
                messagebox.showwarning(
                    "Portal do cliente não iniciou",
                    "A porta 8766 não pôde ser aberta. Isso normalmente indica outro AUTOSEG "
                    "ou uma versão antiga ainda em execução.\n\n"
                    "Feche o outro processo e abra o AUTOSEG novamente.\n\n"
                    f"Detalhe: {self.aviso_prestador}"
                )
            except Exception:
                pass

        self.historico = []
        self.tela_atual = None
        self.logo_img = None
        self.icone_app = None

        self.servidor_portal = ServidorPortal(
            BANCO,
            PASTA_APP,
            porta=int(os.environ.get("CLIENTE_PORT", "8765")),
            host=os.environ.get("CLIENTE_BIND", "127.0.0.1")
        )
        self.erro_portal = ""

        try:
            self.servidor_portal.iniciar()
        except Exception as erro:
            self.erro_portal = str(erro)
            print("Portal do cliente indisponível:", erro)

        self.protocol("WM_DELETE_WINDOW", self.ao_fechar)

        self.definir_icone()
        self.configurar_estilo()
        self.mostrar_inicio()
        self.after(1500, self.processar_eventos_portal)
        self.after(2200, self.agendar_tuneis_v91)

    def ao_fechar(self):
        try:
            if os.environ.get('AUTOSEG_DEV')=='1':
                import tuneis_dev as ger
            else:
                import gerenciar_tuneis as ger
            ger.parar() # apenas túneis iniciados/gerenciados pela aplicação
        except Exception as erro:
            print('Não foi possível encerrar túnel gerenciado:',erro)
        try:
            self.portal_prestador.parar()
        except Exception:
            pass
        try:
            self.servidor_portal.parar()
        except Exception as erro:
            print("Erro encerrando o portal:", erro)

        self.destroy()

    def definir_icone(self):
        caminho = os.path.join(PASTA_APP, "icone.png")
        if not os.path.exists(caminho):
            caminho = LOGO

        try:
            self.icone_app = tk.PhotoImage(file=caminho)
            self.iconphoto(True, self.icone_app)
        except Exception as erro:
            print("Erro carregando ícone:", erro)

    # ========================================================
    # ESTILO
    # ========================================================

    def configurar_estilo(self):
        try:
            self.style = ttk.Style()
            self.style.theme_use("clam")
        except tk.TclError:
            self.style = ttk.Style()

        self.style.configure(
            "Treeview",
            background=DARKER,
            foreground=WHITE,
            fieldbackground=DARKER,
            rowheight=34,
            borderwidth=0,
            font=("Arial", 10)
        )

        self.style.configure(
            "Treeview.Heading",
            background=YELLOW,
            foreground=BLACK,
            relief="flat",
            font=("Arial", 10, "bold")
        )

        self.style.map(
            "Treeview",
            background=[("selected", "#4A4000")],
            foreground=[("selected", YELLOW)]
        )

        self.style.configure(
            "TCombobox",
            fieldbackground=DARKER,
            background=DARKER,
            foreground=WHITE,
            arrowcolor=YELLOW
        )

        estilos_botoes = {
            'Auto.Primary.TButton': ('#FFD400', '#080808', '#FFE36B'),
            'Auto.Secondary.TButton': ('#2B2B2B', '#FFFFFF', '#414141'),
            'Auto.Danger.TButton': ('#B32727', '#FFFFFF', '#D13A3A'),
            'Auto.Warning.TButton': ('#9C6700', '#FFFFFF', '#B98212'),
            'Auto.Success.TButton': ('#12754C', '#FFFFFF', '#16925F'),
        }
        for nome, (fundo, texto, hover) in estilos_botoes.items():
            self.style.configure(nome, background=fundo, foreground=texto,
                                 borderwidth=1, padding=(13, 12), relief='flat',
                                 font=('Arial', 11, 'bold'))
            self.style.map(nome, background=[('active',hover), ('pressed',hover)],
                           foreground=[('disabled','#909090')])

    # ========================================================
    # UTILITÁRIOS DE INTERFACE
    # ========================================================

    def limpar_tela(self):
        for widget in self.winfo_children():
            widget.destroy()

    def navegar_para(self, funcao):
        if self.tela_atual is not None:
            self.historico.append(self.tela_atual)
        funcao()

    def voltar(self):
        if self.historico:
            tela = self.historico.pop()
            tela()
        else:
            self.mostrar_inicio()

    def inicio(self):
        self.historico.clear()
        self.mostrar_inicio()

    def criar_cabecalho(self, titulo):
        cabecalho = tk.Frame(self, bg=BLACK)
        cabecalho.pack(fill="x", padx=25, pady=(18, 8))

        self.criar_botao(
            cabecalho,
            "← VOLTAR",
            self.voltar,
            largura=13
        ).pack(side="left")

        self.criar_botao(
            cabecalho,
            "⌂ INÍCIO",
            self.inicio,
            largura=12,
            frente=WHITE
        ).pack(side="left", padx=8)

        tk.Label(
            cabecalho,
            text=titulo,
            font=("Arial", 21, "bold"),
            fg=YELLOW,
            bg=BLACK
        ).pack(side="left", padx=18)

        return cabecalho

    def criar_botao(self, parent, texto, comando, largura=18, fundo=BLACK, frente=YELLOW):
        # ttk/clam evita que o macOS sobrescreva as cores dos botões Tk nativos.
        if fundo == YELLOW: estilo = 'Auto.Primary.TButton'
        elif frente == RED: estilo = 'Auto.Danger.TButton'
        elif frente == GREEN: estilo = 'Auto.Success.TButton'
        elif frente == ORANGE: estilo = 'Auto.Warning.TButton'
        else: estilo = 'Auto.Secondary.TButton'
        botao = ttk.Button(parent, text=texto, command=comando,
                           style=estilo, width=max(largura,len(texto)+2), takefocus=True)
        return botao

    def criar_titulo_secao(self, parent, texto):
        tk.Label(
            parent,
            text=texto,
            font=("Arial", 13, "bold"),
            fg=YELLOW,
            bg=BLACK
        ).pack(anchor="w", pady=(18, 8))

    def criar_campo(self, parent, rotulo, chave, valor="", combo=None, largura=45):
        linha = tk.Frame(parent, bg=BLACK)
        linha.pack(fill="x", pady=4)

        tk.Label(
            linha,
            text=rotulo,
            width=24,
            anchor="w",
            font=("Arial", 10),
            fg=WHITE,
            bg=BLACK
        ).pack(side="left")

        if combo is not None:
            campo = ttk.Combobox(
                linha,
                values=combo,
                width=largura,
                state="readonly"
            )
            campo.set(valor if valor else combo[0])
            campo.pack(side="left", fill="x", expand=True, ipady=5)
        else:
            campo = tk.Entry(
                linha,
                width=largura,
                font=("Arial", 10),
                bg=DARKER,
                fg=WHITE,
                insertbackground=WHITE,
                relief="flat"
            )
            campo.insert(0, "" if valor is None else valor)
            campo.pack(side="left", fill="x", expand=True, ipady=7)

        return campo

    def texto_do_campo(self, campo):
        if isinstance(campo, tk.Text):
            return campo.get("1.0", "end").strip()
        return campo.get().strip()

    def valor_monetario(self, texto):
        texto = str(texto).strip().replace("R$", "").replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return 0.0

    def dinheiro(self, valor):
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            valor = 0
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def status_visual(self, status):
        mapa = {
            "Aberta": ("🔴", RED),
            "Pendente": ("🟡", ORANGE),
            "Concluída": ("🟢", GREEN),
            "Cancelada": ("⛔", GRAY),
            "Não realizada": ("○", ORANGE),
            "Não processado": ("🔴", RED),
            "Aguardando pagamento": ("🟡", ORANGE),
            "Recebido": ("🟢", GREEN),
        }
        return mapa.get(status, ("●", GRAY))

    def valor_texto(self, valor):
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            valor = 0
        return f"{valor:.2f}".replace(".", ",")

    def criar_card_resumo(self, parent, titulo, valor, cor, detalhe=""):
        card = tk.Frame(
            parent,
            bg=DARK,
            padx=20,
            pady=10,
            highlightthickness=1,
            highlightbackground="#242424"
        )
        card.pack(side="left", padx=(0, 10), fill="x", expand=True)

        tk.Label(
            card,
            text=titulo,
            font=("Arial", 8, "bold"),
            fg=GRAY,
            bg=DARK
        ).pack(anchor="w")

        tk.Label(
            card,
            text=valor,
            font=("Arial", 16, "bold"),
            fg=cor,
            bg=DARK
        ).pack(anchor="w")

        if detalhe:
            tk.Label(
                card,
                text=detalhe,
                font=("Arial", 8),
                fg=GRAY,
                bg=DARK
            ).pack(anchor="w")

        return card

    # ========================================================
    # INÍCIO
    # ========================================================

    def mostrar_inicio(self):
        self.limpar_tela()
        self.tela_atual = self.mostrar_inicio

        topo = tk.Frame(self, bg=BLACK)
        topo.pack(fill="x", pady=(22, 5))

        if os.path.exists(LOGO):
            try:
                original = tk.PhotoImage(file=LOGO)

                fator = 1
                while (
                    original.width() // fator > 620
                    or original.height() // fator > 210
                ) and fator < 8:
                    fator += 1

                self.logo_img = original.subsample(fator, fator)

                tk.Label(
                    topo,
                    image=self.logo_img,
                    bg=BLACK
                ).pack()
            except Exception as erro:
                print("Erro carregando logo:", erro)
                tk.Label(
                    topo,
                    text="GESTÃO DE SERVIÇOS",
                    font=("Arial", 28, "bold"),
                    fg=YELLOW,
                    bg=BLACK
                ).pack()
        else:
            tk.Label(
                topo,
                text="GESTÃO DE SERVIÇOS",
                font=("Arial", 28, "bold"),
                fg=YELLOW,
                bg=BLACK
            ).pack()

        tk.Label(
            self,
            text="PAINEL PRINCIPAL",
            font=("Arial", 11, "bold"),
            fg=GRAY,
            bg=BLACK
        ).pack(pady=(0, 14))

        menu = tk.Frame(self, bg=BLACK)
        menu.pack()

        botoes = [
            ("CLIENTES", self.abrir_clientes),
            ("ORDENS DE SERVIÇO", self.abrir_os),
            ("FINANCEIRO", self.abrir_financeiro),
            ("NOTAS FISCAIS", self.menu_notas),
            ("E-MAILS", self.menu_emails),
            ("HISTÓRICO E RELATÓRIOS", self.abrir_historico_os),
            ("PRESTADORES", self.mostrar_prestadores),
            ("SERVIÇOS E VALORES", self.abrir_catalogo_servicos),
            ("MATERIAIS E ESTOQUE", self.abrir_estoque_desktop),
        ]

        # Menu em duas colunas, sem links redundantes aos portais.
        # Os portais já têm seus próprios botões dentro de CLIENTES/PRESTADORES.
        for i, (texto, comando) in enumerate(botoes):
            linha, coluna = divmod(i, 2)
            ultimo_sozinho = i == len(botoes)-1 and len(botoes) % 2 == 1
            self.criar_botao(
                menu, texto, comando,
                largura=56 if ultimo_sozinho else 27
            ).grid(
                row=linha, column=0 if ultimo_sozinho else coluna,
                columnspan=2 if ultimo_sozinho else 1,
                padx=9, pady=6, sticky='ew'
            )

        visor=tk.Frame(self,bg=DARK,highlightbackground='#353535',highlightthickness=1)
        visor.pack(fill='x',padx=55,pady=(0,8))
        tk.Label(visor,text='LINKS EXTERNOS ATUAIS · CLOUDFLARE',bg=DARK,fg=YELLOW,
                 font=('Arial',10,'bold')).pack(anchor='w',padx=12,pady=(7,2))
        self.v9_links={}
        for porta in links9.PORTAS:
            rot=tk.Label(visor,text=f'{porta}: não detectado',bg=DARK,fg=GRAY,
                         wraplength=920,anchor='w',justify='left',cursor='hand2',font=('Arial',10))
            rot.pack(fill='x',padx=12,pady=2)
            rot.bind('<Button-1>',lambda ev,p=porta:self.abrir_link_publico_v9(p))
            self.v9_links[porta]=rot
        self.atualizar_links_v9()
        barra_tuneis=tk.Frame(visor,bg=DARK)
        barra_tuneis.pack(fill='x',padx=10,pady=(1,8))
        self.criar_botao(barra_tuneis,'INICIAR / RECONECTAR TÚNEIS',lambda:self.iniciar_tuneis_v91()).pack(side='left',padx=4)
        if os.environ.get('AUTOSEG_DEV')!='1':
            self.criar_botao(barra_tuneis,'CONFIGURAR INÍCIO AUTOMÁTICO',self.ativar_automatico_v91).pack(side='left',padx=4)
        else:
            self.criar_botao(barra_tuneis,'PARAR TÚNEIS DEV',self.parar_tuneis_dev).pack(side='left',padx=4)

        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status = 'Aberta' THEN 1 ELSE 0 END), 0) AS abertas,
                COALESCE(SUM(CASE WHEN status = 'Pendente' THEN 1 ELSE 0 END), 0) AS pendentes,
                COALESCE(SUM(CASE WHEN status = 'Concluída' THEN 1 ELSE 0 END), 0) AS concluidas
            FROM ordens_servico
        """)
        resumo_os = cursor.fetchone()

        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status = 'Aguardando pagamento' THEN valor ELSE 0 END), 0) AS a_receber,
                COALESCE(SUM(CASE WHEN status = 'Recebido' THEN valor ELSE 0 END), 0) AS recebido
            FROM financeiro
        """)
        resumo_financeiro = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) AS total FROM clientes WHERE status != 'Inativo'")
        total_clientes = cursor.fetchone()["total"]

        conexao.close()

        indicadores = tk.Frame(self, bg=BLACK)
        indicadores.pack(fill="x", padx=55, pady=(20, 0))

        self.criar_card_resumo(
            indicadores,
            "OS ABERTAS",
            str(resumo_os["abertas"]),
            RED,
            "em andamento"
        )
        self.criar_card_resumo(
            indicadores,
            "OS PENDENTES",
            str(resumo_os["pendentes"]),
            ORANGE,
            "aguardando"
        )
        self.criar_card_resumo(
            indicadores,
            "A RECEBER",
            self.dinheiro(resumo_financeiro["a_receber"]),
            ORANGE,
            "financeiro"
        )
        self.criar_card_resumo(
            indicadores,
            "RECEBIDO",
            self.dinheiro(resumo_financeiro["recebido"]),
            GREEN,
            "financeiro"
        )
        self.criar_card_resumo(
            indicadores,
            "CLIENTES ATIVOS",
            str(total_clientes),
            YELLOW,
            "cadastrados"
        )

        status = tk.Frame(
            self,
            bg=DARK,
            padx=22,
            pady=13,
            highlightthickness=1,
            highlightbackground="#262626"
        )
        status.pack(fill="x", padx=55, pady=(18, 12))

        tk.Label(
            status,
            text="SISTEMA",
            font=("Arial", 10, "bold"),
            fg=GRAY,
            bg=DARK
        ).pack(side="left")

        tk.Label(
            status,
            text="● ONLINE",
            font=("Arial", 10, "bold"),
            fg=GREEN,
            bg=DARK
        ).pack(side="left", padx=12)

        tk.Label(
            status,
            text=f"AUTOSEG {VERSAO_APP}",
            font=("Arial", 10, "bold"),
            fg=YELLOW,
            bg=DARK
        ).pack(side="left")

        tk.Label(
            status,
            text="Banco local ativo  •",
            font=("Arial", 10),
            fg=GRAY,
            bg=DARK
        ).pack(side="right", padx=(0, 8))

        info_portal = self.servidor_portal.info()

        if info_portal["ativo"]:
            texto_portal = f"Portal do cliente ({links9.PORTAS[0]}): " + info_portal["url_rede"]
            cor_portal = GREEN
        else:
            texto_portal = f"Portal do cliente ({links9.PORTAS[0]}): desligado"
            cor_portal = RED

        rotulo_portal = tk.Label(
            status,
            text=texto_portal,
            font=("Arial", 9, "bold"),
            fg=cor_portal,
            bg=DARK,
            cursor="hand2"
        )
        rotulo_portal.pack(side="right")
        rotulo_portal.bind(
            "<Button-1>",
            lambda _event: self.abrir_portal_cliente()
        )


    # ========================================================
    # CLIENTES
    # ========================================================

    def abrir_clientes(self):
        self.navegar_para(self.mostrar_clientes)

    def mostrar_clientes(self):
        self.limpar_tela()
        self.tela_atual = self.mostrar_clientes

        self.criar_cabecalho("CLIENTES")

        barra = tk.Frame(self, bg=BLACK)
        barra.pack(fill="x", padx=30, pady=15)

        self.pesquisa_cliente = tk.Entry(
            barra,
            font=("Arial", 11),
            bg=DARKER,
            fg=WHITE,
            insertbackground=WHITE,
            relief="flat",
            width=38
        )
        self.pesquisa_cliente.pack(side="left", ipady=8)

        self.criar_botao(
            barra,
            "PESQUISAR",
            self.pesquisar_clientes,
            largura=14
        ).pack(side="left", padx=8)

        self.criar_botao(
            barra,
            "+ NOVO CLIENTE",
            self.novo_cliente,
            largura=17
        ).pack(side="right")

        tabela_frame = tk.Frame(self, bg=BLACK)
        tabela_frame.pack(fill="both", expand=True, padx=30, pady=5)

        colunas = ("id", "nome", "documento", "cidade", "telefone", "status")

        self.tabela_clientes = ttk.Treeview(
            tabela_frame,
            columns=colunas,
            show="headings"
        )

        titulos = {
            "id": "ID",
            "nome": "Nome / Razão Social",
            "documento": "CPF / CNPJ",
            "cidade": "Cidade",
            "telefone": "Telefone",
            "status": "Status"
        }

        larguras = {
            "id": 55,
            "nome": 300,
            "documento": 150,
            "cidade": 150,
            "telefone": 140,
            "status": 100
        }

        for coluna in colunas:
            self.tabela_clientes.heading(
                coluna,
                text=titulos[coluna]
            )
            self.tabela_clientes.column(
                coluna,
                width=larguras[coluna],
                anchor="center"
            )

        self.tabela_clientes.pack(fill="both", expand=True)
        self.tabela_clientes.bind(
            "<Double-1>",
            lambda _event: self.editar_cliente_selecionado()
        )

        botoes = tk.Frame(self, bg=BLACK)
        botoes.pack(fill="x", padx=30, pady=15)

        self.criar_botao(
            botoes,
            "ABRIR / EDITAR",
            self.editar_cliente_selecionado,
            largura=17
        ).pack(side="left")

        self.criar_botao(
            botoes,
            "+ NOVA OS DO CLIENTE",
            self.nova_os_cliente_selecionado,
            largura=21
        ).pack(side="left", padx=8)

        self.criar_botao(
            botoes,
            "EXCLUIR / DESATIVAR",
            self.excluir_cliente,
            largura=13,
            frente=RED
        ).pack(side="left")

        self.criar_botao(botoes,'ACESSO WEB / SENHA',self.configurar_acesso_cliente,
                         largura=20,fundo=YELLOW,frente=BLACK).pack(side='left',padx=8)
        # Gestão PF/PJ integrada neste cadastro; menu legado removido da navegação.
        self.criar_botao(self, '🌐 ABRIR PORTAL DO CLIENTE',
                         self.abrir_area_cliente_documentos, largura=30).pack(
                             anchor='w', padx=30, pady=(0,8))
        self.carregar_clientes()

    def carregar_clientes(self, termo=""):
        for item in self.tabela_clientes.get_children():
            self.tabela_clientes.delete(item)

        conexao = conectar_banco()
        cursor = conexao.cursor()

        if termo.strip():
            cursor.execute("""
                SELECT id, nome, documento, cidade, telefone, status
                FROM clientes
                WHERE nome LIKE ?
                   OR documento LIKE ?
                   OR cidade LIKE ?
                ORDER BY nome
            """, (f"%{termo}%", f"%{termo}%", f"%{termo}%"))
        else:
            cursor.execute("""
                SELECT id, nome, documento, cidade, telefone, status
                FROM clientes
                ORDER BY nome
            """)

        registros = cursor.fetchall()
        conexao.close()

        for cliente in registros:
            self.tabela_clientes.insert(
                "",
                "end",
                values=(
                    cliente["id"],
                    cliente["nome"],
                    cad9.formatar_documento(cliente["documento"]),
                    cliente["cidade"] or "",
                    cliente["telefone"] or "",
                    cliente["status"]
                )
            )

    def pesquisar_clientes(self):
        self.carregar_clientes(self.pesquisa_cliente.get())

    def novo_cliente(self):
        self.navegar_para(lambda: self.mostrar_formulario_cliente())

    def editar_cliente_selecionado(self):
        selecionado = self.tabela_clientes.selection()

        if not selecionado:
            messagebox.showwarning(
                "Seleção",
                "Selecione um cliente primeiro."
            )
            return

        valores = self.tabela_clientes.item(selecionado[0])["values"]
        cliente_id = valores[0]

        self.navegar_para(
            lambda: self.mostrar_formulario_cliente(cliente_id)
        )

    def nova_os_cliente_selecionado(self):
        selecionado = self.tabela_clientes.selection()

        if not selecionado:
            messagebox.showwarning(
                "Seleção",
                "Selecione um cliente primeiro."
            )
            return

        valores = self.tabela_clientes.item(selecionado[0])["values"]
        cliente_id = valores[0]

        self.navegar_para(
            lambda: self.mostrar_formulario_os(cliente_id=cliente_id)
        )

    def excluir_cliente(self):
        selecionado = self.tabela_clientes.selection()

        if not selecionado:
            messagebox.showwarning(
                "Seleção",
                "Selecione um cliente primeiro."
            )
            return

        valores = self.tabela_clientes.item(selecionado[0])["values"]
        cliente_id = valores[0]
        nome = valores[1]

        conexao = conectar_banco()
        cursor = conexao.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS total FROM ordens_servico WHERE cliente_id = ?",
            (cliente_id,)
        )
        tem_os = cursor.fetchone()["total"]
        conexao.close()

        if tem_os:
            if messagebox.askyesno("Preservar histórico",
                  "Este cliente possui OS e relatórios. Não é possível apagar fisicamente seus vínculos.\n\n"
                  "Deseja DESATIVAR o cadastro, mantendo as OS, documentos e o histórico?"):
                try:
                    cad9.desativar_cliente(BANCO,cliente_id,'AUTOSEG desktop')
                    self.carregar_clientes()
                except Exception as e:messagebox.showerror('Cadastro',str(e))
            return

        confirmar = messagebox.askyesno(
            "Excluir cliente",
            f"Deseja realmente excluir:\n\n{nome}?"
        )

        if not confirmar:
            return

        try:
            import portal_negocios as neg
            neg.cliente_excluir(BANCO,cliente_id,0)  # Prestador 0 = aplicativo desktop.
            self.carregar_clientes()
        except Exception as erro:
            messagebox.showerror('Exclusão bloqueada',str(erro))

    # ========================================================
    # FORMULÁRIO DE CLIENTE
    # ========================================================

    def mostrar_formulario_cliente(self, cliente_id=None):
        self.limpar_tela()
        self.tela_atual = lambda: self.mostrar_formulario_cliente(cliente_id)

        titulo = "NOVO CLIENTE" if cliente_id is None else "EDITAR CLIENTE"
        self.criar_cabecalho(titulo)

        container = tk.Frame(self, bg=BLACK)
        container.pack(fill="both", expand=True, padx=35, pady=5)

        canvas = tk.Canvas(
            container,
            bg=BLACK,
            highlightthickness=0
        )
        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview
        )

        formulario = tk.Frame(canvas, bg=BLACK)

        formulario.bind(
            "<Configure>",
            lambda event: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        janela_formulario = canvas.create_window(
            (0, 0),
            window=formulario,
            anchor="nw"
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(
                janela_formulario,
                width=event.width
            )
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.campos_cliente = {}

        dados = {}
        if cliente_id is not None:
            conexao = conectar_banco()
            cursor = conexao.cursor()
            cursor.execute(
                "SELECT * FROM clientes WHERE id = ?",
                (cliente_id,)
            )
            registro = cursor.fetchone()
            conexao.close()

            if registro:
                dados = dict(registro)

        self.criar_titulo_secao(formulario, "DADOS PRINCIPAIS")

        self.campos_cliente["tipo_pessoa"] = self.criar_campo(
            formulario,
            "Tipo de pessoa:",
            "tipo_pessoa",
            dados.get("tipo_pessoa", "Jurídica"),
            ["Jurídica", "Física"]
        )

        self.campos_cliente["documento"] = self.criar_campo(
            formulario,
            "CPF / CNPJ:",
            "documento",
            cad9.formatar_documento(dados.get("documento", ""))
        )

        self.campos_cliente["nome"] = self.criar_campo(
            formulario,
            "Nome / Razão Social:",
            "nome",
            dados.get("nome", "")
        )

        self.campos_cliente["nome_fantasia"] = self.criar_campo(
            formulario,
            "Nome Fantasia:",
            "nome_fantasia",
            dados.get("nome_fantasia", "")
        )

        self.campos_cliente["status"] = self.criar_campo(
            formulario,
            "Status:",
            "status",
            dados.get("status", "Ativo"),
            ["Ativo", "Inativo", "Prospect"]
        )

        self.criar_titulo_secao(formulario, "ENDEREÇO")

        linha_cep = tk.Frame(formulario, bg=BLACK)
        linha_cep.pack(fill="x", pady=4)

        tk.Label(
            linha_cep,
            text="CEP:",
            width=24,
            anchor="w",
            font=("Arial", 10),
            fg=WHITE,
            bg=BLACK
        ).pack(side="left")

        self.campos_cliente["cep"] = tk.Entry(
            linha_cep,
            width=18,
            font=("Arial", 10),
            bg=DARKER,
            fg=WHITE,
            insertbackground=WHITE,
            relief="flat"
        )
        self.campos_cliente["cep"].insert(0, dados.get("cep", ""))
        self.campos_cliente["cep"].pack(side="left", ipady=7)

        self.criar_botao(
            linha_cep,
            "BUSCAR CEP",
            self.buscar_cep,
            largura=14
        ).pack(side="left", padx=8)

        self.label_cep_status = tk.Label(
            linha_cep,
            text="",
            font=("Arial", 9),
            fg=GRAY,
            bg=BLACK
        )
        self.label_cep_status.pack(side="left")

        self.campos_cliente["endereco"] = self.criar_campo(
            formulario,
            "Rua / Logradouro:",
            "endereco",
            dados.get("endereco", "")
        )
        self.campos_cliente["numero"] = self.criar_campo(
            formulario,
            "Número:",
            "numero",
            dados.get("numero", "")
        )
        self.campos_cliente["complemento"] = self.criar_campo(
            formulario,
            "Complemento:",
            "complemento",
            dados.get("complemento", "")
        )
        self.campos_cliente["bairro"] = self.criar_campo(
            formulario,
            "Bairro:",
            "bairro",
            dados.get("bairro", "")
        )
        self.campos_cliente["cidade"] = self.criar_campo(
            formulario,
            "Cidade:",
            "cidade",
            dados.get("cidade", "")
        )
        self.campos_cliente["uf"] = self.criar_campo(
            formulario,
            "UF:",
            "uf",
            dados.get("uf", "")
        )

        self.criar_titulo_secao(formulario, "CONTATO")

        self.campos_cliente["telefone"] = self.criar_campo(
            formulario,
            "Telefone:",
            "telefone",
            dados.get("telefone", "")
        )
        self.campos_cliente["email"] = self.criar_campo(
            formulario,
            "E-mail:",
            "email",
            dados.get("email", "")
        )

        self.criar_titulo_secao(formulario, "SÍNDICO / RESPONSÁVEL")

        self.campos_cliente["sindico_nome"] = self.criar_campo(
            formulario,
            "Nome:",
            "sindico_nome",
            dados.get("sindico_nome", "")
        )
        self.campos_cliente["sindico_telefone"] = self.criar_campo(
            formulario,
            "Telefone:",
            "sindico_telefone",
            dados.get("sindico_telefone", "")
        )
        self.campos_cliente["sindico_email"] = self.criar_campo(
            formulario,
            "E-mail:",
            "sindico_email",
            dados.get("sindico_email", "")
        )

        self.criar_titulo_secao(formulario, "IMOBILIÁRIA / ADMINISTRADORA")

        self.campos_cliente["administradora"] = self.criar_campo(
            formulario,
            "Nome:",
            "administradora",
            dados.get("administradora", "")
        )
        self.campos_cliente["administradora_telefone"] = self.criar_campo(
            formulario,
            "Telefone:",
            "administradora_telefone",
            dados.get("administradora_telefone", "")
        )
        self.campos_cliente["administradora_email"] = self.criar_campo(
            formulario,
            "E-mail:",
            "administradora_email",
            dados.get("administradora_email", "")
        )

        self.criar_titulo_secao(formulario, "OBSERVAÇÕES")

        self.campos_cliente["observacoes"] = tk.Text(
            formulario,
            height=5,
            font=("Arial", 10),
            bg=DARKER,
            fg=WHITE,
            insertbackground=WHITE,
            relief="flat"
        )
        self.campos_cliente["observacoes"].pack(fill="x", pady=(0, 15))
        self.campos_cliente["observacoes"].insert(
            "1.0",
            dados.get("observacoes", "") or ""
        )

        botoes = tk.Frame(formulario, bg=BLACK)
        botoes.pack(fill="x", pady=(8, 25))

        self.criar_botao(
            botoes,
            "← CANCELAR",
            self.voltar,
            largura=16,
            frente=WHITE
        ).pack(side="left")

        if cliente_id is not None:
            self.criar_botao(
                botoes,
                "+ INICIAR ORDEM DE SERVIÇO",
                lambda: self.nova_os_a_partir_do_formulario(cliente_id),
                largura=25
            ).pack(side="left", padx=8)

        self.criar_botao(
            botoes,
            "SALVAR CLIENTE",
            lambda: self.salvar_cliente(cliente_id),
            largura=20,
            fundo=YELLOW,
            frente=BLACK
        ).pack(side="right")

    def nova_os_a_partir_do_formulario(self, cliente_id):
        self.navegar_para(
            lambda: self.mostrar_formulario_os(cliente_id=cliente_id)
        )

    # ========================================================
    # VIA CEP
    # ========================================================

    def buscar_cep(self):
        cep = self.campos_cliente["cep"].get().strip()
        cep_limpo = "".join(ch for ch in cep if ch.isdigit())

        if len(cep_limpo) != 8:
            messagebox.showwarning(
                "CEP inválido",
                "Digite um CEP com 8 números."
            )
            return

        self.label_cep_status.config(
            text="Consultando...",
            fg=ORANGE
        )

        threading.Thread(
            target=self.consultar_cep_thread,
            args=(cep_limpo,),
            daemon=True
        ).start()

    def consultar_cep_thread(self, cep):
        url = f"https://viacep.com.br/ws/{cep}/json/"
        try:
            requisicao = urllib.request.Request(
                url,
                headers={"User-Agent": "GestaoServicos/1.0"}
            )

            with urllib.request.urlopen(
                requisicao,
                timeout=8
            ) as resposta:
                dados = json.loads(
                    resposta.read().decode("utf-8")
                )

            self.after(
                0,
                lambda: self.receber_cep(dados)
            )

        except urllib.error.URLError:
            self.after(
                0,
                lambda: self.cep_erro(
                    "Não foi possível acessar o serviço de CEP."
                )
            )
        except Exception:
            self.after(
                0,
                lambda: self.cep_erro(
                    "Ocorreu um erro durante a consulta."
                )
            )

    def receber_cep(self, dados):
        if dados.get("erro"):
            self.cep_erro("CEP não encontrado.")
            return

        self.campos_cliente["endereco"].delete(0, "end")
        self.campos_cliente["endereco"].insert(
            0,
            dados.get("logradouro", "")
        )

        self.campos_cliente["bairro"].delete(0, "end")
        self.campos_cliente["bairro"].insert(
            0,
            dados.get("bairro", "")
        )

        self.campos_cliente["cidade"].delete(0, "end")
        self.campos_cliente["cidade"].insert(
            0,
            dados.get("localidade", "")
        )

        self.campos_cliente["uf"].delete(0, "end")
        self.campos_cliente["uf"].insert(
            0,
            dados.get("uf", "")
        )

        self.label_cep_status.config(
            text="Endereço encontrado",
            fg=GREEN
        )

    def cep_erro(self, mensagem):
        self.label_cep_status.config(
            text=mensagem,
            fg=RED
        )
        messagebox.showwarning(
            "Consulta de CEP",
            mensagem
        )

    # ========================================================
    # SALVAR CLIENTE
    # ========================================================

    def salvar_cliente(self, cliente_id=None):
        dados = {}

        for chave, campo in self.campos_cliente.items():
            dados[chave] = self.texto_do_campo(campo)

        if not dados["nome"]:
            messagebox.showwarning(
                "Campo obrigatório",
                "Preencha Nome / Razão Social."
            )
            return

        conexao = conectar_banco()
        cursor = conexao.cursor()

        campos = [
            "tipo_pessoa",
            "documento",
            "nome",
            "nome_fantasia",
            "endereco",
            "numero",
            "complemento",
            "bairro",
            "cep",
            "cidade",
            "uf",
            "telefone",
            "email",
            "sindico_nome",
            "sindico_telefone",
            "sindico_email",
            "administradora",
            "administradora_email",
            "administradora_telefone",
            "observacoes",
            "status"
        ]

        valores = [dados[campo] for campo in campos]

        if cliente_id is None:
            cursor.execute(
                f"""
                INSERT INTO clientes ({", ".join(campos)}, criado_em)
                VALUES ({", ".join(["?"] * len(campos))}, ?)
                """,
                valores + [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
            )
            cliente_id = cursor.lastrowid
            mensagem = "Cliente cadastrado com sucesso."
        else:
            cursor.execute(
                f"""
                UPDATE clientes
                SET {", ".join([campo + " = ?" for campo in campos])}
                WHERE id = ?
                """,
                valores + [cliente_id]
            )
            mensagem = "Cliente atualizado com sucesso."

        try:
            if dados['tipo_pessoa']=='Jurídica' and dados['status']!='Inativo':
                cad9.sincronizar_cliente_pj(conexao,cliente_id)
            conexao.commit()
        except Exception as erro:
            conexao.rollback()
            messagebox.showerror('Cadastro não salvo',str(erro))
            return
        finally:
            conexao.close()

        messagebox.showinfo("Sucesso", mensagem)
        self.voltar()

    # ========================================================
    # ORDENS DE SERVIÇO
    # ========================================================

    def abrir_os(self):
        self.navegar_para(self.mostrar_ordens_servico)

    def mostrar_ordens_servico(self):
        self.limpar_tela()
        self.tela_atual = self.mostrar_ordens_servico

        self.criar_cabecalho("ORDENS DE SERVIÇO")

        botoes_topo = tk.Frame(self, bg=BLACK)
        botoes_topo.pack(fill="x", padx=30, pady=(5, 12))

        self.criar_botao(
            botoes_topo,
            "+ NOVA OS",
            self.nova_os,
            largura=15
        ).pack(side="left")

        self.criar_botao(
            botoes_topo,
            "HISTÓRICO / PDF",
            self.abrir_historico_os,
            largura=15
        ).pack(side="left", padx=8)

        self.criar_botao(botoes_topo, "ATRIBUIR / TRANSFERIR",
                         self.atribuir_os_selecionada, largura=22,
                         fundo=YELLOW, frente=BLACK).pack(side="left",padx=8)

        tk.Label(
            botoes_topo,
            text="A tela principal mostra apenas OS abertas e pendentes.",
            font=("Arial", 9),
            fg=GRAY,
            bg=BLACK
        ).pack(side="right")

        tk.Label(self,text='Pesquisar OS, cliente, prestador ou situação:',bg=BLACK,fg=GRAY).pack(anchor='w',padx=30)
        self.pesquisa_os=tk.StringVar()
        entrada_os=tk.Entry(self,textvariable=self.pesquisa_os,bg=DARK,fg=WHITE,insertbackground=WHITE)
        entrada_os.pack(fill='x',padx=30,ipady=5,pady=(0,8))
        self.pesquisa_os.trace_add('write',lambda *_:self.carregar_os_ativas())

        tabela_frame = tk.Frame(self, bg=BLACK)
        tabela_frame.pack(fill="both", expand=True, padx=30)

        colunas = (
            "id",
            "numero",
            "cliente",
            "data",
            "valor",
            "pagamento",
            "origem",
            "prestadores",
            "status"
        )

        self.tabela_os = ttk.Treeview(
            tabela_frame,
            columns=colunas,
            show="headings"
        )

        titulos = {
            "id": "ID",
            "numero": "OS",
            "cliente": "Cliente",
            "data": "Abertura",
            "valor": "Valor",
            "pagamento": "Pagamento",
            "origem": "Origem",
            "prestadores": "Prestadores",
            "status": "Status"
        }

        larguras = {
            "id": 50,
            "numero": 90,
            "cliente": 280,
            "data": 115,
            "valor": 105,
            "pagamento": 120,
            "origem": 90,
            "prestadores": 310,
            "status": 125
        }

        for coluna in colunas:
            self.tabela_os.heading(
                coluna,
                text=titulos[coluna]
            )
            self.tabela_os.column(
                coluna,
                width=larguras[coluna],
                anchor="center"
            )

        self.tabela_os.pack(fill="both", expand=True)
        self.tabela_os.bind(
            "<Double-1>",
            lambda _event: self.editar_os_selecionada()
        )

        botoes = tk.Frame(self, bg=BLACK)
        botoes.pack(fill="x", padx=30, pady=15)

        self.criar_botao(
            botoes,
            "ABRIR OS",
            self.editar_os_selecionada,
            largura=14
        ).pack(side="left")

        self.criar_botao(
            botoes, "ALTERAR SITUAÇÃO / ENCERRAR",
            lambda: self.abrir_os_para_encerramento("Concluída"),
            largura=29, fundo=YELLOW, frente=BLACK
        ).pack(side="left", padx=8)
        self.criar_botao(
            botoes, "ATRIBUIR PRESTADOR", self.atribuir_os_selecionada,
            largura=21
        ).pack(side="left", padx=8)

        self.carregar_os_ativas()

    def carregar_os_ativas(self):
        for item in self.tabela_os.get_children():
            self.tabela_os.delete(item)

        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                os.id,
                os.numero_os,
                c.nome AS cliente,
                os.data_abertura,
                os.valor_total,
                os.forma_pagamento,
                os.origem,
                (SELECT GROUP_CONCAT(p.nome, ', ') FROM os_prestadores op JOIN prestadores p ON p.id=op.prestador_id WHERE op.os_id=os.id AND op.ativo=1) AS prestadores,
                resp.nome AS responsavel_atual,
                os.tecnico AS tecnico_legado,
                os.status
            FROM ordens_servico os
            JOIN clientes c ON c.id = os.cliente_id
            LEFT JOIN os_responsaveis atribuicao ON atribuicao.os_id=os.id
            LEFT JOIN prestadores resp ON resp.id=atribuicao.prestador_id
            WHERE os.status IN ('Aberta', 'Pendente')
            ORDER BY os.id DESC
        """)

        registros = cursor.fetchall()
        conexao.close()

        busca=getattr(self,'pesquisa_os',None)
        termo=busca.get().casefold().strip() if busca else ''
        for registro in registros:
            texto=' '.join(str(registro[k] or '') for k in ('numero_os','cliente','prestadores','responsavel_atual','status','forma_pagamento','tecnico_legado')).casefold()
            if termo and termo not in texto:continue
            icone, _cor = self.status_visual(registro["status"])
            origem = registro["origem"] or "App"

            self.tabela_os.insert(
                "",
                "end",
                values=(
                    registro["id"],
                    registro["numero_os"],
                    registro["cliente"],
                    registro["data_abertura"],
                    self.dinheiro(registro["valor_total"]),
                    registro["forma_pagamento"],
                    "🌐 Portal" if origem == "Portal" else "App",
                    (registro['responsavel_atual'] + ' (atual)' if registro['responsavel_atual'] else
                     'Não atribuído') +
                    (' | Equipe: ' + registro['prestadores'] if registro['prestadores'] else
                     (' | Técnico: ' + registro['tecnico_legado'] if registro['tecnico_legado'] else '')),
                    f"{icone} {registro['status']}"
                )
            )

    def nova_os(self):
        self.navegar_para(
            lambda: self.mostrar_formulario_os()
        )

    def editar_os_selecionada(self):
        selecionado = self.tabela_os.selection()

        if not selecionado:
            messagebox.showwarning(
                "Seleção",
                "Selecione uma ordem de serviço."
            )
            return

        valores = self.tabela_os.item(selecionado[0])["values"]
        os_id = valores[0]

        self.navegar_para(
            lambda: self.mostrar_formulario_os(os_id=os_id)
        )

    def marcar_os_pendente(self):
        self.abrir_os_para_encerramento("Pendente")

    def finalizar_os_selecionada(self):
        self.abrir_os_para_encerramento("Concluída")

    def abrir_os_para_encerramento(self, destino):
        selecionado = self.tabela_os.selection()
        if not selecionado:
            messagebox.showwarning("Seleção", "Selecione uma ordem de serviço.")
            return
        os_id = int(self.tabela_os.item(selecionado[0])["values"][0])
        self.navegar_para(lambda: self.mostrar_formulario_os(os_id=os_id, modo_encerramento=destino))

    def concluir_os(self, os_id, janela=None):
        """Compatibilidade com chamadas legadas; usa o mesmo fluxo do portal web.

        Não cria cobrança recebida automaticamente e exige relatório já registrado.
        """
        try:
            with ext.db(BANCO) as c:
                c.execute('BEGIN IMMEDIATE')
                ultimo=c.execute("""SELECT descricao FROM os_eventos WHERE os_id=?
                         AND acao='Relatório técnico' ORDER BY id DESC LIMIT 1""",(os_id,)).fetchone()
                relato=ultimo['descricao'] if ultimo else ''
                fluxo.aplicar_encerramento(c,os_id,'Concluída',relato,ator='Administrador desktop')
        except Exception as erro:
            messagebox.showerror('Não foi possível finalizar',str(erro))
            return
        if janela is not None: janela.destroy()
        self.mostrar_ordens_servico()
        self.publicar_pdf_em_segundo_plano(os_id, enviar_email=True)

    # ========================================================
    # FORMULÁRIO DE OS
    # ========================================================

    def mostrar_formulario_os(self, cliente_id=None, os_id=None, modo_encerramento=None):
        self.limpar_tela()
        self.tela_atual = lambda: self.mostrar_formulario_os(
            cliente_id=cliente_id,
            os_id=os_id,
            modo_encerramento=modo_encerramento
        )

        titulo = "NOVA ORDEM DE SERVIÇO" if os_id is None else "EDITAR ORDEM DE SERVIÇO"
        self.criar_cabecalho(titulo)

        conexao = conectar_banco()
        cursor = conexao.cursor()

        clientes = cursor.execute(
            "SELECT id, nome FROM clientes WHERE status != 'Inativo' ORDER BY nome"
        ).fetchall()

        dados = None
        materiais = []
        if os_id is not None:
            dados = cursor.execute(
                """
                SELECT *
                FROM ordens_servico
                WHERE id = ?
                """,
                (os_id,)
            ).fetchone()

            materiais = cursor.execute(
                """
                SELECT item, quantidade, valor_unitario, valor_total
                FROM materiais_os
                WHERE os_id = ?
                ORDER BY id
                """,
                (os_id,)
            ).fetchall()

        conexao.close()

        if not clientes:
            messagebox.showwarning(
                "Nenhum cliente",
                "Cadastre pelo menos um cliente antes de criar uma OS."
            )
            self.voltar()
            return

        container = tk.Frame(self, bg=BLACK)
        container.pack(fill="both", expand=True, padx=35, pady=5)

        canvas = tk.Canvas(
            container,
            bg=BLACK,
            highlightthickness=0
        )
        scrollbar = tk.Scrollbar(
            container,
            orient="vertical",
            command=canvas.yview
        )

        formulario = tk.Frame(canvas, bg=BLACK)

        formulario.bind(
            "<Configure>",
            lambda event: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        janela_formulario = canvas.create_window(
            (0, 0),
            window=formulario,
            anchor="nw"
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(
                janela_formulario,
                width=event.width
            )
        )
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.campos_os = {}
        self.materiais_os = [dict(registro) for registro in materiais]
        # Fotos selecionadas são guardadas em memória até o encerramento ser confirmado.
        self.imagens_pendentes_os = []

        self.criar_titulo_secao(formulario, "IDENTIFICAÇÃO")

        if dados is not None and (dados["origem"] or "App") == "Portal":
            aviso = tk.Frame(
                formulario,
                bg="#1E1A00",
                padx=14,
                pady=10,
                highlightthickness=1,
                highlightbackground=YELLOW
            )
            aviso.pack(fill="x", pady=(0, 10))

            tk.Label(
                aviso,
                text="🌐 SOLICITAÇÃO RECEBIDA PELO PORTAL DO CLIENTE",
                font=("Arial", 9, "bold"),
                fg=YELLOW,
                bg="#1E1A00"
            ).pack(anchor="w")

            tk.Label(
                aviso,
                text=(
                    f"Urgência: {dados['urgencia'] or 'Normal'}   •   "
                    f"Contato preferido: {dados['contato_preferido'] or 'Não informado'}"
                ),
                font=("Arial", 9),
                fg=WHITE,
                bg="#1E1A00"
            ).pack(anchor="w", pady=(3, 0))

        nomes_clientes = [f"{cliente['id']} - {cliente['nome']}" for cliente in clientes]

        cliente_selecionado = cliente_id

        if dados is not None:
            cliente_selecionado = dados["cliente_id"]

        texto_cliente = ""
        for cliente in clientes:
            if cliente["id"] == cliente_selecionado:
                texto_cliente = f"{cliente['id']} - {cliente['nome']}"
                break

        if not texto_cliente:
            texto_cliente = nomes_clientes[0]

        self.campos_os["cliente"] = self.criar_campo(
            formulario,
            "Cliente:",
            "cliente",
            texto_cliente,
            nomes_clientes
        )

        self.campos_os["tecnico"] = self.criar_campo(
            formulario,
            "Atendido por (cliente no local):",
            "tecnico",
            dados["tecnico"] if dados else ""
        )
        if os_id is not None:
            with ext.db(BANCO) as conn:
                responsavel = conn.execute('''SELECT p.nome FROM os_responsaveis r
                              JOIN prestadores p ON p.id=r.prestador_id WHERE r.os_id=?''',(os_id,)).fetchone()
            linha_atribuicao=tk.Frame(formulario,bg=BLACK)
            linha_atribuicao.pack(fill='x',pady=10)
            self.label_responsavel_os=tk.Label(linha_atribuicao,
                     text='Responsável no portal: '+(responsavel['nome'] if responsavel else 'Não atribuído'),
                     fg=WHITE,bg=BLACK,font=('Arial',11,'bold'))
            self.label_responsavel_os.pack(side='left')
            self.criar_botao(linha_atribuicao,'ATRIBUIR / TRANSFERIR',
                             lambda: self.abrir_dialogo_atribuicao(os_id),largura=24,
                             fundo=YELLOW,frente=BLACK).pack(side='left',padx=12)

        self.campos_os["forma_pagamento"] = self.criar_campo(
            formulario,
            "Forma de pagamento:",
            "forma_pagamento",
            dados["forma_pagamento"] if dados else "PIX",
            ["PIX", "Transferência", "Dinheiro", "Cartão", "Boleto", "Outro"]
        )

        self.criar_titulo_secao(formulario, "SERVIÇO")

        tk.Label(
            formulario,
            text="Descrição do serviço:",
            font=("Arial", 10),
            fg=WHITE,
            bg=BLACK
        ).pack(anchor="w", pady=(3, 3))

        self.campos_os["descricao"] = tk.Text(
            formulario,
            height=6,
            bg=DARKER,
            fg=WHITE,
            insertbackground=WHITE,
            relief="flat",
            font=("Arial", 10)
        )
        self.campos_os["descricao"].pack(fill="x", pady=(0, 12))
        if os_id is not None and dados is not None and dados['origem']=='Portal':
            with ext.db(BANCO) as cc:
                original=cc.execute('SELECT descricao_original FROM os_solicitacoes WHERE os_id=?',(os_id,)).fetchone()
            if original:
                self.campos_os['descricao'].configure(state='normal')
                self.campos_os['descricao'].delete('1.0','end')
                self.campos_os['descricao'].insert('1.0',original['descricao_original'])
                self.campos_os['descricao'].configure(state='disabled')

        if dados:
            self.campos_os["descricao"].insert(
                "1.0",
                dados["descricao"] or ""
            )

        self.criar_titulo_secao(formulario, "MATERIAIS UTILIZADOS")

        tabela_materiais_frame = tk.Frame(formulario, bg=BLACK)
        tabela_materiais_frame.pack(fill="x")

        colunas_materiais = ("item", "quantidade", "unitario", "total")

        self.tabela_materiais_os = ttk.Treeview(
            tabela_materiais_frame,
            columns=colunas_materiais,
            show="headings",
            height=5
        )

        titulos_materiais = {
            "item": "Item / Descrição",
            "quantidade": "Qtd.",
            "unitario": "Valor unitário",
            "total": "Total"
        }

        larguras_materiais = {
            "item": 420,
            "quantidade": 90,
            "unitario": 150,
            "total": 150
        }

        for coluna in colunas_materiais:
            self.tabela_materiais_os.heading(
                coluna,
                text=titulos_materiais[coluna]
            )
            self.tabela_materiais_os.column(
                coluna,
                width=larguras_materiais[coluna],
                anchor="center"
            )

        self.tabela_materiais_os.pack(fill="x")
        self.tabela_materiais_os.bind(
            "<Double-1>",
            lambda _event: self.editar_material_os()
        )

        barra_materiais = tk.Frame(formulario, bg=BLACK)
        barra_materiais.pack(fill="x", pady=6)

        self.criar_botao(
            barra_materiais,
            "+ ADICIONAR ITEM",
            self.adicionar_material_os,
            largura=17
        ).pack(side="left")
        self.criar_botao(
            barra_materiais,
            "DO ESTOQUE",
            self.adicionar_material_do_estoque_os,
            largura=16
        ).pack(side="left",padx=7)

        self.criar_botao(
            barra_materiais,
            "EDITAR ITEM",
            self.editar_material_os,
            largura=14
        ).pack(side="left", padx=8)

        self.criar_botao(
            barra_materiais,
            "REMOVER ITEM",
            self.remover_material_os,
            largura=15,
            frente=RED
        ).pack(side="left")

        self.label_materiais_total = tk.Label(
            barra_materiais,
            text="",
            font=("Arial", 10, "bold"),
            fg=YELLOW,
            bg=BLACK
        )
        self.label_materiais_total.pack(side="right")

        self.criar_titulo_secao(formulario, "VALORES")

        self.campos_os["mao_obra"] = self.criar_campo(
            formulario,
            "Mão de obra (R$):",
            "mao_obra",
            self.dinheiro(dados["valor_mao_obra"]).replace("R$", "").strip() if dados else "0,00"
        )

        self.campos_os["materiais_valor"] = self.criar_campo(
            formulario,
            "Materiais (R$):",
            "materiais_valor",
            self.dinheiro(dados["valor_materiais"]).replace("R$", "").strip() if dados else "0,00"
        )

        self.campos_os["total"] = self.criar_campo(
            formulario,
            "Valor total (R$):",
            "total",
            self.dinheiro(dados["valor_total"]).replace("R$", "").strip() if dados else "0,00"
        )

        self.campos_os["mao_obra"].bind(
            "<KeyRelease>",
            lambda _event: self.recalcular_total_os()
        )
        self.campos_os["mao_obra"].bind(
            "<FocusOut>",
            lambda _event: self.recalcular_total_os()
        )
        self.campos_os["materiais_valor"].bind(
            "<KeyRelease>",
            lambda _event: self.recalcular_total_os()
        )
        self.campos_os["materiais_valor"].bind(
            "<FocusOut>",
            lambda _event: self.recalcular_total_os()
        )

        self.atualizar_tabela_materiais(
            recalcular=bool(self.materiais_os)
        )

        self.criar_titulo_secao(formulario, "OBSERVAÇÕES")

        self.campos_os["observacoes"] = tk.Text(
            formulario,
            height=4,
            bg=DARKER,
            fg=WHITE,
            insertbackground=WHITE,
            relief="flat",
            font=("Arial", 10)
        )
        self.campos_os["observacoes"].pack(fill="x")

        if dados:
            self.campos_os["observacoes"].insert(
                "1.0",
                dados["observacoes"] or ""
            )

        # Relatório técnico e imagens ficam na própria edição da OS.
        if os_id is not None:
            with ext.db(BANCO) as cc:
                andamento=cc.execute('SELECT iniciado_em,rascunho FROM os_atendimentos WHERE os_id=?',(os_id,)).fetchone()
            if not andamento or not andamento['iniciado_em']:
                self.criar_botao(formulario,'▶ INICIAR ATENDIMENTO',lambda:self.iniciar_os_desktop(os_id),largura=26,fundo=YELLOW,frente=BLACK).pack(anchor='w',pady=8)
            else:
                tk.Label(formulario,text='Atendimento iniciado em '+str(andamento['iniciado_em']),bg=BLACK,fg=GREEN).pack(anchor='w')
            self.criar_titulo_secao(formulario, "SITUAÇÃO E RELATÓRIO DE ATENDIMENTO")
            tk.Label(formulario, text="Descreva o atendimento, diagnóstico, o que foi feito e o motivo da pendência, se houver.",
                     bg=BLACK, fg=WHITE, font=("Arial", 10), anchor="w", wraplength=850).pack(fill="x", pady=(0, 7))
            self.relatorio_tecnico_os = tk.Text(formulario, height=7, bg=DARKER, fg=WHITE,
                                                insertbackground=WHITE, relief="flat", font=("Arial", 11),
                                                padx=12, pady=10, wrap="word")
            self.relatorio_tecnico_os.pack(fill="x", pady=(0, 10))
            self.criar_titulo_secao(formulario, "MOTIVO — CANCELAMENTO / NÃO REALIZAÇÃO")
            self.motivo_encerramento_os = tk.Text(formulario,height=3,bg=DARKER,fg=WHITE,
                insertbackground=WHITE,relief="flat",font=("Arial",11),padx=12,pady=8,wrap="word")
            self.motivo_encerramento_os.pack(fill="x",pady=(0,10))
            with ext.db(BANCO) as cc:
                fechamento=cc.execute('SELECT motivo,relatorio FROM os_encerramentos WHERE os_id=?',(os_id,)).fetchone()
                if fechamento:
                    self.motivo_encerramento_os.insert('1.0',fechamento['motivo'] or '')
                    self.relatorio_tecnico_os.insert('1.0',fechamento['relatorio'] or '')
                elif andamento and andamento['rascunho']:
                    self.relatorio_tecnico_os.insert('1.0',andamento['rascunho'])
            tk.Label(formulario,text='Informe o motivo obrigatório se o serviço for Cancelado.',
                     fg=GRAY,bg=BLACK,font=('Arial',9)).pack(anchor='w')
            # Anexos são adicionados apenas durante o fluxo de encerramento, e
            # nunca por um menu isolado de relatórios.
            self.area_encerramento_os = tk.Frame(formulario, bg=BLACK)
            self.area_encerramento_os.pack(fill="x", pady=(8, 10))
            self.status_encerramento_os = tk.StringVar(value=modo_encerramento if modo_encerramento in ("Concluída", "Pendente", "Cancelada") else "Concluída")
            if dados["status"] in ext.ATIVAS:
                tk.Label(self.area_encerramento_os, text="Escolha a situação do atendimento:",
                         bg=BLACK, fg=WHITE, font=("Arial", 11, "bold")).pack(anchor="w", pady=(4, 7))
                linha_status=tk.Frame(self.area_encerramento_os,bg=BLACK)
                linha_status.pack(fill="x")
                for texto,valor in (("Concluído","Concluída"),("Pendente","Pendente"),("Cancelado","Cancelada")):
                    tk.Radiobutton(linha_status, text=texto, variable=self.status_encerramento_os,
                                   value=valor, bg=BLACK, fg=WHITE, selectcolor=DARK,
                                   activebackground=BLACK, activeforeground=YELLOW,
                                   command=self.atualizar_secao_encerramento_os,
                                   font=("Arial",11,"bold")).pack(side="left",padx=(0,18))
                self.fotos_encerramento_os=tk.Frame(self.area_encerramento_os,bg=BLACK)
                self.fotos_encerramento_os.pack(fill="x",pady=(10,0))
                self.criar_botao(self.fotos_encerramento_os,"+ ANEXAR IMAGENS AO RELATÓRIO",
                                 lambda:self.anexar_imagens_formulario(os_id),largura=32,
                                 fundo=YELLOW,frente=BLACK).pack(side="left")
                self.criar_botao(self.fotos_encerramento_os,"REMOVER FOTO SELECIONADA",
                                 lambda:self.remover_imagens_pendentes_os(os_id),largura=29,
                                 fundo=DARK,frente=WHITE).pack(side="left",padx=8)
                self.label_anexos_os=tk.Label(self.fotos_encerramento_os,bg=BLACK,fg=GRAY,
                                              font=("Arial",10),anchor="w")
                self.label_anexos_os.pack(fill="x",pady=(6,0))
                self.atualizar_label_anexos_os(os_id)
                self.atualizar_secao_encerramento_os()
            else:
                tk.Label(self.area_encerramento_os, text="OS encerrada — PDF disponível em Histórico e Relatórios.",
                         bg=BLACK,fg=GREEN,font=("Arial",10)).pack(anchor="w")

        botoes = tk.Frame(formulario, bg=BLACK)
        botoes.pack(fill="x", pady=22)

        self.criar_botao(
            botoes,
            "← CANCELAR",
            self.voltar,
            largura=16,
            frente=WHITE
        ).pack(side="left")

        self.criar_botao(
            botoes,
            "SALVAR RASCUNHO" if os_id is not None else "SALVAR OS",
            lambda: self.salvar_os(os_id),
            largura=18,
            fundo=YELLOW,
            frente=BLACK
        ).pack(side="right")

        if os_id is not None and dados["status"] in ext.ATIVAS:
            self.criar_botao(botoes, "CONFIRMAR SITUAÇÃO DA OS",
                lambda:self.salvar_os(os_id,self.status_encerramento_os.get()),
                largura=29,frente=GREEN).pack(side="right",padx=8)

    def atualizar_secao_encerramento_os(self):
        """Anexos disponíveis apenas ao fechar (não ao deixar pendente)."""
        if not hasattr(self,"fotos_encerramento_os"):
            return
        situacao=self.status_encerramento_os.get()
        if situacao in fluxo.FIM and situacao != "Não realizada":
            self.fotos_encerramento_os.pack(fill="x",pady=(10,0))
        else:
            self.fotos_encerramento_os.pack_forget()

    def total_materiais_os(self):
        total = 0.0

        for material in self.materiais_os:
            try:
                quantidade = float(material.get("quantidade") or 0)
                unitario = float(material.get("valor_unitario") or 0)
            except (TypeError, ValueError):
                continue

            total += quantidade * unitario

        return total

    def atualizar_tabela_materiais(self, recalcular=True):
        if not hasattr(self, "tabela_materiais_os"):
            return

        for item in self.tabela_materiais_os.get_children():
            self.tabela_materiais_os.delete(item)

        for material in self.materiais_os:
            quantidade = float(material.get("quantidade") or 0)
            unitario = float(material.get("valor_unitario") or 0)

            if quantidade == int(quantidade):
                quantidade_texto = str(int(quantidade))
            else:
                quantidade_texto = self.valor_texto(quantidade)

            self.tabela_materiais_os.insert(
                "",
                "end",
                values=(
                    material.get("item", ""),
                    quantidade_texto,
                    self.dinheiro(unitario),
                    self.dinheiro(quantidade * unitario)
                )
            )

        total = self.total_materiais_os()

        if hasattr(self, "label_materiais_total"):
            self.label_materiais_total.config(
                text=f"Total em materiais: {self.dinheiro(total)}"
            )

        campo_materiais = self.campos_os.get("materiais_valor")

        if campo_materiais is None:
            return

        if self.materiais_os:
            campo_materiais.configure(state="normal")
            campo_materiais.delete(0, "end")
            campo_materiais.insert(0, self.valor_texto(total))
            campo_materiais.configure(
                state="readonly",
                readonlybackground=DARKER
            )
        else:
            era_calculado = str(campo_materiais.cget("state")) == "readonly"
            campo_materiais.configure(state="normal")

            if era_calculado:
                campo_materiais.delete(0, "end")
                campo_materiais.insert(0, "0,00")

        if recalcular:
            self.recalcular_total_os()

    def recalcular_total_os(self):
        if not hasattr(self, "campos_os"):
            return

        campos = self.campos_os

        if not all(
            chave in campos
            for chave in ("mao_obra", "materiais_valor", "total")
        ):
            return

        mao_obra = self.valor_monetario(
            self.texto_do_campo(campos["mao_obra"])
        )

        if self.materiais_os:
            materiais = self.total_materiais_os()
        else:
            materiais = self.valor_monetario(
                self.texto_do_campo(campos["materiais_valor"])
            )

        total = mao_obra + materiais

        campos["total"].delete(0, "end")
        campos["total"].insert(0, self.valor_texto(total))

    def adicionar_material_os(self):
        self.abrir_dialogo_material_os()

    def editar_material_os(self):
        selecionado = self.tabela_materiais_os.selection()

        if not selecionado:
            messagebox.showwarning(
                "Seleção",
                "Selecione um material para editar."
            )
            return

        indice = self.tabela_materiais_os.index(selecionado[0])
        self.abrir_dialogo_material_os(indice)

    def remover_material_os(self):
        selecionado = self.tabela_materiais_os.selection()

        if not selecionado:
            messagebox.showwarning(
                "Seleção",
                "Selecione um material para remover."
            )
            return

        indice = self.tabela_materiais_os.index(selecionado[0])
        material = self.materiais_os[indice]

        confirmar = messagebox.askyesno(
            "Remover material",
            f"Remover o item:\n\n{material.get('item', '')}?"
        )

        if not confirmar:
            return

        self.materiais_os.pop(indice)
        self.atualizar_tabela_materiais()

    def abrir_dialogo_material_os(self, indice=None):
        janela = tk.Toplevel(self)
        titulo = "ADICIONAR MATERIAL" if indice is None else "EDITAR MATERIAL"

        janela.title(titulo)
        janela.geometry("440x340")
        janela.configure(bg=BLACK)
        janela.transient(self)
        janela.grab_set()

        tk.Label(
            janela,
            text=titulo,
            font=("Arial", 14, "bold"),
            fg=YELLOW,
            bg=BLACK
        ).pack(pady=(20, 12))

        formulario = tk.Frame(janela, bg=BLACK)
        formulario.pack(fill="x", padx=30)

        atual = {}
        if indice is not None:
            atual = self.materiais_os[indice]

        campos = {}

        def criar_campo_material(rotulo, chave, valor):
            tk.Label(
                formulario,
                text=rotulo,
                font=("Arial", 10),
                fg=WHITE,
                bg=BLACK
            ).pack(anchor="w", pady=(5, 2))

            entrada = tk.Entry(
                formulario,
                font=("Arial", 10),
                bg=DARKER,
                fg=WHITE,
                insertbackground=WHITE,
                relief="flat"
            )
            entrada.insert(0, valor)
            entrada.pack(fill="x", ipady=6)
            campos[chave] = entrada

        criar_campo_material(
            "Item / descrição:",
            "item",
            atual.get("item", "")
        )
        criar_campo_material(
            "Quantidade:",
            "quantidade",
            self.valor_texto(atual.get("quantidade", 1))
        )
        criar_campo_material(
            "Valor unitário (R$):",
            "valor_unitario",
            self.valor_texto(atual.get("valor_unitario", 0))
        )

        def confirmar():
            item = campos["item"].get().strip()
            quantidade = self.valor_monetario(
                campos["quantidade"].get()
            )
            valor_unitario = self.valor_monetario(
                campos["valor_unitario"].get()
            )

            if not item:
                messagebox.showwarning(
                    "Item obrigatório",
                    "Informe a descrição do material."
                )
                return

            if quantidade <= 0:
                messagebox.showwarning(
                    "Quantidade inválida",
                    "A quantidade deve ser maior que zero."
                )
                return

            registro = {
                "item": item,
                "quantidade": quantidade,
                "valor_unitario": valor_unitario,
                "valor_total": quantidade * valor_unitario
            }

            if indice is None:
                self.materiais_os.append(registro)
            else:
                self.materiais_os[indice] = registro

            janela.destroy()
            self.atualizar_tabela_materiais()

        botoes = tk.Frame(janela, bg=BLACK)
        botoes.pack(pady=18)

        self.criar_botao(
            botoes,
            "CANCELAR",
            janela.destroy,
            largura=14,
            frente=WHITE
        ).pack(side="left", padx=6)

        self.criar_botao(
            botoes,
            "CONFIRMAR",
            confirmar,
            largura=15,
            fundo=YELLOW,
            frente=BLACK
        ).pack(side="left", padx=6)

        campos["item"].focus_set()

    def iniciar_os_desktop(self,os_id):
        try:
            aten.iniciar(BANCO,os_id)
            messagebox.showinfo('Atendimento iniciado','Data e horário de início foram registrados.')
            self.mostrar_formulario_os(os_id=os_id)
        except Exception as erro:
            messagebox.showerror('Não foi possível iniciar',str(erro))

    def salvar_os(self, os_id=None, acao_status=None):
        cliente_texto = self.texto_do_campo(self.campos_os["cliente"])

        try:
            cliente_id = int(cliente_texto.split(" - ", 1)[0])
        except (ValueError, IndexError):
            messagebox.showwarning(
                "Cliente inválido",
                "Selecione um cliente válido."
            )
            return

        descricao = self.texto_do_campo(self.campos_os["descricao"])

        if not descricao:
            messagebox.showwarning(
                "Descrição",
                "Preencha a descrição do serviço."
            )
            return

        tecnico = self.texto_do_campo(self.campos_os["tecnico"])
        pagamento = self.texto_do_campo(self.campos_os["forma_pagamento"])
        mao_obra = self.valor_monetario(
            self.texto_do_campo(self.campos_os["mao_obra"])
        )
        materiais = self.valor_monetario(
            self.texto_do_campo(self.campos_os["materiais_valor"])
        )

        if self.materiais_os:
            materiais = self.total_materiais_os()

        total_texto = self.texto_do_campo(self.campos_os["total"])
        total = self.valor_monetario(total_texto)

        if not total_texto or total == 0:
            total = mao_obra + materiais

        observacoes = self.texto_do_campo(self.campos_os["observacoes"])
        relato = (self.relatorio_tecnico_os.get("1.0", "end").strip()
                  if os_id is not None and hasattr(self, "relatorio_tecnico_os") else "")
        motivo = (self.motivo_encerramento_os.get('1.0','end').strip()
                  if os_id is not None and hasattr(self,'motivo_encerramento_os') else '')
        if acao_status in ('Cancelada','Não realizada') and not motivo:
            messagebox.showwarning('Motivo obrigatório','Descreva o motivo do cancelamento ou da não realização.')
            return
        if acao_status and not relato:
            messagebox.showwarning("Relatório obrigatório",
                                   "Preencha o relatório técnico antes de mudar o status da OS.")
            return
        if acao_status in fluxo.FIM and not messagebox.askyesno(
                'Confirmar encerramento', f'Salvar os dados e marcar a OS como {acao_status}?\n\nO PDF será publicado para o cliente. Pagamentos não são confirmados automaticamente.'):
            return

        conexao = conectar_banco()
        cursor = conexao.cursor()
        anterior_os = None
        materiais_anteriores = []
        if os_id is not None:
            anterior_os = cursor.execute('SELECT * FROM ordens_servico WHERE id=?', (os_id,)).fetchone()
            if anterior_os is None:
                conexao.close()
                messagebox.showerror('OS não encontrada', 'A OS já não existe no banco de dados.')
                return
            if anterior_os['origem']=='Portal':
                original=cursor.execute('SELECT cliente_id,descricao_original FROM os_solicitacoes WHERE os_id=?',(os_id,)).fetchone()
                if original:
                    cliente_id=original['cliente_id']
                    descricao=original['descricao_original']
            materiais_anteriores = [dict(m) for m in cursor.execute(
                'SELECT item,quantidade,valor_unitario FROM materiais_os WHERE os_id=? ORDER BY id',
                (os_id,)).fetchall()]

        if os_id is None:
            numero_os = proximo_numero_os(cursor)
            data_abertura = datetime.now().strftime("%d/%m/%Y %H:%M")

            cursor.execute(
                """
                INSERT INTO ordens_servico
                (
                    numero_os,
                    cliente_id,
                    data_abertura,
                    tecnico,
                    descricao,
                    valor_mao_obra,
                    valor_materiais,
                    valor_total,
                    forma_pagamento,
                    status,
                    observacoes,
                    criado_em
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    numero_os,
                    cliente_id,
                    data_abertura,
                    tecnico,
                    descricao,
                    mao_obra,
                    materiais,
                    total,
                    pagamento,
                    "Aberta",
                    observacoes,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            )

            mensagem = f"{numero_os} criada com sucesso."

        else:
            cursor.execute(
                """
                UPDATE ordens_servico
                SET cliente_id = ?,
                    tecnico = ?,
                    descricao = ?,
                    valor_mao_obra = ?,
                    valor_materiais = ?,
                    valor_total = ?,
                    forma_pagamento = ?,
                    observacoes = ?,
                    atualizado_em = ?
                WHERE id = ?
                """,
                (
                    cliente_id,
                    tecnico,
                    descricao,
                    mao_obra,
                    materiais,
                    total,
                    pagamento,
                    observacoes,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    os_id
                )
            )
            mensagem = "Ordem de serviço atualizada."

        os_salvo_id = os_id if os_id is not None else cursor.lastrowid
        if os_id is None:
            aten.registrar_solicitacao(cursor,os_salvo_id,cliente_id,descricao,observacoes,'App')

        anteriores_tuplas = [(m['item'],float(m['quantidade'] or 0),float(m['valor_unitario'] or 0)) for m in materiais_anteriores]
        atuais_tuplas = [(m.get('item',''),float(m.get('quantidade') or 0),float(m.get('valor_unitario') or 0)) for m in self.materiais_os]
        if anteriores_tuplas != atuais_tuplas:
            cursor.execute("DELETE FROM materiais_os WHERE os_id = ?",(os_salvo_id,))

        for material in (self.materiais_os if anteriores_tuplas != atuais_tuplas else []):
            quantidade = float(material.get("quantidade") or 0)
            valor_unitario = float(material.get("valor_unitario") or 0)

            cursor.execute(
                """
                INSERT INTO materiais_os
                (
                    os_id,
                    item,
                    quantidade,
                    valor_unitario,
                    valor_total
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    os_salvo_id,
                    material.get("item", ""),
                    quantidade,
                    valor_unitario,
                    quantidade * valor_unitario
                )
            )

        # Consumo/estorno de materiais na mesma transação da OS.
        estoque.reconciliar_os_conexao(cursor,os_salvo_id,'Desktop')
        # Auditoria de alterações administrativas: não apaga o histórico anterior.
        if anterior_os is not None:
            antes = {
                'cliente_id': anterior_os['cliente_id'], 'tecnico': anterior_os['tecnico'] or '',
                'descricao': anterior_os['descricao'] or '',
                'valor_mao_obra': float(anterior_os['valor_mao_obra'] or 0),
                'valor_materiais': float(anterior_os['valor_materiais'] or 0),
                'valor_total': float(anterior_os['valor_total'] or 0),
                'forma_pagamento': anterior_os['forma_pagamento'] or '',
                'observacoes': anterior_os['observacoes'] or ''
            }
            depois = {'cliente_id': cliente_id, 'tecnico': tecnico,
                      'descricao': descricao, 'valor_mao_obra': mao_obra,
                      'valor_materiais': materiais, 'valor_total': total,
                      'forma_pagamento': pagamento, 'observacoes': observacoes}
            alteracoes = []
            for chave in antes:
                if antes[chave] != depois[chave]:
                    alteracoes.append(f'{chave}: {antes[chave]!s} → {depois[chave]!s}')
            if alteracoes:
                ext.evento(cursor,os_salvo_id,'Edição administrativa','; '.join(alteracoes))
        if os_id is None:
            ext.evento(cursor,os_salvo_id,'OS criada','Ordem de serviço cadastrada pelo administrador.')
        materiais_novos = [dict(item=m.get('item',''),quantidade=float(m.get('quantidade') or 0),
                                 valor_unitario=float(m.get('valor_unitario') or 0)) for m in self.materiais_os]
        antigos = [(m['item'],float(m['quantidade'] or 0),float(m['valor_unitario'] or 0)) for m in materiais_anteriores]
        novos = [(m['item'],m['quantidade'],m['valor_unitario']) for m in materiais_novos]
        if antigos != novos:
            ext.evento(cursor,os_salvo_id,'Materiais atualizados',
                       'Anterior: '+str(antigos)[:1500]+' | Novo: '+str(novos)[:1500])
        if os_id is not None:
            aten.salvar_rascunho(cursor,os_salvo_id,relato,'Administrador desktop')
        if relato and acao_status:
            ext.evento(cursor, os_salvo_id, "Relatório técnico", relato)
        if acao_status == "Pendente":
            cursor.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=? AND status IN ('Aberta','Pendente')", (os_salvo_id,))
            if cursor.rowcount != 1:
                conexao.rollback()
                conexao.close()
                messagebox.showerror("Status inválido", "Esta OS não pode ser colocada como pendente.")
                return
            ext.evento(cursor, os_salvo_id, "Pendência", "OS mantida pendente pelo administrador. Consulte o relatório técnico.")
        conexao.commit()
        conexao.close()
        if acao_status in fluxo.FIM:
            # Salva o encerramento primeiro; publica PDF em thread para não congelar Tkinter.
            try:
                with ext.db(BANCO) as cc:
                    cc.execute('BEGIN IMMEDIATE')
                    for caminho in getattr(self,'imagens_pendentes_os',[]):
                        with open(caminho,'rb') as fh:
                            ext.registrar_imagem_transacao(cc,os_salvo_id,None,
                                os.path.basename(caminho),fh.read())
                    fluxo.aplicar_encerramento(cc,os_salvo_id,acao_status,relato,motivo,
                                              ator='Administrador desktop')
            except Exception as erro:
                messagebox.showerror('Encerramento não realizado',
                    f'Os dados da OS foram salvos, mas não foi possível encerrá-la: {erro}')
                return
            self.mostrar_ordens_servico()
            self.publicar_pdf_em_segundo_plano(os_salvo_id, enviar_email=(acao_status=='Concluída'))
            return
        if anterior_os and anterior_os['status'] in fluxo.FIM and not acao_status:
            self.mostrar_historico_os()
            self.publicar_pdf_em_segundo_plano(os_salvo_id)
            return
        messagebox.showinfo("Sucesso", "OS atualizada e registrada." if acao_status else mensagem)
        self.mostrar_ordens_servico() if acao_status else self.voltar()

    def publicar_pdf_em_segundo_plano(self, os_id, enviar_email=False):
        """Não bloqueia o loop do Tk. Todas as mensagens Tk ficam no thread principal."""
        respostas=queue.Queue()
        def executar():
            try:
                caminho=fluxo.publicar_relatorio(BANCO,os_id)
                if enviar_email:
                    try:
                        import gmail_service
                        gmail_service.enviar_relatorio_os_concluida(BANCO, os_id)
                    except Exception:
                        pass
                respostas.put(('ok',caminho))
            except Exception as e:
                import traceback
                try:
                    pasta=os.path.join(PASTA_APP,'logs')
                    os.makedirs(pasta,exist_ok=True)
                    with open(os.path.join(pasta,'pdf_desktop.log'),'a',encoding='utf-8') as log:
                        log.write('\n'+datetime.now().isoformat()+'\n'+traceback.format_exc()+'\n')
                except OSError: pass
                respostas.put(('erro',str(e)))
        threading.Thread(target=executar,daemon=True).start()
        def verificar():
            try:status,info=respostas.get_nowait()
            except queue.Empty:
                if self.winfo_exists():self.after(200,verificar)
                return
            if status=='ok':
                if getattr(self, 'tela_atual', None) == self.mostrar_historico_os:
                    self.carregar_historico_os()
                messagebox.showinfo('Relatório publicado',
                    'A OS foi encerrada e o relatório PDF está liberado no portal do cliente.\n\n'+info)
            else:
                messagebox.showwarning('OS encerrada, PDF pendente',
                    'A OS foi encerrada, mas não foi possível publicar o PDF.\n\n'
                    +info+'\n\nUse o menu de documentos para tentar novamente.')
        self.after(200,verificar)

    def finalizar_os_por_id(self, os_id):
        self.navegar_para(lambda: self.mostrar_formulario_os(os_id=os_id, modo_encerramento="Concluída"))

    def atualizar_label_anexos_os(self, os_id):
        try:
            with ext.db(BANCO) as conn:
                fotos=conn.execute('SELECT nome_original FROM os_anexos WHERE os_id=? ORDER BY id DESC',
                                   (os_id,)).fetchall()
            pendentes=getattr(self,'imagens_pendentes_os',[])
            texto=(f'{len(fotos)} imagem(ns) já registrada(s); '
                   f'{len(pendentes)} aguardando confirmação do encerramento.')
            self.label_anexos_os.configure(text=texto)
        except Exception as erro:
            self.label_anexos_os.configure(text=f'Não foi possível listar anexos: {erro}')

    def anexar_imagens_formulario(self, os_id):
        """Só seleciona as imagens; grava no banco ao encerrar a OS."""
        caminhos=filedialog.askopenfilenames(parent=self,title='Selecionar imagens do encerramento',
            filetypes=[('Imagens','*.jpg *.jpeg *.png *.webp')])
        if not caminhos:return
        aprovadas=[];falhas=[]
        for caminho in caminhos:
            try:
                with open(caminho,'rb') as arquivo:
                    ext.validar_imagem(arquivo.read())
                if caminho not in self.imagens_pendentes_os:aprovadas.append(caminho)
            except Exception as erro:
                falhas.append(f'{os.path.basename(caminho)}: {erro}')
        self.imagens_pendentes_os.extend(aprovadas)
        self.atualizar_label_anexos_os(os_id)
        if falhas:messagebox.showwarning('Imagens não selecionadas','\n'.join(falhas[:6]))
        elif aprovadas:messagebox.showinfo('Imagens selecionadas',
            f'{len(aprovadas)} imagem(ns) selecionada(s). Serão anexadas ao confirmar o encerramento.')

    def remover_imagens_pendentes_os(self,os_id):
        """Remove fotos ainda não enviadas sem perder o relatório preenchido."""
        fotos=getattr(self,'imagens_pendentes_os',[])
        if not fotos:
            return messagebox.showinfo('Fotos','Nenhuma foto aguardando envio.')
        janela=tk.Toplevel(self);janela.title('Remover fotos antes do envio')
        janela.configure(bg=BLACK);janela.geometry('560x350');janela.transient(self);janela.grab_set()
        tk.Label(janela,text='Escolha a foto para remover. O relatório preenchido será preservado.',
                 bg=BLACK,fg=WHITE,wraplength=510).pack(pady=12)
        lista=tk.Listbox(janela,bg=DARK,fg=WHITE,selectbackground=YELLOW,
                         selectforeground=BLACK,font=('Arial',11))
        lista.pack(fill='both',expand=True,padx=16,pady=6)
        def recarregar():
            lista.delete(0,'end')
            for caminho in self.imagens_pendentes_os:
                lista.insert('end',os.path.basename(caminho))
        def remover():
            indices=lista.curselection()
            if not indices:return
            self.imagens_pendentes_os.pop(indices[0])
            recarregar();self.atualizar_label_anexos_os(os_id)
        recarregar()
        self.criar_botao(janela,'REMOVER FOTO',remover).pack(pady=10)

    def abrir_pdf_da_os(self, os_id):
        try:
            publicado = fluxo.ultimo_documento(BANCO, os_id)
            if not publicado:
                # Procura e vincula um relatório antigo que já esteja na pasta.
                fluxo.recuperar_relatorios_antigos(BANCO, os_id=os_id)
                publicado = fluxo.ultimo_documento(BANCO, os_id)
            if not publicado:
                raise ValueError('PDF ainda não encontrado. Selecione REPUBLICAR PDF para esta OS.')
            caminho = fluxo.validar_pdf_publicado(publicado)
            from pathlib import Path
            webbrowser.open(Path(caminho).resolve().as_uri())
        except Exception as erro:
            messagebox.showerror('PDF', str(erro))

    # ========================================================
    # HISTÓRICO DE OS
    # ========================================================

    def abrir_historico_os(self):
        self.navegar_para(self.mostrar_historico_os)

    def mostrar_historico_os(self):
        self.limpar_tela()
        self.tela_atual = self.mostrar_historico_os

        self.criar_cabecalho("HISTÓRICO E RELATÓRIOS PDF")

        barra = tk.Frame(self, bg=BLACK)
        barra.pack(fill="x", padx=30, pady=12)

        tk.Label(
            barra,
            text="Pesquisa:",
            font=("Arial", 10, "bold"),
            fg=WHITE,
            bg=BLACK
        ).pack(side="left")

        self.pesquisa_historico = tk.Entry(
            barra,
            font=("Arial", 10),
            bg=DARKER,
            fg=WHITE,
            insertbackground=WHITE,
            relief="flat",
            width=38
        )
        self.pesquisa_historico.pack(side="left", padx=8, ipady=7)

        self.criar_botao(
            barra,
            "PESQUISAR",
            self.carregar_historico_os,
            largura=14
        ).pack(side="left")

        tabela_frame = tk.Frame(self, bg=BLACK)
        tabela_frame.pack(fill="both", expand=True, padx=30)

        colunas = (
            "id",
            "numero",
            "cliente",
            "conclusao",
            "valor",
            "pagamento",
            "status",
            "pdf"
        )

        self.tabela_historico = ttk.Treeview(
            tabela_frame,
            columns=colunas,
            show="headings"
        )

        titulos = {
            "id": "ID",
            "numero": "OS",
            "cliente": "Cliente",
            "conclusao": "Conclusão",
            "valor": "Valor",
            "pagamento": "Pagamento",
            "status": "Situação",
            "pdf": "Relatório PDF"
        }

        for coluna in colunas:
            self.tabela_historico.heading(
                coluna,
                text=titulos[coluna]
            )

        self.tabela_historico.column("id", width=50, anchor="center")
        self.tabela_historico.column("numero", width=90, anchor="center")
        self.tabela_historico.column("cliente", width=330, anchor="center")
        self.tabela_historico.column("conclusao", width=150, anchor="center")
        self.tabela_historico.column("valor", width=130, anchor="center")
        self.tabela_historico.column("pagamento", width=130, anchor="center")
        self.tabela_historico.column("status", width=125, anchor="center")
        self.tabela_historico.column("pdf", width=115, anchor="center")

        self.tabela_historico.pack(fill="both", expand=True)

        botoes = tk.Frame(self, bg=BLACK)
        botoes.pack(fill="x", padx=30, pady=15)

        self.criar_botao(
            botoes,
            "ABRIR OS",
            self.editar_historico_os,
            largura=14
        ).pack(side="left")

        self.criar_botao(botoes, "ABRIR PDF PUBLICADO",
                          self.pdf_historico_selecionado, largura=23,
                          fundo=YELLOW, frente=BLACK).pack(side="left",padx=8)
        self.criar_botao(botoes, "REPUBLICAR PDF",
                          self.republicar_pdf_historico, largura=20).pack(side="left",padx=8)
        self.carregar_historico_os()

    def os_historico_selecionada(self):
        selecao=self.tabela_historico.selection()
        if not selecao:
            messagebox.showwarning('Seleção','Selecione uma OS do histórico.')
            return None
        return int(self.tabela_historico.item(selecao[0])['values'][0])

    def pdf_historico_selecionado(self):
        os_id=self.os_historico_selecionada()
        if os_id is not None: self.abrir_pdf_da_os(os_id)

    def republicar_pdf_historico(self):
        os_id=self.os_historico_selecionada()
        if os_id is not None:
            self.publicar_pdf_em_segundo_plano(os_id)

    def carregar_historico_os(self):
        for item in self.tabela_historico.get_children():
            self.tabela_historico.delete(item)

        termo = ""
        if hasattr(self, "pesquisa_historico"):
            termo = self.pesquisa_historico.get().strip()

        conexao = conectar_banco()
        cursor = conexao.cursor()

        if termo:
            cursor.execute(
                """
                SELECT
                    os.id,
                    os.numero_os,
                    c.nome AS cliente,
                    os.data_conclusao,
                    os.valor_total,
                    os.forma_pagamento,
                    os.status,
                    (SELECT COUNT(*) FROM os_documentos d WHERE d.os_id=os.id AND d.tipo='relatorio_pdf') AS pdfs
                FROM ordens_servico os
                JOIN clientes c ON c.id = os.cliente_id
                WHERE os.status IN ('Concluída','Cancelada','Não realizada')
                  AND (
                      os.numero_os LIKE ?
                      OR c.nome LIKE ?
                      OR os.descricao LIKE ?
                  )
                ORDER BY os.id DESC
                """,
                (f"%{termo}%", f"%{termo}%", f"%{termo}%")
            )
        else:
            cursor.execute(
                """
                SELECT
                    os.id,
                    os.numero_os,
                    c.nome AS cliente,
                    os.data_conclusao,
                    os.valor_total,
                    os.forma_pagamento,
                    os.status,
                    (SELECT COUNT(*) FROM os_documentos d WHERE d.os_id=os.id AND d.tipo='relatorio_pdf') AS pdfs
                FROM ordens_servico os
                JOIN clientes c ON c.id = os.cliente_id
                WHERE os.status IN ('Concluída','Cancelada','Não realizada')
                ORDER BY os.id DESC
                """
            )

        registros = cursor.fetchall()
        conexao.close()

        for registro in registros:
            self.tabela_historico.insert(
                "",
                "end",
                values=(
                    registro["id"],
                    registro["numero_os"],
                    registro["cliente"],
                    registro["data_conclusao"],
                    self.dinheiro(registro["valor_total"]),
                    registro["forma_pagamento"],
                    registro["status"],
                    "Disponível" if registro["pdfs"] else "Pendente"
                )
            )

    def editar_historico_os(self):
        selecionado = self.tabela_historico.selection()

        if not selecionado:
            messagebox.showwarning(
                "Seleção",
                "Selecione uma OS."
            )
            return

        valores = self.tabela_historico.item(selecionado[0])["values"]
        os_id = valores[0]

        self.navegar_para(
            lambda: self.mostrar_formulario_os(os_id=os_id)
        )

    # ========================================================
    # FINANCEIRO
    # ========================================================

    def abrir_financeiro(self):
        self.navegar_para(self.mostrar_financeiro)

    def mostrar_financeiro(self):
        self.limpar_tela()
        self.tela_atual = self.mostrar_financeiro

        self.criar_cabecalho("FINANCEIRO")

        resumo = tk.Frame(self, bg=BLACK)
        resumo.pack(fill="x", padx=30, pady=(3, 15))

        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status = 'Aguardando pagamento' THEN valor ELSE 0 END), 0) AS pendente,
                COALESCE(SUM(CASE WHEN status = 'Recebido' THEN valor ELSE 0 END), 0) AS recebido
            FROM financeiro
        """)

        resumo_financeiro = cursor.fetchone()
        conexao.close()

        cards = [
            ("A RECEBER", self.dinheiro(resumo_financeiro["pendente"]), ORANGE),
            ("RECEBIDO", self.dinheiro(resumo_financeiro["recebido"]), GREEN),
        ]

        for titulo, valor, cor in cards:
            card = tk.Frame(
                resumo,
                bg=DARK,
                padx=25,
                pady=12,
                highlightthickness=1,
                highlightbackground="#242424"
            )
            card.pack(side="left", padx=(0, 12))

            tk.Label(
                card,
                text=titulo,
                font=("Arial", 9, "bold"),
                fg=GRAY,
                bg=DARK
            ).pack(anchor="w")

            tk.Label(
                card,
                text=valor,
                font=("Arial", 16, "bold"),
                fg=cor,
                bg=DARK
            ).pack(anchor="w")

        tk.Label(
            self,
            text="PIX já pago não entra nesta fila de cobrança.",
            font=("Arial", 9),
            fg=GRAY,
            bg=BLACK
        ).pack(anchor="w", padx=30, pady=(0, 8))

        tk.Label(self,text='Pesquisar por OS, cliente, pagamento ou situação:',bg=BLACK,fg=GRAY).pack(anchor='w',padx=30)
        self.pesquisa_financeiro=tk.StringVar()
        entrada_fin=tk.Entry(self,textvariable=self.pesquisa_financeiro,bg=DARK,fg=WHITE,insertbackground=WHITE)
        entrada_fin.pack(fill='x',padx=30,ipady=5,pady=(0,8))
        self.pesquisa_financeiro.trace_add('write',lambda *_:self.carregar_financeiro())

        tabela_frame = tk.Frame(self, bg=BLACK)
        tabela_frame.pack(fill="both", expand=True, padx=30)

        colunas = (
            "id",
            "os",
            "cliente",
            "valor",
            "forma",
            "status",
            "vencimento"
        )

        self.tabela_financeiro = ttk.Treeview(
            tabela_frame,
            columns=colunas,
            show="headings"
        )

        titulos = {
            "id": "ID",
            "os": "OS",
            "cliente": "Cliente",
            "valor": "Valor",
            "forma": "Pagamento",
            "status": "Status",
            "vencimento": "Vencimento"
        }

        larguras = {
            "id": 50,
            "os": 90,
            "cliente": 300,
            "valor": 120,
            "forma": 130,
            "status": 180,
            "vencimento": 120
        }

        for coluna in colunas:
            self.tabela_financeiro.heading(
                coluna,
                text=titulos[coluna]
            )
            self.tabela_financeiro.column(
                coluna,
                width=larguras[coluna],
                anchor="center"
            )

        self.tabela_financeiro.pack(fill="both", expand=True)

        botoes = tk.Frame(self, bg=BLACK)
        botoes.pack(fill="x", padx=30, pady=15)

        self.criar_botao(
            botoes,
            "MARCAR COMO RECEBIDO",
            self.marcar_financeiro_recebido,
            largura=22,
            frente=GREEN
        ).pack(side="left")

        self.carregar_financeiro()

    def carregar_financeiro(self):
        for item in self.tabela_financeiro.get_children():
            self.tabela_financeiro.delete(item)

        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                f.id,
                os.numero_os,
                c.nome AS cliente,
                f.valor,
                f.forma_pagamento,
                f.status,
                f.vencimento
            FROM financeiro f
            JOIN ordens_servico os ON os.id = f.os_id
            JOIN clientes c ON c.id = f.cliente_id
            ORDER BY f.id DESC
        """)

        registros = cursor.fetchall()
        conexao.close()

        busca=getattr(self,'pesquisa_financeiro',None)
        termo=busca.get().casefold().strip() if busca else ''
        for registro in registros:
            texto=' '.join(str(registro[k] or '') for k in ('numero_os','cliente','forma_pagamento','status','vencimento')).casefold()
            if termo and termo not in texto:continue
            icone, _cor = self.status_visual(registro["status"])

            self.tabela_financeiro.insert(
                "",
                "end",
                values=(
                    registro["id"],
                    registro["numero_os"],
                    registro["cliente"],
                    self.dinheiro(registro["valor"]),
                    registro["forma_pagamento"],
                    f"{icone} {registro['status']}",
                    registro["vencimento"] or ""
                )
            )

    def marcar_financeiro_recebido(self):
        selecionado = self.tabela_financeiro.selection()

        if not selecionado:
            messagebox.showwarning(
                "Seleção",
                "Selecione um lançamento financeiro."
            )
            return

        valores = self.tabela_financeiro.item(selecionado[0])["values"]
        financeiro_id = valores[0]

        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute(
            """
            UPDATE financeiro
            SET status = 'Recebido',
                data_pagamento = ?
            WHERE id = ?
            """,
            (
                datetime.now().strftime("%d/%m/%Y"),
                financeiro_id
            )
        )

        conexao.commit()
        conexao.close()

        self.carregar_financeiro()

    # ========================================================
    # RELATÓRIO GERAL DE OS
    # ========================================================

    def abrir_relatorios(self):
        self.abrir_historico_os()

    def mostrar_menu_relatorios(self):
        self.limpar_tela()
        self.tela_atual = self.mostrar_menu_relatorios

        self.criar_cabecalho("RELATÓRIOS")

        centro = tk.Frame(self, bg=BLACK)
        centro.pack(expand=True)

        self.criar_botao(
            centro,
            "RELATÓRIO GERAL DE OS",
            self.abrir_relatorios_os,
            largura=28
        ).pack(pady=8)

        self.criar_botao(
            centro,
            "RESUMO FINANCEIRO",
            self.abrir_financeiro,
            largura=28
        ).pack(pady=8)

        self.criar_botao(
            centro,
            "CLIENTES",
            self.abrir_clientes,
            largura=28
        ).pack(pady=8)

    def abrir_relatorios_os(self):
        self.abrir_historico_os()

    def mostrar_relatorio_geral_os(self):
        self.limpar_tela()
        self.tela_atual = self.mostrar_relatorio_geral_os

        self.criar_cabecalho("RELATÓRIO GERAL DE ORDENS DE SERVIÇO")

        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN status = 'Aberta' THEN 1 ELSE 0 END), 0) AS abertas,
                COALESCE(SUM(CASE WHEN status = 'Pendente' THEN 1 ELSE 0 END), 0) AS pendentes,
                COALESCE(SUM(CASE WHEN status = 'Concluída' THEN 1 ELSE 0 END), 0) AS concluidas,
                COALESCE(SUM(CASE WHEN status = 'Concluída' THEN valor_total ELSE 0 END), 0) AS valor_concluido,
                COALESCE(SUM(CASE WHEN status IN ('Aberta', 'Pendente') THEN valor_total ELSE 0 END), 0) AS valor_em_aberto
            FROM ordens_servico
        """)

        resumo = cursor.fetchone()
        conexao.close()

        cards = tk.Frame(self, bg=BLACK)
        cards.pack(fill="x", padx=30, pady=10)

        dados_cards = [
            ("TOTAL", resumo["total"], WHITE),
            ("🔴 ABERTAS", resumo["abertas"], RED),
            ("🟡 PENDENTES", resumo["pendentes"], ORANGE),
            ("🟢 CONCLUÍDAS", resumo["concluidas"], GREEN),
        ]

        for titulo, valor, cor in dados_cards:
            card = tk.Frame(
                cards,
                bg=DARK,
                padx=23,
                pady=13
            )
            card.pack(side="left", padx=(0, 10))

            tk.Label(
                card,
                text=titulo,
                font=("Arial", 9, "bold"),
                fg=GRAY,
                bg=DARK
            ).pack(anchor="w")

            tk.Label(
                card,
                text=str(valor),
                font=("Arial", 19, "bold"),
                fg=cor,
                bg=DARK
            ).pack(anchor="w")

        valores = tk.Frame(self, bg=BLACK)
        valores.pack(fill="x", padx=30, pady=10)

        tk.Label(
            valores,
            text=f"Valor das OS concluídas: {self.dinheiro(resumo['valor_concluido'])}",
            font=("Arial", 11, "bold"),
            fg=GREEN,
            bg=BLACK
        ).pack(anchor="w")

        tk.Label(
            valores,
            text=f"Valor das OS em aberto/pendentes: {self.dinheiro(resumo['valor_em_aberto'])}",
            font=("Arial", 11, "bold"),
            fg=ORANGE,
            bg=BLACK
        ).pack(anchor="w", pady=3)

        tabela_frame = tk.Frame(self, bg=BLACK)
        tabela_frame.pack(fill="both", expand=True, padx=30, pady=8)

        colunas = (
            "numero",
            "cliente",
            "data",
            "valor",
            "pagamento",
            "status"
        )

        tabela = ttk.Treeview(
            tabela_frame,
            columns=colunas,
            show="headings"
        )

        titulos = {
            "numero": "OS",
            "cliente": "Cliente",
            "data": "Abertura",
            "valor": "Valor",
            "pagamento": "Pagamento",
            "status": "Status"
        }

        for coluna in colunas:
            tabela.heading(
                coluna,
                text=titulos[coluna]
            )

        tabela.column("numero", width=90, anchor="center")
        tabela.column("cliente", width=330, anchor="center")
        tabela.column("data", width=130, anchor="center")
        tabela.column("valor", width=130, anchor="center")
        tabela.column("pagamento", width=140, anchor="center")
        tabela.column("status", width=150, anchor="center")

        tabela.pack(fill="both", expand=True)

        conexao = conectar_banco()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT
                os.numero_os,
                c.nome AS cliente,
                os.data_abertura,
                os.valor_total,
                os.forma_pagamento,
                os.status
            FROM ordens_servico os
            JOIN clientes c ON c.id = os.cliente_id
            ORDER BY os.id DESC
        """)

        registros = cursor.fetchall()
        conexao.close()

        for registro in registros:
            icone, _cor = self.status_visual(registro["status"])

            tabela.insert(
                "",
                "end",
                values=(
                    registro["numero_os"],
                    registro["cliente"],
                    registro["data_abertura"],
                    self.dinheiro(registro["valor_total"]),
                    registro["forma_pagamento"],
                    f"{icone} {registro['status']}"
                )
            )

    # ========================================================
    # PORTAL DO CLIENTE
    # ========================================================

    def abrir_portal_cliente(self):
        self.navegar_para(self.mostrar_portal_cliente)

    def mostrar_portal_cliente(self):
        self.limpar_tela()
        self.tela_atual = self.mostrar_portal_cliente

        self.criar_cabecalho("PORTAL DO CLIENTE")

        info = self.servidor_portal.info()

        container = tk.Frame(self, bg=BLACK)
        container.pack(fill="both", expand=True, padx=35, pady=5)

        cartao = tk.Frame(
            container,
            bg=DARK,
            padx=24,
            pady=18,
            highlightthickness=1,
            highlightbackground="#2A2A2A"
        )
        cartao.pack(fill="x")

        esquerda = tk.Frame(cartao, bg=DARK)
        esquerda.pack(side="left", fill="x", expand=True)

        if info["ativo"]:
            texto_status = "● SERVIDOR ONLINE"
            cor_status = GREEN
            texto_detalhe = (
                f"No ar desde {info['iniciado_em']} • porta {info['porta']} • "
                "os clientes podem acessar agora"
            )
        else:
            texto_status = "● SERVIDOR OFFLINE"
            cor_status = RED
            texto_detalhe = (
                info["erro"]
                or "Clique em LIGAR SERVIDOR para liberar o acesso dos clientes."
            )

        tk.Label(
            esquerda,
            text=texto_status,
            font=("Arial", 10, "bold"),
            fg=cor_status,
            bg=DARK
        ).pack(anchor="w")

        tk.Label(
            esquerda,
            text="Portal do Cliente",
            font=("Arial", 22, "bold"),
            fg=YELLOW,
            bg=DARK
        ).pack(anchor="w", pady=(3, 2))

        tk.Label(
            esquerda,
            text=texto_detalhe,
            font=("Arial", 9),
            fg=GRAY,
            bg=DARK,
            wraplength=520,
            justify="left"
        ).pack(anchor="w")

        direita = tk.Frame(cartao, bg=DARK)
        direita.pack(side="right")

        self.criar_botao(
            direita,
            "ABRIR NO NAVEGADOR",
            self.abrir_portal_navegador,
            largura=20
        ).pack(pady=3)

        self.criar_botao(
            direita,
            "COPIAR LINK",
            self.copiar_link_portal,
            largura=20
        ).pack(pady=3)

        self.criar_botao(
            direita,
            "DESLIGAR SERVIDOR" if info["ativo"] else "LIGAR SERVIDOR",
            self.alternar_servidor_portal,
            largura=20,
            frente=RED if info["ativo"] else GREEN
        ).pack(pady=3)

        links = tk.Frame(container, bg=BLACK)
        links.pack(fill="x", pady=(12, 0))

        self.criar_caixa_link_portal(
            links,
            "NESTE COMPUTADOR",
            info["url_local"] or "—",
            WHITE
        )
        self.criar_caixa_link_portal(
            links,
            "NA REDE LOCAL · CELULAR E OUTROS PCs",
            info["url_rede"] or "—",
            YELLOW,
            ultimo=True
        )

        status_v9=links9.estado_com_manuais()
        for p,nome in (('8765','Portal do Cliente'),('8766','Portal do Prestador')):
            tk.Label(container,text=nome+' · link externo: '+status_v9.get(p,{}).get('url','não detectado'),
                     fg=GREEN if p in status_v9 else GRAY,bg=BLACK,wraplength=1000,justify='left').pack(anchor='w',pady=3)

        instrucoes = tk.Frame(
            container,
            bg=DARK,
            padx=20,
            pady=13,
            highlightthickness=1,
            highlightbackground="#262626"
        )
        instrucoes.pack(fill="x", pady=(12, 0))

        tk.Label(
            instrucoes,
            text="COMO O CLIENTE ACESSA",
            font=("Arial", 9, "bold"),
            fg=YELLOW,
            bg=DARK
        ).pack(anchor="w")

        passos = [
            "1.  Conecte o celular ou outro computador na mesma rede Wi-Fi da empresa.",
            "2.  Abra o endereço da rede local no navegador (Chrome, Safari, etc.).",
            "3.  O cliente cria um cadastro ou entra com CPF/CNPJ + telefone/e-mail já cadastrado.",
            "4.  Ao enviar a solicitação, a OS aparece aqui como Pendente, com origem Portal.",
        ]

        for passo in passos:
            tk.Label(
                instrucoes,
                text=passo,
                font=("Arial", 9),
                fg=WHITE,
                bg=DARK
            ).pack(anchor="w", pady=1)

        estatisticas = tk.Frame(container, bg=BLACK)
        estatisticas.pack(fill="x", pady=(12, 0))

        self.portal_labels = {}
        cartoes = [
            ("total", "SOLICITAÇÕES PELO PORTAL", YELLOW),
            ("andamento", "AGUARDANDO ATENDIMENTO", ORANGE),
            ("concluidas", "CONCLUÍDAS", GREEN),
        ]

        for chave, titulo, cor in cartoes:
            card = tk.Frame(
                estatisticas,
                bg=DARK,
                padx=18,
                pady=10,
                highlightthickness=1,
                highlightbackground="#242424"
            )
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))

            tk.Label(
                card,
                text=titulo,
                font=("Arial", 8, "bold"),
                fg=GRAY,
                bg=DARK
            ).pack(anchor="w")

            label = tk.Label(
                card,
                text="0",
                font=("Arial", 20, "bold"),
                fg=cor,
                bg=DARK
            )
            label.pack(anchor="w")

            self.portal_labels[chave] = label

        barra_tabela = tk.Frame(container, bg=BLACK)
        barra_tabela.pack(fill="x", pady=(16, 6))

        tk.Label(
            barra_tabela,
            text="ÚLTIMAS SOLICITAÇÕES PELO PORTAL",
            font=("Arial", 11, "bold"),
            fg=YELLOW,
            bg=BLACK
        ).pack(side="left")

        self.criar_botao(
            barra_tabela,
            "ATUALIZAR",
            self.carregar_solicitacoes_portal,
            largura=12
        ).pack(side="right")

        tabela_frame = tk.Frame(container, bg=BLACK)
        tabela_frame.pack(fill="both", expand=True)

        colunas = ("id", "numero", "cliente", "data", "urgencia", "status")

        self.tabela_portal = ttk.Treeview(
            tabela_frame,
            columns=colunas,
            show="headings",
            height=7
        )

        titulos = {
            "id": "ID",
            "numero": "OS",
            "cliente": "Cliente",
            "data": "Abertura",
            "urgencia": "Urgência",
            "status": "Status"
        }

        larguras = {
            "id": 50,
            "numero": 100,
            "cliente": 320,
            "data": 130,
            "urgencia": 100,
            "status": 130
        }

        for coluna in colunas:
            self.tabela_portal.heading(
                coluna,
                text=titulos[coluna]
            )
            self.tabela_portal.column(
                coluna,
                width=larguras[coluna],
                anchor="center"
            )

        self.tabela_portal.pack(fill="both", expand=True)
        self.tabela_portal.bind(
            "<Double-1>",
            lambda _event: self.abrir_os_portal_selecionada()
        )

        botoes = tk.Frame(container, bg=BLACK)
        botoes.pack(fill="x", pady=(10, 8))

        self.criar_botao(
            botoes,
            "ABRIR OS SELECIONADA",
            self.abrir_os_portal_selecionada,
            largura=22
        ).pack(side="left")

        self.criar_botao(
            botoes,
            "NOVA OS MANUAL",
            lambda: self.navegar_para(lambda: self.mostrar_formulario_os()),
            largura=17
        ).pack(side="left", padx=8)

        self.carregar_solicitacoes_portal()

    def criar_caixa_link_portal(self, parent, titulo, url, cor, ultimo=False):
        caixa = tk.Frame(
            parent,
            bg=DARKER,
            padx=16,
            pady=11,
            highlightthickness=1,
            highlightbackground="#262626"
        )
        caixa.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 0 if ultimo else 10)
        )

        tk.Label(
            caixa,
            text=titulo,
            font=("Arial", 8, "bold"),
            fg=GRAY,
            bg=DARKER
        ).pack(anchor="w")

        rotulo = tk.Label(
            caixa,
            text=url,
            font=("Arial", 13, "bold"),
            fg=cor,
            bg=DARKER,
            cursor="hand2"
        )
        rotulo.pack(anchor="w", pady=(3, 0))
        rotulo.bind(
            "<Button-1>",
            lambda _event, endereco=url: self.copiar_texto_portal(endereco)
        )

    def carregar_solicitacoes_portal(self):
        if not hasattr(self, "tabela_portal"):
            return

        try:
            if not self.tabela_portal.winfo_exists():
                return
        except tk.TclError:
            return

        for item in self.tabela_portal.get_children():
            self.tabela_portal.delete(item)

        conexao = conectar_banco()
        cursor = conexao.cursor()

        resumo = cursor.execute("""
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(CASE WHEN status IN ('Aberta', 'Pendente') THEN 1 ELSE 0 END), 0) AS andamento,
                COALESCE(SUM(CASE WHEN status = 'Concluída' THEN 1 ELSE 0 END), 0) AS concluidas
            FROM ordens_servico
            WHERE origem = 'Portal'
        """).fetchone()

        registros = cursor.execute("""
            SELECT
                os.id,
                os.numero_os,
                c.nome AS cliente,
                os.data_abertura,
                os.urgencia,
                os.status
            FROM ordens_servico os
            JOIN clientes c ON c.id = os.cliente_id
            WHERE os.origem = 'Portal'
            ORDER BY os.id DESC
            LIMIT 50
        """).fetchall()

        conexao.close()

        if hasattr(self, "portal_labels"):
            self.portal_labels["total"].config(text=str(resumo["total"]))
            self.portal_labels["andamento"].config(text=str(resumo["andamento"]))
            self.portal_labels["concluidas"].config(text=str(resumo["concluidas"]))

        for registro in registros:
            icone, _cor = self.status_visual(registro["status"])

            self.tabela_portal.insert(
                "",
                "end",
                values=(
                    registro["id"],
                    registro["numero_os"],
                    registro["cliente"],
                    registro["data_abertura"],
                    registro["urgencia"] or "Normal",
                    f"{icone} {registro['status']}"
                )
            )

    def abrir_os_portal_selecionada(self):
        if not hasattr(self, "tabela_portal"):
            return

        selecionado = self.tabela_portal.selection()

        if not selecionado:
            messagebox.showwarning(
                "Seleção",
                "Selecione uma solicitação do portal."
            )
            return

        valores = self.tabela_portal.item(selecionado[0])["values"]
        os_id = valores[0]

        self.navegar_para(
            lambda: self.mostrar_formulario_os(os_id=os_id)
        )

    def abrir_portal_navegador(self):
        # Portal do Cliente completo na porta 8765 (login por CPF e senha).
        info = self.servidor_portal.info()

        if not info["ativo"]:
            messagebox.showwarning(
                "Portal desligado",
                "Ligue o servidor do Portal do Cliente (8765) antes de abrir no navegador."
            )
            return

        webbrowser.open(info["url_local"])

    def copiar_link_portal(self):
        info = self.servidor_portal.info()
        link = info["url_rede"] or info["url_local"]

        if not link:
            messagebox.showwarning(
                "Portal desligado",
                "Ligue o servidor do Portal do Cliente (8765) para gerar o link."
            )
            return

        self.copiar_texto_portal(link)

    def copiar_texto_portal(self, texto):
        if not texto or texto == "—":
            messagebox.showwarning(
                "Portal desligado",
                "Ligue o servidor do portal para gerar o link."
            )
            return

        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update()

        messagebox.showinfo(
            "Link copiado",
            (
                "Endereço copiado:\n\n"
                f"{texto}\n\n"
                "O cliente precisa estar na mesma rede Wi-Fi da empresa."
            )
        )

    def alternar_servidor_portal(self):
        if self.servidor_portal.ativo:
            confirmar = messagebox.askyesno(
                "Desligar portal",
                "Enquanto o portal estiver desligado, os clientes não "
                "conseguirão acessar.\n\nDeseja desligar?"
            )

            if not confirmar:
                return

            self.servidor_portal.parar()
        else:
            try:
                self.servidor_portal.iniciar()
                self.erro_portal = ""
            except Exception as erro:
                self.erro_portal = str(erro)
                messagebox.showerror("Erro no portal", str(erro))

        self.mostrar_portal_cliente()

    def processar_eventos_portal(self):
        try:
            for evento in self.servidor_portal.consumir_eventos():
                if evento.get("tipo") == "nova_os":
                    self.mostrar_toast_portal(evento)

                    if self.tela_atual == self.mostrar_ordens_servico:
                        self.carregar_os_ativas()
                    elif self.tela_atual == self.mostrar_portal_cliente:
                        self.carregar_solicitacoes_portal()

                elif evento.get("tipo") == "novo_cliente":
                    self.mostrar_toast_portal({
                        "numero": "Novo cadastro",
                        "cliente": evento.get("cliente", ""),
                        "descricao": "Um cliente criou cadastro pelo portal.",
                    })

        except Exception as erro:
            print("Erro processando eventos do portal:", erro)

        finally:
            try:
                self.after(2000, self.processar_eventos_portal)
            except tk.TclError:
                pass

    def mostrar_toast_portal(self, evento):
        try:
            janela = tk.Toplevel(self)
            janela.overrideredirect(True)
            janela.attributes("-topmost", True)
            janela.configure(bg=YELLOW)

            caixa = tk.Frame(janela, bg=DARK, padx=16, pady=12)
            caixa.pack(fill="both", expand=True, padx=2, pady=2)

            titulo = "🌐 NOVA SOLICITAÇÃO PELO PORTAL"

            if evento.get("numero") == "Novo cadastro":
                titulo = "👤 NOVO CADASTRO PELO PORTAL"

            tk.Label(
                caixa,
                text=titulo,
                font=("Arial", 9, "bold"),
                fg=YELLOW,
                bg=DARK
            ).pack(anchor="w")

            tk.Label(
                caixa,
                text=f"{evento.get('numero', '')} • {evento.get('cliente', '')}",
                font=("Arial", 11, "bold"),
                fg=WHITE,
                bg=DARK
            ).pack(anchor="w", pady=(2, 2))

            tk.Label(
                caixa,
                text=(evento.get("descricao") or "")[:90],
                font=("Arial", 9),
                fg=GRAY,
                bg=DARK,
                wraplength=330,
                justify="left"
            ).pack(anchor="w")

            def abrir_evento(_event=None):
                janela.destroy()
                os_id = evento.get("os_id")

                if os_id:
                    self.navegar_para(
                        lambda: self.mostrar_formulario_os(os_id=os_id)
                    )
                elif self.servidor_portal.ativo:
                    self.abrir_portal_cliente()

            for widget in [janela, caixa] + caixa.winfo_children():
                widget.bind("<Button-1>", abrir_evento)

            janela.update_idletasks()

            largura = janela.winfo_width()
            altura = janela.winfo_height()
            x = self.winfo_screenwidth() - largura - 28
            y = self.winfo_screenheight() - altura - 80

            janela.geometry(f"+{x}+{y}")
            janela.after(7000, janela.destroy)

        except Exception as erro:
            print("Erro exibindo aviso do portal:", erro)

    # ========================================================
    # PRESTADORES E DOCUMENTOS
    # ========================================================

    def abrir_area_cliente_documentos(self):
        info = self.servidor_portal.info()
        if not info['ativo']:
            messagebox.showwarning('Portal','O servidor do Portal do Cliente (8765) está desligado.')
            return
        webbrowser.open(info['url_local'])

    def configurar_acesso_cliente(self):
        """Configura senha escolhida para login legado do cliente sem exibir valores anteriores."""
        selecionado=self.tabela_clientes.selection()
        if not selecionado:
            messagebox.showwarning('Cliente','Selecione um cliente para configurar acesso.')
            return
        cid=int(self.tabela_clientes.item(selecionado[0])['values'][0])
        nome=self.tabela_clientes.item(selecionado[0])['values'][1]
        senha=simpledialog.askstring('Acesso web do cliente',
            'Escolha uma senha de pelo menos 10 caracteres para '+str(nome)+':',show='*',parent=self)
        if senha is None:return
        if len(senha)<10:
            messagebox.showwarning('Senha','A senha deve ter no mínimo 10 caracteres.');return
        confirmar=simpledialog.askstring('Confirmar senha','Digite novamente a senha escolhida:',show='*',parent=self)
        if confirmar is None:return
        if confirmar!=senha:
            messagebox.showwarning('Senha','As duas senhas não coincidem.');return
        if not messagebox.askyesno('Confirmar','Atualizar a senha desse cliente? A anterior deixará de funcionar.'):
            return
        try:fluxo.definir_senha_cliente(BANCO,cid,senha)
        except Exception as e:
            messagebox.showerror('Acesso do cliente',str(e));return
        messagebox.showinfo('Acesso configurado',
            f'Senha atualizada para {nome}.\n\nLogin antigo: ID {cid} e senha escolhida.\n'
            'Login novo: CPF e senha no Portal do Cliente (porta 8765).\n\n'
            'Por segurança, a senha não será exibida novamente.')

    def abrir_catalogo_servicos(self):
        """Editor nativo Tkinter do catálogo (não requer navegador ou servidor HTTP)."""
        return self.abrir_catalogo_desktop()

    def abrir_portal_prestador(self):
        if not self.url_prestador:
            messagebox.showwarning('Portal','Servidor do prestador indisponível. Verifique a porta 8766.')
        else:
            webbrowser.open(self.url_prestador)

    def mostrar_prestadores(self):
        self.limpar_tela(); self.tela_atual=self.mostrar_prestadores
        self.criar_cabecalho('PRESTADORES E ATRIBUIÇÕES')
        if self.url_prestador:
            rede=self.portal_prestador.url_rede()
            info_cli=self.servidor_portal.info()
            rede_cli=(info_cli.get('url_rede') or 'http://127.0.0.1:8765').rstrip('/')
            tk.Label(self,text=f'PORTAIS DO AMBIENTE ATUAL  •  Prestador: {self.url_prestador}/  •  Cliente: {info_cli.get("url_local") or rede_cli}/',
                     bg=BLACK,fg=YELLOW,font=('Arial',11,'bold'),wraplength=1050).pack(padx=20,pady=7)
        barra=tk.Frame(self,bg=BLACK);barra.pack(fill='x',padx=30,pady=10)
        self.criar_botao(barra,'+ PRESTADOR',self.cadastrar_prestador,largura=16).pack(side='left')
        self.criar_botao(barra,'ATRIBUIR OS',self.atribuir_prestador).pack(side='left',padx=8)
        self.criar_botao(barra,'ABRIR PORTAL',self.abrir_portal_prestador).pack(side='left')
        self.criar_botao(barra,'CLIENTES PF/PJ',self.mostrar_clientes,largura=20).pack(side='left',padx=8)
        campo_busca=tk.Frame(self,bg=BLACK);campo_busca.pack(fill='x',padx=30,pady=5)
        tk.Label(campo_busca,text='Pesquisar prestador:',bg=BLACK,fg=GRAY).pack(side='left')
        pesquisa=tk.StringVar()
        tk.Entry(campo_busca,textvariable=pesquisa,bg=DARK,fg=WHITE,insertbackground=WHITE).pack(side='left',padx=10,fill='x',expand=True,ipady=5)
        acoes=tk.Frame(self,bg=BLACK);acoes.pack(fill='x',padx=30,pady=4)
        tk.Label(self,text='Prestadores ativos • cada OS pode ter vários responsáveis e histórico permanente',bg=BLACK,fg=GRAY).pack(anchor='w',padx=30,pady=10)
        self.criar_botao(acoes,'Ativar / desativar',lambda:self.alternar_prestador(tb),largura=22,frente=RED).grid(row=0,column=0,padx=5,pady=3,sticky='ew')
        self.criar_botao(acoes,'Permissão de administrador',lambda:self.administrador_prestador_v9(tb),largura=29).grid(row=0,column=1,padx=5,pady=3,sticky='ew')
        self.criar_botao(acoes,'E-mail e dados bancários',lambda:self.configurar_integracoes_prestador(tb),largura=29).grid(row=1,column=0,padx=5,pady=3,sticky='ew')
        self.criar_botao(acoes,'Redefinir senha',lambda:self.redefinir_senha_prestador(tb),largura=29).grid(row=1,column=1,padx=5,pady=3,sticky='ew')
        self.criar_botao(acoes,'Excluir da lista',lambda:self.excluir_prestador(tb),largura=29,frente=RED).grid(row=2,column=0,padx=5,pady=3,sticky='ew')
        acoes.grid_columnconfigure(0,weight=1)
        acoes.grid_columnconfigure(1,weight=1)
        col=('id','nome','email','especialidade','ativo')
        tb=ttk.Treeview(self,columns=col,show='headings')
        for x,w in [('id',60),('nome',240),('email',260),('especialidade',200),('ativo',90)]:tb.heading(x,text=x.upper());tb.column(x,width=w)
        tb.pack(fill='both',expand=True,padx=30,pady=10)
        with ext.db(BANCO) as c: registros=c.execute('SELECT id,nome,email,especialidade,ativo FROM prestadores WHERE excluido=0 ORDER BY nome').fetchall()
        def preencher(*_):
            termo=pesquisa.get().strip().casefold()
            tb.delete(*tb.get_children())
            for pr in registros:
                if termo and termo not in (pr['nome']+' '+pr['email']+' '+(pr['especialidade'] or '')).casefold():continue
                tb.insert('', 'end', values=(pr['id'],pr['nome'],pr['email'],pr['especialidade'],'Sim' if pr['ativo'] else 'Não'))
        pesquisa.trace_add('write',preencher)
        preencher()
        # Controles posicionados ACIMA da tabela para não ficarem fora da janela.


    def cadastrar_prestador(self):
        janela=tk.Toplevel(self);janela.title('Cadastrar prestador');janela.configure(bg=BLACK);janela.geometry('560x485');janela.transient(self);janela.grab_set()
        campos={}
        for rotulo,chave in [('Nome','nome'),('E-mail (login)','email'),('Telefone','telefone'),('CPF/CNPJ','documento'),('Especialidade','especialidade'),('Senha inicial (mínimo 10 caracteres)','senha')]:
            tk.Label(janela,text=rotulo,bg=BLACK,fg=WHITE,font=('Arial',10,'bold')).pack(anchor='w',padx=24,pady=(8,2))
            en=tk.Entry(janela,show='*' if chave=='senha' else '',bg=DARK,fg=WHITE,insertbackground=WHITE,font=('Arial',12));en.pack(fill='x',padx=24,ipady=5);campos[chave]=en
        def salvar():
            try:
                d={k:v.get() for k,v in campos.items()};ext.cadastrar(BANCO,**d)
                janela.destroy();self.mostrar_prestadores();messagebox.showinfo('Prestador','Cadastro realizado.')
            except Exception as e:messagebox.showerror('Cadastro',str(e),parent=janela)
        self.criar_botao(janela,'SALVAR PRESTADOR',salvar,fundo=YELLOW,frente=BLACK).pack(pady=18)

    def redefinir_senha_prestador(self,tabela):
        selecao=tabela.selection()
        if not selecao:return messagebox.showwarning('Prestador','Selecione o prestador na lista.')
        pid=int(tabela.item(selecao[0])['values'][0])
        nome=str(tabela.item(selecao[0])['values'][1])
        janela=tk.Toplevel(self);janela.title('Redefinir senha — '+nome)
        janela.configure(bg=BLACK);janela.geometry('540x290');janela.transient(self);janela.grab_set()
        tk.Label(janela,text='Nova senha para '+nome,bg=BLACK,fg=YELLOW,
                 font=('Arial',14,'bold'),wraplength=480).pack(pady=12)
        entradas=[]
        for rotulo in ('Nova senha (mínimo 10 caracteres)','Confirmar nova senha'):
            tk.Label(janela,text=rotulo,bg=BLACK,fg=WHITE).pack(anchor='w',padx=22,pady=3)
            ent=tk.Entry(janela,show='*',bg=DARK,fg=WHITE,insertbackground=WHITE)
            ent.pack(fill='x',padx=22,ipady=6);entradas.append(ent)
        def salvar():
            a,b=[e.get() for e in entradas]
            if a!=b:return messagebox.showerror('Senhas','As duas senhas são diferentes.',parent=janela)
            if not messagebox.askyesno('Confirmar','Redefinir o login de '+nome+'? As sessões abertas podem exigir novo login.',parent=janela):return
            try:
                ext.redefinir_senha_prestador_desktop(BANCO,pid,a)
                janela.destroy();messagebox.showinfo('Senha','Senha atualizada. Entre novamente no portal com esta senha.')
            except Exception as exc:messagebox.showerror('Senha',str(exc),parent=janela)
        self.criar_botao(janela,'SALVAR NOVA SENHA',salvar).pack(pady=12)

    def configurar_integracoes_prestador(self,tabela):
        """Configuração administrativa: nunca armazena tokens ou senhas de API."""
        selecionados=tabela.selection()
        if not selecionados:
            return messagebox.showwarning('Prestador','Selecione um prestador na lista.')
        pid=int(tabela.item(selecionados[0])['values'][0])
        config=ext.obter_config_prestador(BANCO,pid)
        janela=tk.Toplevel(self);janela.title('Integrações e pagamentos — prestador '+str(pid))
        janela.configure(bg=BLACK);janela.geometry('630x760');janela.transient(self);janela.grab_set()
        legenda=tk.Label(janela,text='Dados para rascunhos de e-mail e futura integração por API.\nNão cole senhas nem tokens aqui.',
                          bg=BLACK,fg=YELLOW,justify='left',wraplength=570)
        legenda.pack(anchor='w',padx=20,pady=12)
        campos={}
        for titulo,chave in [('Provedor de envio (Gmail API)','provedor_email'),('E-mail remetente','email_remetente')]:
            tk.Label(janela,text=titulo,bg=BLACK,fg=WHITE).pack(anchor='w',padx=20,pady=(8,1))
            campo=tk.Entry(janela,bg=DARK,fg=WHITE,insertbackground=WHITE,font=('Arial',11))
            campo.insert(0,config.get(chave,'') or '');campo.pack(fill='x',padx=20,ipady=6)
            campos[chave]=campo
        tk.Label(janela,text='Dados bancários e cadastrais (texto simples para copiar e colar no e-mail)',
            bg=BLACK,fg=YELLOW,wraplength=570,justify='left').pack(anchor='w',padx=20,pady=(15,6))
        dados_texto=tk.Text(janela,height=11,wrap='word',bg=DARK,fg=WHITE,insertbackground=WHITE,font=('Arial',11))
        dados_texto.pack(fill='both',expand=True,padx=20,pady=(0,10))
        dados_texto.insert('1.0',config.get('dados_bancarios_texto','') or '')
        def salvar():
            try:
                atual={**config,**{k:e.get() for k,e in campos.items()}}
                atual['dados_bancarios_texto']=dados_texto.get('1.0','end').strip()
                ext.salvar_config_prestador(BANCO,pid,atual)
                janela.destroy()
                messagebox.showinfo('Prestador','Dados do prestador salvos.')
            except Exception as erro:
                messagebox.showerror('Configuração inválida',str(erro),parent=janela)
        self.criar_botao(janela,'SALVAR CONFIGURAÇÕES',salvar).pack(pady=15)

    def excluir_prestador(self,tabela):
        """Oculta o cadastro sem apagar vínculos com OS ou documentos históricos."""
        selecao=tabela.selection()
        if not selecao:return messagebox.showwarning('Seleção','Selecione um prestador.')
        pid=int(tabela.item(selecao[0])['values'][0])
        if not messagebox.askyesno('Excluir prestador',
            'Excluir este prestador da lista e bloquear seu login?\n'
            'O cadastro será arquivado para preservar OS, relatórios e auditoria.'):
            return
        with ext.db(BANCO) as c:
            c.execute('UPDATE prestadores SET ativo=0,excluido=1 WHERE id=?',(pid,))
        self.mostrar_prestadores()

    def alternar_prestador(self,tabela):
        sel=tabela.selection()
        if not sel:return messagebox.showwarning('Seleção','Selecione um prestador.')
        pid=int(tabela.item(sel[0])['values'][0])
        with ext.db(BANCO) as c:c.execute('UPDATE prestadores SET ativo=1-ativo WHERE id=?',(pid,))
        self.mostrar_prestadores()

    def selecionar_os_dialogo(self):
        with ext.db(BANCO) as c:
            registros=c.execute('SELECT id,numero_os,status FROM ordens_servico ORDER BY id DESC LIMIT 250').fetchall()
        if not registros:raise ValueError('Nenhuma OS cadastrada.')
        escolha=simpledialog.askinteger('Selecionar OS','Informe o ID numérico da OS (não o número formatado).\n'+', '.join(f'{r["id"]}={r["numero_os"]}' for r in registros[:12]),parent=self,minvalue=1)
        if escolha is None:return None
        if escolha not in {r['id'] for r in registros}:raise ValueError('OS não encontrada na lista recente.')
        return escolha

    def atribuir_os_selecionada(self):
        selecionado = self.tabela_os.selection()
        if not selecionado:
            messagebox.showwarning('Seleção','Selecione uma OS aberta ou pendente.'); return
        oid = int(self.tabela_os.item(selecionado[0])['values'][0])
        self.abrir_dialogo_atribuicao(oid)

    def atribuir_prestador(self):
        # Abre uma seleção legível de OS abertas ou pendentes, sem exigir IDs numéricos.
        with ext.db(BANCO) as c:
            ordens=c.execute('''SELECT o.id,o.numero_os,c.nome AS cliente,o.status
                                   FROM ordens_servico o JOIN clientes c ON c.id=o.cliente_id
                                   WHERE o.status IN ('Aberta','Pendente') ORDER BY o.id DESC''').fetchall()
        if not ordens:
            messagebox.showinfo('Atribuição','Não há OS abertas ou pendentes.'); return
        janela=tk.Toplevel(self); janela.title('Selecionar ordem de serviço')
        janela.configure(bg=BLACK);janela.geometry('740x270');janela.transient(self);janela.grab_set()
        painel=tk.Frame(janela,bg=BLACK,padx=24,pady=20)
        painel.pack(fill='both',expand=True)
        tk.Label(painel,text='SELECIONE A ORDEM DE SERVIÇO',bg=BLACK,fg=YELLOW,
                 font=('Arial',16,'bold')).pack(anchor='w',pady=(0,16))
        opcoes={f"{o['numero_os']} — {o['cliente']} ({o['status']}) [ID {o['id']}]":o['id'] for o in ordens}
        caixa=ttk.Combobox(painel,values=list(opcoes),state='readonly',width=78)
        caixa.pack(fill='x',ipady=7);caixa.current(0)
        def continuar():
            oid=opcoes.get(caixa.get())
            if oid is None:return
            janela.destroy()
            self.abrir_dialogo_atribuicao(oid)
        barra=tk.Frame(painel,bg=BLACK);barra.pack(fill='x',pady=18)
        self.criar_botao(barra,'CANCELAR',janela.destroy).pack(side='left')
        self.criar_botao(barra,'ESCOLHER PRESTADOR',continuar,
                         fundo=YELLOW,frente=BLACK,largura=24).pack(side='right')

    def abrir_dialogo_atribuicao(self, oid):
        with ext.db(BANCO) as c:
            ordem = c.execute('SELECT numero_os,status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
            prestadores = c.execute('SELECT id,nome,email FROM prestadores WHERE ativo=1 ORDER BY nome').fetchall()
            atual_id = ext.responsavel_atual(c,oid)
        if not ordem or ordem['status'] not in ext.ATIVAS:
            messagebox.showwarning('Atribuição','Somente OS aberta ou pendente.');return
        if not prestadores:
            messagebox.showwarning('Prestadores','Cadastre um prestador ativo primeiro.');return
        janela = tk.Toplevel(self)
        janela.title('Atribuição de OS')
        janela.configure(bg=BLACK)
        janela.geometry('670x340')
        janela.minsize(580,300)
        janela.transient(self)
        janela.grab_set()
        painel=tk.Frame(janela,bg=BLACK,padx=24,pady=18)
        painel.pack(fill='both',expand=True)
        tk.Label(painel,text=f"ATRIBUIR / TRANSFERIR — {ordem['numero_os']}",
                 font=('Arial',17,'bold'),fg=YELLOW,bg=BLACK).pack(anchor='w')
        mapa={f"{p['nome']} — {p['email']} [ID {p['id']}]":p['id'] for p in prestadores}
        texto_atual=next((nome for nome,pid in mapa.items() if pid==atual_id),'Não atribuído')
        tk.Label(painel,text=f'Responsável atual: {texto_atual}',bg=BLACK,fg=WHITE,
                 font=('Arial',11),wraplength=580).pack(anchor='w',pady=(13,10))
        tk.Label(painel,text='Selecione o prestador que ficará responsável:',
                 bg=BLACK,fg=WHITE,font=('Arial',10,'bold')).pack(anchor='w')
        escolha=ttk.Combobox(painel,values=list(mapa),state='readonly',width=64)
        escolha.pack(fill='x',ipady=5,pady=(5,10))
        if atual_id: escolha.set(texto_atual)
        else: escolha.current(0)
        tk.Label(painel,text='Os outros prestadores continuarão vendo a OS. O histórico de todos será preservado.',
                 bg=BLACK,fg=GRAY,wraplength=580,justify='left').pack(anchor='w')
        rodape=tk.Frame(painel,bg=BLACK)
        rodape.pack(fill='x',pady=15)
        def atribuir():
            pid=mapa.get(escolha.get())
            if pid is None: return messagebox.showwarning('Prestador','Selecione um prestador.',parent=janela)
            if atual_id and pid!=atual_id:
                if not messagebox.askyesno('Transferir OS','Transferir a responsabilidade e registrar a alteração no histórico?',parent=janela):
                    return
            try:
                mudou=ext.atribuir(BANCO,oid,pid)
            except Exception as e:
                return messagebox.showerror('Atribuição',str(e),parent=janela)
            janela.destroy()
            if hasattr(self,'label_responsavel_os') and self.label_responsavel_os.winfo_exists():
                self.label_responsavel_os.config(text='Responsável no portal: '+
                       next((p['nome'] for p in prestadores if p['id']==pid),'Não atribuído'))
            messagebox.showinfo('Atribuição','Responsabilidade registrada.' if mudou else 'Este prestador já é o responsável.')
            if hasattr(self,'tabela_os') and self.tabela_os.winfo_exists(): self.carregar_os_ativas()
        def liberar():
            if not atual_id: return
            if not messagebox.askyesno('Deixar sem responsável',
                    'Deixar esta OS disponível para ser assumida? O histórico será mantido.',parent=janela):return
            try: ext.desatribuir(BANCO,oid)
            except Exception as e: return messagebox.showerror('Atribuição',str(e),parent=janela)
            janela.destroy()
            if hasattr(self,'label_responsavel_os') and self.label_responsavel_os.winfo_exists():
                self.label_responsavel_os.config(text='Responsável no portal: Não atribuído')
            if hasattr(self,'tabela_os') and self.tabela_os.winfo_exists(): self.carregar_os_ativas()
        self.criar_botao(rodape,'CANCELAR',janela.destroy,largura=13).pack(side='left')
        if atual_id:
            self.criar_botao(rodape,'DEIXAR DISPONÍVEL',liberar,largura=21,frente=ORANGE).pack(side='left',padx=8)
        self.criar_botao(rodape,'SALVAR ATRIBUIÇÃO',atribuir,largura=20,
                         fundo=YELLOW,frente=BLACK).pack(side='right')

    def email_admin(self):
        try:
            oid=self.selecionar_os_dialogo()
            if oid is None:return
            publicado=fluxo.ultimo_documento(BANCO,oid)
            if not publicado:
                raise ValueError('Esta OS não possui PDF publicado. Encerre-a ou use Republicar PDF no Histórico.')
            pdf=fluxo.validar_pdf_publicado(publicado)
            rascunho=ext.criar_email_rascunho(BANCO,oid,pdf)
            messagebox.showinfo('E-mail preparado',f'Rascunho .eml com PDF:\n{rascunho}\n\nNenhum e-mail foi enviado.')
            webbrowser.open('file://'+rascunho)
        except Exception as e:messagebox.showerror('E-mail',str(e))

    def nota_admin(self):
        try:
            oid=self.selecionar_os_dialogo()
            if oid is None:return
            caminho=ext.criar_rascunho_fiscal(BANCO,oid)
            messagebox.showinfo('Rascunho fiscal',f'Dados preparados em:\n{caminho}\n\nNENHUMA NOTA FISCAL FOI EMITIDA.')
        except Exception as e:messagebox.showerror('Nota fiscal',str(e))

    # ========================================================
    # MÓDULOS FUTUROS
    # ========================================================

    def tela_em_desenvolvimento(self, titulo):
        self.navegar_para(
            lambda: self.mostrar_tela_em_desenvolvimento(titulo)
        )

    def mostrar_tela_em_desenvolvimento(self, titulo):
        self.limpar_tela()
        self.tela_atual = lambda: self.mostrar_tela_em_desenvolvimento(titulo)

        self.criar_cabecalho(titulo)

        centro = tk.Frame(self, bg=BLACK)
        centro.pack(expand=True)

        tk.Label(
            centro,
            text="MÓDULO EM DESENVOLVIMENTO",
            font=("Arial", 22, "bold"),
            fg=YELLOW,
            bg=BLACK
        ).pack(pady=12)

        tk.Label(
            centro,
            text="A estrutura já está preparada para receber esta função.",
            font=("Arial", 11),
            fg=GRAY,
            bg=BLACK
        ).pack()

    def menu_notas(self):
        self.nota_admin()

    def menu_emails(self):
        self.email_admin()


# ============================================================
# INICIAR
# ============================================================

if __name__ == "__main__":
    app = App()
    app.mainloop()
