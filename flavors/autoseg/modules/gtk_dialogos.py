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

from flavors.autoseg.modules import gtk_comum as ui
from officina.core.banco import BANCO
from officina.core import prestadores_ext as ext
from officina.core import fluxo_os as fluxo
from officina.core import atendimento_os as aten
from officina.core import cadastros_v9 as cad9
from officina.core import portal_negocios as neg
from officina.core import estoque_materiais as estoque
from officina.core import empresa_financeiro as empresa
from officina.core import catalogo_servicos as catalogo
from flavors.autoseg.modules import importacao_yaml
from officina.core import completude
from officina.core import composicao
from flavors.autoseg.modules import texto_os
from officina.application.contracts import AppError, OSInput


def _servico(janela):
    servico = getattr(janela, "service", None)
    if servico is None:
        from officina.application.local_service import LocalService
        servico = LocalService(BANCO)
    return servico


def _linha_custom(widget):
    linha = Adw.PreferencesRow()
    linha.set_child(widget)
    return linha


class DialogoCliente(Adw.Dialog):
    def __init__(self, janela, cliente_id=None, importado=None):
        super().__init__()
        self.janela = janela
        self.cliente_id = cliente_id
        self.servico = getattr(janela, "service", None)
        if self.servico is None:
            from officina.application.local_service import LocalService
            self.servico = LocalService(BANCO)
        self.dados = dict(importado) if importado else {}
        if cliente_id is not None:
            registro = self.servico.obter_cliente(cliente_id)
            self.dados = dict(registro.campos) if registro else {}

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
            registro = self.servico.salvar_cliente(self.cliente_id, dados)
        except AppError as erro:
            ui.aviso_erro(self.janela, erro.titulo, str(erro))
            return
        except Exception as erro:
            ui.aviso_erro(self.janela, "Cadastro não salvo", str(erro))
            return
        ui.toast(self.janela, "Cliente salvo com dados incompletos."
                 if registro.incompleto else "Cliente salvo.")
        self.janela.carregar_clientes()
        self.close()


class DialogoMaterial(Adw.Dialog):
    def __init__(self, parent, ao_salvar, atual=None):
        super().__init__()
        self.parent = parent
        self.ao_salvar = ao_salvar
        self.set_title("Editar material" if atual else "Adicionar material")
        self.set_content_width(480)
        self.set_content_height(410)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="Editar material" if atual else "Adicionar material"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup()
        pagina.add(grupo)
        self.item = ui.campo_entry(grupo, "Item / descrição", (atual or {}).get("item", ""))
        quantidade = (atual or {}).get("quantidade")
        texto_quantidade = ("1" if atual is None else
                            "" if quantidade is None else
                            ui.quantidade_texto(quantidade))
        self.quantidade = ui.campo_entry(grupo, "Quantidade (opcional)", texto_quantidade)
        self.unidade = ui.campo_entry(
            grupo, "Unidade de medida (opcional)",
            "un" if atual is None else str((atual or {}).get("unidade") or ""))
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
        texto_qtd = self.quantidade.get_text().strip()
        qtd = ui.numero(texto_qtd) if texto_qtd else None
        valor = ui.numero(self.valor.get_text())
        unidade = self.unidade.get_text().strip()[:40]
        if not item:
            ui.aviso_erro(self.parent, "Item obrigatório", "Informe a descrição do material.")
            return
        if qtd is not None and qtd <= 0:
            ui.aviso_erro(self.parent, "Quantidade inválida",
                          "Informe uma quantidade maior que zero ou deixe o campo vazio.")
            return
        self.ao_salvar({"item": item, "quantidade": qtd, "unidade": unidade,
                        "valor_unitario": valor,
                        "valor_total": (qtd or 0) * valor})
        self.close()


class DialogoEstoqueOS(Adw.Dialog):
    def __init__(self, parent, ao_adicionar):
        super().__init__()
        self.parent = parent
        self.produtos = _servico(self.parent).listar_materiais_estoque(ativos=True)
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
            "unidade": str(produto.get("unidade") or "un").strip(),
            "valor_unitario": produto["venda_centavos"] / 100,
            "valor_total": qtd * produto["venda_centavos"] / 100,
        })
        self.close()


def _os_tem_composicao_modular(dados):
    """True quando a OS guardou uma composição modular autoritativa."""
    dados = dados or {}
    base = str(dados.get("base_percentuais") or "").strip()
    comp_atual = composicao.de_json(dados.get("composicao_json"))
    return bool(base and isinstance(comp_atual, dict)
                and comp_atual.get("base_percentuais"))


def _composicao_da_os(dados, total, materiais, mao_obra, tempo_horas, config=None):
    """Recalcula a composição preservando a base modular usada pela OS.

    OSs criadas ou editadas pelo portal guardam a base em ``base_percentuais``.
    Ao salvar pelo desktop, usar a mesma base mantém os filhos da visita e os
    percentuais. OSs antigas, sem base, continuam com a regra explícita
    (materiais + mão de obra) que o desktop sempre usou.
    """
    base = str((dados or {}).get("base_percentuais") or "").strip()
    comp_atual = composicao.de_json((dados or {}).get("composicao_json"))
    if isinstance(comp_atual, dict) and comp_atual.get("declarativa"):
        raise ValueError(
            "Esta OS usa composição declarativa. Edite-a pelo portal para "
            "preservar os componentes.")
    total_centavos = composicao.centavos_de_reais(total)
    materiais_centavos = composicao.centavos_de_reais(materiais)
    mao_obra_centavos = composicao.centavos_de_reais(mao_obra)
    # O JSON modular carrega a própria base. OSs antigas (ou salvas com
    # "Aplicar composição" desmarcado) não têm essa marca e continuam na
    # regra explícita do desktop.
    if _os_tem_composicao_modular(dados):
        return composicao.calcular_os(
            total_centavos=total_centavos,
            materiais_centavos=materiais_centavos,
            mao_obra_centavos=mao_obra_centavos,
            horas=tempo_horas,
            base_percentuais=base, config=config), base
    return composicao.calcular(
        total_centavos=total_centavos,
        materiais_centavos=materiais_centavos,
        horas=tempo_horas,
        mao_obra_centavos=mao_obra_centavos, config=config), ""


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
        self.config_composicao = _servico(janela).composicao_config()
        self._carregar()
        if self.os_id is None and self.importado:
            self.materiais = [dict(m) for m in self.importado.get("materiais", [])]
        self._construir()

    def _carregar(self):
        contexto = _servico(self.janela).contexto_os(self.os_id)
        self.clientes = contexto["clientes"]
        if self.os_id is not None:
            self.dados = contexto["dados"]
            if self.dados is None:
                raise ValueError("OS não encontrada.")
            self.materiais = contexto["materiais"]
            self.original_portal = contexto["original_portal"]
            self.andamento = contexto["andamento"]
            self.encerramento = contexto["encerramento"]

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
        self.clientes_filtrados = list(self.clientes)
        self.busca_cliente_os = Gtk.SearchEntry(
            placeholder_text="Buscar cliente por nome ou ID")
        self.busca_cliente_os.set_hexpand(True)
        self.busca_cliente_os.connect(
            "search-changed", lambda *_args: self._filtrar_clientes_os())
        caixa_busca = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        caixa_busca.set_margin_top(8)
        caixa_busca.set_margin_bottom(8)
        caixa_busca.set_margin_start(10)
        caixa_busca.set_margin_end(10)
        caixa_busca.append(self.busca_cliente_os)
        self.status_cliente_os = Gtk.Label(label="", xalign=0)
        self.status_cliente_os.add_css_class("caption")
        self.status_cliente_os.add_css_class("dim-label")
        caixa_busca.append(self.status_cliente_os)
        grupo.add(_linha_custom(caixa_busca))
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
        pagamentos = ["Selecione a forma de pagamento", "PIX", "Transferência", "Dinheiro", "Cartão", "Boleto", "Outro"]
        pagamento = base.get("forma_pagamento", "")
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
        self.custo_materiais = ui.campo_entry(
            grupo, "Custo real dos materiais (R$) — interno, não cobrado",
            ui.dinheiro_texto(base.get("custo_materiais", 0)))
        self.total = ui.campo_entry(grupo, "Valor total (R$)",
                                    ui.dinheiro_texto(base.get("valor_total", 0)))
        self.tempo_horas = ui.campo_entry(
            grupo, "Tempo de execução (horas; 0 usa o padrão)",
            ui.quantidade_texto(base.get("tempo_horas", 0)))
        self.mao_obra.connect("notify::text", lambda *_args: self._recalcular())
        self.materiais_valor.connect("notify::text", lambda *_args: self._recalcular())
        self.total.connect("notify::text", lambda *_args: None)
        self.mao_obra.set_tooltip_text(
            "Serviço em garantia ou cortesia: use 0,00. "
            "Os materiais continuam sendo cobrados pelo valor informado.")
        self.total.set_tooltip_text(
            "O total é a soma de mão de obra + materiais. "
            "Em garantia, a mão de obra pode ficar em 0,00.")
        if self.materiais:
            self.materiais_valor.set_editable(False)
        self._recalcular()

        grupo = Adw.PreferencesGroup(title="Observações")
        pagina.add(grupo)
        self.observacoes = ui.campo_texto(
            grupo, "", base.get("observacoes", ""), 90)
        self.texto_adicional = ui.campo_texto(
            grupo, texto_os.rotulo(),
            base.get("texto_adicional", texto_os.padrao()), 90)
        if texto_os.ajuda():
            self.texto_adicional.set_tooltip_text(texto_os.ajuda())

        self.status = None
        self.relatorio = None
        self.motivo = None
        self.enviar_email = None
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
                status_opcoes = ["Selecione a situação", "Pendente", "Concluída", "Cancelada"]
                self.status = ui.campo_combo(grupo, "Situação ao salvar", status_opcoes, 0)
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
                self.enviar_email = Adw.SwitchRow(
                    title="Enviar relatório por e-mail ao concluir",
                    subtitle="Desligue para concluir sem destinatário.")
                self.enviar_email.set_active(True)
                grupo.add(self.enviar_email)
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

    def _filtrar_clientes_os(self):
        termo = self.busca_cliente_os.get_text().strip().casefold() \
            if hasattr(self, "busca_cliente_os") else ""
        atual = None
        indice = int(self.cliente.get_selected()) if hasattr(self, "cliente") else -1
        if 0 <= indice < len(self.clientes_filtrados):
            atual = self.clientes_filtrados[indice]["id"]
        if termo:
            self.clientes_filtrados = [
                x for x in self.clientes
                if termo in f"{x['id']} {x.get('nome', '')}".casefold()]
        else:
            self.clientes_filtrados = list(self.clientes)
        self.cliente.set_model(Gtk.StringList.new([
            f"{x['id']} - {x['nome']}" for x in self.clientes_filtrados]))
        escolhido = 0
        if atual is not None:
            for indice, cliente in enumerate(self.clientes_filtrados):
                if cliente["id"] == atual:
                    escolhido = indice
                    break
        if self.clientes_filtrados:
            self.cliente.set_selected(escolhido)
            self.status_cliente_os.set_text(
                "Cliente existente selecionado." if not termo else
                "Selecione um resultado ou digite um nome novo.")
        else:
            self.status_cliente_os.set_text(
                "Nome novo: será cadastrado com dados incompletos para completar depois.")

    def _cliente_para_os(self):
        indice = int(self.cliente.get_selected()) if self.clientes_filtrados else -1
        if 0 <= indice < len(self.clientes_filtrados):
            return int(self.clientes_filtrados[indice]["id"])
        nome = self.busca_cliente_os.get_text().strip()
        if len(nome) < 2:
            raise ValueError("Selecione um cliente existente ou digite o nome de um novo cliente.")
        existente = next(
            (x for x in self.clientes if str(x.get("nome") or "").casefold() == nome.casefold()),
            None)
        if existente:
            return int(existente["id"])
        registro = self.janela.service.salvar_cliente(
            None, {"nome": nome, "status": "Ativo", "provisorio": True})
        self.clientes.append({"id": int(registro.id), "nome": registro.nome})
        return int(registro.id)

    def _atualizar_materiais(self):
        linhas = []
        total = 0.0
        for material in self.materiais:
            qtd = material.get("quantidade")
            valor = float(material.get("valor_unitario") or 0)
            subtotal = (float(qtd) if qtd is not None else 0.0) * valor
            total += subtotal
            unidade = str(material.get("unidade") or "").strip()
            texto_qtd = "—" if qtd is None else ui.quantidade_texto(qtd)
            if qtd is not None and unidade:
                texto_qtd += f" {unidade}"
            linhas.append((material.get("item", ""), texto_qtd,
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
        # Em OS com composição modular o total é negociado; não sobrescrever
        # ao mexer em materiais ou mão de obra. O usuário ainda pode editar o
        # campo total diretamente.
        if not _os_tem_composicao_modular(self.dados):
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
        if not _servico(self.janela).listar_materiais_estoque(ativos=True):
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
        existentes = _servico(self.janela).contar_anexos_os(self.os_id)
        self.anexos_label.set_text(
            f"{existentes} imagem(ns) registrada(s); {len(self.imagens)} aguardando confirmação.")

    def _iniciar_atendimento(self):
        try:
            _servico(self.janela).iniciar_os(self.os_id)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Não foi possível iniciar", str(erro))
            return
        ui.toast(self.janela, "Atendimento iniciado.")
        self.close()
        self.janela.abrir_os_id(self.os_id)

    def _confirmar_situacao(self):
        situacao = ui.valor_combo(self.status)
        if situacao not in ("Pendente", "Concluída", "Cancelada"):
            ui.aviso_erro(self.janela, "Situação da OS",
                          "Escolha Pendente, Concluída ou Cancelada antes de confirmar.")
            return
        if situacao == "Pendente":
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
        try:
            cliente_id = self._cliente_para_os()
        except ValueError as erro:
            ui.aviso_erro(self.janela, "Cliente", str(erro))
            return
        except Exception as erro:
            ui.aviso_erro(self.janela, "Cliente", str(erro))
            return
        descricao = self.descricao.get_texto()
        tecnico = self.tecnico.get_text().strip()
        pagamento = ui.valor_combo(self.pagamento)
        if pagamento not in ("PIX", "Transferência", "Dinheiro", "Cartão", "Boleto", "Outro"):
            ui.aviso_erro(self.janela, "Forma de pagamento",
                          "Escolha a forma de pagamento antes de salvar.")
            return
        mao_obra = ui.numero(self.mao_obra.get_text())
        materiais = sum(float(x.get("quantidade") or 0) * float(x.get("valor_unitario") or 0)
                        for x in self.materiais)
        if not self.materiais:
            materiais = ui.numero(self.materiais_valor.get_text())
        custo_materiais = ui.numero(self.custo_materiais.get_text())
        total = ui.numero(self.total.get_text()) or (mao_obra + materiais)
        tempo_horas = ui.numero(self.tempo_horas.get_text())
        try:
            comp, base_percentuais = _composicao_da_os(
                self.dados, total, materiais, mao_obra, tempo_horas,
                config=self.config_composicao)
        except ValueError as erro:
            ui.aviso_erro(self.janela, "Composição do valor", str(erro))
            return
        if base_percentuais:
            total = comp["total_centavos"] / 100
            componente_hora = next(
                (x for x in comp["componentes"] if x.get("modo") == "hora"), None)
            if componente_hora is not None:
                mao_obra = componente_hora["valor_centavos"] / 100
        base_persistida = (base_percentuais
                           or str((self.dados or {}).get("base_percentuais") or "").strip()
                           or "total")
        comp_json = composicao.para_json(comp)
        if getattr(self.janela.service, "mode", "local") == "local":
            composicao.instalar_banco(BANCO)
        observacoes = self.observacoes.get_texto()
        texto_adicional = self.texto_adicional.get_texto()
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

        imagens = []
        for caminho in self.imagens:
            try:
                with open(caminho, "rb") as arquivo:
                    imagens.append((Path(caminho).name, arquivo.read()))
            except OSError as erro:
                ui.aviso_erro(self.janela, "Imagem", str(erro))
                return
        entrada = OSInput(
            os_id=self.os_id,
            cliente_id=cliente_id,
            tecnico=tecnico,
            descricao=descricao,
            valor_mao_obra=mao_obra,
            valor_materiais=materiais,
            custo_materiais=custo_materiais,
            valor_total=total,
            forma_pagamento=pagamento,
            urgencia=ui.valor_combo(self.urgencia),
            observacoes=observacoes,
            texto_adicional=texto_adicional,
            dados_incompletos=dados_incompletos,
            tempo_horas=tempo_horas,
            composicao_json=comp_json,
            base_percentuais=base_persistida,
            materiais=tuple(self.materiais),
            acao=acao,
            relato=relato,
            motivo=motivo,
            imagens=tuple(imagens),
        )
        try:
            resultado = self.janela.service.salvar_os(entrada)
        except AppError as erro:
            ui.aviso_erro(self.janela, erro.titulo, str(erro))
            return
        except Exception as erro:
            ui.aviso_erro(self.janela, "Não foi possível salvar", str(erro))
            return

        os_salvo_id = resultado.os_id
        if resultado.encerrada:
            ui.toast(self.janela, "OS encerrada. Publicando PDF…")
            self.close()
            enviar_email = (acao == "Concluída"
                            and (self.enviar_email is None or self.enviar_email.get_active()))
            self.janela.publicar_pdf(os_salvo_id, enviar_email=enviar_email)
            self.janela.carregar_os()
            self.janela.carregar_historico()
            return

        if self.os_id is not None and resultado.status_anterior in ui.STATUS_FIM:
            ui.toast(self.janela, "OS atualizada. Republicando PDF…")
            self.close()
            self.janela.publicar_pdf(os_salvo_id)
            self.janela.carregar_historico()
            return

        ui.toast(self.janela, "OS salva com dados incompletos."
                 if resultado.dados_incompletos else "OS salva.")
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
        contexto = _servico(janela).contexto_atribuicao(os_id)
        self.ordem = contexto["ordem"]
        self.prestadores = contexto["prestadores"]
        self.atual_id = contexto["atual_id"]
        if not self.ordem or self.ordem["status"] not in ext.ATIVAS:
            raise ValueError("Somente OS ativa.")
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
            mudou = _servico(self.janela).atribuir_os(self.os_id, prestador_id)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Atribuição", str(erro))
            return
        ui.toast(self.janela, "Responsabilidade registrada." if mudou else "Prestador já é o responsável.")
        self.close()
        self.janela.carregar_os()

    def _liberar(self):
        try:
            _servico(self.janela).desatribuir_os(self.os_id)
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
            _servico(self.janela).definir_senha_cliente(self.cliente_id, senha)
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
        self.documento = ui.campo_entry(grupo, "CNPJ do prestador (pode repetir)")
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
            _servico(self.janela).criar_prestador({
                "nome": self.nome.get_text().strip(),
                "email": self.email.get_text().strip(),
                "senha": self.senha.get_text(),
                "telefone": self.telefone.get_text().strip(),
                "documento": documento,
                "especialidade": self.especialidade.get_text().strip(),
            })
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
            _servico(self.janela).redefinir_senha_prestador(
                self.prestador_id, senha)
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
        self.config = _servico(janela).obter_config_prestador(prestador_id)
        self.documento_atual = _servico(janela).documento_prestador(prestador_id)
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
        opcoes_provedor = ('', 'SMTP', 'Microsoft Graph', 'Gmail API', 'Outro')
        provedor_atual = self.config.get("provedor_email", "")
        provedor_sel = (opcoes_provedor.index(provedor_atual)
                        if provedor_atual in opcoes_provedor else 0)
        self.provedor = ui.campo_combo(grupo, "Provedor de envio",
                                       opcoes_provedor, provedor_sel)
        self.remetente = ui.campo_entry(grupo, "E-mail remetente",
                                        self.config.get("email_remetente", ""))
        self.documento = ui.campo_entry(
            grupo, "CNPJ do prestador (usado no relatório quando diferente do principal)",
            cad9.formatar_documento(self.documento_atual))
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
        dados["provedor_email"] = ui.valor_combo(self.provedor)
        dados["email_remetente"] = self.remetente.get_text().strip()
        dados["dados_bancarios_texto"] = self.dados.get_texto()
        try:
            _servico(self.janela).definir_documento_prestador(
                self.prestador_id, self.documento.get_text())
        except Exception as erro:
            ui.aviso_erro(self.janela, "CNPJ inválido", str(erro))
            return
        try:
            _servico(self.janela).salvar_config_prestador(
                self.prestador_id, dados)
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
        self.registro = _servico(janela).catalogo_obter(servico_id) if servico_id else None
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
            _servico(self.janela).catalogo_salvar(dados, self.servico_id)
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
        registro = (_servico(janela).estoque_obter(produto_id) or {})
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
        self.sku = ui.campo_entry(grupo, "Código / SKU (opcional)", registro.get("sku", ""))
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
            _servico(self.janela).estoque_cadastrar({
                "nome": self.nome.get_text().strip(),
                "sku": self.sku.get_text().strip(),
                "unidade": self.unidade.get_text().strip(),
                "custo": self.custo.get_text().strip(),
                "venda": self.venda.get_text().strip(),
                "minimo": self.minimo.get_text().strip(),
            }, self.produto_id)
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
            _servico(self.janela).estoque_ajuste(
                self.produto_id, self.quantidade.get_text(),
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
        registros = _servico(self.janela).estoque_movimentos(produto_id, 300)
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
        contexto = _servico(janela).contexto_responsavel()
        self.orgs = contexto["organizacoes"]
        self.pessoas = contexto["pessoas"]
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
            papel = _servico(self.janela).atribuir_responsavel(
                org["id"], pessoa["id"])
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
            _servico(self.janela).remover_responsavel(org["id"])
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
        contexto = _servico(janela).contexto_os_rapida()
        self.clientes = contexto["clientes"]
        self.prestadores = contexto["prestadores"]
        if not self.clientes:
            raise ValueError("Cadastre um condomínio ou cliente antes de abrir a OS.")
        self.set_title("Nova ordem de serviço")
        self.set_content_width(680)
        self.set_content_height(520)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Nova ordem de serviço"))
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
        self.pagamento = ui.campo_combo(
            grupo, "Forma de pagamento",
            ["Selecione a forma de pagamento", "PIX", "Transferência", "Dinheiro",
             "Cartão", "Boleto", "Outro"], 0)
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
        pagamento = ui.valor_combo(self.pagamento)
        if pagamento not in ("PIX", "Transferência", "Dinheiro", "Cartão", "Boleto", "Outro"):
            ui.aviso_erro(self.janela, "Forma de pagamento",
                          "Escolha a forma de pagamento antes de criar a OS.")
            return
        entrada = OSInput(
            os_id=None, cliente_id=int(cliente["id"]), tecnico="",
            descricao=descricao, valor_mao_obra=0.0, valor_materiais=0.0,
            custo_materiais=0.0, valor_total=0.0, forma_pagamento=pagamento,
            urgencia="Normal", observacoes="", texto_adicional="",
            dados_incompletos=0, tempo_horas=0.0, composicao_json="",
            base_percentuais="total", materiais=(), acao="", relato="",
            motivo="", imagens=())
        try:
            resultado = _servico(self.janela).salvar_os(entrada)
            escolhido = int(self.combo_prestador.get_selected())
            if escolhido > 0 and self.prestadores:
                _servico(self.janela).atribuir_os(
                    resultado.os_id, self.prestadores[escolhido - 1]["id"])
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
        self.config_composicao = _servico(janela).composicao_config()
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
                tipo_servico=self.tipo.get_text().strip(),
                config=self.config_composicao)
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


def _data_br_empresa(valor):
    try:
        return datetime.strptime(str(valor), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(valor or "")


class DialogoCaixaEmpresa(Adw.Dialog):
    """Company cash ledger kept apart from OS revenue, stock and rateios."""

    def __init__(self, janela, ao_atualizar=None):
        super().__init__()
        self.janela = janela
        self.ao_atualizar = ao_atualizar
        self.set_title("Caixa e investimentos")
        self.set_content_width(900)
        self.set_content_height(700)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Caixa e investimentos"))
        toolbar.add_top_bar(header)

        pagina = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pagina.set_margin_top(12)
        pagina.set_margin_bottom(12)
        pagina.set_margin_start(18)
        pagina.set_margin_end(18)

        cartoes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                          homogeneous=True)
        cartao_capital, self.rotulo_capital, _ = ui.cartao(
            "Capital investido", classe="accent")
        cartao_despesas, self.rotulo_despesas, self.detalhe_despesas = ui.cartao(
            "Despesas", classe="warning")
        cartao_saldo, self.rotulo_saldo, self.detalhe_saldo = ui.cartao(
            "Saldo do controle", classe="success")
        cartoes.append(cartao_capital)
        cartoes.append(cartao_despesas)
        cartoes.append(cartao_saldo)
        pagina.append(cartoes)
        self.rotulo_investidores = ui.legenda(
            "Capital por investidor: sem aportes.")
        self.rotulo_investidores.set_wrap(True)
        pagina.append(self.rotulo_investidores)
        pagina.append(ui.legenda(
            "Saldo do controle = capital aportado − despesas registradas. "
            "Não é saldo bancário. Receitas de OS continuam no Financeiro e "
            "não entram aqui. Compra de material vinculada a uma OS é apenas "
            "referência e não altera custo, estoque ou PDF da OS."))

        self.tabela = ui.Tabela([
            ("ID", 50, False, 0.5),
            ("Data", 95, False, 0.5),
            ("Tipo", 145, False, 0.0),
            ("Pessoa / OS", 175, False, 0.0),
            ("Descrição", 0, True, 0.0),
            ("Finalidade", 140, False, 0.0),
            ("Categoria", 115, False, 0.0),
            ("Valor", 110, False, 1.0),
        ])
        pagina.append(self.tabela.widget)

        botoes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        botoes.append(ui.botao("Novo lançamento", self._novo,
                               css="suggested-action"))
        botoes.append(ui.botao("Arquivar selecionado", self._arquivar,
                               css="destructive-action"))
        botoes.append(ui.botao("Fechar", self.close))
        pagina.append(botoes)

        toolbar.set_content(pagina)
        self.set_child(toolbar)
        self._carregar()

    def _carregar(self):
        try:
            resumo = _servico(self.janela).empresa_resumo()
            movimentos = _servico(self.janela).empresa_listar()
        except Exception as erro:
            ui.aviso_erro(self.janela, "Caixa da empresa", str(erro))
            return
        self.rotulo_capital.set_text(ui.brl(resumo["aportes_centavos"] / 100))
        self.rotulo_despesas.set_text(ui.brl(resumo["despesas_centavos"] / 100))
        self.rotulo_saldo.set_text(ui.brl(resumo["saldo_centavos"] / 100))
        self.detalhe_saldo.set_text(
            "capital − despesas; não é saldo bancário")
        if resumo["por_investidor"]:
            self.rotulo_investidores.set_text(
                "Capital por investidor: " + " · ".join(
                    f"{item['nome']}: {ui.brl(item['total_centavos'] / 100)}"
                    for item in resumo["por_investidor"]))
        else:
            self.rotulo_investidores.set_text(
                "Capital por investidor: sem aportes.")
        self.detalhe_despesas.set_text(
            f"Material {ui.brl(resumo['material_centavos'] / 100)} · "
            f"API {ui.brl(resumo['api_centavos'] / 100)} · "
            f"Outras {ui.brl(resumo['outras_despesas_centavos'] / 100)}")
        linhas = []
        for item in movimentos:
            pessoa_os = " · ".join(
                str(valor) for valor in
                (item.get("prestador_nome"), item.get("numero_os")) if valor)
            linhas.append((
                item["id"],
                _data_br_empresa(item["data"]),
                empresa.TIPOS.get(item["tipo"], item["tipo"]),
                pessoa_os or "—",
                item["descricao"],
                item.get("finalidade") or "—",
                item["categoria"] or "—",
                ui.brl(item["valor_centavos"] / 100),
            ))
        self.tabela.definir_linhas(linhas)
        if self.ao_atualizar is not None:
            self.ao_atualizar()

    def _novo(self):
        DialogoNovoMovimentoEmpresa(
            self.janela, self._carregar).present(self.janela)

    def _arquivar(self):
        valores = self.tabela.selecionado()
        if valores is None:
            ui.aviso_erro(self.janela, "Seleção",
                          "Selecione um lançamento para arquivar.")
            return
        ui.alerta(
            self.janela, "Arquivar lançamento",
            f"Arquivar o lançamento #{valores[0]}? O histórico será preservado.",
            lambda: self._confirmar_arquivamento(valores[0]),
            destrutivo=True, rotulo_ok="Arquivar")

    def _confirmar_arquivamento(self, movimento_id):
        try:
            _servico(self.janela).empresa_arquivar(movimento_id)
        except Exception as erro:
            ui.aviso_erro(self.janela, "Caixa da empresa", str(erro))
            return
        self._carregar()
        ui.toast(self.janela, "Lançamento arquivado; histórico preservado.")


class DialogoNovoMovimentoEmpresa(Adw.Dialog):
    """Simple entry form; no SKU, no stock movement and no OS cost change."""

    def __init__(self, janela, ao_salvar=None):
        super().__init__()
        self.janela = janela
        self.ao_salvar = ao_salvar
        contexto = _servico(janela).contexto_movimento_empresa()
        self.prestadores = contexto["prestadores"]
        self.oses = contexto["oses"]
        self.tipos = list(empresa.TIPOS.items())
        self.codigos_tipo = [codigo for codigo, _ in self.tipos]
        self.set_title("Novo lançamento da empresa")
        self.set_content_width(620)
        self.set_content_height(760)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(
            title="Novo lançamento da empresa"))
        toolbar.add_top_bar(header)
        pagina = Adw.PreferencesPage()
        grupo = Adw.PreferencesGroup(title="Lançamento")
        pagina.add(grupo)
        self.tipo = ui.campo_combo(
            grupo, "Tipo de lançamento",
            [rotulo for _, rotulo in self.tipos], 0)
        self.data = ui.campo_entry(
            grupo, "Data", datetime.now().strftime("%d/%m/%Y"))
        self.pessoa = ui.campo_combo(
            grupo, "Investidor (obrigatório no aporte)",
            ["Nenhuma"] + [p["nome"] for p in self.prestadores], 0)
        self.descricao = ui.campo_entry(grupo, "Descrição", "")
        self._descricao_automatica = ""
        self.categoria = ui.campo_entry(grupo, "Categoria", "Capital")
        self.finalidade = ui.campo_entry(
            grupo, "Finalidade do aporte (opcional)", "")
        self.valor = ui.campo_entry(grupo, "Valor (R$)", "")
        opcoes_os = ["Nenhuma"] + [
            f"{o['numero_os']} — {o['cliente'] or 'sem cliente'}"
            for o in self.oses]
        self.os = ui.campo_combo(
            grupo, "OS vinculada (opcional, só referência)", opcoes_os, 0)
        self.observacao = ui.campo_texto(
            grupo, "Observação (opcional)", "", altura=90)
        aviso = ui.legenda(
            "Aporte é capital permanente, não é saldo em caixa e não será "
            "extornado. Informe a finalidade para saber a que se destina. "
            "Compra de material sem SKU pode ser vinculada a uma OS apenas "
            "para referência; nada é alterado na OS, no estoque ou no "
            "Financeiro.")
        aviso.set_wrap(True)
        grupo.add(_linha_custom(aviso))
        toolbar.set_content(pagina)
        rodape = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        rodape.set_margin_top(10)
        rodape.set_margin_bottom(10)
        rodape.set_margin_start(18)
        rodape.set_margin_end(18)
        rodape.set_halign(Gtk.Align.END)
        rodape.append(ui.botao("Cancelar", self.close))
        rodape.append(ui.botao("Salvar lançamento", self._salvar,
                               css="suggested-action"))
        toolbar.add_bottom_bar(rodape)
        self.set_child(toolbar)
        self.tipo.connect("notify::selected", lambda *_args: self._atualizar_tipo())
        self._atualizar_tipo()

    def _codigo_tipo(self):
        indice = int(self.tipo.get_selected())
        if not 0 <= indice < len(self.codigos_tipo):
            return self.codigos_tipo[0]
        return self.codigos_tipo[indice]

    def _atualizar_tipo(self):
        codigo = self._codigo_tipo()
        self.categoria.set_text(empresa.CATEGORIAS_PADRAO[codigo])
        self.categoria.set_visible(codigo != "aporte")
        self.finalidade.set_visible(codigo == "aporte")
        self.os.set_visible(codigo == "material")
        self.pessoa.set_title(
            "Investidor (obrigatório)" if codigo == "aporte"
            else "Pago por (opcional)")
        atual = self.descricao.get_text().strip()
        if not atual or atual == self._descricao_automatica:
            self._descricao_automatica = empresa.TIPOS[codigo]
            self.descricao.set_text(self._descricao_automatica)

    def _salvar(self):
        tipo = self._codigo_tipo()
        prestador_id = None
        indice_pessoa = int(self.pessoa.get_selected())
        if indice_pessoa > 0 and indice_pessoa <= len(self.prestadores):
            prestador_id = self.prestadores[indice_pessoa - 1]["id"]
        os_id = None
        if tipo == "material":
            indice_os = int(self.os.get_selected())
            if indice_os > 0 and indice_os <= len(self.oses):
                os_id = self.oses[indice_os - 1]["id"]
        try:
            _servico(self.janela).empresa_registrar({
                "tipo": tipo,
                "descricao": self.descricao.get_text().strip(),
                "valor": self.valor.get_text().strip(),
                "data": self.data.get_text().strip(),
                "prestador_id": prestador_id,
                "os_id": os_id,
                "categoria": self.categoria.get_text().strip(),
                "finalidade": (self.finalidade.get_text().strip()
                               if tipo == "aporte" else ""),
                "observacao": self.observacao.get_texto(),
            })
        except Exception as erro:
            ui.aviso_erro(self, "Lançamento inválido", str(erro))
            return
        if self.ao_salvar is not None:
            self.ao_salvar()
        ui.toast(self.janela, "Lançamento salvo no caixa da empresa.")
        self.close()
