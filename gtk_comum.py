"""Widgets e utilidades compartilhadas pela interface GTK4/libadwaita do AUTOSEG."""
import os
import sys
from pathlib import Path

PASTA_APP = Path(__file__).resolve().parent
VENDOR = PASTA_APP / ".vendor" / "usr" / "lib" / "python3" / "dist-packages"
if VENDOR.is_dir() and str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

BASE = Path(os.environ.get("AUTOSEG_BASE") or PASTA_APP).expanduser()
os.environ.setdefault("AUTOSEG_BASE", str(BASE))
os.environ.setdefault("GESTAO_BANCO", str(BASE / "dados.db"))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

APP_TITLE = "AUTOSEG — Gestão de Serviços"
try:
    from versao_app import versao_local

    VERSAO = versao_local()
except Exception:
    VERSAO = "9.6.0-dev.4"

STATUS_FIM = ("Concluída", "Cancelada", "Não realizada")
ATIVAS = ("Aberta", "Iniciada", "Pendente")


def brl(valor):
    try:
        valor = float(valor or 0)
    except (TypeError, ValueError):
        valor = 0.0
    return "R$ " + f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def dinheiro_texto(valor):
    return brl(valor).replace("R$", "").strip()


def numero(valor):
    texto = str(valor or "").strip().replace("R$", "").replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def quantidade_texto(valor):
    try:
        valor = float(valor or 0)
    except (TypeError, ValueError):
        return "0"
    return str(int(valor)) if valor == int(valor) else f"{valor:g}".replace(".", ",")


def status_texto(status):
    return str(status or "—")


def abrir_uri(uri, parent=None):
    try:
        Gtk.UriLauncher(uri=uri).launch(parent, None, None)
    except Exception as erro:
        print("Não foi possível abrir", uri, erro)


def abrir_caminho(caminho, parent=None):
    try:
        abrir_uri(Path(caminho).resolve().as_uri(), parent)
    except Exception as erro:
        print("Não foi possível abrir", caminho, erro)


def copiar(texto, parent=None):
    display = Gdk.Display.get_default()
    if display is not None:
        display.get_clipboard().set(str(texto))
    if parent is not None:
        toast(parent, "Link copiado para a área de transferência.")


def toast(janela, mensagem, timeout=5):
    overlay = getattr(janela, "toast_overlay", None)
    if overlay is None:
        print(mensagem)
        return
    aviso = Adw.Toast.new(str(mensagem))
    aviso.set_timeout(timeout)
    overlay.add_toast(aviso)


def barra(*filhos, margem=18, espacamento=8):
    caixa = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=espacamento)
    caixa.set_margin_top(10)
    caixa.set_margin_bottom(4)
    caixa.set_margin_start(margem)
    caixa.set_margin_end(margem)
    for filho in filhos:
        if filho is not None:
            caixa.append(filho)
    return caixa


def botao(texto=None, callback=None, icone=None, css=None, dica=None):
    item = Gtk.Button()
    if texto is not None and icone is not None:
        item.set_child(Adw.ButtonContent(icon_name=icone, label=texto))
    elif texto is not None:
        item.set_label(texto)
    elif icone is not None:
        item.set_icon_name(icone)
        item.add_css_class("flat")
    if css:
        item.add_css_class(css)
    if dica:
        item.set_tooltip_text(dica)
    if callback is not None:
        item.connect("clicked", lambda *_args: callback())
    return item


def titulo(texto, classe="title-2"):
    item = Gtk.Label(label=texto, xalign=0)
    item.add_css_class(classe)
    return item


def legenda(texto):
    item = Gtk.Label(label=texto, xalign=0)
    item.add_css_class("caption")
    item.add_css_class("dim-label")
    return item


def cartao(titulo_texto, valor="—", classe="accent", detalhe=""):
    caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    caixa.add_css_class("card")
    caixa.set_margin_top(2)
    caixa.set_margin_bottom(2)
    caixa.set_hexpand(True)
    rotulo = Gtk.Label(label=titulo_texto.upper(), xalign=0)
    rotulo.add_css_class("caption")
    rotulo.add_css_class("dim-label")
    caixa.append(rotulo)
    valor_label = Gtk.Label(label=str(valor), xalign=0)
    valor_label.add_css_class("title-1")
    if classe:
        valor_label.add_css_class(classe)
    caixa.append(valor_label)
    detalhe_label = Gtk.Label(label=detalhe, xalign=0, wrap=True)
    detalhe_label.add_css_class("caption")
    detalhe_label.add_css_class("dim-label")
    caixa.append(detalhe_label)
    return caixa, valor_label, detalhe_label


class _Linha(GObject.Object):
    __gtype_name__ = "AutosegLinhaTabela"

    def __init__(self, valores):
        super().__init__()
        self.valores = tuple(valores)


class Tabela:
    """ColumnView reutilizável, com seleção única e ativação por duplo clique."""

    def __init__(self, colunas, ao_ativar=None, altura=None):
        self.modelo = Gio.ListStore(item_type=_Linha)
        self.selecao = Gtk.SingleSelection(model=self.modelo)
        self.selecao.set_autoselect(False)
        self.selecao.set_can_unselect(True)
        self.view = Gtk.ColumnView(model=self.selecao)
        self.view.set_show_row_separators(True)
        self.view.set_show_column_separators(False)
        self.view.add_css_class("data-table")
        for indice, (titulo_coluna, largura, expandir, alinhamento) in enumerate(colunas):
            fabrica = Gtk.SignalListItemFactory()
            fabrica.connect("setup", self._setup, indice, alinhamento)
            fabrica.connect("bind", self._bind, indice)
            coluna = Gtk.ColumnViewColumn(title=titulo_coluna, factory=fabrica)
            coluna.set_resizable(True)
            coluna.set_expand(bool(expandir))
            if largura:
                coluna.set_fixed_width(int(largura))
            self.view.append_column(coluna)
        if ao_ativar is not None:
            self.view.connect("activate", lambda *_args: ao_ativar())
        self.scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroller.set_has_frame(True)
        self.scroller.set_child(self.view)
        self.scroller.add_css_class("data-table")
        if altura:
            self.scroller.set_size_request(-1, int(altura))

    def _setup(self, _fabrica, item, indice, alinhamento):
        rotulo = Gtk.Label(
            xalign=alinhamento,
            ellipsize=Pango.EllipsizeMode.END,
            single_line_mode=True,
        )
        rotulo.set_margin_start(8)
        rotulo.set_margin_end(8)
        rotulo.set_margin_top(3)
        rotulo.set_margin_bottom(3)
        item.set_child(rotulo)

    def _bind(self, _fabrica, item, indice):
        linha = item.get_item()
        rotulo = item.get_child()
        valor = linha.valores[indice] if linha and indice < len(linha.valores) else ""
        rotulo.set_text("" if valor is None else str(valor))
        rotulo.set_tooltip_text("" if valor is None else str(valor))

    @property
    def widget(self):
        return self.scroller

    def limpar(self):
        self.modelo.remove_all()

    def definir_linhas(self, linhas):
        self.modelo.remove_all()
        for valores in linhas:
            self.modelo.append(_Linha(valores))

    def selecionado(self):
        linha = self.selecao.get_selected_item()
        return linha.valores if linha is not None else None

    def indice(self):
        posicao = self.selecao.get_selected()
        return int(posicao) if posicao != Gtk.INVALID_LIST_POSITION else None

    def selecionar_indice(self, indice):
        self.selecao.set_selected(int(indice))


class TextoRow(Adw.PreferencesRow):
    """Linha de preferências com TextView para textos longos."""

    def __init__(self, titulo_texto, texto="", altura=120, editavel=True):
        super().__init__()
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        caixa.set_margin_top(10)
        caixa.set_margin_bottom(10)
        caixa.set_margin_start(12)
        caixa.set_margin_end(12)
        if titulo_texto:
            rotulo = Gtk.Label(label=titulo_texto, xalign=0)
            rotulo.add_css_class("caption")
            rotulo.add_css_class("dim-label")
            caixa.append(rotulo)
        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_editable(bool(editavel))
        self.view.set_cursor_visible(bool(editavel))
        self.view.set_accepts_tab(False)
        self.view.set_size_request(-1, int(altura))
        self.view.get_buffer().set_text(str(texto or ""))
        moldura = Gtk.Frame()
        moldura.set_child(self.view)
        caixa.append(moldura)
        self.set_child(caixa)

    def get_texto(self):
        buffer = self.view.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True).strip()

    def set_texto(self, texto):
        self.view.get_buffer().set_text(str(texto or ""))


def grupo(titulo_texto):
    return Adw.PreferencesGroup(title=titulo_texto)


def campo_entry(container, titulo_texto, valor=""):
    linha = Adw.EntryRow(title=titulo_texto)
    linha.set_text("" if valor is None else str(valor))
    container.add(linha)
    return linha


def campo_combo(container, titulo_texto, opcoes, selecionado=0):
    linha = Adw.ComboRow(title=titulo_texto, model=Gtk.StringList.new(list(opcoes)))
    if opcoes:
        linha.set_selected(max(0, min(int(selecionado), len(opcoes) - 1)))
    container.add(linha)
    return linha


def campo_texto(container, titulo_texto, texto="", altura=120, editavel=True):
    linha = TextoRow(titulo_texto, texto, altura, editavel)
    container.add(linha)
    return linha


def valor_combo(linha):
    item = linha.get_selected_item()
    return item.get_string() if item is not None else ""


def novo_dialogo(titulo_texto, largura=680, altura=760):
    dialogo = Adw.Dialog()
    dialogo.set_title(titulo_texto)
    dialogo.set_content_width(int(largura))
    dialogo.set_content_height(int(altura))
    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_title_widget(Adw.WindowTitle(title=titulo_texto))
    toolbar.add_top_bar(header)
    dialogo.set_child(toolbar)
    return dialogo, toolbar, header


def alerta(parent, titulo_texto, corpo, ao_confirmar=None, destrutivo=False, rotulo_ok="Confirmar"):
    dialogo = Adw.AlertDialog(heading=titulo_texto, body=corpo)
    dialogo.add_response("cancelar", "Cancelar")
    dialogo.add_response("ok", rotulo_ok)
    dialogo.set_close_response("cancelar")
    dialogo.set_default_response("ok")
    if destrutivo:
        dialogo.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
    else:
        dialogo.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

    def resposta(_dialogo, resultado):
        try:
            escolha = _dialogo.choose_finish(resultado)
        except GLib.Error:
            return
        if escolha == "ok" and ao_confirmar is not None:
            ao_confirmar()

    dialogo.choose(parent, None, resposta)
    return dialogo


def info(parent, titulo_texto, corpo):
    dialogo = Adw.AlertDialog(heading=titulo_texto, body=corpo)
    dialogo.add_response("ok", "OK")
    dialogo.set_default_response("ok")
    dialogo.set_close_response("ok")
    dialogo.choose(parent, None, lambda *_args: None)
    return dialogo


def aviso_erro(parent, titulo_texto, corpo):
    dialogo = Adw.AlertDialog(heading=titulo_texto, body=corpo)
    dialogo.add_response("ok", "OK")
    dialogo.set_default_response("ok")
    dialogo.set_close_response("ok")
    dialogo.choose(parent, None, lambda *_args: None)
    return dialogo


class DialogoTexto(Adw.Dialog):
    """Diálogo simples de um campo, usado em confirmações e observações."""

    def __init__(self, parent, titulo_texto, rotulo, valor="", senha=False, multilinha=False,
                 ao_confirmar=None, rotulo_ok="Salvar", altura=150):
        super().__init__()
        self.parent = parent
        self.ao_confirmar = ao_confirmar
        self.set_title(titulo_texto)
        self.set_content_width(520)
        self.set_content_height(300 if multilinha else 240)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=titulo_texto))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo_campos = Adw.PreferencesGroup()
        pagina.add(grupo_campos)
        if multilinha:
            self.campo = campo_texto(grupo_campos, rotulo, valor, altura=altura)
        elif senha:
            self.campo = Adw.PasswordEntryRow(title=rotulo)
            self.campo.set_text(str(valor or ""))
            grupo_campos.add(self.campo)
        else:
            self.campo = campo_entry(grupo_campos, rotulo, valor)
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        cancelar = botao("Cancelar", self.close)
        salvar = botao(rotulo_ok, self._salvar, css="suggested-action")
        rodape.append(cancelar)
        rodape.append(salvar)
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _valor(self):
        if isinstance(self.campo, TextoRow):
            return self.campo.get_texto()
        return self.campo.get_text().strip()

    def _salvar(self):
        valor = self._valor()
        if self.ao_confirmar is not None:
            try:
                resultado = self.ao_confirmar(valor)
            except Exception as erro:
                aviso_erro(self.parent, "Não foi possível salvar", str(erro))
                return
            if resultado is False:
                return
        self.close()


class DialogoEscolha(Adw.Dialog):
    def __init__(self, parent, titulo_texto, rotulo, opcoes, ao_confirmar,
                 rotulo_ok="Continuar"):
        super().__init__()
        self.parent = parent
        self.opcoes = list(opcoes)
        self.ao_confirmar = ao_confirmar
        self.set_title(titulo_texto)
        self.set_content_width(560)
        self.set_content_height(250)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=titulo_texto))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo_campos = Adw.PreferencesGroup()
        pagina.add(grupo_campos)
        self.linha = campo_combo(grupo_campos, rotulo, self.opcoes, 0)
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(botao("Cancelar", self.close))
        rodape.append(botao(rotulo_ok, self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        indice = int(self.linha.get_selected())
        valor = self.opcoes[indice] if 0 <= indice < len(self.opcoes) else None
        if valor is not None and self.ao_confirmar is not None:
            self.ao_confirmar(valor)
        self.close()
