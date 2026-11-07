"""AUTOSEG — interface desktop GTK4/libadwaita.

Mesmo backend, banco e regras dos portais. Roda em Linux (Wayland/X11) e
macOS. Documentação em docs/GTK4_LINUX_MACOS.md.
"""
import json
import os
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

import gtk_comum as ui
import gtk_dialogos as dialogos
from banco import BANCO, conectar_banco
import prestadores_ext as ext
import fluxo_os as fluxo
import atendimento_os as aten
import cadastros_v9 as cad9
import estoque_materiais as estoque
import empresa_financeiro as empresa
import catalogo_servicos as catalogo
import portal_negocios as neg
import links_publicos as links9
import importacao_yaml
import completude
import composicao
from integracao import clientes as clientes_core
from repositorios import ordens as ordens_repo
import runtime_config

if os.environ.get("AUTOSEG_DEV") == "1":
    import tuneis_dev as tuneis
else:
    import gerenciar_tuneis as tuneis


CSS = b"""
.card {
    padding: 14px 18px;
    border-radius: 12px;
}
.data-table {
    border-radius: 10px;
}
.data-table listview {
    background: transparent;
}
.data-table header button {
    font-weight: 600;
}
"""


class Janela(Adw.ApplicationWindow):
    def __init__(self, aplicativo):
        super().__init__(application=aplicativo)
        self.set_title(ui.APP_TITLE)
        self.set_default_size(1180, 700)
        self.set_size_request(900, 560)
        self._ativo = True
        self._links_estado = {}
        self._links_busy = False
        self._pagina_atual = "inicio"
        self.url_prestador = ""
        self.aviso_prestador = ""
        self.erro_portal = ""
        self._iniciar_backend()
        self._construir()
        self.connect("close-request", self._ao_fechar)
        self._carregar_tudo()
        GLib.timeout_add_seconds(2, self._processar_eventos_portal)
        GLib.timeout_add_seconds(10, self._atualizar_links_async)
        if os.environ.get("AUTOSEG_SMOKE") == "1":
            GLib.timeout_add(3000, self._fechar_smoke)

    def _fechar_smoke(self):
        self.close()
        return False

    def _iniciar_backend(self):
        self.portal_prestador = None
        self.servidor_portal = None
        try:
            ui.BASE.mkdir(parents=True, exist_ok=True)
            from banco import criar_banco
            criar_banco()
            ext.instalar(BANCO)
            fluxo.instalar(BANCO)
            aten.instalar(BANCO)
            cad9.instalar(BANCO)
            estoque.instalar(BANCO)
            empresa.instalar(BANCO)
            catalogo.instalar(BANCO)
            composicao.instalar()
            composicao.instalar_banco(BANCO)
            try:
                fluxo.recuperar_relatorios_antigos(BANCO)
            except Exception as erro:
                print("Aviso: recuperação de PDFs anteriores:", erro)
            if runtime_config.web_access_enabled():
                from portal_prestador import PortalPrestador
                from servidor_web import ServidorPortal
                prestador_cfg = runtime_config.provider_server()
                self.portal_prestador = PortalPrestador(
                    BANCO, host=prestador_cfg.host, porta=prestador_cfg.port)
                try:
                    self.url_prestador = self.portal_prestador.iniciar()
                except Exception as erro:
                    self.aviso_prestador = str(erro)
                    print("Portal do prestador indisponível:", erro)
                cliente_cfg = runtime_config.client_server()
                self.servidor_portal = ServidorPortal(
                    BANCO, ui.PASTA_APP,
                    porta=cliente_cfg.port, host=cliente_cfg.host)
                try:
                    self.servidor_portal.iniciar()
                except Exception as erro:
                    self.erro_portal = str(erro)
                    print("Portal do cliente indisponível:", erro)
            else:
                self.aviso_prestador = "Servidor web desativado (modo local)."
        except Exception as erro:
            self.erro_portal = str(erro)
            self.portal_prestador = None
            self.servidor_portal = None
            print("Falha ao iniciar o backend:", erro)

    # ------------------------------------------------------------------
    # Estrutura principal
    # ------------------------------------------------------------------

    def _construir(self):
        self._instalar_css()
        self._acoes()
        split = Adw.NavigationSplitView()
        split.set_min_sidebar_width(220)
        split.set_max_sidebar_width(280)
        split.set_sidebar(self._construir_lateral())
        split.set_content(self._construir_conteudo())
        self.set_content(split)

    def _instalar_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _acoes(self):
        for nome, retorno in (
            ("sobre", self._sobre),
            ("pasta", lambda: ui.abrir_caminho(ui.BASE, self)),
            ("atualizar", self._atualizar_tudo),
        ):
            acao = Gio.SimpleAction.new(nome, None)
            acao.connect("activate", lambda *_args, cb=retorno: cb())
            self.add_action(acao)

    def _construir_lateral(self):
        pagina = Adw.NavigationPage(title="AUTOSEG")
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="AUTOSEG", subtitle=f"v{ui.VERSAO}"))
        toolbar.add_top_bar(header)

        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.lista_navegacao = Gtk.ListBox()
        self.lista_navegacao.add_css_class("navigation-sidebar")
        self.lista_navegacao.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_itens = [
            ("inicio", "Início", "go-home-symbolic"),
            ("clientes", "Clientes", "system-users-symbolic"),
            ("os", "Ordens de serviço", "document-edit-symbolic"),
            ("historico", "Histórico e relatórios", "document-open-recent-symbolic"),
            ("financeiro", "Financeiro", "accessories-calculator-symbolic"),
            ("prestadores", "Prestadores", "avatar-default-symbolic"),
            ("portal", "Portal do cliente", "network-server-symbolic"),
            ("pj", "Condomínios e chamados", "view-grid-symbolic"),
            ("catalogo", "Serviços e valores", "view-list-symbolic"),
            ("composicao", "Composição de valores", "emblem-important-symbolic"),
            ("estoque", "Materiais e estoque", "package-x-generic-symbolic"),
        ]
        for _nome, titulo_texto, icone in self.nav_itens:
            linha = Adw.ActionRow(title=titulo_texto, icon_name=icone)
            linha.set_activatable(True)
            self.lista_navegacao.append(linha)
        self.lista_navegacao.connect("row-selected", self._navegar)

        rolagem = Gtk.ScrolledWindow(vexpand=True)
        rolagem.set_child(self.lista_navegacao)
        caixa.append(rolagem)

        rodape = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(12)
        rodape.set_margin_start(14)
        rodape.set_margin_end(14)
        self.rotulo_armazenamento = Gtk.Label(xalign=0, wrap=True)
        self.rotulo_armazenamento.add_css_class("caption")
        self.rotulo_armazenamento.add_css_class("dim-label")
        self.rotulo_banco = Gtk.Label(xalign=0, wrap=True)
        self.rotulo_banco.add_css_class("caption")
        self.rotulo_banco.add_css_class("dim-label")
        rodape.append(self.rotulo_armazenamento)
        rodape.append(self.rotulo_banco)
        caixa.append(rodape)
        toolbar.set_content(caixa)
        pagina.set_child(toolbar)
        return pagina

    def _construir_conteudo(self):
        pagina = Adw.NavigationPage(title="Início")
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.titulo_janela = Adw.WindowTitle(title="Início")
        header.set_title_widget(self.titulo_janela)
        menu = Gio.Menu()
        menu.append("Atualizar dados", "win.atualizar")
        menu.append("Abrir pasta de dados", "win.pasta")
        menu.append("Sobre o AUTOSEG", "win.sobre")
        botao_menu = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        botao_menu.set_tooltip_text("Menu principal")
        header.pack_end(botao_menu)
        toolbar.add_top_bar(header)

        self.stack = Adw.ViewStack()
        self.stack.add_titled(self._pagina_inicio(), "inicio", "Início")
        self.stack.add_titled(self._pagina_clientes(), "clientes", "Clientes")
        self.stack.add_titled(self._pagina_os(), "os", "Ordens de serviço")
        self.stack.add_titled(self._pagina_historico(), "historico", "Histórico")
        self.stack.add_titled(self._pagina_financeiro(), "financeiro", "Financeiro")
        self.stack.add_titled(self._pagina_prestadores(), "prestadores", "Prestadores")
        self.stack.add_titled(self._pagina_portal(), "portal", "Portal do cliente")
        self.stack.add_titled(self._pagina_pj(), "pj", "Condomínios e chamados")
        self.stack.add_titled(self._pagina_catalogo(), "catalogo", "Serviços e valores")
        self.stack.add_titled(self._pagina_composicao(), "composicao", "Composição de valores")
        self.stack.add_titled(self._pagina_estoque(), "estoque", "Materiais e estoque")
        self.toast_overlay = Adw.ToastOverlay(child=self.stack)
        toolbar.set_content(self.toast_overlay)
        pagina.set_child(toolbar)
        self.lista_navegacao.select_row(self.lista_navegacao.get_row_at_index(0))
        GLib.idle_add(self._selecionar_inicio)
        return pagina

    def _sobre(self):
        sobre = Adw.AboutDialog(
            application_name="AUTOSEG",
            application_icon="utilities-system-monitor-symbolic",
            developer_name="AUTOSEG — Automação e Segurança",
            version=ui.VERSAO,
            comments="Gestão de serviços, ordens, financeiro e portais.\n"
                     "Interface GTK4/libadwaita sobre o backend compartilhado.",
            website="https://github.com/spindler051/AUTOSEG",
        )
        sobre.present(self)

    def _selecionar_inicio(self):
        self._ir_para("inicio")
        return False

    def _navegar(self, _lista, linha):
        if linha is None:
            return
        indice = linha.get_index()
        if not 0 <= indice < len(self.nav_itens):
            return
        nome, titulo_texto, _icone = self.nav_itens[indice]
        self._pagina_atual = nome
        self.stack.set_visible_child_name(nome)
        self.titulo_janela.set_title(titulo_texto)
        self._atualizar_pagina(nome)

    def _ir_para(self, nome):
        for indice, (chave, _titulo, _icone) in enumerate(self.nav_itens):
            if chave == nome:
                self.lista_navegacao.select_row(self.lista_navegacao.get_row_at_index(indice))
                return

    def _atualizar_pagina(self, nome):
        try:
            {
                "inicio": self._atualizar_inicio,
                "clientes": self.carregar_clientes,
                "os": self.carregar_os,
                "historico": self.carregar_historico,
                "financeiro": self.carregar_financeiro,
                "prestadores": self.carregar_prestadores,
                "portal": self.carregar_portal,
                "pj": self.carregar_pj,
                "catalogo": self.carregar_catalogo,
                "composicao": self.carregar_composicao,
                "estoque": self.carregar_estoque,
            }[nome]()
        except Exception as erro:
            print("Falha ao atualizar", nome, erro)

    def _carregar_tudo(self):
        for nome in ("clientes", "os", "historico", "financeiro", "prestadores",
                     "portal", "pj", "catalogo", "composicao", "estoque"):
            self._atualizar_pagina(nome)
        self._atualizar_inicio()
        self._atualizar_links_async()

    def _atualizar_tudo(self):
        self._carregar_tudo()
        ui.toast(self, "Dados atualizados.")

    # ------------------------------------------------------------------
    # Início
    # ------------------------------------------------------------------

    def _pagina_inicio(self):
        rolagem = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        clamp = Adw.Clamp(maximum_size=1100, tightening_threshold=780)
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        caixa.set_margin_top(20)
        caixa.set_margin_bottom(26)
        caixa.set_margin_start(24)
        caixa.set_margin_end(24)

        logo = ui.PASTA_APP / "logo.png"
        if logo.is_file():
            try:
                imagem = Gtk.Picture.new_for_filename(str(logo))
                imagem.set_content_fit(Gtk.ContentFit.CONTAIN)
                imagem.set_size_request(-1, 78)
                imagem.set_halign(Gtk.Align.START)
                caixa.append(imagem)
            except Exception:
                pass
        subtitulo = Gtk.Label(label="Painel principal", xalign=0)
        subtitulo.add_css_class("title-2")
        caixa.append(subtitulo)
        caixa.append(ui.legenda(
            "Mesmo banco e mesmas regras dos portais. "
            "A interface é GTK4/libadwaita em Linux e macOS."))

        atalhos = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        atalhos.append(ui.botao("Novo cliente", lambda: self.novo_cliente(), icone="list-add-symbolic"))
        atalhos.append(ui.botao("Nova OS", lambda: self.nova_os_rapida(), icone="document-new-symbolic"))
        atalhos.append(ui.botao("Abrir portal do cliente", self._abrir_portal_navegador,
                                icone="web-browser-symbolic"))
        atalhos.append(ui.botao("Preparar e-mail", self._email_admin))
        atalhos.append(ui.botao("Rascunho fiscal", self._nota_admin))
        caixa.append(atalhos)

        grade = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
        self.cards = {}
        for indice, (chave, titulo_card, classe) in enumerate((
            ("abertas", "OS abertas", "error"),
            ("iniciadas", "OS iniciadas", "warning"),
            ("pendentes", "OS pendentes", "warning"),
            ("receber", "A receber", "warning"),
            ("recebido", "Recebido", "success"),
            ("clientes", "Clientes ativos", "accent"),
        )):
            card, valor_label, _detalhe = ui.cartao(titulo_card, "—", classe)
            grade.attach(card, indice, 0, 1, 1)
            self.cards[chave] = valor_label
        caixa.append(grade)

        grupo = Adw.PreferencesGroup(title="Sistema")
        caixa.append(grupo)
        self.linha_portal = Adw.ActionRow(
            title="Portal do cliente", subtitle="Verificando…",
            icon_name="network-server-symbolic")
        self.linha_portal.set_activatable(True)
        self.linha_portal.connect("activated", lambda *_args: self._abrir_portal_navegador())
        grupo.add(self.linha_portal)
        self.linha_prestador = Adw.ActionRow(
            title="Portal do prestador", subtitle="Verificando…",
            icon_name="network-workgroup-symbolic")
        self.linha_prestador.set_activatable(True)
        self.linha_prestador.connect("activated", lambda *_args: self._abrir_portal_prestador())
        grupo.add(self.linha_prestador)
        self.linha_espaco = Adw.ActionRow(
            title="Espaço em disco", subtitle="—", icon_name="drive-harddisk-symbolic")
        abrir_pasta = Gtk.Button(label="Abrir pasta")
        abrir_pasta.add_css_class("flat")
        abrir_pasta.connect("clicked", lambda *_args: ui.abrir_caminho(ui.BASE, self))
        self.linha_espaco.add_suffix(abrir_pasta)
        grupo.add(self.linha_espaco)
        self.linha_banco = Adw.ActionRow(
            title="Banco local", subtitle="—", icon_name="x-office-database-symbolic")
        grupo.add(self.linha_banco)

        grupo_links = Adw.PreferencesGroup(title="Links externos atuais")
        caixa.append(grupo_links)
        self.linhas_links = {}
        for porta in links9.PORTAS:
            linha = Adw.ActionRow(
                title=f"Link público — porta {porta}", subtitle="Não detectado",
                icon_name="globe-symbolic")
            linha.set_activatable(True)
            linha.connect("activated", lambda *_args, p=porta: self._abrir_link_publico(p))
            grupo_links.add(linha)
            self.linhas_links[porta] = linha
        acoes_tuneis = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        acoes_tuneis.set_margin_top(4)
        acoes_tuneis.append(ui.botao("Iniciar / reconectar túneis", self._iniciar_tuneis))
        acoes_tuneis.append(ui.botao("Início automático", self._configurar_auto))
        caixa.append(acoes_tuneis)

        clamp.set_child(caixa)
        rolagem.set_child(clamp)
        return rolagem

    def _atualizar_inicio(self):
        clientes = clientes_core.contar_ativos(BANCO)
        resumo_os = ordens_repo.resumo(BANCO)
        resumo_fin = ordens_repo.financeiro_resumo(BANCO)
        self.cards["abertas"].set_text(str(resumo_os["abertas"]))
        self.cards["iniciadas"].set_text(str(resumo_os["iniciadas"]))
        self.cards["pendentes"].set_text(str(resumo_os["pendentes"]))
        self.cards["receber"].set_text(ui.brl(resumo_fin["a_receber"]))
        self.cards["recebido"].set_text(ui.brl(resumo_fin["recebido"]))
        self.cards["clientes"].set_text(str(clientes))

        info = self.servidor_portal.info() if getattr(self, "servidor_portal", None) else {
            "ativo": False, "url_local": "", "url_rede": "", "erro": self.erro_portal}
        if info["ativo"]:
            rede = self._url_rede_portal(info)
            self.linha_portal.set_subtitle(
                f"Online • {info['url_local']}" + (f" • {rede}" if rede else " • somente este computador"))
        else:
            self.linha_portal.set_subtitle(
                f"Offline • {info.get('erro') or self.erro_portal or 'clique para abrir o portal'}")
        if self.url_prestador:
            self.linha_prestador.set_subtitle(f"Online • {self.url_prestador}")
        else:
            self.linha_prestador.set_subtitle(
                self.aviso_prestador or "Offline • porta 8766 indisponível")

        try:
            uso = shutil.disk_usage(ui.BASE)
            livres = uso.free / 1024 ** 3
            total = uso.total / 1024 ** 3
            percentual = (uso.used / uso.total) * 100
            self.linha_espaco.set_subtitle(
                f"{livres:.1f} GB livres de {total:.0f} GB ({percentual:.0f}% em uso) • {ui.BASE}")
            self.rotulo_armazenamento.set_text(
                f"Disco: {livres:.1f} GB livres de {total:.0f} GB")
        except OSError as erro:
            self.linha_espaco.set_subtitle(str(erro))
        try:
            tamanho = Path(BANCO).stat().st_size / 1024 ** 2
            self.linha_banco.set_subtitle(f"{BANCO} • {tamanho:.1f} MB")
            self.rotulo_banco.set_text(f"Banco: {tamanho:.1f} MB")
        except OSError:
            self.linha_banco.set_subtitle(str(BANCO))
        self._aplicar_links(self._links_estado)

    def _abrir_link_publico(self, porta):
        url = self._links_estado.get(str(porta), {}).get("url", "")
        if not url:
            ui.info(self, "Link público", "Nenhum link público verificado para esta porta.")
            return
        ui.abrir_uri(url, self)

    def _atualizar_links_async(self):
        if self._links_busy:
            return True
        self._links_busy = True

        def worker():
            try:
                estado = links9.estado_com_manuais()
            except Exception as erro:
                print("Falha consultando links públicos:", erro)
                estado = {}
            GLib.idle_add(self._aplicar_links, estado)
            return False

        threading.Thread(target=worker, daemon=True, name="AUTOSEG-Links").start()
        return True

    def _aplicar_links(self, estado):
        self._links_busy = False
        if not self._ativo:
            return False
        self._links_estado = estado or {}
        for porta, linha in getattr(self, "linhas_links", {}).items():
            url = self._links_estado.get(str(porta), {}).get("url", "")
            linha.set_subtitle(url or "Não detectado")
        if getattr(self, "portal_links", None):
            for porta, linha in self.portal_links.items():
                url = self._links_estado.get(str(porta), {}).get("url", "")
                linha.set_subtitle(url or "Não detectado")
        return False

    def _escolher_os(self, titulo_texto, ao_escolher):
        with ext.db(BANCO) as c:
            registros = c.execute(
                "SELECT id,numero_os,status FROM ordens_servico ORDER BY id DESC LIMIT 250"
            ).fetchall()
        if not registros:
            ui.info(self, "Ordens de serviço", "Nenhuma OS cadastrada.")
            return
        mapa = {f"{r['numero_os']} — {r['status']} [ID {r['id']}]": r["id"]
                for r in registros}
        ui.DialogoEscolha(self, titulo_texto, "Ordem de serviço", list(mapa),
                          lambda texto: ao_escolher(mapa.get(texto))).present(self)

    def _email_admin(self):
        self._escolher_os("Preparar e-mail com PDF", self._email_os)

    def _email_os(self, os_id):
        if os_id is None:
            return
        try:
            publicado = fluxo.ultimo_documento(BANCO, os_id)
            if not publicado:
                raise ValueError("Esta OS não possui PDF publicado. Encerre-a ou use "
                                 "Republicar PDF no Histórico.")
            pdf = fluxo.validar_pdf_publicado(publicado)
            rascunho = ext.criar_email_rascunho(BANCO, os_id, pdf)
            ui.info(self, "E-mail preparado",
                    f"Rascunho .eml com PDF:\n{rascunho}\n\nNenhum e-mail foi enviado.")
            ui.abrir_caminho(rascunho, self)
        except Exception as erro:
            ui.aviso_erro(self, "E-mail", str(erro))

    def _nota_admin(self):
        self._escolher_os("Preparar rascunho fiscal", self._nota_os)

    def _nota_os(self, os_id):
        if os_id is None:
            return
        try:
            caminho = ext.criar_rascunho_fiscal(BANCO, os_id)
            ui.info(self, "Rascunho fiscal",
                    f"Dados preparados em:\n{caminho}\n\nNENHUMA NOTA FISCAL FOI EMITIDA.")
        except Exception as erro:
            ui.aviso_erro(self, "Nota fiscal", str(erro))

    def _iniciar_tuneis(self):
        ui.toast(self, "Tentando iniciar os túneis…")

        def worker():
            try:
                tuneis.iniciar()
                mensagem = "Túneis iniciados. Os links aparecem após a verificação."
            except Exception as erro:
                mensagem = f"Túneis: {erro}"
            GLib.idle_add(self._fim_tuneis, mensagem)
            return False

        threading.Thread(target=worker, daemon=True, name="AUTOSEG-Tuneis").start()

    def _fim_tuneis(self, mensagem):
        if self._ativo:
            ui.toast(self, mensagem)
            self._atualizar_links_async()
        return False

    def _configurar_auto(self):
        config = links9.TUNEIS / "auto_iniciar.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        try:
            ativo = bool(json.loads(config.read_text(encoding="utf-8")).get("ativo"))
        except (OSError, ValueError):
            ativo = False
        if ativo:
            def desativar():
                config.write_text(json.dumps({"ativo": False}), encoding="utf-8")
                ui.toast(self, "Início automático desativado.")
            ui.alerta(self, "Cloudflare", "Desativar a abertura automática de túneis ao iniciar?",
                      desativar)
            return

        def ativar():
            config.write_text(json.dumps({"ativo": True}), encoding="utf-8")
            self._iniciar_tuneis()
            ui.toast(self, "Início automático ativado.")

        ui.alerta(
            self, "Cloudflare — publicação na internet",
            "Os dois portais serão publicados na internet sem Cloudflare Access.\n\n"
            "Não utilize dados reais até revisar login e permissões.\n\n"
            "Ativar o início automático dos dois túneis de teste?",
            ativar, destrutivo=True, rotulo_ok="Ativar")

    # ------------------------------------------------------------------
    # Clientes
    # ------------------------------------------------------------------

    def _pagina_clientes(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.busca_clientes = Gtk.SearchEntry(
            placeholder_text="Pesquisar nome, documento ou cidade")
        self.busca_clientes.set_hexpand(True)
        self.busca_clientes.connect("search-changed", lambda *_args: self.carregar_clientes())
        topo = ui.barra(
            self.busca_clientes,
            ui.botao("Pesquisar", self.carregar_clientes, icone="system-search-symbolic"),
            ui.botao("Importar YAML", self._importar_cliente_yaml),
            ui.botao("Modelo YAML", self._modelo_cliente_yaml),
            ui.botao("Atribuir síndico/gestor", self._atribuir_responsavel,
                     icone="system-users-symbolic"),
            ui.botao("Novo cliente", self.novo_cliente, icone="list-add-symbolic",
                     css="suggested-action"))
        pagina.append(topo)
        self.tabela_clientes = ui.Tabela([
            ("ID", 65, False, 0.5),
            ("Nome / Razão Social", 0, True, 0.0),
            ("CPF / CNPJ", 145, False, 0.5),
            ("Cidade", 140, False, 0.0),
            ("Telefone", 130, False, 0.5),
            ("Status", 95, False, 0.5),
            ("Dados", 110, False, 0.5),
        ], ao_ativar=self._editar_cliente)
        pagina.append(self.tabela_clientes.widget)
        rodape = ui.barra(
            ui.botao("Abrir / editar", self._editar_cliente),
            ui.botao("Nova OS do cliente", self._nova_os_cliente),
            ui.botao("Excluir / desativar", self._excluir_cliente, css="destructive-action"),
            ui.botao("Acesso web / senha", self._senha_cliente),
            ui.botao("Abrir portal do cliente", self._abrir_portal_navegador))
        pagina.append(rodape)
        return pagina

    def novo_cliente(self):
        dialogos.DialogoCliente(self).present(self)

    def nova_os_rapida(self):
        try:
            dialogos.DialogoOSRapida(self).present(self)
        except Exception as erro:
            ui.aviso_erro(self, "Nova OS", str(erro))

    def _atribuir_responsavel(self):
        try:
            dialogos.DialogoResponsavel(self).present(self)
        except Exception as erro:
            ui.aviso_erro(self, "Síndico / gestor", str(erro))

    def carregar_clientes(self):
        termo = self.busca_clientes.get_text().strip() if hasattr(self, "busca_clientes") else ""
        linhas = []
        for registro in clientes_core.listar(termo):
            dados = dict(registro["fields"])
            linhas.append((
                int(registro["id"]), dados.get("nome") or "(sem nome)",
                cad9.formatar_documento(dados.get("documento", "")),
                dados.get("cidade") or "", dados.get("telefone") or "",
                dados.get("status") or "",
                "Incompletos" if completude.cliente_faltantes(dados) else "OK"))
        self.tabela_clientes.definir_linhas(linhas)

    def _cliente_selecionado(self):
        valores = self.tabela_clientes.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Seleção", "Selecione um cliente primeiro.")
            return None
        return valores

    def _editar_cliente(self):
        valores = self._cliente_selecionado()
        if valores:
            dialogos.DialogoCliente(self, valores[0]).present(self)

    def _nova_os_cliente(self):
        valores = self._cliente_selecionado()
        if valores:
            self.nova_os(cliente_id=valores[0])

    def _excluir_cliente(self):
        valores = self._cliente_selecionado()
        if not valores:
            return
        cliente_id, nome = valores[0], valores[1]
        conexao = conectar_banco()
        try:
            total = conexao.execute("SELECT COUNT(*) FROM ordens_servico WHERE cliente_id=?",
                                    (cliente_id,)).fetchone()[0]
        finally:
            conexao.close()
        if total:
            def desativar():
                try:
                    cad9.desativar_cliente(BANCO, cliente_id, "AUTOSEG desktop")
                except Exception as erro:
                    ui.aviso_erro(self, "Cadastro", str(erro))
                    return
                self.carregar_clientes()
                ui.toast(self, "Cliente desativado; histórico preservado.")
            ui.alerta(
                self, "Preservar histórico",
                f"{nome} possui OS e relatórios. Não é possível apagar fisicamente os vínculos.\n\n"
                "Deseja desativar o cadastro, mantendo OS, documentos e histórico?",
                desativar, rotulo_ok="Desativar")
            return

        def excluir():
            try:
                neg.cliente_excluir(BANCO, cliente_id, 0)
            except Exception as erro:
                ui.aviso_erro(self, "Exclusão bloqueada", str(erro))
                return
            self.carregar_clientes()
            ui.toast(self, "Cliente excluído.")

        ui.alerta(self, "Excluir cliente", f"Deseja realmente excluir:\n\n{nome}?",
                  excluir, destrutivo=True, rotulo_ok="Excluir")

    def _senha_cliente(self):
        valores = self._cliente_selecionado()
        if valores:
            dialogos.DialogoSenhaCliente(self, valores[0], valores[1]).present(self)

    def _escolher_yaml(self, titulo_texto, callback):
        dialogo = Gtk.FileDialog(title=titulo_texto)
        filtro = Gtk.FileFilter()
        filtro.set_name("YAML")
        filtro.add_pattern("*.yaml")
        filtro.add_pattern("*.yml")
        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)
        dialogo.set_filters(filtros)
        dialogo.open(self, None, callback)

    def _importar_cliente_yaml(self):
        self._escolher_yaml("Importar cliente YAML", self._cliente_yaml_escolhido)

    def _cliente_yaml_escolhido(self, dialogo, resultado):
        try:
            arquivo = dialogo.open_finish(resultado)
            caminho = Path(arquivo.get_path())
            pre = importacao_yaml.cliente(caminho.name, caminho.read_bytes())
        except Exception as erro:
            ui.aviso_erro(self, "YAML de cliente", str(erro))
            return
        dialogos.DialogoCliente(self, importado=pre).present(self)

    def _modelo_cliente_yaml(self):
        self._baixar_modelo_yaml("modelo_cliente.yaml", importacao_yaml.MODELO_CLIENTE_VAZIO)

    def _baixar_modelo_yaml(self, nome, conteudo):
        dialogo = Gtk.FileDialog(title="Salvar modelo YAML", initial_name=nome)
        filtro = Gtk.FileFilter()
        filtro.set_name("YAML")
        filtro.add_pattern("*.yaml")
        filtro.add_pattern("*.yml")
        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)
        dialogo.set_filters(filtros)
        dialogo.save(self, None, lambda d, r: self._modelo_salvo(d, r, conteudo))

    def _modelo_salvo(self, dialogo, resultado, conteudo):
        try:
            arquivo = dialogo.save_finish(resultado)
            destino = Path(arquivo.get_path())
        except GLib.Error:
            return
        if destino.suffix.lower() not in (".yaml", ".yml"):
            destino = destino.with_suffix(".yaml")
        try:
            destino.write_text(conteudo, encoding="utf-8")
        except OSError as erro:
            ui.aviso_erro(self, "Modelo YAML", str(erro))
            return
        ui.toast(self, f"Modelo salvo em {destino}")

    # ------------------------------------------------------------------
    # Ordens de serviço
    # ------------------------------------------------------------------

    def _pagina_os(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.busca_os = Gtk.SearchEntry(
            placeholder_text="Pesquisar OS, cliente, prestador ou situação")
        self.busca_os.set_hexpand(True)
        self.busca_os.connect("search-changed", lambda *_args: self.carregar_os())
        topo = ui.barra(
            self.busca_os,
            ui.botao("Nova OS", self.nova_os_rapida, icone="list-add-symbolic",
                     css="suggested-action"),
            ui.botao("Importar YAML", self._importar_os_yaml),
            ui.botao("Modelo YAML", self._modelo_os_yaml),
            ui.botao("Histórico / PDF", lambda: self._ir_para("historico")),
            ui.botao("Atribuir / transferir", self._atribuir_os_selecionada))
        pagina.append(topo)
        pagina.append(ui.barra(ui.legenda(
            "A tela mostra apenas OS ativas: abertas, iniciadas e pendentes. O histórico fica em Histórico e relatórios.")))
        self.tabela_os = ui.Tabela([
            ("ID", 65, False, 0.5),
            ("OS", 85, False, 0.5),
            ("Cliente", 0, True, 0.0),
            ("Abertura", 110, False, 0.5),
            ("Valor", 100, False, 0.5),
            ("Pagamento", 110, False, 0.5),
            ("Origem", 80, False, 0.5),
            ("Prestadores", 220, False, 0.0),
            ("Status", 110, False, 0.5),
            ("Dados", 110, False, 0.5),
        ], ao_ativar=self._editar_os)
        pagina.append(self.tabela_os.widget)
        pagina.append(ui.barra(
            ui.botao("Abrir OS", self._editar_os),
            ui.botao("Alterar situação / encerrar", self._encerrar_os,
                     css="suggested-action"),
            ui.botao("Atribuir prestador", self._atribuir_os_selecionada)))
        return pagina

    def carregar_os(self):
        conexao = conectar_banco()
        try:
            registros = conexao.execute(
                """SELECT os.id,os.numero_os,os.cliente_id,c.nome cliente,os.data_abertura,os.valor_total,
                          os.descricao,os.observacoes,os.forma_pagamento,os.urgencia,os.origem,
                          (SELECT GROUP_CONCAT(p.nome, ', ') FROM os_prestadores op
                             JOIN prestadores p ON p.id=op.prestador_id
                             WHERE op.os_id=os.id AND op.ativo=1) prestadores,
                          resp.nome responsavel_atual,os.tecnico tecnico_legado,os.status,
                          os.dados_incompletos
                   FROM ordens_servico os
                   JOIN clientes c ON c.id=os.cliente_id
                   LEFT JOIN os_responsaveis r ON r.os_id=os.id
                   LEFT JOIN prestadores resp ON resp.id=r.prestador_id
                   WHERE os.status IN ('Aberta','Iniciada','Pendente') ORDER BY os.id DESC""").fetchall()
        finally:
            conexao.close()
        termo = self.busca_os.get_text().casefold().strip() if hasattr(self, "busca_os") else ""
        linhas = []
        for r in registros:
            texto = " ".join(str(r[k] or "") for k in (
                "numero_os", "cliente", "prestadores", "responsavel_atual", "status",
                "forma_pagamento", "tecnico_legado")).casefold()
            if termo and termo not in texto:
                continue
            responsavel = (r["responsavel_atual"] + " (atual)" if r["responsavel_atual"]
                           else "Não atribuído")
            if r["prestadores"]:
                responsavel += " | Equipe: " + r["prestadores"]
            elif r["tecnico_legado"]:
                responsavel += " | Técnico: " + r["tecnico_legado"]
            dados = dict(r)
            dados["tecnico"] = r["tecnico_legado"]
            linhas.append((
                r["id"], r["numero_os"], r["cliente"], r["data_abertura"],
                ui.brl(r["valor_total"]), r["forma_pagamento"],
                "Portal" if (r["origem"] or "App") == "Portal" else "App",
                responsavel, r["status"],
                "Incompletos" if completude.os_faltantes(dados) else "OK"))
        self.tabela_os.definir_linhas(linhas)

    def _os_selecionada(self):
        valores = self.tabela_os.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Seleção", "Selecione uma ordem de serviço.")
            return None
        return valores

    def _editar_os(self):
        valores = self._os_selecionada()
        if valores:
            self.abrir_os_id(valores[0])

    def _encerrar_os(self):
        valores = self._os_selecionada()
        if valores:
            dialogos.DialogoOS(self, valores[0]).present(self)

    def _atribuir_os_selecionada(self):
        valores = self._os_selecionada()
        if valores:
            try:
                dialogos.DialogoAtribuicao(self, valores[0]).present(self)
            except Exception as erro:
                ui.aviso_erro(self, "Atribuição", str(erro))

    def _importar_os_yaml(self):
        self._escolher_yaml("Importar ordem de serviço YAML", self._os_yaml_escolhido)

    def _os_yaml_escolhido(self, dialogo, resultado):
        try:
            arquivo = dialogo.open_finish(resultado)
            caminho = Path(arquivo.get_path())
            pre = importacao_yaml.ordem_servico(caminho.name, caminho.read_bytes())
            conexao = conectar_banco()
            try:
                if pre.get("cliente_id"):
                    row = conexao.execute(
                        "SELECT id,nome FROM clientes WHERE id=? AND status!='Inativo'",
                        (pre["cliente_id"],)).fetchone()
                else:
                    doc = cad9.digitos(pre.get("cliente_documento", ""))
                    row = conexao.execute(
                        """SELECT id,nome FROM clientes
                           WHERE status!='Inativo' AND replace(
                               replace(replace(replace(documento,'.',''),'/',''),'-',''),' ','')=?
                           LIMIT 1""", (doc,)).fetchone()
            finally:
                conexao.close()
            if not row:
                raise ValueError("Cliente do YAML não encontrado. Informe cliente_id ou "
                                 "cliente_documento de um cliente ativo.")
            pre["cliente_id"] = row["id"]
        except Exception as erro:
            ui.aviso_erro(self, "YAML de ordem de serviço", str(erro))
            return
        dialogos.DialogoOS(self, importado=pre).present(self)

    def _modelo_os_yaml(self):
        self._baixar_modelo_yaml("modelo_ordem_servico.yaml", importacao_yaml.MODELO_OS_VAZIO)

    def nova_os(self, cliente_id=None):
        conexao = conectar_banco()
        try:
            total = conexao.execute(
                "SELECT COUNT(*) FROM clientes WHERE status!='Inativo'").fetchone()[0]
        finally:
            conexao.close()
        if not total:
            ui.aviso_erro(self, "Nenhum cliente",
                          "Cadastre pelo menos um cliente antes de criar uma OS.")
            return
        dialogos.DialogoOS(self, cliente_id=cliente_id).present(self)

    def abrir_os_id(self, os_id):
        try:
            dialogos.DialogoOS(self, os_id).present(self)
        except Exception as erro:
            ui.aviso_erro(self, "OS", str(erro))

    def publicar_pdf(self, os_id, enviar_email=False):
        def worker():
            try:
                caminho = fluxo.publicar_relatorio(BANCO, os_id)
                if enviar_email:
                    # Envio automático em segundo plano; nunca trava a interface.
                    try:
                        import gmail_service
                        gmail_service.enviar_relatorio_os_concluida(BANCO, os_id)
                    except Exception:
                        pass
                GLib.idle_add(self._pdf_publicado, True, caminho)
            except Exception as erro:
                GLib.idle_add(self._pdf_publicado, False, str(erro))
            return False

        threading.Thread(target=worker, daemon=True, name="AUTOSEG-PDF").start()

    def _pdf_publicado(self, sucesso, info):
        if not self._ativo:
            return False
        if sucesso:
            ui.toast(self, f"PDF publicado: {Path(info).name}")
        else:
            ui.toast(self, f"OS encerrada, PDF pendente: {info}", timeout=8)
        self.carregar_historico()
        return False

    # ------------------------------------------------------------------
    # Histórico e relatórios
    # ------------------------------------------------------------------

    def _pagina_historico(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.busca_historico = Gtk.SearchEntry(
            placeholder_text="Pesquisar OS, cliente, descrição")
        self.busca_historico.set_hexpand(True)
        self.busca_historico.connect("search-changed", lambda *_args: self.carregar_historico())
        pagina.append(ui.barra(
            self.busca_historico,
            ui.botao("Pesquisar", self.carregar_historico, icone="system-search-symbolic")))
        grade = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
        grade.set_margin_start(18)
        grade.set_margin_end(18)
        self.cards_hist = {}
        for indice, (chave, titulo_card, classe) in enumerate((
            ("total", "Total", "accent"),
            ("abertas", "Abertas", "error"),
            ("iniciadas", "Iniciadas", "warning"),
            ("pendentes", "Pendentes", "warning"),
            ("concluidas", "Concluídas", "success"),
        )):
            card, valor_label, _detalhe = ui.cartao(titulo_card, "—", classe)
            grade.attach(card, indice, 0, 1, 1)
            self.cards_hist[chave] = valor_label
        pagina.append(grade)
        self.resumo_valores = ui.legenda("")
        pagina.append(ui.barra(self.resumo_valores))
        self.tabela_historico = ui.Tabela([
            ("ID", 65, False, 0.5),
            ("OS", 85, False, 0.5),
            ("Cliente", 0, True, 0.0),
            ("Conclusão", 140, False, 0.5),
            ("Valor", 100, False, 0.5),
            ("Pagamento", 105, False, 0.5),
            ("Situação", 110, False, 0.5),
            ("Relatório PDF", 110, False, 0.5),
        ], ao_ativar=self._editar_historico)
        pagina.append(self.tabela_historico.widget)
        pagina.append(ui.barra(
            ui.botao("Abrir OS", self._editar_historico),
            ui.botao("Abrir PDF publicado", self._abrir_pdf_historico,
                     css="suggested-action"),
            ui.botao("Republicar PDF", self._republicar_pdf)))
        return pagina

    def carregar_historico(self):
        termo = self.busca_historico.get_text().strip() if hasattr(self, "busca_historico") else ""
        conexao = conectar_banco()
        try:
            if termo:
                registros = conexao.execute(
                    """SELECT os.id,os.numero_os,c.nome cliente,os.data_conclusao,
                              os.valor_total,os.forma_pagamento,os.status,
                              (SELECT COUNT(*) FROM os_documentos d
                                 WHERE d.os_id=os.id AND d.tipo='relatorio_pdf') pdfs
                       FROM ordens_servico os JOIN clientes c ON c.id=os.cliente_id
                       WHERE os.status IN ('Concluída','Cancelada','Não realizada')
                         AND (os.numero_os LIKE ? OR c.nome LIKE ? OR os.descricao LIKE ?)
                       ORDER BY os.id DESC""",
                    (f"%{termo}%", f"%{termo}%", f"%{termo}%")).fetchall()
            else:
                registros = conexao.execute(
                    """SELECT os.id,os.numero_os,c.nome cliente,os.data_conclusao,
                              os.valor_total,os.forma_pagamento,os.status,
                              (SELECT COUNT(*) FROM os_documentos d
                                 WHERE d.os_id=os.id AND d.tipo='relatorio_pdf') pdfs
                       FROM ordens_servico os JOIN clientes c ON c.id=os.cliente_id
                       WHERE os.status IN ('Concluída','Cancelada','Não realizada')
                       ORDER BY os.id DESC""").fetchall()
            resumo = conexao.execute(
                """SELECT COUNT(*) total,
                          COALESCE(SUM(status='Aberta'),0) abertas,
                          COALESCE(SUM(status='Iniciada'),0) iniciadas,
                          COALESCE(SUM(status='Pendente'),0) pendentes,
                          COALESCE(SUM(status='Concluída'),0) concluidas,
                          COALESCE(SUM(CASE WHEN status='Concluída' THEN valor_total ELSE 0 END),0) valor_concluido,
                          COALESCE(SUM(CASE WHEN status IN ('Aberta','Iniciada','Pendente') THEN valor_total ELSE 0 END),0) valor_aberto
                   FROM ordens_servico""").fetchone()
        finally:
            conexao.close()
        for chave in ("total", "abertas", "iniciadas", "pendentes", "concluidas"):
            self.cards_hist[chave].set_text(str(resumo[chave]))
        self.resumo_valores.set_text(
            f"Valor das OS concluídas: {ui.brl(resumo['valor_concluido'])}   •   "
            f"Valor em OS ativas: {ui.brl(resumo['valor_aberto'])}")
        self.tabela_historico.definir_linhas([
            (r["id"], r["numero_os"], r["cliente"], r["data_conclusao"],
             ui.brl(r["valor_total"]), r["forma_pagamento"], r["status"],
             "Disponível" if r["pdfs"] else "Pendente")
            for r in registros
        ])

    def _historico_selecionado(self):
        valores = self.tabela_historico.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Seleção", "Selecione uma OS do histórico.")
            return None
        return valores

    def _editar_historico(self):
        valores = self._historico_selecionado()
        if valores:
            self.abrir_os_id(valores[0])

    def _abrir_pdf_historico(self):
        valores = self._historico_selecionado()
        if not valores:
            return
        os_id = valores[0]
        try:
            publicado = fluxo.ultimo_documento(BANCO, os_id)
            if not publicado:
                fluxo.recuperar_relatorios_antigos(BANCO, os_id=os_id)
                publicado = fluxo.ultimo_documento(BANCO, os_id)
            if not publicado:
                raise ValueError("PDF ainda não encontrado. Use Republicar PDF para esta OS.")
            caminho = fluxo.validar_pdf_publicado(publicado)
            ui.abrir_caminho(caminho, self)
        except Exception as erro:
            ui.aviso_erro(self, "PDF", str(erro))

    def _republicar_pdf(self):
        valores = self._historico_selecionado()
        if not valores:
            return
        ui.alerta(
            self, "Republicar PDF",
            "Gerar uma nova versão pública do relatório desta OS?",
            lambda: self.publicar_pdf(valores[0]), rotulo_ok="Republicar")

    # ------------------------------------------------------------------
    # Financeiro
    # ------------------------------------------------------------------

    def _pagina_financeiro(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        grade = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
        grade.set_margin_top(14)
        grade.set_margin_start(18)
        grade.set_margin_end(18)
        self.cards_fin = {}
        for indice, (chave, titulo_card, classe) in enumerate((
            ("receber", "A receber", "warning"),
            ("recebido", "Recebido", "success"),
        )):
            card, valor_label, _detalhe = ui.cartao(titulo_card, "—", classe)
            grade.attach(card, indice, 0, 1, 1)
            self.cards_fin[chave] = valor_label
        pagina.append(grade)
        pagina.append(ui.barra(ui.legenda(
            "PIX já pago não entra nesta fila de cobrança.")))
        self.busca_financeiro = Gtk.SearchEntry(
            placeholder_text="Pesquisar OS, cliente, pagamento ou situação")
        self.busca_financeiro.set_hexpand(True)
        self.busca_financeiro.connect("search-changed", lambda *_args: self.carregar_financeiro())
        pagina.append(ui.barra(self.busca_financeiro,
                               ui.botao("Pesquisar", self.carregar_financeiro,
                                        icone="system-search-symbolic")))
        self.tabela_financeiro = ui.Tabela([
            ("ID", 65, False, 0.5),
            ("OS", 85, False, 0.5),
            ("Cliente", 0, True, 0.0),
            ("Valor", 110, False, 0.5),
            ("Pagamento", 115, False, 0.5),
            ("Status", 170, False, 0.5),
            ("Vencimento", 100, False, 0.5),
        ])
        pagina.append(self.tabela_financeiro.widget)
        pagina.append(ui.barra(
            ui.botao("Marcar como recebido", self._marcar_recebido, css="suggested-action")))
        return pagina

    def carregar_financeiro(self):
        conexao = conectar_banco()
        try:
            resumo = conexao.execute(
                """SELECT COALESCE(SUM(CASE WHEN status='Aguardando pagamento' THEN valor ELSE 0 END),0) pendente,
                          COALESCE(SUM(CASE WHEN status='Recebido' THEN valor ELSE 0 END),0) recebido
                   FROM financeiro""").fetchone()
            registros = conexao.execute(
                """SELECT f.id,os.numero_os,c.nome cliente,f.valor,f.forma_pagamento,
                          f.status,f.vencimento
                   FROM financeiro f JOIN ordens_servico os ON os.id=f.os_id
                   JOIN clientes c ON c.id=f.cliente_id ORDER BY f.id DESC""").fetchall()
        finally:
            conexao.close()
        self.cards_fin["receber"].set_text(ui.brl(resumo["pendente"]))
        self.cards_fin["recebido"].set_text(ui.brl(resumo["recebido"]))
        termo = self.busca_financeiro.get_text().casefold().strip() if hasattr(
            self, "busca_financeiro") else ""
        linhas = []
        for r in registros:
            texto = " ".join(str(r[k] or "") for k in (
                "numero_os", "cliente", "forma_pagamento", "status", "vencimento")).casefold()
            if termo and termo not in texto:
                continue
            linhas.append((r["id"], r["numero_os"], r["cliente"], ui.brl(r["valor"]),
                           r["forma_pagamento"], r["status"], r["vencimento"] or ""))
        self.tabela_financeiro.definir_linhas(linhas)

    def _marcar_recebido(self):
        valores = self.tabela_financeiro.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Seleção", "Selecione um lançamento financeiro.")
            return
        conexao = conectar_banco()
        try:
            conexao.execute(
                "UPDATE financeiro SET status='Recebido',data_pagamento=? WHERE id=?",
                (datetime.now().strftime("%d/%m/%Y"), valores[0]))
            conexao.commit()
        except Exception as erro:
            conexao.rollback()
            ui.aviso_erro(self, "Financeiro", str(erro))
            return
        finally:
            conexao.close()
        self.carregar_financeiro()
        self._atualizar_inicio()
        ui.toast(self, "Lançamento marcado como recebido.")

    # ------------------------------------------------------------------
    # Prestadores
    # ------------------------------------------------------------------

    def _pagina_prestadores(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.rotulo_portais = ui.legenda("")
        pagina.append(ui.barra(self.rotulo_portais))
        self.busca_prestadores = Gtk.SearchEntry(placeholder_text="Pesquisar prestador")
        self.busca_prestadores.set_hexpand(True)
        self.busca_prestadores.connect("search-changed",
                                       lambda *_args: self.carregar_prestadores())
        pagina.append(ui.barra(
            self.busca_prestadores,
            ui.botao("Cadastrar prestador", self._novo_prestador,
                     icone="list-add-symbolic", css="suggested-action"),
            ui.botao("Atribuir OS", self._atribuir_prestador),
            ui.botao("Abrir portal", self._abrir_portal_prestador)))
        self.tabela_prestadores = ui.Tabela([
            ("ID", 55, False, 0.5),
            ("Nome", 0, True, 0.0),
            ("CNPJ", 165, False, 0.0),
            ("E-mail", 220, False, 0.0),
            ("Especialidade", 160, False, 0.0),
            ("Ativo", 70, False, 0.5),
        ])
        pagina.append(self.tabela_prestadores.widget)
        pagina.append(ui.barra(
            ui.botao("Ativar / desativar", self._alternar_prestador),
            ui.botao("Administrador", self._admin_prestador),
            ui.botao("Redefinir senha", self._senha_prestador),
            ui.botao("Integrações", self._integracoes_prestador),
            ui.botao("Excluir da lista", self._excluir_prestador, css="destructive-action")))
        return pagina

    def carregar_prestadores(self):
        if hasattr(self, "rotulo_portais"):
            cliente = self.servidor_portal.info() if getattr(self, "servidor_portal", None) else {}
            texto = ("Portais: "
                     f"prestador {self.url_prestador or 'offline'} • "
                     f"cliente {cliente.get('url_local') or 'offline'}")
            if self.aviso_prestador:
                texto += " • " + self.aviso_prestador
            self.rotulo_portais.set_text(texto)
        termo = self.busca_prestadores.get_text().casefold().strip() if hasattr(
            self, "busca_prestadores") else ""
        with ext.db(BANCO) as c:
            registros = c.execute(
                "SELECT id,nome,documento,email,especialidade,ativo FROM prestadores "
                "WHERE excluido=0 ORDER BY nome").fetchall()
        linhas = []
        for p in registros:
            cnpj = cad9.formatar_documento(p['documento'])
            texto = f"{p['nome']} {cnpj} {p['email']} {p['especialidade'] or ''}".casefold()
            if termo and termo not in texto:
                continue
            linhas.append((p["id"], p["nome"], cnpj, p["email"], p["especialidade"] or "",
                           "Sim" if p["ativo"] else "Não"))
        self.tabela_prestadores.definir_linhas(linhas)

    def _prestador_selecionado(self):
        valores = self.tabela_prestadores.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Seleção", "Selecione um prestador.")
            return None
        return valores

    def _novo_prestador(self):
        dialogos.DialogoPrestador(self).present(self)

    def _alternar_prestador(self):
        valores = self._prestador_selecionado()
        if not valores:
            return
        with ext.db(BANCO) as c:
            c.execute("UPDATE prestadores SET ativo=1-ativo WHERE id=?", (valores[0],))
        self.carregar_prestadores()

    def _admin_prestador(self):
        valores = self._prestador_selecionado()
        if not valores:
            return
        atual = cad9.prestador_admin(BANCO, valores[0])
        texto = ("Revogar a permissão ADMINISTRADOR?" if atual else
                 "Conceder acesso ADMINISTRADOR? Permite analisar, autorizar chamados "
                 "e acessar cadastros/financeiro.")
        ui.alerta(self, "Administrador AUTOSEG", texto,
                  lambda: self._definir_admin(valores[0], not atual), destrutivo=atual)

    def _definir_admin(self, prestador_id, ativo):
        try:
            cad9.definir_admin(BANCO, prestador_id, ativo)
        except Exception as erro:
            ui.aviso_erro(self, "Permissão", str(erro))
            return
        ui.toast(self, "Permissão atualizada.")

    def _senha_prestador(self):
        valores = self._prestador_selecionado()
        if valores:
            dialogos.DialogoRedefinirSenhaPrestador(self, valores[0], valores[1]).present(self)

    def _integracoes_prestador(self):
        valores = self._prestador_selecionado()
        if valores:
            dialogos.DialogoIntegracoesPrestador(self, valores[0]).present(self)

    def _excluir_prestador(self):
        valores = self._prestador_selecionado()
        if not valores:
            return

        def excluir():
            with ext.db(BANCO) as c:
                c.execute("UPDATE prestadores SET ativo=0,excluido=1 WHERE id=?", (valores[0],))
            self.carregar_prestadores()
            ui.toast(self, "Prestador arquivado; histórico preservado.")

        ui.alerta(
            self, "Excluir prestador",
            "Excluir este prestador da lista e bloquear seu login?\n\n"
            "O cadastro será arquivado para preservar OS, relatórios e auditoria.",
            excluir, destrutivo=True, rotulo_ok="Excluir")

    def _atribuir_prestador(self):
        with ext.db(BANCO) as c:
            ordens = c.execute(
                """SELECT o.id,o.numero_os,c.nome cliente,o.status FROM ordens_servico o
                   JOIN clientes c ON c.id=o.cliente_id
                   WHERE o.status IN ('Aberta','Iniciada','Pendente') ORDER BY o.id DESC""").fetchall()
        if not ordens:
            ui.info(self, "Atribuição", "Não há OS ativas para atribuir.")
            return
        mapa = {f"{o['numero_os']} — {o['cliente']} ({o['status']}) [ID {o['id']}]": o["id"]
                for o in ordens}

        def escolher(texto):
            os_id = mapa.get(texto)
            if os_id is None:
                return
            try:
                dialogos.DialogoAtribuicao(self, os_id).present(self)
            except Exception as erro:
                ui.aviso_erro(self, "Atribuição", str(erro))

        ui.DialogoEscolha(self, "Selecionar OS", "Ordem de serviço", list(mapa),
                          escolher).present(self)

    def _abrir_portal_prestador(self):
        if not self.url_prestador:
            ui.aviso_erro(self, "Portal do prestador",
                          self.aviso_prestador or "Servidor do prestador indisponível (porta 8766).")
            return
        ui.abrir_uri(self.url_prestador, self)

    # ------------------------------------------------------------------
    # Portal do cliente
    # ------------------------------------------------------------------

    def _pagina_portal(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        grupo = Adw.PreferencesGroup(title="Servidor do portal")
        grupo.set_margin_top(14)
        grupo.set_margin_start(18)
        grupo.set_margin_end(18)
        self.portal_status = Adw.ActionRow(title="Status", subtitle="Verificando…")
        self.portal_status_icon = Gtk.Image.new_from_icon_name("network-server-symbolic")
        self.portal_status.add_prefix(self.portal_status_icon)
        grupo.add(self.portal_status)
        self.portal_local = Adw.ActionRow(title="Neste computador", subtitle="—")
        self._sufixo_copiar(self.portal_local, lambda: self._copiar_link(True))
        grupo.add(self.portal_local)
        self.portal_rede = Adw.ActionRow(title="Na rede local", subtitle="—")
        self._sufixo_copiar(self.portal_rede, lambda: self._copiar_link(False))
        grupo.add(self.portal_rede)
        self.portal_links = {}
        for porta in links9.PORTAS:
            linha = Adw.ActionRow(title=f"Link externo — {porta}", subtitle="Não detectado")
            linha.set_activatable(True)
            linha.connect("activated", lambda *_args, p=porta: self._abrir_link_publico(p))
            grupo.add(linha)
            self.portal_links[porta] = linha
        pagina.append(grupo)
        self.botao_portal = ui.botao("Ligar servidor", self._alternar_servidor,
                                     css="suggested-action")
        pagina.append(ui.barra(
            self.botao_portal,
            ui.botao("Abrir no navegador", self._abrir_portal_navegador),
            ui.botao("Copiar link", lambda: self._copiar_link(False)),
            ui.botao("Atualizar", self.carregar_portal, icone="view-refresh-symbolic")))

        grade = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
        grade.set_margin_start(18)
        grade.set_margin_end(18)
        self.cards_portal = {}
        for indice, (chave, titulo_card, classe) in enumerate((
            ("total", "Solicitações pelo portal", "accent"),
            ("andamento", "Aguardando atendimento", "warning"),
            ("concluidas", "Concluídas", "success"),
        )):
            card, valor_label, _detalhe = ui.cartao(titulo_card, "0", classe)
            grade.attach(card, indice, 0, 1, 1)
            self.cards_portal[chave] = valor_label
        pagina.append(grade)
        pagina.append(ui.barra(ui.titulo("Últimas solicitações pelo portal", "title-3")))
        self.tabela_portal = ui.Tabela([
            ("ID", 65, False, 0.5),
            ("OS", 85, False, 0.5),
            ("Cliente", 0, True, 0.0),
            ("Abertura", 130, False, 0.5),
            ("Urgência", 90, False, 0.5),
            ("Status", 110, False, 0.5),
        ], ao_ativar=self._abrir_os_portal)
        pagina.append(self.tabela_portal.widget)
        pagina.append(ui.barra(
            ui.botao("Abrir OS selecionada", self._abrir_os_portal),
            ui.botao("Nova OS manual", lambda: self.nova_os())))
        return pagina

    def _sufixo_copiar(self, linha, callback):
        botao = Gtk.Button(icon_name="edit-copy-symbolic")
        botao.add_css_class("flat")
        botao.set_tooltip_text("Copiar")
        botao.connect("clicked", lambda *_args: callback())
        linha.add_suffix(botao)

    def carregar_portal(self):
        if not getattr(self, "servidor_portal", None):
            self.portal_status.set_subtitle(self.erro_portal or "Servidor indisponível.")
            return
        info = self.servidor_portal.info()
        if info["ativo"]:
            self.portal_status.set_subtitle(
                f"Online desde {info['iniciado_em']} • porta {info['porta']}")
            self.portal_status_icon.set_from_icon_name("emblem-ok-symbolic")
        else:
            self.portal_status.set_subtitle(
                info.get("erro") or self.erro_portal or "Offline")
            self.portal_status_icon.set_from_icon_name("dialog-error-symbolic")
        self.portal_local.set_subtitle(info.get("url_local") or "—")
        rede = self._url_rede_portal(info)
        self.portal_rede.set_subtitle(
            rede or "Somente este computador (defina CLIENTE_BIND=0.0.0.0 para a rede local)")
        if hasattr(self, "botao_portal"):
            self.botao_portal.set_label("Desligar servidor" if info["ativo"] else "Ligar servidor")
            if info["ativo"]:
                self.botao_portal.add_css_class("destructive-action")
                self.botao_portal.remove_css_class("suggested-action")
            else:
                self.botao_portal.remove_css_class("destructive-action")
                self.botao_portal.add_css_class("suggested-action")
        self._aplicar_links(self._links_estado)
        conexao = conectar_banco()
        try:
            resumo = conexao.execute(
                """SELECT COUNT(*) total,
                          COALESCE(SUM(status IN ('Aberta','Iniciada','Pendente')),0) andamento,
                          COALESCE(SUM(status='Concluída'),0) concluidas
                   FROM ordens_servico WHERE origem='Portal'""").fetchone()
            registros = conexao.execute(
                """SELECT os.id,os.numero_os,c.nome cliente,os.data_abertura,
                          os.urgencia,os.status FROM ordens_servico os
                   JOIN clientes c ON c.id=os.cliente_id
                   WHERE os.origem='Portal' ORDER BY os.id DESC LIMIT 50""").fetchall()
        finally:
            conexao.close()
        for chave in ("total", "andamento", "concluidas"):
            self.cards_portal[chave].set_text(str(resumo[chave]))
        self.tabela_portal.definir_linhas([
            (r["id"], r["numero_os"], r["cliente"], r["data_abertura"],
             r["urgencia"] or "Normal", r["status"]) for r in registros
        ])

    def _abrir_os_portal(self):
        valores = self.tabela_portal.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Seleção", "Selecione uma solicitação do portal.")
            return
        self.abrir_os_id(valores[0])

    def _abrir_portal_navegador(self):
        info = self.servidor_portal.info() if getattr(self, "servidor_portal", None) else {}
        if not info.get("ativo"):
            ui.aviso_erro(self, "Portal desligado",
                          "Ligue o servidor do Portal do Cliente antes de abrir no navegador.")
            return
        ui.abrir_uri(info["url_local"], self)

    def _url_rede_portal(self, info):
        if info.get("ativo") and getattr(self.servidor_portal, "host", "") in ("0.0.0.0", "::"):
            return info.get("url_rede") or ""
        return ""

    def _copiar_link(self, local):
        info = self.servidor_portal.info() if getattr(self, "servidor_portal", None) else {}
        link = info.get("url_local") if local else (self._url_rede_portal(info) or info.get("url_local"))
        if not link:
            ui.aviso_erro(self, "Portal desligado",
                          "Ligue o servidor do portal para gerar o link.")
            return
        ui.copiar(link, self)

    def _alternar_servidor(self):
        if not getattr(self, "servidor_portal", None):
            ui.aviso_erro(self, "Portal", self.erro_portal or "Servidor indisponível.")
            return
        if self.servidor_portal.ativo:
            def desligar():
                self.servidor_portal.parar()
                self.carregar_portal()
                self._atualizar_inicio()
                ui.toast(self, "Portal do cliente desligado.")
            ui.alerta(self, "Desligar portal",
                      "Enquanto o portal estiver desligado, os clientes não conseguirão acessar.\n\n"
                      "Deseja desligar?", desligar, destrutivo=True, rotulo_ok="Desligar")
        else:
            try:
                self.servidor_portal.iniciar()
                self.erro_portal = ""
            except Exception as erro:
                self.erro_portal = str(erro)
                ui.aviso_erro(self, "Erro no portal", str(erro))
                return
            self.carregar_portal()
            self._atualizar_inicio()
            ui.toast(self, "Portal do cliente ligado.")

    def _processar_eventos_portal(self):
        if not self._ativo or not getattr(self, "servidor_portal", None):
            return True
        try:
            for evento in self.servidor_portal.consumir_eventos():
                if evento.get("tipo") == "nova_os":
                    ui.toast(self, f"{evento.get('numero','Nova OS')} • "
                                   f"{evento.get('cliente','')} recebida pelo portal.")
                    self.carregar_os()
                    self.carregar_portal()
                elif evento.get("tipo") == "novo_cliente":
                    ui.toast(self, f"Novo cadastro pelo portal: {evento.get('cliente','')}")
                    self.carregar_clientes()
        except Exception as erro:
            print("Erro processando eventos do portal:", erro)
        return True

    # ------------------------------------------------------------------
    # Condomínios e chamados (PJ)
    # ------------------------------------------------------------------

    def _pagina_pj(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sub = Adw.ViewStack()
        chamados = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        chamados.append(ui.barra(ui.legenda(
            "Chamados só viram OS após análise AUTOSEG, confirmação do síndico e vínculo com cliente.")))
        self.tabela_chamados = ui.Tabela([
            ("ID", 65, False, 0.5),
            ("OS", 80, False, 0.5),
            ("Condomínio", 0, True, 0.0),
            ("Solicitante", 160, False, 0.0),
            ("Status", 150, False, 0.5),
            ("Descrição", 260, False, 0.0),
        ], ao_ativar=self._abrir_os_chamado)
        chamados.append(self.tabela_chamados.widget)
        chamados.append(ui.barra(
            ui.botao("Abrir WhatsApp", self._whatsapp_chamado),
            ui.botao("Encaminhar ao síndico", self._analisar_chamado),
            ui.botao("Registrar confirmação", self._confirmar_chamado),
            ui.botao("Gerar OS autorizada", self._gerar_os_chamado),
            ui.botao("Recusar", self._recusar_chamado, css="destructive-action")))
        organizacoes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.tabela_organizacoes = ui.Tabela([
            ("ID", 65, False, 0.5),
            ("Nome", 0, True, 0.0),
            ("Tipo", 110, False, 0.5),
            ("Situação", 140, False, 0.5),
            ("Cliente", 80, False, 0.5),
        ], ao_ativar=self._validar_organizacao)
        organizacoes.append(self.tabela_organizacoes.widget)
        organizacoes.append(ui.barra(
            ui.botao("Validar / vincular ao cliente", self._validar_organizacao),
            ui.botao("Editar WhatsApp do síndico", self._whatsapp_sindico),
            ui.botao("Mesclar cadastros duplicados", self._mesclar_organizacoes)))
        organizacoes.append(ui.barra(ui.titulo("Vínculos pendentes", "title-3")))
        self.tabela_vinculos = ui.Tabela([
            ("ID", 55, False, 0.5),
            ("Condomínio", 0, True, 0.0),
            ("Pessoa", 240, False, 0.0),
            ("Papel", 110, False, 0.5),
        ])
        organizacoes.append(self.tabela_vinculos.widget)
        organizacoes.append(ui.barra(
            ui.botao("Aprovar vínculo", lambda: self._alterar_vinculo(True)),
            ui.botao("Recusar vínculo", lambda: self._alterar_vinculo(False),
                     css="destructive-action")))
        sub.add_titled(chamados, "chamados", "Chamados")
        sub.add_titled(organizacoes, "organizacoes", "Organizações e vínculos")
        barra_abas = Adw.ViewSwitcherBar()
        barra_abas.set_stack(sub)
        barra_abas.set_reveal(True)
        pagina.append(sub)
        pagina.append(barra_abas)
        return pagina

    def carregar_pj(self):
        with ext.db(BANCO) as c:
            chamados = c.execute(
                """SELECT h.id,h.os_id,o.nome organizacao,u.nome solicitante,h.status,h.descricao
                   FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id
                   JOIN v9_usuarios u ON u.id=h.usuario_id ORDER BY h.id DESC LIMIT 300""").fetchall()
            organizacoes = c.execute(
                "SELECT id,nome,tipo,situacao,cliente_id FROM v9_organizacoes "
                "WHERE mesclado_em IS NULL ORDER BY nome").fetchall()
            vinculos = c.execute(
                """SELECT v.id,o.nome organizacao,u.nome pessoa,v.papel
                   FROM v9_vinculos v JOIN v9_organizacoes o ON o.id=v.organizacao_id
                   JOIN v9_usuarios u ON u.id=v.usuario_id
                   WHERE v.situacao='Pendente' ORDER BY v.id DESC""").fetchall()
        self.tabela_chamados.definir_linhas([
            (h["id"], h["os_id"] or "—", h["organizacao"], h["solicitante"],
             h["status"], (h["descricao"] or "")[:140]) for h in chamados])
        self.tabela_organizacoes.definir_linhas([
            (o["id"], o["nome"], o["tipo"], o["situacao"], o["cliente_id"] or "—")
            for o in organizacoes])
        self.tabela_vinculos.definir_linhas([
            (v["id"], v["organizacao"], v["pessoa"], v["papel"]) for v in vinculos])

    def _chamado_selecionado(self):
        valores = self.tabela_chamados.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Chamado", "Selecione um chamado.")
            return None
        return valores

    def _abrir_os_chamado(self):
        valores = self._chamado_selecionado()
        if valores and valores[1] not in ("—", None):
            self.abrir_os_id(valores[1])

    def _whatsapp_chamado(self):
        valores = self._chamado_selecionado()
        if not valores:
            return
        try:
            url, destino = cad9.url_whatsapp(
                BANCO, valores[0], self._links_estado.get(str(links9.PORTAS[1]), {}).get("url", ""))
            ui.abrir_uri(url, self)
            ui.toast(self, f"WhatsApp aberto para o {destino}.")
        except Exception as erro:
            ui.aviso_erro(self, "WhatsApp", str(erro))

    def _analisar_chamado(self):
        valores = self._chamado_selecionado()
        if not valores:
            return

        def analisar(observacao):
            try:
                cad9.analisar(BANCO, valores[0], "AUTOSEG desktop",
                              "Aguardando síndico", observacao)
            except Exception as erro:
                ui.aviso_erro(self, "Chamado", str(erro))
                return False
            self.carregar_pj()
            ui.toast(self, "Chamado encaminhado ao síndico.")

        ui.DialogoTexto(self, "Encaminhar ao síndico", "Observação da análise",
                        ao_confirmar=analisar, rotulo_ok="Encaminhar",
                        multilinha=True).present(self)

    def _confirmar_chamado(self):
        valores = self._chamado_selecionado()
        if not valores:
            return

        def confirmar(texto):
            if len(texto.strip()) < 8:
                ui.aviso_erro(self, "Confirmação",
                              "Informe o nome do síndico e o meio de confirmação.")
                return False
            try:
                cad9.confirmar(BANCO, valores[0], "AUTOSEG desktop — " + texto.strip(), True)
            except Exception as erro:
                ui.aviso_erro(self, "Confirmação", str(erro))
                return False
            self.carregar_pj()
            ui.toast(self, "Confirmação do síndico registrada.")

        ui.DialogoTexto(self, "Registrar confirmação",
                        "Nome do síndico e meio de confirmação",
                        ao_confirmar=confirmar, rotulo_ok="Registrar").present(self)

    def _gerar_os_chamado(self):
        valores = self._chamado_selecionado()
        if not valores:
            return
        try:
            cad9.gerar_os(BANCO, valores[0], "AUTOSEG desktop")
        except Exception as erro:
            ui.aviso_erro(self, "Gerar OS", str(erro))
            return
        self.carregar_pj()
        self.carregar_os()
        ui.toast(self, "OS gerada a partir do chamado.")

    def _recusar_chamado(self):
        valores = self._chamado_selecionado()
        if not valores:
            return

        def recusar(motivo):
            if len(motivo.strip()) < 5:
                ui.aviso_erro(self, "Recusa", "Informe o motivo da recusa.")
                return False
            try:
                cad9.analisar(BANCO, valores[0], "AUTOSEG desktop", "Recusado", motivo)
            except Exception as erro:
                ui.aviso_erro(self, "Recusa", str(erro))
                return False
            self.carregar_pj()
            ui.toast(self, "Chamado recusado.")

        ui.DialogoTexto(self, "Recusar chamado", "Motivo",
                        ao_confirmar=recusar, rotulo_ok="Recusar",
                        multilinha=True, altura=100).present(self)

    def _organizacao_selecionada(self):
        valores = self.tabela_organizacoes.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Organização", "Selecione a organização.")
            return None
        return valores

    def _validar_organizacao(self):
        valores = self._organizacao_selecionada()
        if not valores:
            return

        def validar(texto):
            try:
                cliente_id = int(texto.strip())
            except ValueError:
                ui.aviso_erro(self, "Vincular", "Informe um ID de cliente numérico.")
                return False
            try:
                cad9.validar_organizacao(BANCO, valores[0], cliente_id, "AUTOSEG desktop")
            except Exception as erro:
                ui.aviso_erro(self, "Cadastro PJ", str(erro))
                return False
            self.carregar_pj()
            ui.toast(self, "Organização validada e vinculada.")

        ui.DialogoTexto(self, "Vincular organização",
                        "ID do cliente contratante no desktop",
                        ao_confirmar=validar, rotulo_ok="Vincular").present(self)

    def _whatsapp_sindico(self):
        valores = self._organizacao_selecionada()
        if not valores:
            return
        with ext.db(BANCO) as c:
            atual = c.execute(
                "SELECT sindico_nome,sindico_telefone FROM v9_organizacoes WHERE id=?",
                (valores[0],)).fetchone()
        nome = atual["sindico_nome"] or ""
        telefone = atual["sindico_telefone"] or ""

        def salvar(texto):
            partes = texto.split("|", 1)
            if len(partes) != 2:
                ui.aviso_erro(self, "Síndico", "Use: nome | telefone com DDD")
                return False
            try:
                cad9.atualizar_sindico(BANCO, valores[0], partes[0].strip(),
                                       partes[1].strip(), "AUTOSEG desktop")
            except Exception as erro:
                ui.aviso_erro(self, "WhatsApp", str(erro))
                return False
            self.carregar_pj()
            ui.toast(self, "Contato do síndico atualizado.")

        ui.DialogoTexto(self, "WhatsApp do síndico", "Nome | telefone com DDD",
                        f"{nome} | {telefone}" if nome or telefone else "",
                        ao_confirmar=salvar, rotulo_ok="Salvar").present(self)

    def _mesclar_organizacoes(self):
        valores = self._organizacao_selecionada()
        if not valores:
            return

        def pedir_destino(origem_texto):
            try:
                origem = int(origem_texto.strip())
            except ValueError:
                ui.aviso_erro(self, "Mesclar", "Informe o ID numérico da origem.")
                return False

            def mesclar(destino_texto):
                try:
                    destino = int(destino_texto.strip())
                    cad9.mesclar_organizacoes(BANCO, origem, destino, "AUTOSEG desktop")
                except Exception as erro:
                    ui.aviso_erro(self, "Mesclagem", str(erro))
                    return False
                self.carregar_pj()
                ui.toast(self, "Organizações mescladas.")

            ui.DialogoTexto(self, "Mesclar organizações", "ID do cadastro principal (destino)",
                            ao_confirmar=mesclar, rotulo_ok="Mesclar").present(self)
            return True

        ui.DialogoTexto(self, "Mesclar organizações",
                        "ID do cadastro duplicado (origem)",
                        str(valores[0]), ao_confirmar=pedir_destino,
                        rotulo_ok="Continuar").present(self)

    def _alterar_vinculo(self, aprovar):
        valores = self.tabela_vinculos.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Vínculo", "Selecione um vínculo pendente.")
            return

        def confirmar():
            try:
                cad9.alterar_vinculo(BANCO, valores[0], aprovar, "AUTOSEG desktop")
            except Exception as erro:
                ui.aviso_erro(self, "Vínculos", str(erro))
                return
            self.carregar_pj()
            ui.toast(self, "Vínculo aprovado." if aprovar else "Vínculo recusado.")

        ui.alerta(self, "Verificação de vínculo",
                  "O vínculo foi realmente conferido?", confirmar,
                  destrutivo=not aprovar,
                  rotulo_ok="Aprovar" if aprovar else "Recusar")

    # ------------------------------------------------------------------
    # Catálogo de serviços
    # ------------------------------------------------------------------

    def _pagina_catalogo(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.busca_catalogo = Gtk.SearchEntry(placeholder_text="Pesquisar serviço")
        self.busca_catalogo.set_hexpand(True)
        self.busca_catalogo.connect("search-changed", lambda *_args: self.carregar_catalogo())
        pagina.append(ui.barra(
            self.busca_catalogo,
            ui.botao("Novo serviço", self._novo_servico, icone="list-add-symbolic",
                     css="suggested-action"),
            ui.botao("Editar", self._editar_servico),
            ui.botao("Excluir serviço", self._excluir_servico, css="destructive-action"),
            ui.botao("Importar YAML", self._importar_servico),
            ui.botao("Arquivar / reativar", self._arquivar_servico)))
        self.tabela_catalogo = ui.Tabela([
            ("ID", 65, False, 0.5),
            ("Serviço", 0, True, 0.0),
            ("Mão de obra", 130, False, 0.5),
            ("Situação", 110, False, 0.5),
        ], ao_ativar=self._editar_servico)
        pagina.append(self.tabela_catalogo.widget)
        return pagina

    def carregar_catalogo(self):
        registros = catalogo.listar(BANCO)
        termo = self.busca_catalogo.get_text().casefold().strip() if hasattr(
            self, "busca_catalogo") else ""
        linhas = []
        for servico in registros:
            texto = f"{servico['nome']} {servico['descricao']}".casefold()
            if termo and termo not in texto:
                continue
            linhas.append((servico["id"], servico["nome"],
                           catalogo.reais(servico["preco_servico_centavos"]),
                           "Ativo" if servico["ativo"] else "Arquivado"))
        self.tabela_catalogo.definir_linhas(linhas)

    def _servico_selecionado(self):
        valores = self.tabela_catalogo.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Seleção", "Selecione um serviço.")
            return None
        return valores

    def _novo_servico(self):
        dialogos.DialogoServico(self).present(self)

    def _editar_servico(self):
        valores = self._servico_selecionado()
        if valores:
            dialogos.DialogoServico(self, valores[0]).present(self)

    def _excluir_servico(self):
        valores = self._servico_selecionado()
        if not valores:
            return
        registro = catalogo.obter(BANCO, valores[0])
        if not registro:
            return
        ui.alerta(
            self, "Excluir serviço",
            f"Excluir “{registro['nome']}” do catálogo?\n\n"
            "As ordens de serviço antigas preservam os valores já registrados.",
            lambda: self._executar_exclusao_servico(valores[0]),
            destrutivo=True, rotulo_ok="Excluir")

    def _executar_exclusao_servico(self, servico_id):
        try:
            catalogo.excluir(BANCO, servico_id)
        except Exception as erro:
            ui.aviso_erro(self, "Catálogo", str(erro))
            return
        self.carregar_catalogo()
        ui.toast(self, "Serviço excluído do catálogo.")

    def _arquivar_servico(self):
        valores = self._servico_selecionado()
        if not valores:
            return
        registro = catalogo.obter(BANCO, valores[0])
        if not registro:
            return
        acao = catalogo.arquivar if registro["ativo"] else catalogo.reativar
        rotulo = "Arquivar" if registro["ativo"] else "Reativar"
        ui.alerta(self, f"{rotulo} serviço", f"{rotulo} “{registro['nome']}”?",
                  lambda: self._executar_arquivamento(acao, valores[0]),
                  destrutivo=registro["ativo"], rotulo_ok=rotulo)

    def _executar_arquivamento(self, acao, servico_id):
        try:
            acao(BANCO, servico_id)
        except Exception as erro:
            ui.aviso_erro(self, "Catálogo", str(erro))
            return
        self.carregar_catalogo()

    def _importar_servico(self):
        dialogo = Gtk.FileDialog(title="Importar serviço YAML")
        filtro = Gtk.FileFilter()
        filtro.set_name("YAML")
        filtro.add_pattern("*.yaml")
        filtro.add_pattern("*.yml")
        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)
        dialogo.set_filters(filtros)
        dialogo.open(self, None, self._servico_yaml_escolhido)

    def _servico_yaml_escolhido(self, dialogo, resultado):
        try:
            arquivo = dialogo.open_finish(resultado)
            caminho = Path(arquivo.get_path())
            pre = importacao_yaml.servico(caminho.name, caminho.read_bytes())
        except Exception as erro:
            ui.aviso_erro(self, "YAML inválido", str(erro))
            return
        dialogos.DialogoServico(self, importado=pre).present(self)

    # ------------------------------------------------------------------
    # Composição de valores
    # ------------------------------------------------------------------

    def _pagina_composicao(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        pagina.append(ui.barra(ui.legenda(
            "Componentes configuráveis em composicao.yaml. Nenhuma taxa é fixa "
            "no código; a soma sempre fecha com o valor final do serviço.")))
        pagina.append(ui.barra(
            ui.botao("Novo componente", self._novo_componente,
                     icone="list-add-symbolic", css="suggested-action"),
            ui.botao("Editar", self._editar_componente),
            ui.botao("Ativar / desativar", self._alternar_componente),
            ui.botao("Subir", lambda: self._mover_componente(-1), icone="go-up-symbolic"),
            ui.botao("Descer", lambda: self._mover_componente(1), icone="go-down-symbolic"),
            ui.botao("Excluir", self._excluir_componente, css="destructive-action"),
            ui.botao("Ver composição", self._ver_composicao_admin),
            ui.botao("Recalcular", self._recalcular_composicoes)))
        self.tabela_composicao = ui.Tabela([
            ("Ordem", 70, False, 0.5),
            ("Componente", 0, True, 0.0),
            ("Modo", 180, False, 0.5),
            ("Valor", 120, False, 0.5),
            ("Ativo", 70, False, 0.5),
            ("Obrigatório", 90, False, 0.5),
            ("Aplicável a", 160, False, 0.5),
        ], ao_ativar=self._editar_componente)
        pagina.append(self.tabela_composicao.widget)
        return pagina

    def carregar_composicao(self):
        try:
            self._config_composicao = composicao.carregar()
        except Exception as erro:
            print("Composição de valores inválida:", erro)
            self._config_composicao = {"versao": 1, "componentes": []}
        self._componentes_composicao = sorted(
            self._config_composicao.get("componentes", []),
            key=lambda c: (c.get("ordem", 0), c.get("id", "")))
        linhas = []
        for componente in self._componentes_composicao:
            modo = componente.get("modo", "")
            if modo == "percentual":
                valor = f"{float(componente.get('valor', 0)):g}%"
            elif modo in ("fixo", "hora"):
                valor = ui.brl(float(componente.get("valor", 0)) / 100)
            elif modo == "formula":
                valor = componente.get("formula", "")
            else:
                valor = "—"
            linhas.append((
                componente.get("ordem", 0), componente.get("nome", ""),
                composicao.MODOS.get(modo, modo), valor,
                "Sim" if componente.get("ativo", True) else "Não",
                "Sim" if componente.get("obrigatorio") else "Não",
                ", ".join(componente.get("aplicavel_a") or []) or "Todos"))
        self.tabela_composicao.definir_linhas(linhas)

    def _componente_selecionado(self):
        indice = self.tabela_composicao.indice()
        if indice is None or indice >= len(getattr(self, "_componentes_composicao", [])):
            ui.aviso_erro(self, "Seleção", "Selecione um componente.")
            return None
        return self._componentes_composicao[indice]

    def _salvar_config_composicao(self):
        try:
            composicao.salvar(self._config_composicao)
            composicao.recalcular_tudo(BANCO)
        except Exception as erro:
            ui.aviso_erro(self, "Composição inválida", str(erro))
            return False
        self.carregar_composicao()
        return True

    def _novo_componente(self):
        ids = [c.get("id") for c in self._componentes_composicao]

        def salvar(componente):
            ordem = max([c.get("ordem", 0) for c in self._config_composicao["componentes"]] + [0]) + 1
            componente["ordem"] = ordem
            self._config_composicao["componentes"].append(componente)
            if self._salvar_config_composicao():
                ui.toast(self, "Componente criado.")

        dialogos.DialogoComponente(
            self, ids_existentes=ids, ao_salvar=salvar).present(self)

    def _editar_componente(self):
        componente = self._componente_selecionado()
        if componente is None:
            return

        def salvar(novo):
            for indice, atual in enumerate(self._config_composicao["componentes"]):
                if atual.get("id") == componente.get("id"):
                    novo["ordem"] = atual.get("ordem", indice + 1)
                    self._config_composicao["componentes"][indice] = novo
                    break
            if self._salvar_config_composicao():
                ui.toast(self, "Componente atualizado.")

        dialogos.DialogoComponente(
            self, componente=componente,
            ids_existentes=[c.get("id") for c in self._componentes_composicao],
            ao_salvar=salvar).present(self)

    def _alternar_componente(self):
        componente = self._componente_selecionado()
        if componente is None:
            return
        componente["ativo"] = not componente.get("ativo", True)
        if self._salvar_config_composicao():
            ui.toast(self, "Componente ativado." if componente["ativo"]
                     else "Componente desativado.")

    def _mover_componente(self, delta):
        componente = self._componente_selecionado()
        if componente is None:
            return
        lista = sorted(self._config_composicao["componentes"],
                       key=lambda c: (c.get("ordem", 0), c.get("id", "")))
        indice = next((i for i, c in enumerate(lista)
                       if c.get("id") == componente.get("id")), None)
        if indice is None:
            return
        alvo = indice + delta
        if not 0 <= alvo < len(lista):
            return
        lista[indice], lista[alvo] = lista[alvo], lista[indice]
        for posicao, item in enumerate(lista):
            item["ordem"] = posicao + 1
        self._config_composicao["componentes"] = lista
        if self._salvar_config_composicao():
            ui.toast(self, "Ordem atualizada.")

    def _excluir_componente(self):
        componente = self._componente_selecionado()
        if componente is None:
            return
        if len(self._config_composicao["componentes"]) <= 1:
            ui.aviso_erro(self, "Composição", "Mantenha pelo menos um componente.")
            return
        ui.alerta(
            self, "Excluir componente",
            f"Excluir “{componente.get('nome','')}” da composição?",
            lambda: self._executar_exclusao_componente(componente.get("id")),
            destrutivo=True, rotulo_ok="Excluir")

    def _executar_exclusao_componente(self, componente_id):
        self._config_composicao["componentes"] = [
            c for c in self._config_composicao["componentes"]
            if c.get("id") != componente_id]
        for posicao, item in enumerate(sorted(
                self._config_composicao["componentes"],
                key=lambda c: (c.get("ordem", 0), c.get("id", "")))):
            item["ordem"] = posicao + 1
        if self._salvar_config_composicao():
            ui.toast(self, "Componente excluído.")

    def _ver_composicao_admin(self):
        dialogos.DialogoComposicao(self).present(self)

    def _recalcular_composicoes(self):
        try:
            totais = composicao.recalcular_tudo(BANCO)
        except Exception as erro:
            ui.aviso_erro(self, "Recalcular composições", str(erro))
            return
        self.carregar_composicao()
        mensagem = (f"Composições atualizadas: {totais['servicos']} serviço(s), "
                    f"{totais['os']} OS aberta(s).")
        if totais.get("preservadas"):
            mensagem += (f" {totais['preservadas']} OS mantida(s) por composição "
                         "declarativa ou base que não fecha com a nova configuração.")
        ui.toast(self, mensagem)

    # ------------------------------------------------------------------
    # Estoque de materiais
    # ------------------------------------------------------------------

    def _pagina_estoque(self):
        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.rotulo_estoque = ui.legenda("Carregando materiais…")
        pagina.append(ui.barra(self.rotulo_estoque))
        self.rotulo_caixa = ui.legenda("Empresa: sem lançamentos.")
        self.rotulo_caixa.set_hexpand(True)
        pagina.append(ui.barra(
            self.rotulo_caixa,
            ui.botao("Caixa e investimentos", self._abrir_caixa_empresa,
                     css="suggested-action")))
        self.busca_estoque = Gtk.SearchEntry(placeholder_text="Buscar por nome ou código")
        self.busca_estoque.set_hexpand(True)
        self.busca_estoque.connect("search-changed", lambda *_args: self.carregar_estoque())
        pagina.append(ui.barra(
            self.busca_estoque,
            ui.botao("Cadastrar material", self._novo_material, icone="list-add-symbolic",
                     css="suggested-action"),
            ui.botao("Editar", self._editar_material),
            ui.botao("Entrada / ajuste", self._ajustar_material),
            ui.botao("Histórico", self._historico_material),
            ui.botao("Excluir material", self._excluir_material, css="destructive-action"),
            ui.botao("Importar YAML", self._importar_materiais),
            ui.botao("Modelo YAML", self._modelo_materiais)))
        self.tabela_estoque = ui.Tabela([
            ("ID", 65, False, 0.5),
            ("Material", 0, True, 0.0),
            ("Código", 120, False, 0.0),
            ("Unid.", 55, False, 0.5),
            ("Saldo", 80, False, 0.5),
            ("Mínimo", 80, False, 0.5),
            ("Venda", 110, False, 0.5),
        ], ao_ativar=self._editar_material)
        pagina.append(self.tabela_estoque.widget)
        return pagina

    def carregar_estoque(self):
        if hasattr(self, "rotulo_caixa"):
            try:
                resumo = empresa.resumo(BANCO)
                self.rotulo_caixa.set_text(
                    "Empresa: capital "
                    f"{ui.brl(resumo['aportes_centavos'] / 100)} · despesas "
                    f"{ui.brl(resumo['despesas_centavos'] / 100)} · saldo do controle "
                    f"{ui.brl(resumo['saldo_centavos'] / 100)}")
            except Exception:
                self.rotulo_caixa.set_text(
                    "Empresa: não foi possível carregar os lançamentos.")
        registros = estoque.listar(BANCO)
        termo = estoque._chave(self.busca_estoque.get_text()) if hasattr(
            self, "busca_estoque") else ""
        linhas = []
        negativos = 0
        baixos = 0
        for material in registros:
            if not material.get("ativo", 1):
                continue
            if termo and termo not in estoque._chave(
                    f"{material['nome']} {material['sku']}"):
                continue
            if material["saldo"] < 0:
                negativos += 1
                aviso = "⚠ "
            elif material["saldo"] <= material["minimo"]:
                baixos += 1
                aviso = "! "
            else:
                aviso = ""
            linhas.append((
                material["id"], aviso + material["nome"], material["sku"],
                material["unidade"], ui.quantidade_texto(material["saldo"]),
                ui.quantidade_texto(material["minimo"]),
                catalogo.reais(material["venda_centavos"])))
        self.tabela_estoque.definir_linhas(linhas)
        self.rotulo_estoque.set_text(
            f"{len(linhas)} materiais exibidos • {negativos} negativos • "
            f"{baixos} abaixo ou no mínimo • saldo negativo é permitido e identificado")

    def _material_selecionado(self):
        valores = self.tabela_estoque.selecionado()
        if valores is None:
            ui.aviso_erro(self, "Seleção", "Selecione um material.")
            return None
        return valores

    def _abrir_caixa_empresa(self):
        dialogos.DialogoCaixaEmpresa(
            self, ao_atualizar=self.carregar_estoque).present(self)

    def _novo_material(self):
        dialogos.DialogoMaterialEstoque(self).present(self)

    def _editar_material(self):
        valores = self._material_selecionado()
        if valores:
            dialogos.DialogoMaterialEstoque(self, valores[0]).present(self)

    def _ajustar_material(self):
        valores = self._material_selecionado()
        if valores:
            dialogos.DialogoAjusteEstoque(self, valores[0], valores[1]).present(self)

    def _historico_material(self):
        valores = self.tabela_estoque.selecionado()
        dialogos.DialogoHistoricoEstoque(
            self, valores[0] if valores else None).present(self)

    def _excluir_material(self):
        valores = self._material_selecionado()
        if not valores:
            return
        ui.alerta(
            self, "Excluir material",
            f"Excluir “{valores[1]}” do estoque?\n\n"
            "Se houver histórico de uso, o material será arquivado e deixará de aparecer.",
            lambda: self._executar_exclusao_material(valores[0]),
            destrutivo=True, rotulo_ok="Excluir")

    def _executar_exclusao_material(self, produto_id):
        try:
            resultado = estoque.excluir(BANCO, produto_id)
        except Exception as erro:
            ui.aviso_erro(self, "Estoque", str(erro))
            return
        self.carregar_estoque()
        ui.toast(self, "Material arquivado." if resultado == "arquivado"
                 else "Material excluído do estoque.")

    def _modelo_materiais(self):
        self._baixar_modelo_yaml("modelo_materiais.yaml", importacao_yaml.MODELO_MATERIAIS_VAZIO)

    def _importar_materiais(self):
        dialogo = Gtk.FileDialog(title="Importar materiais YAML")
        filtro = Gtk.FileFilter()
        filtro.set_name("YAML")
        filtro.add_pattern("*.yaml")
        filtro.add_pattern("*.yml")
        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)
        dialogo.set_filters(filtros)
        dialogo.open(self, None, self._materiais_yaml_escolhidos)

    def _materiais_yaml_escolhidos(self, dialogo, resultado):
        try:
            arquivo = dialogo.open_finish(resultado)
            caminho = Path(arquivo.get_path())
            pre = importacao_yaml.materiais(caminho.name, caminho.read_bytes())
        except Exception as erro:
            ui.aviso_erro(self, "YAML inválido", str(erro))
            return
        if not pre:
            ui.info(self, "Importação", "Nenhum material encontrado no YAML.")
            return
        existentes = {estoque._chave(x["nome"]) for x in estoque.listar(BANCO)}
        repetidos = [x["nome"] for x in pre if estoque._chave(x["nome"]) in existentes]
        if repetidos:
            ui.aviso_erro(self, "Importação", "Já cadastrados: " + ", ".join(repetidos[:10]))
            return
        previa = "\n".join(f"• {x['nome']} ({x['unidade']})" for x in pre[:12])
        if len(pre) > 12:
            previa += f"\n… e mais {len(pre) - 12} materiais."
        ui.alerta(
            self, "Confirmar importação",
            f"Importar {len(pre)} materiais após revisão?\n\n{previa}",
            lambda: self._executar_importacao_materiais(pre), rotulo_ok="Importar")

    def _executar_importacao_materiais(self, materiais):
        try:
            estoque.importar_lote(BANCO, materiais)
        except Exception as erro:
            ui.aviso_erro(self, "Importação YAML", str(erro))
            return
        self.carregar_estoque()
        ui.toast(self, f"{len(materiais)} materiais importados sem alterar saldos.")

    # ------------------------------------------------------------------
    # Encerramento
    # ------------------------------------------------------------------

    def _ao_fechar(self, *_args):
        self._ativo = False
        try:
            tuneis.parar()
        except Exception as erro:
            print("Não foi possível encerrar túnel gerenciado:", erro)
        try:
            if getattr(self, "portal_prestador", None):
                self.portal_prestador.parar()
        except Exception:
            pass
        try:
            if getattr(self, "servidor_portal", None):
                self.servidor_portal.parar()
        except Exception as erro:
            print("Erro encerrando o portal:", erro)
        return False


class Aplicativo(Adw.Application):
    def __init__(self):
        super().__init__(application_id="br.com.autoseg.Gestao",
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.janela = None

    def do_activate(self):
        if self.janela is None:
            self.janela = Janela(self)
        self.janela.present()


def main():
    if '--no-web' in sys.argv:
        os.environ['AUTOSEG_WEB_ACCESS'] = '0'
        sys.argv = [arg for arg in sys.argv if arg != '--no-web']
    Adw.init()
    return Aplicativo().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
