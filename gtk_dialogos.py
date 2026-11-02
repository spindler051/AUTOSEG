"""Diálogos de cadastro e operação da interface GTK4/libadwaita do AUTOSEG."""
import json
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

import gtk_comum as ui
from banco import BANCO, conectar_banco, proximo_numero_os
import prestadores_ext as ext
import fluxo_os as fluxo
import atendimento_os as aten
import cadastros_v9 as cad9
import portal_negocios as neg
import estoque_materiais as estoque
import catalogo_servicos as catalogo
import importacao_yaml
import completude
import composicao
from integracao import clientes as clientes_core


def _linha_custom(widget):
    linha = Adw.PreferencesRow()
    linha.set_child(widget)
    return linha


class DialogoCliente(Adw.Dialog):
    def __init__(self, janela, cliente_id=None, importado=None):
        super().__init__()
        self.janela = janela
        self.cliente_id = cliente_id
        self.dados = dict(importado) if importado else {}
        if cliente_id is not None:
            registro = clientes_core.obter(cliente_id)
            self.dados = dict(registro["fields"]) if registro else {}

        titulo = "Editar cliente" if cliente_id else (
            "Novo cliente (YAML)" if importado else "Novo cliente")
        self.set_title(titulo)
        self.set_content_width(700)
        self.set_content_height(780)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=titulo))
        toolbar.add_top_bar(header)

        pagina = Adw.PreferencesPage()
        toolbar.set_content(pagina)

        if self.cliente_id is not None and completude.cliente_faltantes(self.dados):
            aviso = Adw.PreferencesGroup()
            pagina.add(aviso)
            aviso.add(Adw.ActionRow(
                title="Dados incompletos",
                subtitle="Complete os campos mínimos configurados em completude.yaml.",
                icon_name="dialog-warning-symbolic"))

        grupo = Adw.PreferencesGroup(title="Dados principais")
        pagina.add(grupo)
        self.tipo_pessoa = ui.campo_combo(grupo, "Tipo de pessoa", ["Jurídica", "Física"],
                                         0 if self.dados.get("tipo_pessoa", "Jurídica") != "Física" else 1)
        self.documento = ui.campo_entry(grupo, "CPF / CNPJ",
                                        cad9.formatar_documento(self.dados.get("documento", "")))
        self.documento_status = Gtk.Image()
        self.documento_status.set_pixel_size(16)
        self.documento_status.set_visible(False)
        self.documento.add_suffix(self.documento_status)
        self.tipo_pessoa.connect("notify::selected",
                                 lambda *_args: self._atualizar_documento_ui())
        self.documento.connect("notify::text",
                               lambda *_args: self._atualizar_documento_ui())
        self.nome = ui.campo_entry(grupo, "Nome / Razão Social", self.dados.get("nome", ""))
        self.nome_fantasia = ui.campo_entry(grupo, "Nome fantasia", self.dados.get("nome_fantasia", ""))
        status_opcoes = ["Ativo", "Inativo", "Prospect"]
        self.status = ui.campo_combo(
            grupo, "Status", status_opcoes,
            status_opcoes.index(self.dados.get("status", "Ativo"))
            if self.dados.get("status", "Ativo") in status_opcoes else 0)

        grupo = Adw.PreferencesGroup(title="Endereço")
        pagina.add(grupo)
        self.cep = ui.campo_entry(grupo, "CEP", self.dados.get("cep", ""))
        buscar = Gtk.Button(icon_name="system-search-symbolic")
        buscar.add_css_class("flat")
        buscar.set_tooltip_text("Buscar CEP")
        buscar.connect("clicked", lambda *_args: self._buscar_cep())
        self.cep.add_suffix(buscar)
        self.cep_status = Adw.ActionRow(title="Consulta de CEP", subtitle="")
        grupo.add(self.cep_status)
        self.endereco = ui.campo_entry(grupo, "Rua / Logradouro", self.dados.get("endereco", ""))
        self.numero_end = ui.campo_entry(grupo, "Número", self.dados.get("numero", ""))
        self.complemento = ui.campo_entry(grupo, "Complemento", self.dados.get("complemento", ""))
        self.bairro = ui.campo_entry(grupo, "Bairro", self.dados.get("bairro", ""))
        self.cidade = ui.campo_entry(grupo, "Cidade", self.dados.get("cidade", ""))
        self.uf = ui.campo_entry(grupo, "UF", self.dados.get("uf", ""))

        grupo = Adw.PreferencesGroup(title="Contato")
        pagina.add(grupo)
        self.telefone = ui.campo_entry(grupo, "Telefone", self.dados.get("telefone", ""))
        self.email = ui.campo_entry(grupo, "E-mail", self.dados.get("email", ""))

        grupo = Adw.PreferencesGroup(title="Síndico / responsável")
        pagina.add(grupo)
        self.sindico_nome = ui.campo_entry(grupo, "Nome", self.dados.get("sindico_nome", ""))
        self.sindico_telefone = ui.campo_entry(grupo, "Telefone", self.dados.get("sindico_telefone", ""))
        self.sindico_email = ui.campo_entry(grupo, "E-mail", self.dados.get("sindico_email", ""))

        grupo = Adw.PreferencesGroup(title="Imobiliária / administradora")
        pagina.add(grupo)
        self.administradora = ui.campo_entry(grupo, "Nome", self.dados.get("administradora", ""))
        self.administradora_telefone = ui.campo_entry(grupo, "Telefone",
                                                       self.dados.get("administradora_telefone", ""))
        self.administradora_email = ui.campo_entry(grupo, "E-mail",
                                                   self.dados.get("administradora_email", ""))

        grupo = Adw.PreferencesGroup(title="Observações")
        pagina.add(grupo)
        self.observacoes = ui.campo_texto(grupo, "", self.dados.get("observacoes", ""), altura=100)

        self._atualizar_documento_ui()

        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.append(ui.botao("Cancelar", self.close))
        if cliente_id is not None:
            rodape.append(ui.botao("Iniciar OS", self._nova_os))
        espaco = Gtk.Box()
        espaco.set_hexpand(True)
        rodape.append(espaco)
        rodape.append(ui.botao("Salvar cliente", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _atualizar_documento_ui(self):
        tipo = ui.valor_combo(self.tipo_pessoa)
        esperado = 11 if tipo == "Física" else 14
        self.documento.set_title("CPF" if tipo == "Física" else "CNPJ")
        doc = cad9.digitos(self.documento.get_text())
        if not doc:
            self.documento_status.set_visible(False)
            self.documento.remove_css_class("error")
            return
        if len(doc) < esperado:
            self.documento_status.set_from_icon_name("dialog-warning-symbolic")
            self.documento_status.set_tooltip_text(
                f"Faltam {esperado - len(doc)} dígito(s).")
            self.documento_status.set_visible(True)
            self.documento.remove_css_class("error")
            return
        try:
            cad9.validar_documento(tipo, doc)
        except ValueError as erro:
            self.documento_status.set_from_icon_name("dialog-error-symbolic")
            self.documento_status.set_tooltip_text(str(erro))
            self.documento_status.set_visible(True)
            self.documento.add_css_class("error")
        else:
            self.documento_status.set_from_icon_name("emblem-ok-symbolic")
            self.documento_status.set_tooltip_text(f"{'CPF' if tipo == 'Física' else 'CNPJ'} válido.")
            self.documento_status.set_visible(True)
            self.documento.remove_css_class("error")

    def _nova_os(self):
        self.close()
        self.janela.nova_os(cliente_id=self.cliente_id)

    def _buscar_cep(self):
        cep = "".join(ch for ch in self.cep.get_text() if ch.isdigit())
        if len(cep) != 8:
            ui.aviso_erro(self.janela, "CEP inválido", "Digite um CEP com 8 números.")
            return
        self.cep_status.set_subtitle("Consultando…")

        def worker():
            try:
                pedido = urllib.request.Request(
                    f"https://viacep.com.br/ws/{cep}/json/",
                    headers={"User-Agent": "AUTOSEG-GTK/1.0"},
                )
                with urllib.request.urlopen(pedido, timeout=8) as resposta:
                    dados = json.loads(resposta.read().decode("utf-8"))
                GLib.idle_add(self._receber_cep, dados)
            except Exception:
                GLib.idle_add(self._cep_erro)

        threading.Thread(target=worker, daemon=True, name="AUTOSEG-CEP").start()

    def _receber_cep(self, dados):
        if not self.get_visible():
            return False
        if dados.get("erro"):
            self._cep_erro()
            return False
        self.endereco.set_text(dados.get("logradouro", ""))
        self.bairro.set_text(dados.get("bairro", ""))
        self.cidade.set_text(dados.get("localidade", ""))
        self.uf.set_text(dados.get("uf", ""))
        self.cep_status.set_subtitle("Endereço encontrado.")
        return False

    def _cep_erro(self):
        if not self.get_visible():
            return False
        self.cep_status.set_subtitle("CEP não encontrado ou serviço indisponível.")
        return False

    def _salvar(self):
        dados = {
            "tipo_pessoa": ui.valor_combo(self.tipo_pessoa),
            "documento": self.documento.get_text().strip(),
            "nome": self.nome.get_text().strip(),
            "nome_fantasia": self.nome_fantasia.get_text().strip(),
            "endereco": self.endereco.get_text().strip(),
            "numero": self.numero_end.get_text().strip(),
            "complemento": self.complemento.get_text().strip(),
            "bairro": self.bairro.get_text().strip(),
            "cep": self.cep.get_text().strip(),
            "cidade": self.cidade.get_text().strip(),
            "uf": self.uf.get_text().strip(),
            "telefone": self.telefone.get_text().strip(),
            "email": self.email.get_text().strip(),
            "sindico_nome": self.sindico_nome.get_text().strip(),
            "sindico_telefone": self.sindico_telefone.get_text().strip(),
            "sindico_email": self.sindico_email.get_text().strip(),
            "administradora": self.administradora.get_text().strip(),
            "administradora_telefone": self.administradora_telefone.get_text().strip(),
            "administradora_email": self.administradora_email.get_text().strip(),
            "observacoes": self.observacoes.get_texto(),
            "status": ui.valor_combo(self.status),
        }
        try:
            registro = clientes_core.salvar(self.cliente_id, dados)
        except clientes_core.ErroCliente as erro:
            ui.aviso_erro(self.janela, erro.titulo, str(erro))
            return
        except Exception as erro:
            ui.aviso_erro(self.janela, "Cadastro não salvo", str(erro))
            return
        ui.toast(self.janela, "Cliente salvo com dados incompletos."
                 if registro["fields"]["dados_incompletos"] else "Cliente salvo.")
        self.janela.carregar_clientes()
        self.close()


class DialogoMaterial(Adw.Dialog):
    def __init__(self, parent, ao_salvar, atual=None):
        super().__init__()
        self.parent = parent
        self.ao_salvar = ao_salvar
        self.set_title("Editar material" if atual else "Adicionar material")
        self.set_content_width(480)
        self.set_content_height(360)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="Editar material" if atual else "Adicionar material"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup()
        pagina.add(grupo)
        self.item = ui.campo_entry(grupo, "Item / descrição", (atual or {}).get("item", ""))
        self.quantidade = ui.campo_entry(grupo, "Quantidade",
                                          ui.quantidade_texto((atual or {}).get("quantidade", 1)))
        self.valor = ui.campo_entry(grupo, "Valor unitário (R$)",
                                     ui.dinheiro_texto((atual or {}).get("valor_unitario", 0)))
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Confirmar", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        item = self.item.get_text().strip()
        qtd = ui.numero(self.quantidade.get_text())
        valor = ui.numero(self.valor.get_text())
        if not item:
            ui.aviso_erro(self.parent, "Item obrigatório", "Informe a descrição do material.")
            return
        if qtd <= 0:
            ui.aviso_erro(self.parent, "Quantidade inválida", "A quantidade deve ser maior que zero.")
            return
        self.ao_salvar({"item": item, "quantidade": qtd, "valor_unitario": valor,
                        "valor_total": qtd * valor})
        self.close()


class DialogoEstoqueOS(Adw.Dialog):
    def __init__(self, parent, ao_adicionar):
        super().__init__()
        self.parent = parent
        self.produtos = estoque.listar(BANCO, ativos=True)
        self.ao_adicionar = ao_adicionar
        self.set_title("Selecionar material do estoque")
        self.set_content_width(520)
        self.set_content_height(340)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Selecionar material do estoque"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup()
        pagina.add(grupo)
        opcoes = [f"{p['id']} — {p['nome']} (saldo {ui.quantidade_texto(p['saldo'])})"
                  for p in self.produtos]
        self.escolha = ui.campo_combo(grupo, "Material", opcoes or ["Nenhum material"], 0)
        self.quantidade = ui.campo_entry(grupo, "Quantidade utilizada", "1")
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Adicionar à OS", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        if not self.produtos:
            self.close()
            return
        indice = int(self.escolha.get_selected())
        if not 0 <= indice < len(self.produtos):
            return
        qtd = ui.numero(self.quantidade.get_text())
        if qtd <= 0:
            ui.aviso_erro(self.parent, "Quantidade inválida", "Informe uma quantidade maior que zero.")
            return
        produto = self.produtos[indice]
        self.ao_adicionar({
            "item": produto["nome"],
            "quantidade": qtd,
            "valor_unitario": produto["venda_centavos"] / 100,
            "valor_total": qtd * produto["venda_centavos"] / 100,
        })
        self.close()


class DialogoOS(Adw.Dialog):
    def __init__(self, janela, os_id=None, modo=None, cliente_id=None, importado=None):
        super().__init__()
        self.janela = janela
        self.os_id = os_id
        self.modo = modo
        self.importado = importado or {}
        self.cliente_inicial = cliente_id or self.importado.get("cliente_id")
        self.materiais = []
        self.imagens = []
        self.dados = None
        self.original_portal = None
        self.andamento = None
        self.encerramento = None
        self._carregar()
        if self.os_id is None and self.importado:
            self.materiais = [dict(m) for m in self.importado.get("materiais", [])]
        self._construir()

    def _carregar(self):
        conexao = conectar_banco()
        try:
            self.clientes = [dict(x) for x in conexao.execute(
                "SELECT id,nome FROM clientes WHERE status!='Inativo' ORDER BY nome")]
            if self.os_id is not None:
                registro = conexao.execute("SELECT * FROM ordens_servico WHERE id=?",
                                           (self.os_id,)).fetchone()
                self.dados = dict(registro) if registro else None
                if self.dados is None:
                    raise ValueError("OS não encontrada.")
                self.materiais = [dict(x) for x in conexao.execute(
                    "SELECT item,quantidade,valor_unitario,valor_total FROM materiais_os "
                    "WHERE os_id=? ORDER BY id", (self.os_id,))]
                if self.dados.get("origem") == "Portal":
                    original = conexao.execute(
                        "SELECT descricao_original FROM os_solicitacoes WHERE os_id=?",
                        (self.os_id,)).fetchone()
                    self.original_portal = original["descricao_original"] if original else None
                self.andamento = conexao.execute(
                    "SELECT iniciado_em,rascunho FROM os_atendimentos WHERE os_id=?",
                    (self.os_id,)).fetchone()
                self.encerramento = conexao.execute(
                    "SELECT motivo,relatorio FROM os_encerramentos WHERE os_id=?",
                    (self.os_id,)).fetchone()
        finally:
            conexao.close()

    def _construir(self):
        titulo_texto = "Nova ordem de serviço" if self.os_id is None else "Editar ordem de serviço"
        self.set_title(titulo_texto)
        self.set_content_width(780)
        self.set_content_height(820)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=titulo_texto))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        toolbar.set_content(pagina)

        if self.dados is not None and (self.dados.get("origem") or "App") == "Portal":
            grupo = Adw.PreferencesGroup()
            pagina.add(grupo)
            urg = self.dados.get("urgencia") or "Normal"
            contato = self.dados.get("contato_preferido") or "Não informado"
            grupo.add(Adw.ActionRow(
                title="Solicitação recebida pelo portal do cliente",
                subtitle=f"Urgência: {urg} • Contato preferido: {contato}",
                icon_name="network-transmit-receive-symbolic"))

        if self.os_id is not None and completude.os_faltantes(self.dados or {}):
            aviso = Adw.PreferencesGroup()
            pagina.add(aviso)
            faltantes = ", ".join(completude.os_faltantes(self.dados or {}))
            aviso.add(Adw.ActionRow(
                title="Dados incompletos",
                subtitle="Campos pendentes: " + faltantes
                         + ". Ajuste o mínimo em completude.yaml.",
                icon_name="dialog-warning-symbolic"))

        grupo = Adw.PreferencesGroup(title="Identificação")
        pagina.add(grupo)
        base = self.dados or self.importado or {}
        self.opcoes_cliente = [f"{x['id']} - {x['nome']}" for x in self.clientes]
        indice = 0
        alvo = self.dados.get("cliente_id") if self.dados else self.cliente_inicial
        if alvo is not None:
            for i, cliente in enumerate(self.clientes):
                if cliente["id"] == alvo:
                    indice = i
                    break
        self.cliente = ui.campo_combo(grupo, "Cliente", self.opcoes_cliente or ["Nenhum cliente"], indice)
        self.tecnico = ui.campo_entry(grupo, "Atendido por (cliente no local)",
                                      base.get("tecnico", ""))
        pagamentos = ["PIX", "Transferência", "Dinheiro", "Cartão", "Boleto", "Outro"]
        pagamento = base.get("forma_pagamento", "PIX")
        self.pagamento = ui.campo_combo(
            grupo, "Forma de pagamento", pagamentos,
            pagamentos.index(pagamento) if pagamento in pagamentos else 0)
        urgencias = ["Baixa", "Normal", "Alta"]
        urgencia = base.get("urgencia", "Normal")
        self.urgencia = ui.campo_combo(
            grupo, "Urgência", urgencias,
            urgencias.index(urgencia) if urgencia in urgencias else 1)

        grupo = Adw.PreferencesGroup(title="Serviço")
        pagina.add(grupo)
        descricao = base.get("descricao", "")
        editavel = True
        if self.original_portal is not None:
            descricao = self.original_portal
            editavel = False
        self.descricao = ui.campo_texto(grupo, "Descrição do serviço", descricao, 110, editavel)

        grupo = Adw.PreferencesGroup(title="Materiais utilizados")
        pagina.add(grupo)
        caixa_materiais = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        caixa_materiais.set_margin_top(8)
        caixa_materiais.set_margin_bottom(8)
        caixa_materiais.set_margin_start(10)
        caixa_materiais.set_margin_end(10)
        self.tabela_materiais = ui.Tabela([
            ("Item / descrição", 0, True, 0.0),
            ("Qtd.", 70, False, 0.5),
            ("Valor unitário", 110, False, 0.5),
            ("Total", 110, False, 0.5),
        ], ao_ativar=self._editar_material, altura=150)
        caixa_materiais.append(self.tabela_materiais.widget)
        acoes_materiais = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        acoes_materiais.append(ui.botao("Adicionar", self._adicionar_material))
        acoes_materiais.append(ui.botao("Do estoque", self._do_estoque))
        acoes_materiais.append(ui.botao("Materiais YAML", self._importar_materiais_yaml))
        acoes_materiais.append(ui.botao(
            "Modelo YAML",
            lambda: self.janela._baixar_modelo_yaml(
                "modelo_materiais_os.yaml", importacao_yaml.MODELO_MATERIAIS_OS_VAZIO)))
        acoes_materiais.append(ui.botao("Editar", self._editar_material))
        acoes_materiais.append(ui.botao("Remover", self._remover_material, css="destructive-action"))
        self.total_materiais = Gtk.Label(label="", xalign=1)
        self.total_materiais.add_css_class("heading")
        self.total_materiais.set_hexpand(True)
        acoes_materiais.append(self.total_materiais)
        caixa_materiais.append(acoes_materiais)
        grupo.add(_linha_custom(caixa_materiais))
        self._atualizar_materiais()

        grupo = Adw.PreferencesGroup(title="Valores")
        pagina.add(grupo)
        self.mao_obra = ui.campo_entry(grupo, "Mão de obra (R$)",
                                       ui.dinheiro_texto(base.get("valor_mao_obra", base.get("mao_obra", 0))))
        self.materiais_valor = ui.campo_entry(grupo, "Materiais (R$)",
                                              ui.dinheiro_texto(base.get("valor_materiais", 0)))
        self.total = ui.campo_entry(grupo, "Valor total (R$)",
                                    ui.dinheiro_texto(base.get("valor_total", 0)))
        self.tempo_horas = ui.campo_entry(
            grupo, "Tempo de execução (horas; 0 usa o padrão)",
            ui.quantidade_texto(base.get("tempo_horas", 0)))
        self.mao_obra.connect("notify::text", lambda *_args: self._recalcular())
        self.materiais_valor.connect("notify::text", lambda *_args: self._recalcular())
        self.total.connect("notify::text", lambda *_args: None)
        if self.materiais:
            self.materiais_valor.set_editable(False)
        self._recalcular()

        grupo = Adw.PreferencesGroup(title="Observações")
        pagina.add(grupo)
        self.observacoes = ui.campo_texto(
            grupo, "", base.get("observacoes", ""), 90)

        self.status = None
        self.relatorio = None
        self.motivo = None
        self.anexos_label = None
        if self.os_id is not None:
            grupo = Adw.PreferencesGroup(title="Atendimento e encerramento")
            pagina.add(grupo)
            if self.andamento and self.andamento["iniciado_em"]:
                grupo.add(Adw.ActionRow(
                    title="Atendimento iniciado",
                    subtitle=str(self.andamento["iniciado_em"]),
                    icon_name="emblem-ok-symbolic"))
            elif self.dados and self.dados.get("status") in ui.ATIVAS:
                grupo.add(Adw.ActionRow(
                    title="Atendimento ainda não iniciado",
                    subtitle="O início registra data, hora e responsável.",
                    icon_name="media-playback-start-symbolic"))
            if self.dados and self.dados.get("status") in ui.ATIVAS:
                status_opcoes = ["Manter em aberto", "Pendente", "Concluída", "Cancelada"]
                padrao = 0
                if self.modo == "Concluída":
                    padrao = 2
                elif self.modo == "Pendente":
                    padrao = 1
                elif self.modo == "Cancelada":
                    padrao = 3
                self.status = ui.campo_combo(grupo, "Situação ao salvar", status_opcoes, padrao)
                relato = ""
                motivo = ""
                if self.encerramento:
                    relato = self.encerramento["relatorio"] or ""
                    motivo = self.encerramento["motivo"] or ""
                elif self.andamento and self.andamento["rascunho"]:
                    relato = self.andamento["rascunho"]
                self.relatorio = ui.campo_texto(grupo, "Relatório técnico", relato, 120)
                self.motivo = ui.campo_texto(grupo, "Motivo — cancelamento / não realização",
                                             motivo, 60)
                caixa_fotos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                caixa_fotos.set_margin_top(8)
                caixa_fotos.set_margin_bottom(8)
                caixa_fotos.set_margin_start(12)
                caixa_fotos.set_margin_end(12)
                botao_fotos = ui.botao("Anexar imagens ao relatório", self._anexar_imagens)
                caixa_fotos.append(botao_fotos)
                self.anexos_label = Gtk.Label(label="", xalign=0)
                self.anexos_label.add_css_class("caption")
                self.anexos_label.add_css_class("dim-label")
                caixa_fotos.append(self.anexos_label)
                grupo.add(_linha_custom(caixa_fotos))
                self._atualizar_anexos()
            elif self.dados:
                grupo.add(Adw.ActionRow(
                    title="OS encerrada",
                    subtitle="O PDF está disponível em Histórico e Relatórios.",
                    icon_name="document-open-recent-symbolic"))

        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Ver composição", self._ver_composicao))
        if self.os_id is not None and self.dados and self.dados.get("status") in ui.ATIVAS:
            if not (self.andamento and self.andamento["iniciado_em"]):
                rodape.append(ui.botao("Iniciar atendimento", self._iniciar_atendimento))
        espaco = Gtk.Box()
        espaco.set_hexpand(True)
        rodape.append(espaco)
        if self.os_id is not None:
            rodape.append(ui.botao("Salvar rascunho", lambda: self._salvar(None)))
            if self.status is not None:
                rodape.append(ui.botao("Confirmar situação", self._confirmar_situacao,
                                       css="suggested-action"))
        else:
            rodape.append(ui.botao("Salvar OS", lambda: self._salvar(None), css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _atualizar_materiais(self):
        linhas = []
        total = 0.0
        for material in self.materiais:
            qtd = float(material.get("quantidade") or 0)
            valor = float(material.get("valor_unitario") or 0)
            subtotal = qtd * valor
            total += subtotal
            linhas.append((material.get("item", ""), ui.quantidade_texto(qtd),
                           ui.brl(valor), ui.brl(subtotal)))
        self.tabela_materiais.definir_linhas(linhas)
        self.total_materiais.set_text(f"Total em materiais: {ui.brl(total)}")
        if hasattr(self, "materiais_valor"):
            self.materiais_valor.set_editable(not self.materiais)
            if self.materiais:
                self.materiais_valor.set_text(ui.dinheiro_texto(total))
            self._recalcular()

    def _recalcular(self):
        if not hasattr(self, "mao_obra") or not hasattr(self, "total"):
            return
        mao = ui.numero(self.mao_obra.get_text())
        materiais = sum(float(x.get("quantidade") or 0) * float(x.get("valor_unitario") or 0)
                        for x in self.materiais)
        if not self.materiais:
            materiais = ui.numero(self.materiais_valor.get_text())
        total = mao + materiais
        self.total.set_text(ui.dinheiro_texto(total))

    def _ver_composicao(self):
        try:
            mao = ui.numero(self.mao_obra.get_text())
            materiais = sum(float(x.get("quantidade") or 0) * float(x.get("valor_unitario") or 0)
                            for x in self.materiais)
            if not self.materiais:
                materiais = ui.numero(self.materiais_valor.get_text())
            total = ui.numero(self.total.get_text()) or (mao + materiais)
            DialogoComposicao(
                self.janela, total_reais=total, materiais_reais=materiais,
                horas=ui.numero(self.tempo_horas.get_text())).present(self.janela)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Composição do valor", str(erro))

    def _adicionar_material(self):
        DialogoMaterial(self.janela, self._inserir_material).present(self.janela)

    def _inserir_material(self, material):
        self.materiais.append(material)
        self._atualizar_materiais()

    def _do_estoque(self):
        if not estoque.listar(BANCO, ativos=True):
            ui.info(self.janela, "Estoque", "Nenhum produto cadastrado no estoque.")
            return
        DialogoEstoqueOS(self.janela, self._inserir_material).present(self.janela)

    def _importar_materiais_yaml(self):
        dialogo = Gtk.FileDialog(title="Importar materiais da OS em YAML")
        filtro = Gtk.FileFilter()
        filtro.set_name("YAML")
        filtro.add_pattern("*.yaml")
        filtro.add_pattern("*.yml")
        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)
        dialogo.set_filters(filtros)
        dialogo.open(self.janela, None, self._materiais_yaml_escolhidos)

    def _materiais_yaml_escolhidos(self, dialogo, resultado):
        try:
            arquivo = dialogo.open_finish(resultado)
            caminho = Path(arquivo.get_path())
            materiais = importacao_yaml.materiais_os(caminho.name, caminho.read_bytes())
        except Exception as erro:
            ui.aviso_erro(self.janela, "YAML de materiais", str(erro))
            return
        self.materiais.extend(materiais)
        self._atualizar_materiais()
        ui.toast(self.janela, f"{len(materiais)} material(is) importado(s) do YAML.")

    def _editar_material(self):
        indice = self.tabela_materiais.indice()
        if indice is None:
            ui.aviso_erro(self.janela, "Seleção", "Selecione um material para editar.")
            return
        atual = self.materiais[indice]

        def salvar(material):
            self.materiais[indice] = material
            self._atualizar_materiais()

        DialogoMaterial(self.janela, salvar, atual).present(self.janela)

    def _remover_material(self):
        indice = self.tabela_materiais.indice()
        if indice is None:
            ui.aviso_erro(self.janela, "Seleção", "Selecione um material para remover.")
            return
        self.materiais.pop(indice)
        self._atualizar_materiais()

    def _anexar_imagens(self):
        dialogo = Gtk.FileDialog(title="Selecionar imagens do encerramento")
        filtro = Gtk.FileFilter()
        filtro.set_name("Imagens")
        for mime in ("image/jpeg", "image/png", "image/webp"):
            filtro.add_mime_type(mime)
        filtros = Gio.ListStore.new(Gtk.FileFilter)
        filtros.append(filtro)
        dialogo.set_filters(filtros)
        dialogo.open_multiple(self.janela, None, self._imagens_escolhidas)

    def _imagens_escolhidas(self, dialogo, resultado):
        try:
            arquivos = dialogo.open_multiple_finish(resultado)
        except GLib.Error:
            return
        aprovadas = []
        falhas = []
        for i in range(arquivos.get_n_items()):
            arquivo = arquivos.get_item(i)
            caminho = arquivo.get_path()
            if not caminho:
                continue
            try:
                conteudo = Path(caminho).read_bytes()
                ext.validar_imagem(conteudo)
                if caminho not in self.imagens:
                    aprovadas.append(caminho)
            except Exception as erro:
                falhas.append(f"{Path(caminho).name}: {erro}")
        self.imagens.extend(aprovadas)
        self._atualizar_anexos()
        if falhas:
            ui.aviso_erro(self.janela, "Imagens não selecionadas", "\n".join(falhas[:6]))
        elif aprovadas:
            ui.toast(self.janela, f"{len(aprovadas)} imagem(ns) aguardando encerramento.")

    def _atualizar_anexos(self):
        if self.anexos_label is None:
            return
        try:
            with ext.db(BANCO) as c:
                existentes = c.execute("SELECT COUNT(*) FROM os_anexos WHERE os_id=?",
                                       (self.os_id,)).fetchone()[0]
        except Exception:
            existentes = 0
        self.anexos_label.set_text(
            f"{existentes} imagem(ns) registrada(s); {len(self.imagens)} aguardando confirmação.")

    def _iniciar_atendimento(self):
        try:
            aten.iniciar(BANCO, self.os_id)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Não foi possível iniciar", str(erro))
            return
        ui.toast(self.janela, "Atendimento iniciado.")
        self.close()
        self.janela.abrir_os_id(self.os_id)

    def _confirmar_situacao(self):
        situacao = ui.valor_combo(self.status)
        if situacao == "Manter em aberto":
            self._salvar(None)
        elif situacao == "Pendente":
            self._salvar("Pendente")
        elif situacao == "Concluída":
            ui.alerta(
                self.janela, "Confirmar encerramento",
                "Salvar os dados e marcar a OS como Concluída?\n\n"
                "O PDF será publicado para o cliente. Pagamentos não são confirmados automaticamente.",
                lambda: self._salvar("Concluída"), rotulo_ok="Concluir")
        elif situacao == "Cancelada":
            self._salvar("Cancelada")

    def _salvar(self, acao):
        if not self.clientes:
            ui.aviso_erro(self.janela, "Nenhum cliente", "Cadastre um cliente antes de criar uma OS.")
            return
        indice = int(self.cliente.get_selected())
        if not 0 <= indice < len(self.clientes):
            ui.aviso_erro(self.janela, "Cliente inválido", "Selecione um cliente válido.")
            return
        cliente_id = self.clientes[indice]["id"]
        descricao = self.descricao.get_texto()
        tecnico = self.tecnico.get_text().strip()
        pagamento = ui.valor_combo(self.pagamento)
        mao_obra = ui.numero(self.mao_obra.get_text())
        materiais = sum(float(x.get("quantidade") or 0) * float(x.get("valor_unitario") or 0)
                        for x in self.materiais)
        if not self.materiais:
            materiais = ui.numero(self.materiais_valor.get_text())
        total = ui.numero(self.total.get_text()) or (mao_obra + materiais)
        tempo_horas = ui.numero(self.tempo_horas.get_text())
        comp = composicao.calcular(
            total_centavos=composicao.centavos_de_reais(total),
            materiais_centavos=composicao.centavos_de_reais(materiais),
            horas=tempo_horas)
        comp_json = composicao.para_json(comp)
        composicao.instalar_banco(BANCO)
        observacoes = self.observacoes.get_texto()
        dados_incompletos = 1 if completude.os_faltantes({
            "cliente_id": cliente_id,
            "descricao": descricao,
            "tecnico": tecnico,
            "forma_pagamento": pagamento,
            "valor_total": total,
            "urgencia": ui.valor_combo(self.urgencia),
            "observacoes": observacoes,
        }) else 0
        if acao in ui.STATUS_FIM and dados_incompletos:
            ui.aviso_erro(self.janela, "Dados incompletos",
                          "Complete os campos mínimos antes de encerrar a OS.")
            return
        relato = self.relatorio.get_texto() if self.relatorio is not None else ""
        motivo = self.motivo.get_texto() if self.motivo is not None else ""
        if acao in ("Cancelada", "Não realizada") and not motivo:
            ui.aviso_erro(self.janela, "Motivo obrigatório",
                          "Descreva o motivo do cancelamento ou da não realização.")
            return
        if acao and not relato:
            ui.aviso_erro(self.janela, "Relatório obrigatório",
                          "Preencha o relatório técnico antes de mudar o status da OS.")
            return

        conexao = conectar_banco()
        anterior = None
        materiais_anteriores = []
        try:
            cursor = conexao.cursor()
            if self.os_id is not None:
                anterior = cursor.execute("SELECT * FROM ordens_servico WHERE id=?",
                                          (self.os_id,)).fetchone()
                if anterior is None:
                    ui.aviso_erro(self.janela, "OS não encontrada",
                                  "A OS já não existe no banco de dados.")
                    return
                if anterior["origem"] == "Portal":
                    original = cursor.execute(
                        "SELECT cliente_id,descricao_original FROM os_solicitacoes WHERE os_id=?",
                        (self.os_id,)).fetchone()
                    if original:
                        cliente_id = original["cliente_id"]
                        descricao = original["descricao_original"]
                materiais_anteriores = [dict(m) for m in cursor.execute(
                    "SELECT item,quantidade,valor_unitario FROM materiais_os WHERE os_id=? ORDER BY id",
                    (self.os_id,)).fetchall()]

            if self.os_id is None:
                numero_os = proximo_numero_os(cursor)
                cursor.execute(
                    """INSERT INTO ordens_servico
                    (numero_os,cliente_id,data_abertura,tecnico,descricao,valor_mao_obra,
                     valor_materiais,valor_total,forma_pagamento,status,urgencia,observacoes,
                     dados_incompletos,tempo_horas,composicao_json,criado_em)
                    VALUES(?,?,?,?,?,?,?,?,?,'Aberta',?,?,?,?,?,?)""",
                    (numero_os, cliente_id, datetime.now().strftime("%d/%m/%Y %H:%M"),
                     tecnico, descricao, mao_obra, materiais, total, pagamento,
                     ui.valor_combo(self.urgencia), observacoes, dados_incompletos,
                     tempo_horas, comp_json, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                os_salvo_id = cursor.lastrowid
                aten.registrar_solicitacao(cursor, os_salvo_id, cliente_id, descricao,
                                           observacoes, "App")
            else:
                cursor.execute(
                    """UPDATE ordens_servico SET cliente_id=?,tecnico=?,descricao=?,
                    valor_mao_obra=?,valor_materiais=?,valor_total=?,forma_pagamento=?,
                    urgencia=?,observacoes=?,dados_incompletos=?,tempo_horas=?,
                    composicao_json=?,atualizado_em=? WHERE id=?""",
                    (cliente_id, tecnico, descricao, mao_obra, materiais, total, pagamento,
                     ui.valor_combo(self.urgencia), observacoes, dados_incompletos,
                     tempo_horas, comp_json,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.os_id))
                os_salvo_id = self.os_id

            anteriores = [(m["item"], float(m["quantidade"] or 0), float(m["valor_unitario"] or 0))
                          for m in materiais_anteriores]
            atuais = [(m.get("item", ""), float(m.get("quantidade") or 0),
                       float(m.get("valor_unitario") or 0)) for m in self.materiais]
            if anteriores != atuais:
                cursor.execute("DELETE FROM materiais_os WHERE os_id=?", (os_salvo_id,))
                for material in self.materiais:
                    qtd = float(material.get("quantidade") or 0)
                    valor = float(material.get("valor_unitario") or 0)
                    cursor.execute(
                        "INSERT INTO materiais_os(os_id,item,quantidade,valor_unitario,valor_total) "
                        "VALUES(?,?,?,?,?)",
                        (os_salvo_id, material.get("item", ""), qtd, valor, qtd * valor))
            estoque.reconciliar_os_conexao(cursor, os_salvo_id, "Desktop")

            if anterior is not None:
                antes = {
                    "cliente_id": anterior["cliente_id"], "tecnico": anterior["tecnico"] or "",
                    "descricao": anterior["descricao"] or "",
                    "valor_mao_obra": float(anterior["valor_mao_obra"] or 0),
                    "valor_materiais": float(anterior["valor_materiais"] or 0),
                    "valor_total": float(anterior["valor_total"] or 0),
                    "forma_pagamento": anterior["forma_pagamento"] or "",
                    "observacoes": anterior["observacoes"] or "",
                    "tempo_horas": float(anterior["tempo_horas"] or 0)
                    if "tempo_horas" in anterior.keys() else 0.0,
                }
                depois = {"cliente_id": cliente_id, "tecnico": tecnico, "descricao": descricao,
                          "valor_mao_obra": mao_obra, "valor_materiais": materiais,
                          "valor_total": total, "forma_pagamento": pagamento,
                          "observacoes": observacoes, "tempo_horas": tempo_horas}
                alteracoes = [f"{chave}: {antes[chave]!s} → {depois[chave]!s}"
                              for chave in antes if antes[chave] != depois[chave]]
                if alteracoes:
                    ext.evento(cursor, os_salvo_id, "Edição administrativa",
                               "; ".join(alteracoes))
            elif self.os_id is None:
                ext.evento(cursor, os_salvo_id, "OS criada",
                           "Ordem de serviço cadastrada pelo administrador.")
            if self.os_id is not None:
                aten.salvar_rascunho(cursor, os_salvo_id, relato, "Administrador desktop")
            if relato and acao:
                ext.evento(cursor, os_salvo_id, "Relatório técnico", relato)
            if acao == "Pendente":
                cursor.execute(
                    "UPDATE ordens_servico SET status='Pendente' WHERE id=? AND status IN ('Aberta','Pendente')",
                    (os_salvo_id,))
                if cursor.rowcount != 1:
                    conexao.rollback()
                    ui.aviso_erro(self.janela, "Status inválido",
                                  "Esta OS não pode ser colocada como pendente.")
                    return
                ext.evento(cursor, os_salvo_id, "Pendência",
                           "OS mantida pendente pelo administrador. Consulte o relatório técnico.")
            conexao.commit()
        except Exception as erro:
            conexao.rollback()
            ui.aviso_erro(self.janela, "Não foi possível salvar", str(erro))
            return
        finally:
            conexao.close()

        if acao in ui.STATUS_FIM:
            try:
                with ext.db(BANCO) as conexao_encerramento:
                    conexao_encerramento.execute("BEGIN IMMEDIATE")
                    for caminho in self.imagens:
                        with open(caminho, "rb") as arquivo:
                            ext.registrar_imagem_transacao(
                                conexao_encerramento, os_salvo_id, None,
                                Path(caminho).name, arquivo.read())
                    fluxo.aplicar_encerramento(
                        conexao_encerramento, os_salvo_id, acao, relato, motivo,
                        ator="Administrador desktop")
            except Exception as erro:
                ui.aviso_erro(
                    self.janela, "Encerramento não realizado",
                    f"Os dados da OS foram salvos, mas não foi possível encerrá-la:\n{erro}")
                return
            ui.toast(self.janela, "OS encerrada. Publicando PDF…")
            self.close()
            self.janela.publicar_pdf(os_salvo_id, enviar_email=(acao == "Concluída"))
            self.janela.carregar_os()
            self.janela.carregar_historico()
            return

        if self.os_id is not None and anterior is not None and anterior["status"] in ui.STATUS_FIM:
            ui.toast(self.janela, "OS atualizada. Republicando PDF…")
            self.close()
            self.janela.publicar_pdf(os_salvo_id)
            self.janela.carregar_historico()
            return

        ui.toast(self.janela, "OS salva com dados incompletos."
                 if dados_incompletos else "OS salva.")
        self.close()
        self.janela.carregar_os()
        self.janela.carregar_clientes()
        self.janela.carregar_financeiro()


class DialogoAtribuicao(Adw.Dialog):
    def __init__(self, janela, os_id):
        super().__init__()
        self.janela = janela
        self.os_id = os_id
        self.ordem = None
        self.prestadores = []
        self.atual_id = None
        with ext.db(BANCO) as c:
            self.ordem = c.execute("SELECT numero_os,status FROM ordens_servico WHERE id=?",
                                   (os_id,)).fetchone()
            self.prestadores = [dict(x) for x in c.execute(
                "SELECT id,nome,email FROM prestadores WHERE ativo=1 AND excluido=0 ORDER BY nome")]
            self.atual_id = ext.responsavel_atual(c, os_id)
        if not self.ordem or self.ordem["status"] not in ext.ATIVAS:
            raise ValueError("Somente OS aberta ou pendente.")
        self.set_title("Atribuição de OS")
        self.set_content_width(580)
        self.set_content_height(360)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title=f"Atribuir / transferir — {self.ordem['numero_os']}"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup()
        pagina.add(grupo)
        self.opcoes = [f"{p['nome']} — {p['email']} [ID {p['id']}]" for p in self.prestadores]
        indice = 0
        for i, prestador in enumerate(self.prestadores):
            if prestador["id"] == self.atual_id:
                indice = i
                break
        atual_nome = next((p["nome"] for p in self.prestadores
                           if p["id"] == self.atual_id), "Não atribuído")
        grupo.add(Adw.ActionRow(title="Responsável atual", subtitle=atual_nome))
        self.escolha = ui.campo_combo(grupo, "Prestador responsável",
                                      self.opcoes or ["Nenhum prestador ativo"], indice)
        grupo.add(Adw.ActionRow(
            title="Histórico preservado",
            subtitle="Os demais prestadores continuam com acesso à OS."))
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.append(ui.botao("Cancelar", self.close))
        if self.atual_id:
            rodape.append(ui.botao("Deixar disponível", self._liberar))
        espaco = Gtk.Box()
        espaco.set_hexpand(True)
        rodape.append(espaco)
        rodape.append(ui.botao("Salvar atribuição", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        if not self.prestadores:
            ui.aviso_erro(self.janela, "Prestadores", "Cadastre um prestador ativo primeiro.")
            return
        indice = int(self.escolha.get_selected())
        if not 0 <= indice < len(self.prestadores):
            return
        prestador_id = self.prestadores[indice]["id"]
        if self.atual_id and prestador_id != self.atual_id:
            ui.alerta(
                self.janela, "Transferir OS",
                "Transferir a responsabilidade e registrar a alteração no histórico?",
                lambda: self._atribuir(prestador_id))
        else:
            self._atribuir(prestador_id)

    def _atribuir(self, prestador_id):
        try:
            mudou = ext.atribuir(BANCO, self.os_id, prestador_id)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Atribuição", str(erro))
            return
        ui.toast(self.janela, "Responsabilidade registrada." if mudou else "Prestador já é o responsável.")
        self.close()
        self.janela.carregar_os()

    def _liberar(self):
        try:
            ext.desatribuir(BANCO, self.os_id)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Atribuição", str(erro))
            return
        ui.toast(self.janela, "OS disponível para nova atribuição.")
        self.close()
        self.janela.carregar_os()


class DialogoSenhaCliente(Adw.Dialog):
    def __init__(self, janela, cliente_id, nome):
        super().__init__()
        self.janela = janela
        self.cliente_id = cliente_id
        self.nome = nome
        self.set_title("Acesso web do cliente")
        self.set_content_width(500)
        self.set_content_height(340)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Acesso web do cliente"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(
            title="Senha de acesso",
            description=f"Defina uma senha para {nome}. A senha anterior deixará de funcionar.")
        pagina.add(grupo)
        self.senha = Adw.PasswordEntryRow(title="Nova senha (mínimo 10 caracteres)")
        grupo.add(self.senha)
        self.confirmar = Adw.PasswordEntryRow(title="Confirmar nova senha")
        grupo.add(self.confirmar)
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Atualizar senha", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        senha = self.senha.get_text()
        if len(senha) < 10:
            ui.aviso_erro(self.janela, "Senha", "A senha deve ter no mínimo 10 caracteres.")
            return
        if senha != self.confirmar.get_text():
            ui.aviso_erro(self.janela, "Senha", "As duas senhas não coincidem.")
            return
        try:
            fluxo.definir_senha_cliente(BANCO, self.cliente_id, senha)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Acesso do cliente", str(erro))
            return
        ui.info(self.janela, "Acesso configurado",
                f"Senha atualizada para {self.nome}.\n\n"
                f"Login antigo: ID {self.cliente_id} e senha escolhida.\n"
                "Login novo: CPF e senha no Portal do Cliente.")
        self.close()


class DialogoPrestador(Adw.Dialog):
    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        self.set_title("Cadastrar prestador")
        self.set_content_width(560)
        self.set_content_height(560)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Cadastrar prestador"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup()
        pagina.add(grupo)
        self.nome = ui.campo_entry(grupo, "Nome")
        self.email = ui.campo_entry(grupo, "E-mail (login)")
        self.telefone = ui.campo_entry(grupo, "Telefone")
        self.documento = ui.campo_entry(grupo, "CPF / CNPJ")
        self.especialidade = ui.campo_entry(grupo, "Especialidade")
        self.senha = Adw.PasswordEntryRow(title="Senha inicial (mínimo 10 caracteres)")
        grupo.add(self.senha)
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Salvar prestador", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        try:
            documento = cad9.validar_documento_auto(self.documento.get_text())
        except ValueError as erro:
            ui.aviso_erro(self.janela, "Documento inválido", str(erro))
            return
        try:
            ext.cadastrar(BANCO, nome=self.nome.get_text().strip(),
                          email=self.email.get_text().strip(),
                          senha=self.senha.get_text(),
                          telefone=self.telefone.get_text().strip(),
                          documento=documento,
                          especialidade=self.especialidade.get_text().strip())
        except Exception as erro:
            ui.aviso_erro(self.janela, "Cadastro", str(erro))
            return
        ui.toast(self.janela, "Prestador cadastrado.")
        self.janela.carregar_prestadores()
        self.close()


class DialogoRedefinirSenhaPrestador(Adw.Dialog):
    def __init__(self, janela, prestador_id, nome):
        super().__init__()
        self.janela = janela
        self.prestador_id = prestador_id
        self.set_title("Redefinir senha")
        self.set_content_width(500)
        self.set_content_height(330)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=f"Redefinir senha — {nome}"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup()
        pagina.add(grupo)
        self.senha = Adw.PasswordEntryRow(title="Nova senha (mínimo 10 caracteres)")
        grupo.add(self.senha)
        self.confirmar = Adw.PasswordEntryRow(title="Confirmar nova senha")
        grupo.add(self.confirmar)
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Salvar nova senha", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        senha = self.senha.get_text()
        if senha != self.confirmar.get_text():
            ui.aviso_erro(self.janela, "Senhas", "As duas senhas são diferentes.")
            return
        try:
            ext.redefinir_senha_prestador_desktop(BANCO, self.prestador_id, senha)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Senha", str(erro))
            return
        ui.toast(self.janela, "Senha do prestador atualizada.")
        self.close()


class DialogoIntegracoesPrestador(Adw.Dialog):
    def __init__(self, janela, prestador_id):
        super().__init__()
        self.janela = janela
        self.prestador_id = prestador_id
        self.config = ext.obter_config_prestador(BANCO, prestador_id)
        self.set_title("Integrações e pagamentos")
        self.set_content_width(620)
        self.set_content_height(680)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Integrações e pagamentos"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(
            title="Envio e dados bancários",
            description="Dados para rascunhos de e-mail. Não cole senhas nem tokens.")
        pagina.add(grupo)
        self.provedor = ui.campo_entry(grupo, "Provedor de envio",
                                       self.config.get("provedor_email", ""))
        self.remetente = ui.campo_entry(grupo, "E-mail remetente",
                                        self.config.get("email_remetente", ""))
        self.dados = ui.campo_texto(grupo, "Dados bancários e cadastrais",
                                    self.config.get("dados_bancarios_texto", ""), 180)
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Salvar configurações", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        dados = dict(self.config)
        dados["provedor_email"] = self.provedor.get_text().strip()
        dados["email_remetente"] = self.remetente.get_text().strip()
        dados["dados_bancarios_texto"] = self.dados.get_texto()
        try:
            ext.salvar_config_prestador(BANCO, self.prestador_id, dados)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Configuração inválida", str(erro))
            return
        ui.toast(self.janela, "Dados do prestador salvos.")
        self.close()


class DialogoServico(Adw.Dialog):
    def __init__(self, janela, servico_id=None, importado=None):
        super().__init__()
        self.janela = janela
        self.servico_id = servico_id
        self.registro = catalogo.obter(BANCO, servico_id) if servico_id else None
        info = importado or self.registro or {}
        self.set_title("Editar serviço" if servico_id else "Novo serviço")
        self.set_content_width(680)
        self.set_content_height(720)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="Editar serviço" if servico_id else "Novo serviço"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup()
        pagina.add(grupo)
        self.nome = ui.campo_entry(grupo, "Nome do serviço", info.get("nome", ""))
        self.descricao = ui.campo_texto(grupo, "Descrição ao cliente", info.get("descricao", ""), 100)
        preco = info.get("preco_servico",
                         str((info.get("preco_servico_centavos") or 0) / 100).replace(".", ","))
        self.preco = ui.campo_entry(grupo, "Preço da mão de obra (R$)", preco)
        self.tempo_horas = ui.campo_entry(
            grupo, "Tempo estimado (horas; 0 usa o padrão)",
            ui.quantidade_texto(info.get("tempo_horas", 0)))
        self.relatorio = ui.campo_texto(grupo, "Relatório técnico padrão",
                                        info.get("relatorio_padrao", ""), 100)
        if importado and isinstance(importado.get("materiais_lista"), list):
            linhas = []
            for material in importado["materiais_lista"]:
                linhas.append(f"{material.get('nome','')} | {material.get('quantidade','1')} | "
                              f"{ui.dinheiro_texto(material.get('preco_centavos', 0) / 100)}")
            materiais_texto = "\n".join(linhas)
        else:
            try:
                materiais = json.loads(info.get("materiais_json") or "[]")
            except ValueError:
                materiais = []
            materiais_texto = "\n".join(
                f"{m.get('nome','')} | {m.get('quantidade','1')} | "
                f"{ui.dinheiro_texto((m.get('preco_centavos') or 0) / 100)}"
                for m in materiais)
        self.materiais = ui.campo_texto(
            grupo, "Materiais (um por linha: nome | quantidade | valor unitário)",
            materiais_texto, 120)
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Ver composição", self._ver_composicao))
        rodape.append(ui.botao("Salvar serviço", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _ver_composicao(self):
        try:
            materiais = catalogo.normalizar_materiais(self.materiais.get_texto())
            total_materiais = sum(
                int(float(m.get("quantidade") or 0) * int(m.get("preco_centavos") or 0))
                for m in materiais)
            total = composicao.centavos_de_reais(self.preco.get_text()) + total_materiais
            DialogoComposicao(
                self.janela, total_reais=total / 100,
                materiais_reais=total_materiais / 100,
                horas=ui.numero(self.tempo_horas.get_text()),
                tipo_servico=self.nome.get_text().strip()).present(self.janela)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Composição do valor", str(erro))

    def _salvar(self):
        dados = {
            "nome": self.nome.get_text().strip(),
            "descricao": self.descricao.get_texto(),
            "preco_servico": self.preco.get_text().strip(),
            "tempo_horas": self.tempo_horas.get_text().strip(),
            "relatorio_padrao": self.relatorio.get_texto(),
            "materiais": self.materiais.get_texto(),
        }
        try:
            catalogo.salvar(BANCO, dados, self.servico_id)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Serviço inválido", str(erro))
            return
        ui.toast(self.janela, "Serviço salvo.")
        self.janela.carregar_catalogo()
        self.close()


class DialogoMaterialEstoque(Adw.Dialog):
    def __init__(self, janela, produto_id=None):
        super().__init__()
        self.janela = janela
        self.produto_id = produto_id
        registro = next((x for x in estoque.listar(BANCO) if x["id"] == produto_id), {})
        self.set_title("Editar material" if produto_id else "Cadastrar material")
        self.set_content_width(560)
        self.set_content_height(520)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="Editar material" if produto_id else "Cadastrar material"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup()
        pagina.add(grupo)
        self.nome = ui.campo_entry(grupo, "Nome do material", registro.get("nome", ""))
        self.sku = ui.campo_entry(grupo, "Código / SKU", registro.get("sku", ""))
        self.unidade = ui.campo_entry(grupo, "Unidade de medida", registro.get("unidade", "un"))
        self.custo = ui.campo_entry(grupo, "Custo de compra (R$)",
                                    ui.dinheiro_texto((registro.get("custo_centavos") or 0) / 100))
        self.venda = ui.campo_entry(grupo, "Preço de venda (R$)",
                                    ui.dinheiro_texto((registro.get("venda_centavos") or 0) / 100))
        self.minimo = ui.campo_entry(grupo, "Estoque mínimo",
                                     ui.quantidade_texto(registro.get("minimo", 0)))
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Salvar material", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        try:
            estoque.cadastrar(
                BANCO, nome=self.nome.get_text().strip(), sku=self.sku.get_text().strip(),
                unidade=self.unidade.get_text().strip(),
                custo=self.custo.get_text().strip(), venda=self.venda.get_text().strip(),
                minimo=self.minimo.get_text().strip(), identificador=self.produto_id)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Material inválido", str(erro))
            return
        ui.toast(self.janela, "Material salvo.")
        self.janela.carregar_estoque()
        self.close()


class DialogoAjusteEstoque(Adw.Dialog):
    def __init__(self, janela, produto_id, nome):
        super().__init__()
        self.janela = janela
        self.produto_id = produto_id
        self.set_title("Entrada / ajuste de estoque")
        self.set_content_width(500)
        self.set_content_height(300)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=f"Ajuste — {nome}"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(description="Use sinal: +5 entrada, -2 saída.")
        pagina.add(grupo)
        self.quantidade = ui.campo_entry(grupo, "Quantidade com sinal", "+1")
        self.motivo = ui.campo_entry(grupo, "Motivo obrigatório", "")
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Registrar", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _salvar(self):
        try:
            estoque.ajuste(BANCO, self.produto_id, self.quantidade.get_text(),
                           self.motivo.get_text().strip())
        except Exception as erro:
            ui.aviso_erro(self.janela, "Movimentação inválida", str(erro))
            return
        ui.toast(self.janela, "Movimentação registrada.")
        self.janela.carregar_estoque()
        self.close()


class DialogoHistoricoEstoque(Adw.Dialog):
    def __init__(self, janela, produto_id=None):
        super().__init__()
        self.janela = janela
        self.set_title("Histórico de movimentações")
        self.set_content_width(760)
        self.set_content_height(620)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Histórico de movimentações"))
        toolbar.add_top_bar(header)
        caixa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        caixa.set_margin_top(12)
        caixa.set_margin_bottom(12)
        caixa.set_margin_start(12)
        caixa.set_margin_end(12)
        tabela = ui.Tabela([
            ("Data", 150, False, 0.0),
            ("Material", 240, True, 0.0),
            ("Delta", 70, False, 0.5),
            ("Tipo", 120, False, 0.0),
            ("OS", 70, False, 0.5),
            ("Motivo", 0, True, 0.0),
        ])
        registros = estoque.movimentos(BANCO, produto_id, 300)
        tabela.definir_linhas([
            (r["criado_em"], r["nome"], f"{r['delta']:+g}", r["tipo"],
             r["os_id"] or "—", r["motivo"])
            for r in registros
        ])
        caixa.append(tabela.widget)
        toolbar.set_content(caixa)
        self.set_child(toolbar)


class DialogoResponsavel(Adw.Dialog):
    """Nomeia/remove síndico ou gestor usando o mesmo núcleo do Portal Prestador."""

    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        with ext.db(BANCO) as c:
            self.orgs = [dict(x) for x in c.execute(
                """SELECT o.id,o.nome,o.tipo,o.cnpj,r.usuario_id,u.nome responsavel
                   FROM v9_organizacoes o
                   LEFT JOIN v9_responsaveis r ON r.organizacao_id=o.id
                   LEFT JOIN v9_usuarios u ON u.id=r.usuario_id
                   WHERE o.mesclado_em IS NULL ORDER BY o.nome""").fetchall()]
            self.pessoas = [dict(x) for x in c.execute(
                "SELECT id,nome,cpf FROM v9_usuarios WHERE ativo=1 ORDER BY nome").fetchall()]
        if not self.orgs:
            raise ValueError("Cadastre um condomínio ou empresa antes de nomear o responsável.")
        if not self.pessoas:
            raise ValueError("Nenhuma conta PF ativa. O síndico/gestor deve criar acesso por CPF antes.")
        self.set_title("Atribuir síndico / gestor")
        self.set_content_width(660)
        self.set_content_height(430)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Síndico / gestor do condomínio"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(
            title="Nomeação administrativa",
            description="A mesma nomeação aparece imediatamente no Portal Prestador e no Portal Cliente.")
        pagina.add(grupo)
        self.opcoes_org = [f"#{o['id']} {o['nome']} ({o['tipo']})" for o in self.orgs]
        self.combo_org = ui.campo_combo(grupo, "Condomínio / empresa", self.opcoes_org, 0)
        self.opcoes_pessoa = [f"#{p['id']} {p['nome']} — CPF final {p['cpf'][-4:]}"
                              for p in self.pessoas]
        self.combo_pessoa = ui.campo_combo(grupo, "Pessoa física com login CPF ativo",
                                           self.opcoes_pessoa, 0)
        self.linha_atual = Adw.ActionRow(title="Responsável atual", subtitle="—")
        grupo.add(self.linha_atual)
        self.linha_papel = Adw.ActionRow(title="Papel a atribuir", subtitle="—")
        grupo.add(self.linha_papel)
        self.combo_org.connect("notify::selected", lambda *_args: self._atualizar())
        self._atualizar()
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Remover responsável", self._remover,
                               css="destructive-action"))
        espaco = Gtk.Box()
        espaco.set_hexpand(True)
        rodape.append(espaco)
        rodape.append(ui.botao("Nomear / trocar", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _org(self):
        indice = int(self.combo_org.get_selected())
        return self.orgs[max(0, min(indice, len(self.orgs) - 1))]

    def _pessoa(self):
        indice = int(self.combo_pessoa.get_selected())
        return self.pessoas[max(0, min(indice, len(self.pessoas) - 1))]

    def _atualizar(self):
        org = self._org()
        self.linha_atual.set_subtitle(org.get("responsavel") or "Nenhum responsável nomeado")
        self.linha_papel.set_subtitle("Síndico" if org["tipo"] == "Condomínio" else "Gestor")

    def _salvar(self):
        org = self._org()
        pessoa = self._pessoa()
        try:
            papel = cad9.atribuir_responsavel(BANCO, org["id"], pessoa["id"],
                                              "Desktop AUTOSEG")
        except Exception as erro:
            ui.aviso_erro(self.janela, "Nomeação não realizada", str(erro))
            return
        ui.toast(self.janela, f"{papel} nomeado(a): {pessoa['nome']}.")
        self.close()
        self.janela.carregar_clientes()

    def _remover(self):
        org = self._org()
        if not org.get("usuario_id"):
            ui.toast(self.janela, "Esta organização não tem responsável nomeado.")
            return
        try:
            cad9.remover_responsavel(BANCO, org["id"], "Desktop AUTOSEG")
        except Exception as erro:
            ui.aviso_erro(self.janela, "Remoção não realizada", str(erro))
            return
        ui.toast(self.janela, "Responsável removido. O vínculo continua como morador.")
        self.close()
        self.janela.carregar_clientes()

class DialogoOSRapida(Adw.Dialog):
    """Cria OS aberta com busca de condomínio/cliente e atribuição opcional."""

    def __init__(self, janela):
        super().__init__()
        self.janela = janela
        with ext.db(BANCO) as c:
            self.clientes = [dict(x) for x in c.execute(
                "SELECT id,nome,tipo_pessoa FROM clientes WHERE status!='Inativo' ORDER BY nome")]
            self.prestadores = [dict(x) for x in c.execute(
                "SELECT id,nome FROM prestadores WHERE ativo=1 ORDER BY nome")]
        if not self.clientes:
            raise ValueError("Cadastre um condomínio ou cliente antes de abrir a OS.")
        self.set_title("Nova OS rápida")
        self.set_content_width(680)
        self.set_content_height(520)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Nova OS rápida"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(
            title="Condomínio, cliente e solicitação",
            description="A OS é criada como Aberta, pronta para preenchimento e finalização.")
        pagina.add(grupo)
        self.filtro = Gtk.SearchEntry(placeholder_text="Buscar condomínio, empresa ou cliente")
        self.filtro.connect("search-changed", lambda *_args: self._filtrar())
        grupo.add(_linha_custom(self.filtro))
        self.clientes_filtrados = list(self.clientes)
        self.combo_cliente = ui.campo_combo(
            grupo, "Cliente / condomínio",
            [f"#{x['id']} {x['nome']} ({x['tipo_pessoa']})" for x in self.clientes_filtrados], 0)
        self.solicitacao = ui.campo_texto(grupo, "Solicitação / descrição do serviço",
                                          altura=110)
        opcoes = ["Não atribuir agora"] + [f"#{p['id']} {p['nome']}" for p in self.prestadores]
        self.combo_prestador = ui.campo_combo(grupo, "Atribuir prestador (opcional)", opcoes, 0)
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.append(ui.botao("Cancelar", self.close))
        espaco = Gtk.Box()
        espaco.set_hexpand(True)
        rodape.append(espaco)
        rodape.append(ui.botao("Criar OS aberta", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _filtrar(self):
        termo = self.filtro.get_text().strip().casefold()
        self.clientes_filtrados = [x for x in self.clientes
                                   if not termo or termo in str(x["nome"]).casefold()
                                   or termo in str(x["id"])]
        if not self.clientes_filtrados:
            self.clientes_filtrados = list(self.clientes)
        self.combo_cliente.set_model(Gtk.StringList.new(
            [f"#{x['id']} {x['nome']} ({x['tipo_pessoa']})" for x in self.clientes_filtrados]))
        self.combo_cliente.set_selected(0)

    def _salvar(self):
        indice = int(self.combo_cliente.get_selected())
        if not 0 <= indice < len(self.clientes_filtrados):
            ui.aviso_erro(self.janela, "Cliente", "Selecione um cliente/condomínio válido.")
            return
        descricao = self.solicitacao.get_texto().strip()
        if len(descricao) < 5:
            ui.aviso_erro(self.janela, "Solicitação", "Descreva a solicitação com pelo menos 5 caracteres.")
            return
        cliente = self.clientes_filtrados[indice]
        dados = {"cliente_id": str(cliente["id"]), "descricao": descricao, "tecnico": "",
                 "forma_pagamento": "PIX", "valor_mao_obra": "0",
                 "valor_materiais_manual": "0", "materiais_presentes": "1",
                 "acao_status": "salvar"}
        try:
            oid = neg.os_salvar(BANCO, dados, 0)
            escolhido = int(self.combo_prestador.get_selected())
            if escolhido > 0 and self.prestadores:
                ext.atribuir(BANCO, oid, self.prestadores[escolhido - 1]["id"],
                             ator="Desktop AUTOSEG")
        except Exception as erro:
            ui.aviso_erro(self.janela, "Não foi possível criar a OS", str(erro))
            return
        ui.toast(self.janela, "OS aberta criada. Preencha e finalize quando necessário.")
        self.close()
        self.janela.carregar_os()



class DialogoComponente(Adw.Dialog):
    """Edição de um componente da composição configurável."""

    def __init__(self, janela, componente=None, ids_existentes=None, ao_salvar=None):
        super().__init__()
        self.janela = janela
        self.componente = dict(componente or {})
        self.ids_existentes = set(ids_existentes or [])
        self.ao_salvar = ao_salvar
        titulo = "Editar componente" if componente else "Novo componente"
        self.set_title(titulo)
        self.set_content_width(680)
        self.set_content_height(720)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=titulo))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(title="Componente da composição")
        pagina.add(grupo)
        self.nome = ui.campo_entry(grupo, "Nome", self.componente.get("nome", ""))
        self.descricao = ui.campo_texto(grupo, "Descrição",
                                        self.componente.get("descricao", ""), 80)
        modo = self.componente.get("modo", "percentual")
        self.modo = ui.campo_combo(
            grupo, "Modo de cálculo", composicao.MODOS_LABELS,
            composicao.MODOS_CHAVES.index(modo) if modo in composicao.MODOS_CHAVES else 0)
        valor = self.componente.get("valor", 0)
        if modo == "percentual":
            valor_texto = str(valor)
        elif modo in ("fixo", "hora"):
            valor_texto = ui.dinheiro_texto(float(valor or 0) / 100)
        else:
            valor_texto = ""
        self.valor = ui.campo_entry(grupo, "Valor", valor_texto)
        self.formula = ui.campo_entry(grupo, "Fórmula (use IDs de componentes anteriores)",
                                      self.componente.get("formula", ""))
        self.horas = ui.campo_entry(grupo, "Horas padrão",
                                    ui.quantidade_texto(self.componente.get("horas_padrao", 0)))
        self.aplicavel = ui.campo_entry(
            grupo, "Aplicável a (nomes separados por vírgula; vazio = todos)",
            ", ".join(self.componente.get("aplicavel_a") or []))
        self.obrigatorio = Adw.SwitchRow(title="Obrigatório")
        self.obrigatorio.set_active(bool(self.componente.get("obrigatorio", False)))
        grupo.add(self.obrigatorio)
        self.ativo = Adw.SwitchRow(title="Ativo")
        self.ativo.set_active(bool(self.componente.get("ativo", True)))
        grupo.add(self.ativo)
        self.modo.connect("notify::selected", lambda *_args: self._atualizar_campos())
        self._atualizar_campos()
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Salvar componente", self._salvar, css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)

    def _modo(self):
        indice = self.modo.get_selected()
        if indice >= len(composicao.MODOS_CHAVES):
            return "percentual"
        return composicao.MODOS_CHAVES[indice]

    def _atualizar_campos(self):
        modo = self._modo()
        self.valor.set_visible(modo in ("fixo", "hora", "percentual"))
        self.formula.set_visible(modo == "formula")
        self.horas.set_visible(modo == "hora")
        self.valor.set_title(
            "Percentual (%)" if modo == "percentual" else
            "Valor da hora (R$)" if modo == "hora" else "Valor (R$)")

    def _salvar(self):
        nome = self.nome.get_text().strip()
        modo = self._modo()
        try:
            if modo == "percentual":
                valor = ui.numero(self.valor.get_text())
            elif modo in ("fixo", "hora"):
                valor = composicao.centavos_de_reais(self.valor.get_text())
            else:
                valor = 0
            componente = dict(self.componente)
            componente.update({
                "id": self.componente.get("id") or composicao.novo_id(nome, self.ids_existentes),
                "nome": nome,
                "descricao": self.descricao.get_texto(),
                "modo": modo,
                "valor": valor,
                "formula": self.formula.get_text().strip() if modo == "formula" else "",
                "horas_padrao": ui.numero(self.horas.get_text()) if modo == "hora" else 0,
                "aplicavel_a": [x.strip() for x in self.aplicavel.get_text().split(",") if x.strip()],
                "obrigatorio": self.obrigatorio.get_active(),
                "ativo": self.ativo.get_active(),
            })
            if not nome:
                raise ValueError("Informe o nome do componente.")
            if modo == "formula" and not componente["formula"]:
                raise ValueError("Informe a fórmula do componente.")
            if self.ao_salvar is not None:
                self.ao_salvar(componente)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Componente inválido", str(erro))
            return
        self.close()


class DialogoComposicao(Adw.Dialog):
    """Visualização da composição e simulação com valores informados."""

    def __init__(self, janela, total_reais=0, materiais_reais=0, horas=0,
                 tipo_servico=""):
        super().__init__()
        self.janela = janela
        self.set_title("Composição do valor")
        self.set_content_width(760)
        self.set_content_height(720)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Composição do valor"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(title="Simulação")
        pagina.add(grupo)
        self.total = ui.campo_entry(grupo, "Valor final (R$)", ui.dinheiro_texto(total_reais))
        self.materiais = ui.campo_entry(grupo, "Materiais (R$)", ui.dinheiro_texto(materiais_reais))
        self.horas = ui.campo_entry(grupo, "Horas de execução", ui.quantidade_texto(horas))
        self.tipo = ui.campo_entry(grupo, "Tipo de serviço (opcional)", tipo_servico)
        botao = ui.botao("Calcular composição", self._calcular,
                         icone="accessories-calculator-symbolic", css="suggested-action")
        grupo.add(_linha_custom(botao))
        self.tabela = ui.Tabela([
            ("Componente", 0, True, 0.0),
            ("Valor", 130, False, 0.5),
            ("Participação", 110, False, 0.5),
        ], altura=300)
        self.aviso = ui.legenda("")
        grupo_resultado = Adw.PreferencesGroup(title="Resultado")
        pagina.add(grupo_resultado)
        caixa_resultado = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        caixa_resultado.set_margin_top(8)
        caixa_resultado.set_margin_bottom(8)
        caixa_resultado.set_margin_start(10)
        caixa_resultado.set_margin_end(10)
        caixa_resultado.append(self.tabela.widget)
        caixa_resultado.append(self.aviso)
        grupo_resultado.add(_linha_custom(caixa_resultado))
        toolbar.set_content(pagina)
        self.set_child(toolbar)
        self._calcular()

    def _calcular(self):
        try:
            comp = composicao.calcular(
                total_centavos=composicao.centavos_de_reais(self.total.get_text()),
                materiais_centavos=composicao.centavos_de_reais(self.materiais.get_text()),
                horas=ui.numero(self.horas.get_text()),
                tipo_servico=self.tipo.get_text().strip())
            linhas = [
                (item["nome"], ui.brl(item["valor_centavos"] / 100),
                 f"{item['percentual']:.2f}%".replace(".", ","))
                for item in comp["componentes"]
            ]
            linhas.append(("TOTAL", ui.brl(comp["total_centavos"] / 100), "100,00%"))
            self.tabela.definir_linhas(linhas)
            self.aviso.set_text(comp.get("aviso") or
                                "A soma dos componentes confere com o valor final.")
        except Exception as erro:
            self.tabela.limpar()
            self.aviso.set_text(str(erro))
