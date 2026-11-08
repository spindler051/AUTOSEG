"""Login window for the GTK desktop.

The login window always offers local and server modes. DEV selects server by
default; local mode creates the local database only when chosen and can
bootstrap the first local administrator.
"""
from __future__ import annotations

import sqlite3
import threading

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from application.bootstrap import preparar_banco_local
from application.connection import (
    ConnectionMode,
    ConnectionSettings,
    load_settings,
    save_settings,
)
from application.contracts import (
    AppError,
    AutenticacaoError,
    ServicoIndisponivelError,
)
from application.http_service import HttpService
from application.session import Sessao, limpar_sessao, salvar_sessao
from banco import BANCO
import prestador_auth


class DialogoPrimeiroAdmin(Adw.Dialog):
    def __init__(self, janela, ao_criar):
        super().__init__()
        self.janela = janela
        self.ao_criar = ao_criar
        self.set_title('Primeiro administrador local')
        self.set_content_width(520)
        self.set_content_height(430)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title='Primeiro administrador local'))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(
            title='Conta local',
            description='O administrador local é dono deste banco e não vira '
                        'administrador do servidor automaticamente.')
        pagina.add(grupo)
        self.nome = Adw.EntryRow(title='Nome')
        self.email = Adw.EntryRow(title='E-mail')
        self.senha = Adw.PasswordEntryRow(title='Senha (mínimo 10 caracteres)')
        self.confirmar = Adw.PasswordEntryRow(title='Confirmar senha')
        for campo in (self.nome, self.email, self.senha, self.confirmar):
            grupo.add(campo)
        self.erro = Gtk.Label(xalign=0, wrap=True)
        self.erro.add_css_class('error')
        self.erro.set_visible(False)
        grupo.add(self.erro)
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        cancelar = Gtk.Button(label='Cancelar')
        cancelar.connect('clicked', lambda *_args: self.close())
        rodape.append(cancelar)
        salvar = Gtk.Button(label='Criar administrador')
        salvar.add_css_class('suggested-action')
        salvar.connect('clicked', lambda *_args: self._salvar())
        rodape.append(salvar)
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        senha = self.senha.get_text()
        if len(senha) < 10:
            self._erro('A senha deve ter pelo menos 10 caracteres.')
            return
        if senha != self.confirmar.get_text():
            self._erro('As duas senhas não coincidem.')
            return
        try:
            info = prestador_auth.criar_primeiro_admin(
                BANCO, self.nome.get_text().strip(),
                self.email.get_text().strip(), senha)
        except (ValueError, sqlite3.Error) as erro:
            self._erro(str(erro))
            return
        self.close()
        self.ao_criar(info)

    def _erro(self, texto):
        self.erro.set_text(str(texto))
        self.erro.set_visible(True)


class LoginWindow(Adw.ApplicationWindow):
    def __init__(self, aplicativo, ao_entrar):
        super().__init__(application=aplicativo)
        self.ao_entrar = ao_entrar
        self.settings = load_settings()
        self.prefer_remote = self.settings.mode is ConnectionMode.REMOTE
        self._local_preparado = False
        self.set_title('Entrar — AUTOSEG')
        self.set_default_size(560, 760)
        self.set_size_request(460, 620)
        self._construir()

    def _construir(self):
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title='AUTOSEG'))
        toolbar.add_top_bar(header)
        rolagem = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        clamp = Adw.Clamp(maximum_size=560, tightening_threshold=460)
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        caixa.set_margin_top(28)
        caixa.set_margin_bottom(28)
        caixa.set_margin_start(26)
        caixa.set_margin_end(26)
        titulo = Gtk.Label(label='Entrar', xalign=0)
        titulo.add_css_class('title-1')
        caixa.append(titulo)
        subtitulo = Gtk.Label(
            label='Escolha entre a conta local e um servidor',
            xalign=0, wrap=True)
        subtitulo.add_css_class('dim-label')
        caixa.append(subtitulo)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_titled(self._pagina_local(), 'local', 'Local')
        self.stack.add_titled(self._pagina_servidor(), 'servidor', 'Servidor')
        seletor = Gtk.StackSwitcher(stack=self.stack)
        seletor.set_halign(Gtk.Align.CENTER)
        caixa.append(seletor)
        caixa.append(self.stack)
        self.stack.set_visible_child_name(
            'servidor' if self.prefer_remote else 'local')
        self.stack.connect('notify::visible-child',
                           lambda *_args: self._modo_mudou())
        self._modo_mudou()

        self.rodape = Gtk.Label(
            label='A senha nunca é salva. No servidor, o dispositivo guarda '
                  'apenas um token revogável.',
            xalign=0, wrap=True)
        self.rodape.add_css_class('caption')
        self.rodape.add_css_class('dim-label')
        caixa.append(self.rodape)
        clamp.set_child(caixa)
        rolagem.set_child(clamp)
        toolbar.set_content(rolagem)
        # GtkWindow.set_child() aborts AdwApplicationWindow on size allocation.
        self.set_content(toolbar)

    def _pagina_local(self):
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(
            title='Conta local',
            description='Usa o banco SQLite deste computador. Não acessa o servidor.')
        pagina.add(grupo)
        self.local_email = Adw.EntryRow(title='E-mail')
        self.local_email.set_text(self.settings.last_user)
        self.local_senha = Adw.PasswordEntryRow(title='Senha')
        grupo.add(self.local_email)
        grupo.add(self.local_senha)
        self.local_erro = Gtk.Label(xalign=0, wrap=True)
        self.local_erro.add_css_class('error')
        self.local_erro.set_visible(False)
        grupo.add(self.local_erro)
        entrar = Gtk.Button(label='Entrar localmente')
        entrar.add_css_class('suggested-action')
        entrar.connect('clicked', lambda *_args: self._entrar_local())
        grupo.add(entrar)
        self.local_primeiro = Gtk.Button(
            label='Criar primeiro administrador local')
        self.local_primeiro.set_visible(False)
        self.local_primeiro.connect(
            'clicked', lambda *_args: self._criar_primeiro_admin())
        grupo.add(self.local_primeiro)
        return pagina

    def _pagina_servidor(self):
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(
            title='Servidor',
            description='A conta e as permissões pertencem ao servidor.')
        pagina.add(grupo)
        self.servidor_url = Adw.EntryRow(title='URL do servidor')
        self.servidor_url.set_text(
            self.settings.server_url or 'http://127.0.0.1:8766')
        grupo.add(self.servidor_url)
        self.servidor_email = Adw.EntryRow(title='E-mail do prestador')
        self.servidor_email.set_text(self.settings.last_user)
        self.servidor_senha = Adw.PasswordEntryRow(title='Senha')
        self.lembrar = Adw.SwitchRow(
            title='Lembrar este dispositivo',
            subtitle='Guarda apenas um token revogável, nunca a senha.')
        self.lembrar.set_active(True)
        grupo.add(self.servidor_email)
        grupo.add(self.servidor_senha)
        grupo.add(self.lembrar)
        self.servidor_erro = Gtk.Label(xalign=0, wrap=True)
        self.servidor_erro.add_css_class('error')
        self.servidor_erro.set_visible(False)
        grupo.add(self.servidor_erro)
        self.servidor_status = Gtk.Label(xalign=0, wrap=True)
        self.servidor_status.add_css_class('dim-label')
        grupo.add(self.servidor_status)
        self.entrar_servidor = Gtk.Button(label='Entrar no servidor')
        self.entrar_servidor.add_css_class('suggested-action')
        self.entrar_servidor.connect(
            'clicked', lambda *_args: self._entrar_servidor())
        grupo.add(self.entrar_servidor)
        return pagina

    def _modo_mudou(self):
        if self.stack.get_visible_child_name() != 'local':
            return
        self._preparar_local()
        if hasattr(self, 'local_primeiro'):
            self.local_primeiro.set_visible(self._sem_prestador_local())

    def _preparar_local(self):
        if self._local_preparado:
            return True
        try:
            preparar_banco_local(BANCO)
        except Exception as erro:
            self._erro_local(f'Não foi possível abrir o banco local: {erro}')
            return False
        self._local_preparado = True
        return True

    def _sem_prestador_local(self) -> bool:
        try:
            import prestadores_ext as ext
            with ext.db(BANCO) as c:
                return not bool(c.execute(
                    'SELECT 1 FROM prestadores WHERE excluido=0 LIMIT 1'
                ).fetchone())
        except (sqlite3.Error, OSError):
            return True

    def _criar_primeiro_admin(self):
        if not self._preparar_local():
            return
        DialogoPrimeiroAdmin(self, self._entrar_com_info_local).present(self)

    def _entrar_com_info_local(self, info):
        self._entrar_local_info(info)

    def _entrar_local(self):
        email = self.local_email.get_text().strip()
        senha = self.local_senha.get_text()
        try:
            if not self._preparar_local():
                return
            info = prestador_auth.autenticar_local(BANCO, email, senha)
        except (ValueError, sqlite3.Error, OSError) as erro:
            self._erro_local(str(erro))
            return
        if not info:
            self._erro_local('E-mail ou senha incorretos.')
            return
        self._entrar_local_info(info)

    def _entrar_local_info(self, info):
        self._salvar_settings(ConnectionMode.LOCAL, self.settings.server_url,
                              info['email'])
        sessao = Sessao(
            mode=ConnectionMode.LOCAL.value,
            prestador_id=info['id'], nome=info['nome'],
            email=info['email'], admin=bool(info.get('admin')))
        limpar_sessao()
        self.ao_entrar(sessao)

    def _entrar_servidor(self):
        url = self.servidor_url.get_text().strip().rstrip('/')
        if not url.startswith(('http://', 'https://')):
            self._erro_servidor(
                'Use uma URL começando com http:// ou https://.')
            return
        email = self.servidor_email.get_text().strip()
        senha = self.servidor_senha.get_text()
        if not email or not senha:
            self._erro_servidor('Informe e-mail e senha.')
            return
        self.entrar_servidor.set_sensitive(False)
        self.servidor_erro.set_visible(False)
        self.servidor_status.set_text('Conectando…')
        lembrar = self.lembrar.get_active()

        def worker():
            try:
                servico = HttpService(url, timeout=6)
                resultado = servico.login(email, senha, lembrar)
                GLib.idle_add(self._fim_login_servidor,
                              resultado, url, email, None)
            except (AppError, OSError, ValueError) as erro:
                GLib.idle_add(self._fim_login_servidor,
                              None, url, email, erro)
            return False

        threading.Thread(target=worker, daemon=True,
                         name='AUTOSEG-Login').start()

    def _fim_login_servidor(self, resultado, url, email, erro):
        self.entrar_servidor.set_sensitive(True)
        self.servidor_status.set_text('')
        if erro is not None:
            if isinstance(erro, (AutenticacaoError, AppError)):
                texto = str(erro)
            elif isinstance(erro, ServicoIndisponivelError):
                texto = f'Servidor indisponível: {erro}'
            else:
                texto = f'Falha ao entrar: {erro}'
            self._erro_servidor(texto)
            return
        pessoa = dict(resultado.get('prestador') or {})
        sessao = Sessao(
            mode=ConnectionMode.REMOTE.value,
            prestador_id=int(pessoa.get('id') or 0),
            nome=str(pessoa.get('nome') or ''),
            email=str(pessoa.get('email') or email),
            admin=bool(pessoa.get('admin')),
            server_url=url,
            token=str(resultado.get('token') or ''),
            expira_em=str(resultado.get('expira_em') or ''))
        if self.lembrar.get_active():
            salvar_sessao(sessao)
        else:
            limpar_sessao()
        self._salvar_settings(ConnectionMode.REMOTE, url, email)
        self.ao_entrar(sessao)

    def _salvar_settings(self, mode, server_url, email):
        self.settings = ConnectionSettings(
            mode=mode, server_url=server_url,
            web_access=self.settings.web_access,
            tunnel=self.settings.tunnel, last_user=email)
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _erro_local(self, texto):
        self.local_erro.set_text(texto)
        self.local_erro.set_visible(True)

    def _erro_servidor(self, texto):
        self.servidor_erro.set_text(texto)
        self.servidor_erro.set_visible(True)
