/* ============================================================
   PORTAL DO CLIENTE · GESTÃO DE SERVIÇOS
   ============================================================ */

(() => {
  "use strict";

  const CHAVE_TOKEN = "gestao_servicos_portal_token";
  const STATUS = {
    Aberta: { label: "Aberta", classe: "chip-aberta" },
    Pendente: { label: "Pendente", classe: "chip-pendente" },
    "Concluída": { label: "Concluída", classe: "chip-concluida" },
    Cancelada: { label: "Cancelada", classe: "chip-cancelada" },
  };

  let token = localStorage.getItem(CHAVE_TOKEN) || "";
  let cliente = null;
  let ordens = [];
  let temporizadorToast = null;

  const $ = (seletor) => document.querySelector(seletor);

  const els = {
    viewAuth: $("#view-auth"),
    viewDashboard: $("#view-dashboard"),
    tabLogin: $("#tab-login"),
    tabCadastro: $("#tab-cadastro"),
    panelLogin: $("#panel-login"),
    panelCadastro: $("#panel-cadastro"),
    formLogin: $("#form-login"),
    formCadastro: $("#form-cadastro"),
    btnLogin: $("#btn-login"),
    btnCadastro: $("#btn-cadastro"),
    erroLogin: $("#erro-login"),
    erroCadastro: $("#erro-cadastro"),
    clienteNome: $("#cliente-nome"),
    clienteInfo: $("#cliente-info"),
    statTotal: $("#stat-total"),
    statAndamento: $("#stat-andamento"),
    statConcluidas: $("#stat-concluidas"),
    listaOs: $("#lista-os"),
    btnNovaOs: $("#btn-nova-os"),
    btnSair: $("#btn-sair"),
    btnAtualizar: $("#btn-atualizar"),
    modalOs: $("#modal-os"),
    btnFecharModal: $("#btn-fechar-modal"),
    btnCancelarModal: $("#btn-cancelar-modal"),
    formOs: $("#form-os"),
    osDescricao: $("#os-descricao"),
    osUrgencia: $("#os-urgencia"),
    osContato: $("#os-contato"),
    osDisponibilidade: $("#os-disponibilidade"),
    osObservacoes: $("#os-observacoes"),
    erroOs: $("#erro-os"),
    btnEnviarOs: $("#btn-enviar-os"),
    contadorDescricao: $("#contador-descricao"),
    toast: $("#toast"),
    footerHora: $("#footer-hora"),
  };

  // ------------------------------------------------------------
  // UTILITÁRIOS
  // ------------------------------------------------------------

  function escapar(valor) {
    return String(valor ?? "").replace(/[&<>"']/g, (caractere) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[caractere]));
  }

  function formatarMoeda(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL",
    });
  }

  function mostrarToast(mensagem, tipo = "ok") {
    if (!els.toast) return;

    window.clearTimeout(temporizadorToast);
    els.toast.textContent = mensagem;
    els.toast.classList.toggle("erro", tipo === "erro");
    els.toast.classList.add("show");

    temporizadorToast = window.setTimeout(() => {
      els.toast.classList.remove("show");
    }, 4800);
  }

  function setErro(elemento, mensagem) {
    if (!elemento) return;

    elemento.textContent = mensagem || "";
    elemento.classList.toggle("show", Boolean(mensagem));
  }

  function setLoading(botao, ativo, texto) {
    if (!botao) return;

    if (ativo) {
      if (!botao.dataset.textoOriginal) {
        botao.dataset.textoOriginal = botao.textContent.trim();
      }
      botao.disabled = true;
      botao.textContent = texto || "Aguarde...";
      return;
    }

    botao.disabled = false;
    botao.textContent = texto || botao.dataset.textoOriginal || "Enviar";
    delete botao.dataset.textoOriginal;
  }

  function salvarToken(novoToken) {
    token = novoToken;
    localStorage.setItem(CHAVE_TOKEN, token);
  }

  function limparToken() {
    token = "";
    localStorage.removeItem(CHAVE_TOKEN);
  }

  async function api(caminho, opcoes = {}) {
    const cabecalhos = {
      "Content-Type": "application/json",
      ...(opcoes.headers || {}),
    };

    if (token) {
      cabecalhos.Authorization = `Bearer ${token}`;
    }

    let resposta;

    try {
      resposta = await fetch(caminho, { ...opcoes, headers: cabecalhos });
    } catch (erro) {
      throw new Error("Não foi possível falar com o servidor. Verifique se o portal está online.");
    }

    let dados = null;

    try {
      dados = await resposta.json();
    } catch (erro) {
      dados = null;
    }

    if (!resposta.ok) {
      if (resposta.status === 401 && token) {
        sair(false);
      }

      throw new Error(
        (dados && dados.erro) || "Não foi possível concluir a solicitação."
      );
    }

    return dados;
  }

  // ------------------------------------------------------------
  // NAVEGAÇÃO
  // ------------------------------------------------------------

  function mostrarAuth() {
    els.viewAuth.classList.remove("hidden");
    els.viewDashboard.classList.add("hidden");
    document.body.classList.remove("modal-aberto");
  }

  function mostrarDashboard() {
    els.viewAuth.classList.add("hidden");
    els.viewDashboard.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function ativarAba(nome) {
    const login = nome === "login";

    els.tabLogin.classList.toggle("active", login);
    els.tabCadastro.classList.toggle("active", !login);
    els.tabLogin.setAttribute("aria-selected", String(login));
    els.tabCadastro.setAttribute("aria-selected", String(!login));
    els.panelLogin.classList.toggle("active", login);
    els.panelCadastro.classList.toggle("active", !login);

    setErro(els.erroLogin, "");
    setErro(els.erroCadastro, "");
  }

  function sair(avisar = true) {
    limparToken();
    cliente = null;
    ordens = [];
    mostrarAuth();

    if (avisar) {
      mostrarToast("Você saiu do portal.");
    }
  }

  // ------------------------------------------------------------
  // DADOS DO CLIENTE E DAS ORDENS
  // ------------------------------------------------------------

  function atualizarCliente() {
    if (!cliente) return;

    const primeiroNome = String(cliente.nome || "cliente").trim().split(/\s+/)[0];
    els.clienteNome.textContent = primeiroNome;

    const local = cliente.cidade
      ? `${cliente.cidade}${cliente.uf ? `/${cliente.uf}` : ""}`
      : "";

    const partes = [
      cliente.documento,
      local,
      cliente.email,
    ].filter(Boolean);

    els.clienteInfo.textContent = partes.length
      ? partes.join("  ·  ")
      : "Cadastro ativo no portal";
  }

  function atualizarResumo(resumo) {
    els.statTotal.textContent = String(resumo.total || 0);
    els.statAndamento.textContent = String(resumo.andamento || 0);
    els.statConcluidas.textContent = String(resumo.concluidas || 0);
  }

  async function carregarOrdens() {
    const dados = await api("/api/ordens");
    ordens = Array.isArray(dados.ordens) ? dados.ordens : [];
    renderizarOrdens();
    atualizarResumo(dados.resumo || {});
  }

  function renderizarOrdens() {
    if (!els.listaOs) return;

    if (!ordens.length) {
      els.listaOs.innerHTML = `
        <div class="empty">
          Nenhuma solicitação por aqui ainda.<br>
          Clique em <strong>Nova solicitação</strong> para abrir sua primeira OS.
        </div>
      `;
      return;
    }

    els.listaOs.innerHTML = ordens.map((os) => {
      const status = STATUS[os.status] || {
        label: os.status || "Pendente",
        classe: "chip-cancelada",
      };

      const urgencia = os.urgencia && os.urgencia !== "Normal"
        ? `<span class="chip chip-urgencia">${escapar(os.urgencia)}</span>`
        : "";

      const valor = Number(os.valor_total) > 0
        ? formatarMoeda(os.valor_total)
        : "A combinar";

      const conclusao = os.data_conclusao
        ? `<span>Concluída em <strong>${escapar(os.data_conclusao)}</strong></span>`
        : "";

      const cancelar = os.pode_cancelar
        ? `<button type="button" class="btn btn-danger btn-sm" data-cancelar="${Number(os.id)}">Cancelar</button>`
        : "";

      return `
        <article class="os-item">
          <div class="os-main">
            <div class="os-top">
              <span class="os-number">${escapar(os.numero_os)}</span>
              <span class="chip ${status.classe}">${escapar(status.label)}</span>
              ${urgencia}
            </div>
            <p class="os-desc">${escapar(os.descricao)}</p>
            <div class="os-meta">
              <span>Aberta em <strong>${escapar(os.data_abertura)}</strong></span>
              <span>Valor: <strong>${valor}</strong></span>
              <span>Origem: <strong>${os.origem === "Portal" ? "Portal do cliente" : "Atendimento"}</strong></span>
              ${conclusao}
            </div>
          </div>
          <div class="os-side">${cancelar}</div>
        </article>
      `;
    }).join("");
  }

  // ------------------------------------------------------------
  // MODAL DE NOVA OS
  // ------------------------------------------------------------

  function abrirModalOS() {
    setErro(els.erroOs, "");
    els.modalOs.classList.remove("hidden");
    document.body.classList.add("modal-aberto");
    window.setTimeout(() => els.osDescricao.focus(), 60);
  }

  function fecharModalOS() {
    els.modalOs.classList.add("hidden");
    document.body.classList.remove("modal-aberto");
  }

  // ------------------------------------------------------------
  // EVENTOS
  // ------------------------------------------------------------

  els.tabLogin.addEventListener("click", () => ativarAba("login"));
  els.tabCadastro.addEventListener("click", () => ativarAba("cadastro"));

  document.querySelectorAll("[data-ir-para]").forEach((botao) => {
    botao.addEventListener("click", () => ativarAba(botao.dataset.irPara));
  });

  els.formLogin.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    setErro(els.erroLogin, "");
    setLoading(els.btnLogin, true, "Entrando...");

    try {
      const dados = await api("/api/login", {
        method: "POST",
        body: JSON.stringify({
          documento: $("#login-documento").value.trim(),
          acesso: $("#login-acesso").value.trim(),
        }),
      });

      salvarToken(dados.token);
      cliente = dados.cliente;
      atualizarCliente();
      mostrarDashboard();
      await carregarOrdens();

      const nome = String(cliente.nome || "").split(/\s+/)[0];
      mostrarToast(`Bem-vindo, ${nome}!`);
    } catch (erro) {
      setErro(els.erroLogin, erro.message);
    } finally {
      setLoading(els.btnLogin, false, "Entrar e ver minhas OS");
    }
  });

  els.formCadastro.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    setErro(els.erroCadastro, "");
    setLoading(els.btnCadastro, true, "Criando cadastro...");

    const payload = {
      nome: $("#cad-nome").value.trim(),
      documento: $("#cad-documento").value.trim(),
      telefone: $("#cad-telefone").value.trim(),
      email: $("#cad-email").value.trim(),
      cidade: $("#cad-cidade").value.trim(),
      uf: $("#cad-uf").value.trim(),
      endereco: $("#cad-endereco").value.trim(),
      numero: $("#cad-numero").value.trim(),
      bairro: $("#cad-bairro").value.trim(),
    };

    try {
      const dados = await api("/api/cadastro", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      salvarToken(dados.token);
      cliente = dados.cliente;
      atualizarCliente();
      els.formCadastro.reset();
      mostrarDashboard();
      await carregarOrdens();
      mostrarToast("Cadastro criado! Você já pode solicitar sua OS.");
    } catch (erro) {
      setErro(els.erroCadastro, erro.message);
    } finally {
      setLoading(els.btnCadastro, false, "Criar cadastro e continuar");
    }
  });

  els.btnSair.addEventListener("click", () => sair(true));

  els.btnNovaOs.addEventListener("click", abrirModalOS);
  els.btnFecharModal.addEventListener("click", fecharModalOS);
  els.btnCancelarModal.addEventListener("click", fecharModalOS);

  els.modalOs.addEventListener("click", (evento) => {
    if (evento.target === els.modalOs) {
      fecharModalOS();
    }
  });

  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && !els.modalOs.classList.contains("hidden")) {
      fecharModalOS();
    }
  });

  els.osDescricao.addEventListener("input", () => {
    els.contadorDescricao.textContent = String(els.osDescricao.value.length);
  });

  els.formOs.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    setErro(els.erroOs, "");

    const descricao = els.osDescricao.value.trim();

    if (descricao.length < 10) {
      setErro(els.erroOs, "Descreva o serviço com pelo menos 10 caracteres.");
      els.osDescricao.focus();
      return;
    }

    setLoading(els.btnEnviarOs, true, "Enviando...");

    try {
      const dados = await api("/api/ordens", {
        method: "POST",
        body: JSON.stringify({
          descricao,
          urgencia: els.osUrgencia.value,
          contato_preferido: els.osContato.value,
          disponibilidade: els.osDisponibilidade.value.trim(),
          observacoes: els.osObservacoes.value.trim(),
        }),
      });

      fecharModalOS();
      els.formOs.reset();
      els.contadorDescricao.textContent = "0";
      mostrarToast(dados.mensagem || "Solicitação enviada com sucesso!");
      await carregarOrdens();
    } catch (erro) {
      setErro(els.erroOs, erro.message);
    } finally {
      setLoading(els.btnEnviarOs, false, "Enviar solicitação");
    }
  });

  els.btnAtualizar.addEventListener("click", async () => {
    setLoading(els.btnAtualizar, true, "Atualizando...");

    try {
      await carregarOrdens();
      mostrarToast("Lista atualizada.");
    } catch (erro) {
      mostrarToast(erro.message, "erro");
    } finally {
      setLoading(els.btnAtualizar, false, "Atualizar");
    }
  });

  els.listaOs.addEventListener("click", async (evento) => {
    const botao = evento.target.closest("[data-cancelar]");

    if (!botao) return;

    const confirmar = window.confirm(
      "Deseja cancelar esta solicitação?\n\nEssa ação não pode ser desfeita."
    );

    if (!confirmar) return;

    const textoOriginal = botao.textContent.trim();
    setLoading(botao, true, "Cancelando...");

    try {
      const dados = await api(`/api/ordens/${botao.dataset.cancelar}/cancelar`, {
        method: "POST",
      });
      mostrarToast(dados.mensagem || "Solicitação cancelada.");
      await carregarOrdens();
    } catch (erro) {
      mostrarToast(erro.message, "erro");
      setLoading(botao, false, textoOriginal);
    }
  });

  // ------------------------------------------------------------
  // INICIALIZAÇÃO
  // ------------------------------------------------------------

  async function carregarSessao() {
    if (!token) {
      mostrarAuth();
      return;
    }

    try {
      const dados = await api("/api/eu");
      cliente = dados.cliente;
      atualizarCliente();
      mostrarDashboard();
      await carregarOrdens();
    } catch (erro) {
      limparToken();
      mostrarAuth();

      if (erro && erro.message) {
        mostrarToast(erro.message, "erro");
      }
    }
  }

  function atualizarHora() {
    if (!els.footerHora) return;

    els.footerHora.textContent = new Date().toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  ativarAba("login");
  atualizarHora();
  window.setInterval(atualizarHora, 30000);
  carregarSessao();
})();
