// AUTOSEG Portal v6: interface sem dependências externas.
(function () {
  'use strict';

  // Toast global para erros de formulário: nunca navega para uma página de
  // erro e preserva o que o usuário digitou/selecionou.
  const mostrarAvisoGlobal = texto => {
    const aviso = document.getElementById('feedback-toast');
    if (!aviso) {
      window.alert(texto);
      return;
    }
    aviso.textContent = texto;
    aviso.hidden = false;
    window.clearTimeout(mostrarAvisoGlobal.timer);
    mostrarAvisoGlobal.timer = window.setTimeout(() => {
      aviso.hidden = true;
    }, 6000);
  };

  const csrfGlobal = document.querySelector('input[name="csrf"]')?.value || '';
  const modoUi = () => (document.body?.classList?.contains('ui-app') ? 'app' : 'classic');
  const abaAtiva = () => (document.querySelector('.os-tab.active')?.textContent || '')
    .replace(/\s+/g, ' ').trim().replace(/^\d+\s*/, '');
  const registrarUi = (aba = abaAtiva()) => {
    if (!csrfGlobal || typeof FormData === 'undefined'
        || !document.getElementById('dialogo-feedback')) return;
    const corpo = new FormData();
    corpo.append('csrf', csrfGlobal);
    corpo.append('pagina', location.pathname || '/');
    corpo.append('ui_mode', modoUi());
    corpo.append('aba', aba || '');
    try {
      if (navigator.sendBeacon) navigator.sendBeacon('/telemetria/ui', corpo);
      else fetch('/telemetria/ui', {
        method: 'POST', body: corpo, credentials: 'same-origin'
      }).catch(() => {});
    } catch (_erro) {}
  };

  document.querySelectorAll('form[data-ajax-preserve]').forEach(form => {
    form.addEventListener('submit', async evento => {
      if (evento.defaultPrevented || !window.fetch || !window.FormData) return;
      evento.preventDefault();
      const submitter = evento.submitter;
      const action = submitter?.getAttribute('formaction') || form.action;
      const method = (submitter?.getAttribute('formmethod') || form.method || 'post').toUpperCase();
      const dados = new FormData(form);
      if (submitter?.name && !dados.has(submitter.name)) {
        dados.append(submitter.name, submitter.value);
      }
      const textoOriginal = submitter?.textContent;
      if (submitter) {
        submitter.disabled = true;
        submitter.textContent = document.body.classList.contains('ui-app') ? 'Salvando…' : 'SALVANDO...';
      }
      try {
        const resposta = await fetch(action, {
          method,
          body: dados,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
          },
          credentials: 'same-origin'
        });
        if (resposta.redirected) {
          window.location.assign(resposta.url);
          return;
        }
        if (!resposta.ok) {
          let mensagem = 'Não foi possível salvar.';
          try {
            const corpo = await resposta.json();
            mensagem = corpo.error || corpo.message || mensagem;
          } catch (_erro) {}
          throw new Error(mensagem);
        }
        // Sucesso sem redirecionamento (ex.: rascunho salvo): recarrega a OS.
        window.location.reload();
      } catch (erro) {
        mostrarAvisoGlobal(erro.message || 'Não foi possível salvar. Tente novamente.');
        if (submitter) {
          submitter.disabled = false;
          submitter.textContent = textoOriginal || 'Salvar';
        }
      }
    });
  });

  const form = document.getElementById('form-os');
  if (form) {

    // REV08: preservar campos técnicos do formulário no upload YAML e desfazer
    // após a prévia, sem tocar no SQLite. O armazenamento fica limitado à aba.
    // Fotos de input[type=file] não podem ser restauradas pelo navegador.
    const uploadYAML = document.querySelector('form[action$="/yaml"] input[type="file"][name="yaml"]');
    const botaoDesfazerYAML = document.getElementById('desfazer-yaml-rev08');
    const sinalYAML = document.getElementById('yaml-importado-rev08');
    const erroYAML = document.getElementById('yaml-erro-rev08');
    if (form.id === 'form-os') {
      const matchOS = form.getAttribute('action')?.match(/^\/os\/(\d+)\/salvar$/);
      if (matchOS) {
        const chave = 'autoseg:rev08:yaml:' + matchOS[1];
        const campos = [
          'v9_diagnostico','v9_execucao','v9_resultado','relatorio_tecnico',
          'valor_mao_obra','valor_materiais_manual','valor_total_override',
          'forma_pagamento','tecnico','motivo_encerramento','acao_status'
        ];
        const linhas = document.getElementById('lista-materiais');
        const lerEstado = () => {
          const valores = {};
          for (const nome of campos) {
            if (form.elements[nome]) valores[nome] = String(form.elements[nome].value);
          }
          const materiais = [];
          linhas?.querySelectorAll('.material-row').forEach(row => {
            const ler = nome => row.querySelector('[name="'+nome+'"]')?.value || '';
            materiais.push({item:ler('material_item[]'),qtd:ler('material_qtd[]'),
                            unidade:ler('material_unidade[]'),unit:ler('material_unit[]')});
          });
          return {valores,materiais};
        };
        const colocarEstado = estado => {
          if (!estado || !estado.valores || !Array.isArray(estado.materiais)) return;
          for (const [nome,valor] of Object.entries(estado.valores)) {
            if (campos.includes(nome) && form.elements[nome]) form.elements[nome].value = valor;
          }
          if (linhas) {
            linhas.replaceChildren();
            const template = document.getElementById('modelo-material');
            for (const m of estado.materiais.slice(0,100)) {
              const row = template?.content?.firstElementChild?.cloneNode(true);
              if (!row) continue;
              row.querySelector('[name="material_item[]"]').value = m.item;
              row.querySelector('[name="material_qtd[]"]').value = m.qtd;
              const unidade = row.querySelector('[name="material_unidade[]"]');
              if (unidade) unidade.value = m.unidade || '';
              row.querySelector('[name="material_unit[]"]').value = m.unit;
              linhas.appendChild(row);
            }
          }
          form.dispatchEvent(new Event('input',{bubbles:true}));
        };
        if (uploadYAML) {
          uploadYAML.closest('form')?.addEventListener('submit', e => {
            const selecionadas = document.getElementById('fotos-relatorio')?.files?.length || 0;
            if (selecionadas && !window.confirm('Fotos ainda não enviadas não são recuperadas após importar YAML. Continuar?')) {
              e.preventDefault();return;
            }
            try {
              sessionStorage.setItem(chave, JSON.stringify({
                estado:lerEstado(),
                substituir:!!uploadYAML.closest('form')?.querySelector('[name="substituir"]:checked'),
                pendente:true
              }));
            } catch (_erro) {window.alert('Não foi possível preservar a prévia. Salve o texto antes de importar.'); e.preventDefault();}
          });
        }
        if (sinalYAML || erroYAML) {
          let backup = null;
          try {backup = JSON.parse(sessionStorage.getItem(chave) || 'null');} catch (_erro) {}
          if (backup?.pendente && backup.estado) {
            if (sinalYAML) {
              const importado = lerEstado();
              colocarEstado(backup.estado);
              for (const nome of ['v9_diagnostico','v9_execucao','v9_resultado','relatorio_tecnico']) {
                const antigo = backup.estado.valores[nome] || '';
                const valorYAML = importado.valores[nome] || '';
                if (valorYAML && (backup.substituir || !antigo.trim()) && form.elements[nome]) {
                  form.elements[nome].value = valorYAML;
                }
              }
              if (importado.materiais.length && (backup.substituir || !backup.estado.materiais.length)) {
                const estadoNovo = lerEstado();
                estadoNovo.materiais = importado.materiais;
                colocarEstado(estadoNovo);
              }
              window.dispatchEvent(new Event('autoseg-yaml-rev08'));
              backup.pendente=false;
              sessionStorage.setItem(chave,JSON.stringify(backup));
            } else {
              colocarEstado(backup.estado);
              sessionStorage.removeItem(chave);
            }
          }
        }
        botaoDesfazerYAML?.addEventListener('click',()=>{
          let backup=null;
          try {backup=JSON.parse(sessionStorage.getItem(chave)||'null');} catch (_erro) {}
          if (!backup?.estado) return window.alert('Não há versão anterior disponível nesta aba.');
          if (!window.confirm('Restaurar os campos anteriores à importação? Alterações feitas depois da prévia serão descartadas.'))return;
          colocarEstado(backup.estado);
          sessionStorage.removeItem(chave);
          botaoDesfazerYAML.disabled=true;
          if (sinalYAML) sinalYAML.textContent='Importação desfeita nesta aba. Confira o formulário.';
        });
        form.addEventListener('submit',()=>{sessionStorage.removeItem(chave);});
      }
    }

    const container = document.getElementById('lista-materiais');
    const add = document.getElementById('adicionar-material');
    const modeloMaterial = document.getElementById('modelo-material');
    const total = document.getElementById('total-previsto');
    const composicaoPreview = document.getElementById('composicao-prevista');
    const aplicarComposicao = form.querySelector('[name="aplicar_composicao"]');
    let timerComposicao = null;
    function number(v) {
      let x = String(v || '').trim().replace(/R\$/g, '').replace(/\s/g, '');
      if (x.includes(',')) x = x.replace(/\./g, '').replace(',', '.');
      return Number(x) || 0;
    }
    function brl(v) {
      return Number(v || 0).toLocaleString('pt-BR', {style:'currency',currency:'BRL'});
    }
    function valoresBase() {
      const labour = number(form.elements['valor_mao_obra'].value);
      let material = 0, hasMaterial = false;
      container.querySelectorAll('.material-row').forEach(row => {
        const item = row.querySelector('[name="material_item[]"]');
        const qtd = row.querySelector('[name="material_qtd[]"]');
        const unit = row.querySelector('[name="material_unit[]"]');
        if (item && item.value.trim()) {
          hasMaterial = true;
          const quantidade = String(qtd?.value || '').trim();
          material += (quantidade === '' ? 1 : number(quantidade)) * number(unit?.value);
        }
      });
      if (!hasMaterial) material = number(form.elements['valor_materiais_manual'].value);
      const negociado = String(form.elements['valor_total_override'].value).trim();
      return {labour, material, negociado, cost: negociado ? number(negociado) : labour + material};
    }
    function limparComposicao() {
      if (composicaoPreview) composicaoPreview.replaceChildren();
    }
    async function atualizarComposicao() {
      if (!total || !composicaoPreview || !aplicarComposicao || !aplicarComposicao.checked) {
        limparComposicao();
        return;
      }
      const base = valoresBase();
      const params = new URLSearchParams({
        materiais: base.material.toFixed(2),
        mao_obra: base.labour.toFixed(2),
        total: base.negociado || '',
        base: form.elements['base_percentuais']?.value || 'total'
      });
      try {
        const resposta = await fetch('/composicao/simular?' + params.toString(), {
          headers: {'Accept':'application/json'},
          credentials: 'same-origin'
        });
        let dados = {};
        try { dados = await resposta.json(); } catch (_erro) {}
        if (!resposta.ok || !dados.ok) throw new Error(dados.error || 'Composição indisponível.');
        total.textContent = brl(dados.total_centavos / 100);
        composicaoPreview.replaceChildren();
        for (const item of (dados.componentes || [])) {
          const linha = document.createElement('span');
          const nome = document.createElement('b');
          nome.textContent = item.nome;
          linha.append(nome, ' ' + brl(item.valor_centavos / 100));
          composicaoPreview.appendChild(linha);
          for (const filho of (item.filhos || [])) {
            const detalhe = document.createElement('span');
            detalhe.className = 'filho';
            const nomeFilho = document.createElement('b');
            nomeFilho.textContent = filho.nome;
            detalhe.append('— ', nomeFilho, ' ' + brl(filho.valor_centavos / 100));
            composicaoPreview.appendChild(detalhe);
          }
        }
        if (dados.aviso) {
          const aviso = document.createElement('span');
          aviso.className = 'aviso';
          aviso.textContent = dados.aviso;
          composicaoPreview.appendChild(aviso);
        }
      } catch (erro) {
        limparComposicao();
        const aviso = document.createElement('span');
        aviso.className = 'aviso';
        aviso.textContent = erro.message || 'Não foi possível calcular a composição agora.';
        composicaoPreview.appendChild(aviso);
      }
    }
    function recalc() {
      if (!total) return;
      const base = valoresBase();
      total.textContent = brl(base.cost);
      if (timerComposicao) window.clearTimeout(timerComposicao);
      if (aplicarComposicao && aplicarComposicao.checked) {
        timerComposicao = window.setTimeout(atualizarComposicao, 250);
      } else {
        limparComposicao();
      }
    }
    if (add && container) {
      add.addEventListener('click', () => {
        if (container.querySelectorAll('.material-row').length >= 100) {
          window.alert('Limite de 100 materiais por OS.');
          return;
        }
        if (!modeloMaterial || !modeloMaterial.content) return;
        const clone = modeloMaterial.content.firstElementChild.cloneNode(true);
        clone.querySelectorAll('input').forEach(input => {input.value = '';input.removeAttribute('id');});
        clone.querySelectorAll('label').forEach(label => label.removeAttribute('for'));
        container.appendChild(clone);
        const primeiro = clone.querySelector('input');
        if (primeiro) primeiro.focus();
        recalc();
      });
      container.addEventListener('click', e => {
        if (e.target.closest('.remover-material')) {
          const row = e.target.closest('.material-row');
          if (row) row.remove();
          recalc();
        }
      });
      form.addEventListener('input', recalc);
      if (aplicarComposicao) aplicarComposicao.addEventListener('change', recalc);
      form.querySelector('[name="base_percentuais"]')?.addEventListener('change', recalc);
      recalc();
    }
    // Fotos: prévia + legenda individual + chave estável por arquivo.
    // A chave viaja junto com o arquivo para o servidor não duplicar fotos no rascunho.
    const campoFotos = document.getElementById('fotos-relatorio');
    const listaFotos = document.getElementById('lista-fotos-selecionadas');
    const limparFotos = document.getElementById('limpar-fotos');
    const chavesFotos = new Map();
    const legendasFotos = new Map();
    const urlsPreview = [];
    const chaveDoArquivo = (foto) => `${foto.name}|${foto.size}|${foto.lastModified}`;
    const novaChave = () => (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID() : `foto-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    if (campoFotos && listaFotos) {
      const mostrarFotos = () => {
        urlsPreview.splice(0).forEach(url => URL.revokeObjectURL(url));
        listaFotos.replaceChildren();
        const fotos = Array.from(campoFotos.files || []);
        let invalida = false;
        if (!fotos.length) {
          const vazio = document.createElement('p');
          vazio.className = 'muted';
          vazio.textContent = 'Nenhuma foto nova selecionada.';
          listaFotos.appendChild(vazio);
        }
        fotos.forEach((foto, i) => {
          const idArquivo = chaveDoArquivo(foto);
          if (!chavesFotos.has(idArquivo)) chavesFotos.set(idArquivo, novaChave());
          const chave = chavesFotos.get(idArquivo);
          const linha = document.createElement('div');
          linha.className = 'foto-selecionada';
          linha.dataset.chave = chave;
          linha.style.cssText = 'display:grid;grid-template-columns:120px 1fr;gap:12px;border:1px solid #3b3b3b;padding:10px;margin:10px 0;border-radius:8px';
          const preview = document.createElement('img');
          const url = URL.createObjectURL(foto);
          urlsPreview.push(url);
          preview.src = url;
          preview.alt = `Prévia de ${foto.name}`;
          preview.style.cssText = 'width:120px;height:90px;object-fit:cover;border-radius:6px';
          const direita = document.createElement('div');
          const nome = document.createElement('p');
          nome.style.margin = '0 0 6px';
          nome.textContent = `${foto.name} (${(foto.size/1024/1024).toFixed(1)} MB)`;
          const legenda = document.createElement('label');
          legenda.textContent = 'Legenda da foto';
          const entrada = document.createElement('input');
          entrada.type = 'text';
          entrada.name = 'foto_legenda[]';
          entrada.maxLength = 160;
          entrada.placeholder = 'Ex.: Antes do reparo, detalhe do componente...';
          entrada.value = legendasFotos.get(idArquivo) || '';
          entrada.addEventListener('input', () => legendasFotos.set(idArquivo, entrada.value));
          const ocultaChave = document.createElement('input');
          ocultaChave.type = 'hidden';
          ocultaChave.name = 'foto_chave[]';
          ocultaChave.value = chave;
          const ocultaVisivel = document.createElement('input');
          ocultaVisivel.type = 'hidden';
          ocultaVisivel.name = 'foto_visivel[]';
          ocultaVisivel.value = '1';
          const remover = document.createElement('button');
          remover.type = 'button';
          remover.className = 'secondary';
          remover.textContent = 'Remover foto';
          remover.setAttribute('aria-label', `Remover ${foto.name}`);
          remover.addEventListener('click', () => {
            try {
              const transfer = new DataTransfer();
              fotos.filter((_,j) => j !== i).forEach(f => transfer.items.add(f));
              campoFotos.files = transfer.files;
            } catch (_erro) {
              campoFotos.value = '';
            }
            mostrarFotos();
          });
          if (foto.size > 8 * 1024 * 1024) {
            invalida = true;
            const aviso = document.createElement('p');
            aviso.className = 'bad';
            aviso.textContent = 'Esta foto ultrapassa 8 MB e não pode ser enviada.';
            direita.append(nome, aviso);
          } else {
            direita.append(nome);
          }
          direita.append(legenda, entrada, ocultaChave, ocultaVisivel, remover);
          linha.append(preview, direita);
          listaFotos.appendChild(linha);
        });
        campoFotos.setCustomValidity(invalida ? 'Remova as fotos maiores que 8 MB.' : '');
        if (limparFotos) limparFotos.hidden = !fotos.length;
      };
      campoFotos.addEventListener('change', mostrarFotos);
      document.getElementById('adicionar-mais-fotos')?.addEventListener('click', () => campoFotos.click());
      if (limparFotos) limparFotos.addEventListener('click', () => {
        campoFotos.value = ''; chavesFotos.clear(); legendasFotos.clear(); mostrarFotos();
      });
      mostrarFotos();
    }
    const status = form.querySelector('[name="acao_status"]');
    const fotoBox = document.getElementById('anexo-encerramento');
    const motivo = form.querySelector('[name="motivo_encerramento"]');
    const rateioBox = document.getElementById('rateio-conclusao');
    const relato = form.querySelector('[name="relatorio_tecnico"]');
    function atualizarEncerramento() {
      if (!status) return;
      if (fotoBox) fotoBox.hidden = false;
      if (motivo) motivo.required = status.value === 'Cancelada';
      if (rateioBox) rateioBox.hidden = status.value !== 'Concluída';
    }
    if (status) {status.addEventListener('change', atualizarEncerramento); atualizarEncerramento();}
    const irParaCampo = campo => {
      if (!campo) return;
      const painel = campo.closest('fieldset.os-panel');
      if (painel) {
        const indice = Array.from(form.querySelectorAll('#form-os > fieldset')).indexOf(painel);
        const abas = document.querySelectorAll('.os-tabs .os-tab');
        if (indice >= 0 && abas[indice]) abas[indice].click();
      }
      window.setTimeout(() => {
        try { campo.focus({preventScroll:false}); } catch (_erro) {}
      }, 0);
    };

    const primeiroInvalido = () => {
      for (const campo of form.elements) {
        if (!campo.willValidate || campo.disabled || campo.type === 'hidden') continue;
        if (!campo.checkValidity()) return campo;
      }
      return null;
    };

    const nomeDoCampo = campo => {
      const rotulo = campo.labels && campo.labels[0];
      return (rotulo?.textContent || campo.name || 'campo obrigatório').replace(/\s+/g,' ').trim();
    };

    // Captura antes do envio AJAX: revela a aba do campo inválido e evita
    // que o navegador bloqueie o envio com um campo escondido.
    form.addEventListener('submit', e => {
      const botao = e.submitter;
      if (botao && botao.hasAttribute('formnovalidate')) return;
      const invalido = primeiroInvalido();
      if (invalido) {
        e.preventDefault();
        e.stopImmediatePropagation();
        irParaCampo(invalido);
        mostrarAvisoGlobal('Preencha: ' + nomeDoCampo(invalido));
        return;
      }
      if (!botao || botao.value !== 'encerrar') return;
      if (!status || !status.value) {
        e.preventDefault();e.stopImmediatePropagation();
        irParaCampo(status);
        mostrarAvisoGlobal('Selecione a situação do atendimento.');
        return;
      }
      const executado = form.querySelector('[name="v9_execucao"]');
      if (relato && !relato.value.trim() && !(executado && executado.value.trim())) {
        e.preventDefault();e.stopImmediatePropagation();
        irParaCampo(relato);
        mostrarAvisoGlobal('Preencha o relatório técnico antes de confirmar.');
        return;
      }
      if (status.value === 'Cancelada' && motivo && !motivo.value.trim()) {
        e.preventDefault();e.stopImmediatePropagation();
        irParaCampo(motivo);
        mostrarAvisoGlobal('Informe o motivo do cancelamento.');
        return;
      }
      const encerrada = status.value !== 'Pendente';
      if (!window.confirm(encerrada
        ? 'Confirmar OS como '+status.value+'? O relatório PDF será publicado e ficará disponível ao cliente.'
        : 'Confirmar OS pendente? Ela continuará visível aos prestadores e ainda não terá PDF final.')) {
        e.preventDefault();e.stopImmediatePropagation();
      }
    }, true);
  }
  // Catálogo: linhas visuais em lugar do campo "Nome | Qtd | Valor".
  const formServ = document.getElementById('form-servico');
  if (formServ) {
    const lista = document.getElementById('lista-materiais-servico');
    const modelo = document.getElementById('modelo-material-servico');
    const add = document.getElementById('adicionar-material-servico');
    if (lista && modelo && add) {
      add.addEventListener('click', () => {
        if (lista.querySelectorAll('.material-row').length >= 30) return window.alert('Máximo de 30 materiais por serviço.');
        const row = modelo.content.firstElementChild.cloneNode(true);
        lista.appendChild(row);
        row.querySelector('input')?.focus();
      });
      lista.addEventListener('click',e=>{
        const remover=e.target.closest('.remover-material-servico');
        if (remover) remover.closest('.material-row')?.remove();
      });
    }
  }
  // Adiciona material cadastrado na OS sem revelar saldos ou custo do estoque.
  const botaoEstoque=document.getElementById('adicionar-do-estoque');
  if (form && botaoEstoque) {
    botaoEstoque.addEventListener('click',()=>{
      try {
        const dados=JSON.parse(document.getElementById('produtos-estoque-os').textContent);
        const indice=Number(document.getElementById('material-estoque-selecionar').value);
        const produto=dados[indice];
        const lista=document.getElementById('lista-materiais');
        const modelo=document.getElementById('modelo-material');
        if (!produto || !lista || !modelo)return;
        if (lista.querySelectorAll('.material-row').length>=100)return window.alert('Máximo de 100 materiais por OS.');
        const linha=modelo.content.firstElementChild.cloneNode(true);
        linha.querySelector('[name="material_item[]"]').value=produto.nome;
        linha.querySelector('[name="material_qtd[]"]').value='1';
        const unidade = linha.querySelector('[name="material_unidade[]"]');
        if (unidade) unidade.value='un';
        linha.querySelector('[name="material_unit[]"]').value=Number(produto.valor).toFixed(2).replace('.',',');
        lista.appendChild(linha);
        form.querySelector('[name="valor_mao_obra"]').dispatchEvent(new Event('input',{bubbles:true}));
      } catch (_erro) { window.alert('Não foi possível selecionar este produto.'); }
    });
  }
  // Busca em todas as tabelas exibidas no Portal do Prestador.
  // Não promete pesquisar registros além da página carregada.
  document.querySelectorAll('.table-scroll').forEach((area,indice) => {
    const tabela = area.querySelector('table');
    if (!tabela) return;
    const linhas = Array.from(tabela.querySelectorAll('tbody tr'));
    if (!linhas.length) return;
    const modoApp = document.body.classList.contains('ui-app');
    const titulo = document.createElement('label');
    titulo.className = 'table-filter-label';
    titulo.textContent = 'Filtrar registros exibidos';
    titulo.setAttribute('for',`busca-tabela-${indice}`);
    const busca = document.createElement('input');
    busca.type = 'search';
    busca.className = 'table-filter-input';
    busca.id = `busca-tabela-${indice}`;
    busca.placeholder = modoApp
      ? 'Buscar na tabela'
      : 'Digite nome, OS, situação ou outro dado da tabela';
    const aviso = document.createElement('small');
    aviso.className = 'table-filter-count';
    aviso.setAttribute('aria-live','polite');
    const filtrar = () => {
      const termo = busca.value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
      let exibidas = 0;
      for (const linha of linhas) {
        const texto = linha.textContent.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
        linha.hidden = !texto.includes(termo);
        if (!linha.hidden) exibidas += 1;
      }
      aviso.textContent = modoApp
        ? `${exibidas} de ${linhas.length} registros`
        : `${exibidas} de ${linhas.length} registro(s) carregados nesta página`;
    };
    busca.addEventListener('input',filtrar);
    area.before(titulo,busca,aviso);
    filtrar();
  });
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit',e => {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });
  document.querySelectorAll('button[data-confirm]').forEach(botao => {
    botao.addEventListener('click', evento => {
      if (!window.confirm(botao.getAttribute('data-confirm'))) {
        evento.preventDefault();
        evento.stopImmediatePropagation();
      }
    });
  });

  // Máscaras visuais de documentos, sem alterar a validação do servidor.
  function mascaraDocumento(valor) {
    const d = String(valor || '').replace(/\D/g, '').slice(0,14);
    if (d.length > 11) return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{0,2}).*/, '$1.$2.$3/$4-$5').replace(/-$/, '');
    if (d.length > 3) return d.replace(/^(\d{3})(\d{0,3})(\d{0,3})(\d{0,2}).*/, (_,a,b,c,e) => a+(b?'.'+b:'')+(c?'.'+c:'')+(e?'-'+e:''));
    return d;
  }
  document.querySelectorAll('input[name="documento"],input[name="cpf"],input[name="cnpj"]').forEach(el => {
    if (el.type === 'hidden') return;
    el.value = mascaraDocumento(el.value);
    el.setAttribute('inputmode','numeric');
    el.addEventListener('input', () => { el.value = mascaraDocumento(el.value); });
  });
  const aplicar = document.getElementById('aplicar-modelo-servico');
  const catalogoJson = document.getElementById('catalogo-os-json');
  if (aplicar && catalogoJson && form) {
    aplicar.addEventListener('click', () => {
      const select = document.getElementById('c_modelo_servico_id');
      const modelos = JSON.parse(catalogoJson.textContent || '[]');
      const item = modelos.find(x => String(x.id) === String(select?.value));
      if (!item) return;
      const preco = form.elements['valor_mao_obra'];
      if (preco) preco.value = item.preco.replace('.',',');
      const relatorio = form.elements['v9_execucao'];
      if (relatorio && item.relatorio) {
        if (relatorio.value.trim() && !window.confirm('Substituir o texto atual do relatório pelo modelo?')) return;
        relatorio.value = item.relatorio;
      }
      const linhas = document.getElementById('lista-materiais');
      const template = document.getElementById('modelo-material');
      if (linhas && template && item.materiais.length) {
        if (linhas.children.length && !window.confirm('Adicionar os materiais do modelo aos materiais existentes?')) return;
        for (const material of item.materiais) {
          const clone = template.content.firstElementChild.cloneNode(true);
          clone.querySelector('[name="material_item[]"]').value = material.nome;
          clone.querySelector('[name="material_qtd[]"]').value = material.quantidade;
          clone.querySelector('[name="material_unit[]"]').value = String(material.preco_centavos / 100).replace('.',',');
          linhas.appendChild(clone);
        }
      }
      form.dispatchEvent(new Event('input',{bubbles:true}));
    });
  }

  // Busca local de cliente: funciona no formulário de OS e no orçamento.
  const campoBuscaCliente = document.getElementById('busca-cliente-os');
  if (campoBuscaCliente) {
    const formCliente = campoBuscaCliente.closest('form');
    const seletorCliente = formCliente?.querySelector('select[name="cliente_id"]');
    if (seletorCliente) {
      const opcoesCliente = Array.from(seletorCliente.options)
        .map(o => ({valor:o.value, nome:o.textContent}));
      campoBuscaCliente.addEventListener('input', () => {
        const termo = campoBuscaCliente.value.normalize('NFD')
          .replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
        const selecionado = seletorCliente.value;
        seletorCliente.replaceChildren();
        const candidatos = opcoesCliente.filter(x => x.nome.normalize('NFD')
          .replace(/[\u0300-\u036f]/g,'').toLowerCase().includes(termo));
        for (const o of candidatos) seletorCliente.add(new Option(o.nome, o.valor));
        if (candidatos.some(o => o.valor === selecionado)) seletorCliente.value = selecionado;
        else seletorCliente.selectedIndex = -1;
        if (!candidatos.length) campoBuscaCliente.setCustomValidity('Nenhum cliente encontrado. Limpe a busca.');
        else campoBuscaCliente.setCustomValidity('');
      });
    }
  }

  // Orçamento: linhas dinâmicas de serviços e materiais adicionais.
  const totalOrcamento = document.getElementById('total-orcamento');
  const atualizarTotalOrcamento = () => {
    if (!totalOrcamento) return;
    let totalCentavos = 0;
    document.querySelectorAll('#lista-servicos-orcamento .orcamento-servico-row').forEach(row => {
      const select = row.querySelector('select[name="servico_id[]"]');
      const qtd = row.querySelector('input[name="servico_qtd[]"]');
      const opcao = select?.selectedOptions?.[0];
      const unitario = Number(opcao?.dataset?.unitarioCentavos || 0);
      const quantidade = Number(String(qtd?.value || '0').replace(',','.'));
      if (select?.value && quantidade > 0) totalCentavos += unitario * quantidade;
    });
    document.querySelectorAll('#lista-materiais-orcamento .orcamento-material-row').forEach(row => {
      const select = row.querySelector('select[name="material_id[]"]');
      const qtd = row.querySelector('input[name="material_qtd[]"]');
      const opcao = select?.selectedOptions?.[0];
      const unitario = Number(opcao?.dataset?.unitarioCentavos || 0);
      const quantidade = Number(String(qtd?.value || '0').replace(',','.'));
      if (select?.value && quantidade > 0) totalCentavos += unitario * quantidade;
    });
    totalOrcamento.textContent = (totalCentavos / 100).toLocaleString('pt-BR', {
      style:'currency', currency:'BRL'
    });
  };
  const configurarLinhasOrcamento = (lista, modelo, adicionar, classeLinha,
                                     classeRemover, maximo, mensagem) => {
    if (!lista || !modelo || !adicionar) return;
    adicionar.addEventListener('click', () => {
      if (lista.querySelectorAll('.' + classeLinha).length >= maximo) {
        window.alert(mensagem);
        return;
      }
      const clone = modelo.content.firstElementChild.cloneNode(true);
      lista.appendChild(clone);
      clone.querySelector('select,input')?.focus();
      atualizarTotalOrcamento();
    });
    lista.addEventListener('click', evento => {
      const remover = evento.target.closest('.' + classeRemover);
      if (!remover) return;
      remover.closest('.' + classeLinha)?.remove();
      atualizarTotalOrcamento();
    });
    lista.addEventListener('input', atualizarTotalOrcamento);
    lista.addEventListener('change', atualizarTotalOrcamento);
    atualizarTotalOrcamento();
  };
  configurarLinhasOrcamento(
    document.getElementById('lista-servicos-orcamento'),
    document.getElementById('modelo-servico-orcamento'),
    document.getElementById('adicionar-servico-orcamento'),
    'orcamento-servico-row', 'remover-servico-orcamento', 20,
    'Limite de 20 serviços por orçamento.');
  configurarLinhasOrcamento(
    document.getElementById('lista-materiais-orcamento'),
    document.getElementById('modelo-material-orcamento'),
    document.getElementById('adicionar-material-orcamento'),
    'orcamento-material-row', 'remover-material-orcamento', 50,
    'Limite de 50 materiais adicionais por orçamento.');

  // Controlled auto-refresh: the server emits an inert meta marker instead of
  // http-equiv="refresh". The timer is paused while a form control is focused,
  // a dialog is open or the tab is hidden, so typing is never discarded.
  const metaAutoRefresh = document.querySelector('meta[name="autoseg-auto-refresh"]');
  const dialogoFeedback = document.getElementById('dialogo-feedback');
  let timerAutoRefresh = null;
  const campoEmUso = () => {
    const ativo = document.activeElement;
    return !!ativo && /^(INPUT|TEXTAREA|SELECT)$/.test(ativo.tagName);
  };
  const dialogoAberto = () => {
    if (!dialogoFeedback) return false;
    return typeof dialogoFeedback.open === 'boolean'
      ? dialogoFeedback.open
      : dialogoFeedback.hasAttribute('open');
  };
  const podeAtualizarPagina = () => document.visibilityState !== 'hidden'
    && !dialogoAberto()
    && !campoEmUso();
  const pausarAutoRefresh = () => {
    if (timerAutoRefresh !== null) window.clearTimeout(timerAutoRefresh);
    timerAutoRefresh = null;
  };
  const agendarAutoRefresh = () => {
    pausarAutoRefresh();
    if (!metaAutoRefresh || !podeAtualizarPagina()) return;
    const segundos = Math.max(5, Number(metaAutoRefresh.getAttribute('content')) || 20);
    timerAutoRefresh = window.setTimeout(() => {
      timerAutoRefresh = null;
      if (podeAtualizarPagina()) window.location.reload();
      else agendarAutoRefresh();
    }, segundos * 1000);
  };
  if (metaAutoRefresh) {
    document.addEventListener('visibilitychange', agendarAutoRefresh);
    document.addEventListener('focusin', pausarAutoRefresh);
    document.addEventListener('focusout', () => window.setTimeout(agendarAutoRefresh, 0));
    document.addEventListener('submit', pausarAutoRefresh, true);
    window.addEventListener('pagehide', pausarAutoRefresh);
    agendarAutoRefresh();
  }

  // A draft save can take a moment on a busy SQLite database. Pause the
  // refresh and show progress so the page does not look frozen or reload
  // before the POST completes.
  document.addEventListener('submit', evento => {
    pausarAutoRefresh();
    const botao = evento.submitter;
    if (!botao) return;
    const acao = botao.getAttribute('formaction') || '';
    if (!/\/rascunho\/salvar$/.test(acao)) return;
    window.setTimeout(() => {
      botao.disabled = true;
      botao.textContent = 'SALVANDO...';
    }, 0);
  }, true);

  // Feedback do Portal do Prestador: diálogo global, sem sair da página.
  const abrirFeedback = document.getElementById('abrir-feedback');
  if (dialogoFeedback && abrirFeedback) {
    const formFeedback = document.getElementById('form-feedback');
    const paginaFeedback = document.getElementById('feedback-pagina');
    const mensagemFeedback = document.getElementById('feedback-mensagem');
    const fecharFeedback = document.getElementById('fechar-feedback');
    const responderIaFeedback = document.getElementById('feedback-responder-ia');
    const csrfFeedback = formFeedback?.querySelector('input[name="csrf"]');
    const idRascunho = document.getElementById('feedback-rascunho-id');
    const uiModeFeedback = document.getElementById('feedback-ui-mode');
    const abaFeedback = document.getElementById('feedback-aba');
    const diagnosticoFeedback = document.getElementById('feedback-diagnostico');
    const coletarDiagnostico = () => {
      if (!diagnosticoFeedback) return;
      const total = document.getElementById('total-previsto');
      const composicao = document.getElementById('composicao-prevista');
      const retangulo = elemento => {
        if (!elemento) return null;
        const r = elemento.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height)};
      };
      try {
        diagnosticoFeedback.value = JSON.stringify({
          path: location.pathname,
          ui_mode: modoUi(),
          aba: abaAtiva(),
          viewport: {w: innerWidth, h: innerHeight, dpr: devicePixelRatio},
          scroll: {x: scrollX, y: scrollY},
          total_previsto: total?.textContent || '',
          total_rect: retangulo(total),
          composicao_rect: retangulo(composicao),
          composicao_texto: (composicao?.innerText || '').slice(0, 2000),
          texto_principal: (document.querySelector('main')?.innerText || '').slice(0, 2500)
        });
      } catch (_erro) {}
    };
    const CHAVE_RASCUNHO = 'autoseg:feedback:draft:v1';
    const CHAVE_ENVIADO = 'autoseg:feedback:submitted:v1';
    const RASCUNHO_VALIDO_MS = 10 * 60 * 1000;
    let timerRascunhoServidor = null;
    let descartarAoFechar = false;
    const corpoRascunhoServidor = () => {
      if (typeof FormData === 'undefined') return null;
      const corpo = new FormData();
      if (csrfFeedback?.value) corpo.append('csrf', csrfFeedback.value);
      corpo.append('pagina', paginaFeedback?.value || location.pathname.slice(0, 300) || '/');
      corpo.append('mensagem', mensagemFeedback?.value || '');
      if (responderIaFeedback?.checked) corpo.append('responder_ia', '1');
      corpo.append('ui_mode', modoUi());
      corpo.append('aba', abaAtiva());
      corpo.append('diagnostico', diagnosticoFeedback?.value || '');
      if (idRascunho?.value) corpo.append('rascunho_id', idRascunho.value);
      return corpo;
    };
    const salvarRascunhoServidor = (beacon = false) => {
      if (!formFeedback || !mensagemFeedback) return;
      const corpo = corpoRascunhoServidor();
      if (!corpo) return;
      try {
        if (beacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
          navigator.sendBeacon('/feedback/rascunho', corpo);
          return;
        }
        if (typeof fetch === 'undefined') return;
        fetch('/feedback/rascunho', {
          method: 'POST',
          body: corpo,
          credentials: 'same-origin',
          keepalive: !!beacon
        }).then(resposta => resposta.ok ? resposta.json() : null)
          .then(dados => {
            if (dados && dados.id && idRascunho) idRascunho.value = String(dados.id);
          }).catch(() => {});
      } catch (_erro) {}
    };
    const agendarRascunhoServidor = () => {
      if (typeof FormData === 'undefined') return;
      window.clearTimeout(timerRascunhoServidor);
      timerRascunhoServidor = window.setTimeout(() => salvarRascunhoServidor(false), 900);
    };
    const descartarRascunhoServidor = () => {
      if (!formFeedback) return;
      window.clearTimeout(timerRascunhoServidor);
      const corpo = corpoRascunhoServidor();
      if (!corpo || typeof fetch === 'undefined') return;
      fetch('/feedback/rascunho/descartar', {
        method: 'POST',
        body: corpo,
        credentials: 'same-origin',
        keepalive: true
      }).catch(() => {});
      if (idRascunho) idRascunho.value = '';
    };
    const limparRascunho = () => {
      try { sessionStorage.removeItem(CHAVE_RASCUNHO); } catch (_erro) {}
    };
    const lerRascunho = () => {
      try {
        const valor = JSON.parse(sessionStorage.getItem(CHAVE_RASCUNHO) || 'null');
        return valor && typeof valor === 'object' ? valor : null;
      } catch (_erro) {
        return null;
      }
    };
    const salvarRascunho = () => {
      if (!mensagemFeedback) return;
      const mensagem = mensagemFeedback.value.slice(0, 4000);
      const responderIa = !!responderIaFeedback?.checked;
      if (!mensagem && !responderIa) {
        limparRascunho();
        if (idRascunho) idRascunho.value = '';
        return;
      }
      try {
        sessionStorage.setItem(CHAVE_RASCUNHO, JSON.stringify({
          mensagem,
          responder_ia: responderIa,
          aberto: dialogoAberto(),
          atualizado_em: Date.now()
        }));
      } catch (_erro) {}
    };
    const marcarPagina = () => {
      if (paginaFeedback) paginaFeedback.value = location.pathname.slice(0, 300) || '/';
    };
    const abrirDialogo = () => {
      marcarPagina();
      if (uiModeFeedback) uiModeFeedback.value = modoUi();
      if (abaFeedback) abaFeedback.value = abaAtiva();
      coletarDiagnostico();
      if (typeof dialogoFeedback.showModal === 'function') {
        if (!dialogoFeedback.open) dialogoFeedback.showModal();
      } else {
        dialogoFeedback.setAttribute('open', '');
      }
      pausarAutoRefresh();
      mensagemFeedback?.focus();
      if (csrfFeedback?.value) {
        const corpo = new URLSearchParams({
          csrf: csrfFeedback.value,
          pagina: paginaFeedback?.value || location.pathname.slice(0, 300) || '/',
          ui_mode: modoUi(),
          aba: abaAtiva()
        });
        fetch('/feedback/aberto', {
          method: 'POST',
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: corpo,
          credentials: 'same-origin',
          keepalive: true
        }).catch(() => {});
      }
    };
    const fecharDialogo = () => {
      if (typeof dialogoFeedback.close === 'function') {
        dialogoFeedback.close();
      } else {
        dialogoFeedback.removeAttribute('open');
        salvarRascunho();
        window.setTimeout(agendarAutoRefresh, 0);
      }
    };

    // A draft survives reloads and navigation inside the same tab. It is only
    // discarded after a successful submit or an explicit cancel.
    try {
      if (sessionStorage.getItem(CHAVE_ENVIADO) === '1'
          && /^\/feedback\/\d+\/?$/.test(location.pathname)) {
        sessionStorage.removeItem(CHAVE_ENVIADO);
        limparRascunho();
      }
    } catch (_erro) {}
    const rascunho = lerRascunho();
    if (rascunho) {
      if (mensagemFeedback && typeof rascunho.mensagem === 'string') {
        mensagemFeedback.value = rascunho.mensagem.slice(0, 4000);
      }
      if (responderIaFeedback) responderIaFeedback.checked = !!rascunho.responder_ia;
      const recente = Number(rascunho.atualizado_em) > Date.now() - RASCUNHO_VALIDO_MS;
      if (rascunho.aberto && recente) abrirDialogo();
    }

    abrirFeedback.addEventListener('click', abrirDialogo);
    fecharFeedback?.addEventListener('click', () => {
      descartarAoFechar = true;
      descartarRascunhoServidor();
      if (mensagemFeedback) mensagemFeedback.value = '';
      if (responderIaFeedback) responderIaFeedback.checked = false;
      limparRascunho();
      try { sessionStorage.removeItem(CHAVE_ENVIADO); } catch (_erro) {}
      fecharDialogo();
    });
    dialogoFeedback.addEventListener('click', evento => {
      if (evento.target === dialogoFeedback) fecharDialogo();
    });
    dialogoFeedback.addEventListener('close', () => {
      if (descartarAoFechar) {
        descartarAoFechar = false;
      } else {
        salvarRascunho();
        salvarRascunhoServidor(true);
      }
      window.setTimeout(agendarAutoRefresh, 0);
    });
    mensagemFeedback?.addEventListener('input', () => {
      salvarRascunho();
      agendarRascunhoServidor();
    });
    responderIaFeedback?.addEventListener('change', () => {
      salvarRascunho();
      salvarRascunhoServidor(false);
    });
    window.addEventListener('pagehide', () => {
      salvarRascunho();
      salvarRascunhoServidor(true);
    });
    const mostrarAvisoFeedback = texto => {
      const aviso = document.getElementById('feedback-toast');
      if (!aviso) return;
      aviso.textContent = texto;
      aviso.hidden = false;
      window.clearTimeout(mostrarAvisoFeedback.timer);
      mostrarAvisoFeedback.timer = window.setTimeout(() => {
        aviso.hidden = true;
      }, 6000);
    };

    formFeedback?.addEventListener('submit', async evento => {
      const pediuIa = !!responderIaFeedback?.checked;
      const status = document.getElementById('feedback-envio-status');
      const enviar = formFeedback.querySelector('button[type="submit"]');
      const prepararEnvio = () => {
        if (status) {
          status.textContent = pediuIa
            ? 'Enviando feedback e aguardando a resposta da IA...'
            : 'Enviando feedback...';
        }
        if (enviar) {
          enviar.disabled = true;
          enviar.textContent = pediuIa ? 'Aguardando IA...' : 'Enviando...';
        }
      };

      // Navegadores antigos continuam usando o envio normal com confirmação.
      if (!window.fetch || !window.FormData) {
        try { sessionStorage.setItem(CHAVE_ENVIADO, '1'); } catch (_erro) {}
        prepararEnvio();
        return;
      }

      evento.preventDefault();
      if (formFeedback.dataset.enviando === '1') return;
      formFeedback.dataset.enviando = '1';
      coletarDiagnostico();
      prepararEnvio();
      try {
        const resposta = await fetch('/feedback', {
          method: 'POST',
          body: new FormData(formFeedback),
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
          },
          credentials: 'same-origin'
        });
        let dados = {};
        try { dados = await resposta.json(); } catch (_erro) {}
        if (!resposta.ok || !dados.ok) {
          throw new Error(dados.error || 'Não foi possível enviar o feedback.');
        }
        try {
          sessionStorage.removeItem(CHAVE_RASCUNHO);
          sessionStorage.removeItem(CHAVE_ENVIADO);
        } catch (_erro) {}
        window.clearTimeout(timerRascunhoServidor);
        formFeedback.reset();
        if (mensagemFeedback) mensagemFeedback.value = '';
        if (responderIaFeedback) responderIaFeedback.checked = false;
        if (idRascunho) idRascunho.value = '';
        if (enviar) {
          enviar.disabled = false;
          enviar.textContent = 'Enviar feedback';
        }
        if (status) status.textContent = '';
        descartarAoFechar = true;
        fecharDialogo();
        const numero = String(dados.id || '').padStart(4, '0');
        mostrarAvisoFeedback(dados.ia_status === 'ok'
          ? `Feedback FB-${numero} enviado. A resposta da IA foi registrada em Feedbacks.`
          : `Feedback FB-${numero} enviado. Obrigado!`);
      } catch (erro) {
        if (status) {
          status.textContent = erro.message || 'Não foi possível enviar. Tente novamente.';
        }
        if (enviar) {
          enviar.disabled = false;
          enviar.textContent = 'Enviar feedback';
        }
      } finally {
        delete formFeedback.dataset.enviando;
      }
    });
  }

  // Cancelamento de OS: motivo em duas etapas e confirmação pelo número.
  const dialogoCancelar = document.getElementById('dialogo-cancelar-os');
  const abrirCancelar = document.getElementById('abrir-cancelar-os');
  if (dialogoCancelar && abrirCancelar) {
    const passos = Array.from(dialogoCancelar.querySelectorAll('.cancel-step'));
    const motivoCancelar = document.getElementById('cancelar-motivo');
    const confirmarNumero = document.getElementById('confirmar-numero-os');
    const erroCancelar = document.getElementById('cancelar-erro');
    const mostrarPasso = numero => {
      passos.forEach(passo => {
        passo.hidden = passo.dataset.step !== String(numero);
      });
    };
    const limparCancelar = () => {
      if (motivoCancelar) motivoCancelar.value = '';
      if (confirmarNumero) confirmarNumero.value = '';
      if (erroCancelar) {
        erroCancelar.hidden = true;
        erroCancelar.textContent = '';
      }
      mostrarPasso(1);
    };
    const fecharCancelar = () => {
      if (typeof dialogoCancelar.close === 'function') dialogoCancelar.close();
      else dialogoCancelar.removeAttribute('open');
    };
    abrirCancelar.addEventListener('click', () => {
      limparCancelar();
      if (typeof dialogoCancelar.showModal === 'function') {
        if (!dialogoCancelar.open) dialogoCancelar.showModal();
      } else {
        dialogoCancelar.setAttribute('open', '');
      }
      motivoCancelar?.focus();
    });
    dialogoCancelar.querySelector('[data-fechar-cancelar]')?.addEventListener('click', fecharCancelar);
    dialogoCancelar.querySelector('[data-proximo-cancelar]')?.addEventListener('click', () => {
      if (!(motivoCancelar?.value || '').trim()) {
        mostrarAvisoGlobal('Descreva o motivo do cancelamento antes de continuar.');
        motivoCancelar?.focus();
        return;
      }
      if (erroCancelar) erroCancelar.hidden = true;
      mostrarPasso(2);
      confirmarNumero?.focus();
    });
    dialogoCancelar.querySelector('[data-voltar-cancelar]')?.addEventListener('click', () => {
      mostrarPasso(1);
      motivoCancelar?.focus();
    });
    dialogoCancelar.addEventListener('click', evento => {
      if (evento.target === dialogoCancelar) fecharCancelar();
    });
    document.getElementById('form-os')?.addEventListener('submit', evento => {
      const submitter = evento.submitter;
      if (!submitter || submitter.name !== 'cancelar_os') return;
      if (!(motivoCancelar?.value || '').trim()) {
        evento.preventDefault();
        evento.stopImmediatePropagation();
        mostrarPasso(1);
        mostrarAvisoGlobal('Descreva o motivo do cancelamento antes de continuar.');
        motivoCancelar?.focus();
        return;
      }
      const esperado = (dialogoCancelar.dataset.numeroOs || '').trim();
      if ((confirmarNumero?.value || '').trim() !== esperado) {
        evento.preventDefault();
        evento.stopImmediatePropagation();
        mostrarPasso(2);
        if (erroCancelar) {
          erroCancelar.hidden = false;
          erroCancelar.textContent = 'Digite exatamente o número da OS para confirmar.';
        }
        confirmarNumero?.focus();
      }
    }, true);
  }

  // Rascunho automático: cada alteração é preservada sem botão de salvar.
  const formAuto = document.getElementById('form-os');
  const statusAuto = document.getElementById('rascunho-auto-status');
  if (formAuto && formAuto.dataset.osId && formAuto.dataset.autoSave === '1') {
    const urlAuto = '/os/' + formAuto.dataset.osId + '/rascunho/auto';
    let timerAuto = null;
    let salvandoAuto = false;
    const agendarAuto = () => {
      window.clearTimeout(timerAuto);
      timerAuto = window.setTimeout(salvarAuto, 900);
    };
    const salvarAuto = async () => {
      if (salvandoAuto) { agendarAuto(); return; }
      salvandoAuto = true;
      const dados = new FormData(formAuto);
      ['nota_fiscal', 'imagens_encerramento[]', 'imagem_encerramento'].forEach(nome => dados.delete(nome));
      if (statusAuto) statusAuto.textContent = 'Salvando rascunho…';
      try {
        const resposta = await fetch(urlAuto, {
          method: 'POST', body: dados, credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
          }
        });
        let corpo = {};
        try { corpo = await resposta.json(); } catch (_erro) {}
        if (!resposta.ok || !corpo.ok) {
          throw new Error(corpo.error || 'Não foi possível salvar o rascunho.');
        }
        const hora = new Date().toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
        if (statusAuto) statusAuto.textContent = `Rascunho salvo automaticamente às ${hora}.`;
      } catch (erro) {
        if (statusAuto) statusAuto.textContent = erro.message || 'Não foi possível salvar o rascunho.';
      } finally {
        salvandoAuto = false;
      }
    };
    formAuto.addEventListener('input', evento => {
      const alvo = evento.target;
      if (alvo && ['file', 'submit', 'button'].includes(alvo.type)) return;
      agendarAuto();
    });
    formAuto.addEventListener('change', evento => {
      const alvo = evento.target;
      if (alvo && ['file', 'submit', 'button'].includes(alvo.type)) return;
      agendarAuto();
    });
    window.addEventListener('pagehide', () => {
      if (!timerAuto) return;
      window.clearTimeout(timerAuto);
      try {
        const dados = new FormData(formAuto);
        ['nota_fiscal', 'imagens_encerramento[]', 'imagem_encerramento'].forEach(nome => dados.delete(nome));
        if (navigator.sendBeacon) navigator.sendBeacon(urlAuto, dados);
      } catch (_erro) {}
    });
  }
  // Interface app: transforma os fieldsets da OS em seções navegáveis.
  const formApp = document.getElementById('form-os');
  if (formApp && document.body.classList.contains('ui-app')) {
    const paineis = Array.from(formApp.children)
      .filter(elemento => elemento.tagName === 'FIELDSET');
    if (paineis.length > 1) {
      if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
      const chaveEstadoOS = 'autoseg:os-estado:' + location.pathname;
      let estadoOS = {};
      try {
        estadoOS = JSON.parse(sessionStorage.getItem(chaveEstadoOS) || '{}') || {};
      } catch (_erro) {
        estadoOS = {};
      }
      let indiceAtivo = 0;
      const abas = document.createElement('div');
      abas.className = 'os-tabs';
      abas.setAttribute('role', 'tablist');
      abas.setAttribute('aria-label', 'Seções da ordem de serviço');
      const ativar = indice => {
        indiceAtivo = indice;
        paineis.forEach((painel, i) => {
          painel.hidden = i !== indice;
          painel.setAttribute('aria-hidden', i === indice ? 'false' : 'true');
        });
        Array.from(abas.children).forEach((botao, i) => {
          const ativo = i === indice;
          botao.classList.toggle('active', ativo);
          botao.setAttribute('aria-selected', ativo ? 'true' : 'false');
          botao.tabIndex = ativo ? 0 : -1;
        });
      };
      paineis.forEach((painel, indice) => {
        const legenda = painel.querySelector('legend');
        const nomeCompleto = (legenda?.textContent || `Seção ${indice + 1}`).trim();
        const nomesCurtos = [
          ['identificação', 'Identificação'],
          ['materiais', 'Materiais'],
          ['situação', 'Situação e relatório'],
          ['fotos', 'Fotos e legendas'],
        ];
        const nome = (nomesCurtos.find(([chave]) =>
          nomeCompleto.toLowerCase().includes(chave)) || [null, nomeCompleto])[1];
        const painelId = 'os-panel-' + (indice + 1);
        const abaId = 'os-tab-' + (indice + 1);
        painel.id = painelId;
        painel.classList.add('os-panel');
        painel.setAttribute('role', 'tabpanel');
        painel.setAttribute('aria-labelledby', abaId);
        const botao = document.createElement('button');
        botao.type = 'button';
        botao.className = 'os-tab';
        botao.id = abaId;
        botao.setAttribute('role', 'tab');
        botao.setAttribute('aria-controls', painelId);
        const numero = document.createElement('span');
        numero.className = 'tab-index';
        numero.textContent = String(indice + 1).padStart(2, '0');
        const rotulo = document.createElement('span');
        rotulo.textContent = nome;
        botao.append(numero, rotulo);
        botao.addEventListener('click', () => {
          ativar(indice);
          registrarUi();
        });
        abas.appendChild(botao);
      });
      abas.addEventListener('keydown', evento => {
        const atual = Array.from(abas.children).indexOf(document.activeElement);
        if (atual < 0) return;
        let destino = null;
        if (evento.key === 'ArrowRight') destino = (atual + 1) % paineis.length;
        else if (evento.key === 'ArrowLeft') destino = (atual - 1 + paineis.length) % paineis.length;
        else if (evento.key === 'Home') destino = 0;
        else if (evento.key === 'End') destino = paineis.length - 1;
        if (destino === null) return;
        evento.preventDefault();
        ativar(destino);
        registrarUi();
        abas.children[destino].focus();
      });
      formApp.insertBefore(abas, paineis[0]);
      const indiceInicial = Number.isInteger(estadoOS.aba)
        && estadoOS.aba >= 0 && estadoOS.aba < paineis.length ? estadoOS.aba : 0;
      ativar(indiceInicial);
      if (Number.isFinite(estadoOS.scroll) && estadoOS.scroll > 0) {
        requestAnimationFrame(() => window.scrollTo(0, estadoOS.scroll));
      }
      const salvarEstadoOS = () => {
        try {
          sessionStorage.setItem(chaveEstadoOS, JSON.stringify({
            aba: indiceAtivo,
            scroll: window.scrollY
          }));
        } catch (_erro) {}
      };
      window.addEventListener('pagehide', salvarEstadoOS);
      window.addEventListener('beforeunload', salvarEstadoOS);

      const modelo = formApp.querySelector('.os-service-model');
      if (modelo && paineis[0]) {
        const statusBloco = paineis[0].querySelector('.os-status-block');
        if (statusBloco) statusBloco.after(modelo);
        else if (!paineis[0].contains(modelo)) paineis[0].prepend(modelo);
      }

      // O fechamento pertence à aba de situação, não à de fotos.
      const painelSituacao = paineis.find(painel =>
        (painel.querySelector('legend')?.textContent || '').toLowerCase().includes('situação'));
      const notaFiscal = document.getElementById('nota-fiscal-upload');
      if (painelSituacao && notaFiscal) {
        const titulo = document.createElement('div');
        titulo.className = 'os-close-head';
        const h3 = document.createElement('h3');
        h3.textContent = 'Fechamento';
        const texto = document.createElement('p');
        texto.textContent = 'Nota fiscal e confirmação da OS.';
        titulo.append(h3, texto);
        painelSituacao.append(titulo, notaFiscal);
      }

      formApp.addEventListener('submit', evento => {
        const botao = evento.submitter;
        if (botao && botao.hasAttribute('formnovalidate')) return;
        for (const campo of formApp.elements) {
          if (!campo.willValidate || campo.disabled || campo.type === 'hidden') continue;
          if (!campo.checkValidity()) {
            evento.preventDefault();
            evento.stopImmediatePropagation();
            const indice = paineis.indexOf(campo.closest('fieldset.os-panel'));
            if (indice >= 0) {
              ativar(indice);
              abas.children[indice].focus();
            }
            const rotulo = campo.labels && campo.labels[0];
            mostrarAvisoGlobal('Preencha: ' + ((rotulo?.textContent || campo.name || 'campo obrigatório').replace(/\s+/g,' ').trim()));
            window.setTimeout(() => {
              try { campo.focus({preventScroll:false}); } catch (_erro) {}
            }, 0);
            return;
          }
        }
      }, true);
    }
  }

  const ordenarOS = document.getElementById('c_ordem');
  if (ordenarOS) {
    ordenarOS.addEventListener('change', () => ordenarOS.form?.submit());
  }
  document.querySelectorAll('input[data-auto-upload-nf]').forEach(campoNf => {
    campoNf.addEventListener('change', async () => {
      const arquivo = campoNf.files && campoNf.files[0];
      if (!arquivo) return;
      const form = campoNf.closest('form');
      const url = campoNf.dataset.uploadUrl;
      if (!form || !url) return;
      const status = form.querySelector('[data-nf-status]');
      const dados = new FormData(form);
      campoNf.disabled = true;
      if (status) {
        status.textContent = `Anexando ${arquivo.name} e salvando rascunho…`;
      }
      try {
        const resposta = await fetch(url, {
          method: 'POST', body: dados, credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json'
          }
        });
        let corpo = {};
        try { corpo = await resposta.json(); } catch (_erro) {}
        if (!resposta.ok || !corpo.ok) {
          throw new Error(corpo.error || 'Não foi possível anexar o PDF da nota fiscal.');
        }
        window.location.reload();
      } catch (erro) {
        campoNf.disabled = false;
        campoNf.value = '';
        if (status) {
          status.textContent = erro.message || 'Não foi possível anexar o PDF.';
        } else {
          mostrarAvisoGlobal(erro.message || 'Não foi possível anexar o PDF.');
        }
      }
    });
  });
  const menuToggle = document.getElementById('toggle-side-nav');
  const menuLateral = document.getElementById('side-nav');
  if (menuToggle && menuLateral) {
    const fecharMenu = () => {
      menuLateral.classList.remove('open');
      document.body.classList.remove('menu-open');
      menuToggle.setAttribute('aria-expanded', 'false');
    };
    const abrirMenu = () => {
      menuLateral.classList.add('open');
      document.body.classList.add('menu-open');
      menuToggle.setAttribute('aria-expanded', 'true');
    };
    menuToggle.addEventListener('click', evento => {
      evento.stopPropagation();
      if (menuLateral.classList.contains('open')) fecharMenu();
      else abrirMenu();
    });
    document.getElementById('fechar-side-nav')?.addEventListener('click', fecharMenu);
    document.addEventListener('click', evento => {
      if (!menuLateral.classList.contains('open')) return;
      if (evento.target.closest('#side-nav,#toggle-side-nav,#fechar-side-nav')) return;
      fecharMenu();
    });
    menuLateral.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', fecharMenu);
    });
    document.addEventListener('keydown', evento => {
      if (evento.key === 'Escape') fecharMenu();
    });
  }
  document.querySelectorAll('button[data-mover]').forEach(botao => {
    botao.addEventListener('click', async () => {
      const card = botao.closest('.foto-rascunho');
      const form = botao.closest('form');
      if (!card || !form) return;
      const corpo = new FormData();
      const csrf = form.querySelector('input[name="csrf"]')?.value || '';
      if (csrf) corpo.append('csrf', csrf);
      corpo.append('direcao', botao.dataset.direcao || '');
      botao.disabled = true;
      try {
        const resposta = await fetch(botao.dataset.mover, {
          method: 'POST', body: corpo, credentials: 'same-origin',
          headers: {'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'}
        });
        let dados = {};
        try { dados = await resposta.json(); } catch (_erro) {}
        if (!resposta.ok || !dados.ok) {
          throw new Error(dados.error || 'Não foi possível mover a foto.');
        }
        if (botao.dataset.direcao === 'up' && card.previousElementSibling) {
          card.parentElement.insertBefore(card, card.previousElementSibling);
        } else if (botao.dataset.direcao === 'down' && card.nextElementSibling) {
          card.parentElement.insertBefore(card.nextElementSibling, card);
        }
      } catch (erro) {
        mostrarAvisoGlobal(erro.message || 'Não foi possível mover a foto.');
      } finally {
        botao.disabled = false;
      }
    });
  });
  document.getElementById('abrir-feedback-side')?.addEventListener('click', () => {
    document.getElementById('abrir-feedback')?.click();
  });
  document.querySelectorAll('table tbody tr').forEach(tr => {
    const link = tr.querySelector('td:first-child a[href^="/os/"]');
    if (!link) return;
    tr.classList.add('row-link');
    tr.addEventListener('click', evento => {
      if (evento.target.closest('a,button,input,select,label,form')) return;
      window.location.assign(link.href);
    });
  });
  registrarUi();
}());
// Formulário de encerramento: somente confirmação explícita; sem salvamento automático.
