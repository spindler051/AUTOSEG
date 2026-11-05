// AUTOSEG Portal v6: interface sem dependências externas.
(function () {
  'use strict';
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
            materiais.push({item:ler('material_item[]'),qtd:ler('material_qtd[]'),unit:ler('material_unit[]')});
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
    function number(v) {
      let x = String(v || '').trim().replace(/R\$/g, '').replace(/\s/g, '');
      if (x.includes(',')) x = x.replace(/\./g, '').replace(',', '.');
      return Number(x) || 0;
    }
    function recalc() {
      if (!total) return;
      const labour = number(form.elements['valor_mao_obra'].value);
      let material = 0, hasMaterial = false;
      container.querySelectorAll('.material-row').forEach(row => {
        const item = row.querySelector('[name="material_item[]"]');
        const qtd = row.querySelector('[name="material_qtd[]"]');
        const unit = row.querySelector('[name="material_unit[]"]');
        if (item && item.value.trim()) {
          hasMaterial = true;
          material += number(qtd.value) * number(unit.value);
        }
      });
      if (!hasMaterial) material = number(form.elements['valor_materiais_manual'].value);
      const negociado = String(form.elements['valor_total_override'].value).trim();
      const cost = negociado ? number(negociado) : labour + material;
      total.textContent = cost.toLocaleString('pt-BR', {style:'currency',currency:'BRL'});
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
    form.addEventListener('submit', e => {
      const botao = e.submitter;
      if (!botao || botao.value !== 'encerrar') return;
      if (!status || !status.value) {e.preventDefault();window.alert('Selecione uma situação.');return;}
      const executado = form.querySelector('[name="v9_execucao"]');
      if (relato && !relato.value.trim() && !(executado && executado.value.trim())) {
        e.preventDefault();window.alert('Preencha o relatório técnico antes de confirmar.');relato.focus();return;
      }
      if (status.value === 'Cancelada' && motivo && !motivo.value.trim()) {
        e.preventDefault();window.alert('Informe o motivo do cancelamento.');motivo.focus();return;
      }
      const encerrada = status.value !== 'Pendente';
      if (!window.confirm(encerrada
        ? 'Confirmar OS como '+status.value+'? O relatório PDF será publicado e ficará disponível ao cliente.'
        : 'Confirmar OS pendente? Ela continuará visível aos prestadores e ainda não terá PDF final.')) {
        e.preventDefault();
      }
    });
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
    const titulo = document.createElement('label');
    titulo.textContent = 'Filtrar registros exibidos';
    titulo.setAttribute('for',`busca-tabela-${indice}`);
    const busca = document.createElement('input');
    busca.type = 'search';
    busca.id = `busca-tabela-${indice}`;
    busca.placeholder = 'Digite nome, OS, situação ou outro dado da tabela';
    const aviso = document.createElement('small');
    aviso.setAttribute('aria-live','polite');
    const filtrar = () => {
      const termo = busca.value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
      let exibidas = 0;
      for (const linha of linhas) {
        const texto = linha.textContent.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
        linha.hidden = !texto.includes(termo);
        if (!linha.hidden) exibidas += 1;
      }
      aviso.textContent = `${exibidas} de ${linhas.length} registro(s) carregados nesta página`;
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

  // Feedback do Portal do Prestador: diálogo global, sem sair da página.
  const dialogoFeedback = document.getElementById('dialogo-feedback');
  const abrirFeedback = document.getElementById('abrir-feedback');
  if (dialogoFeedback && abrirFeedback) {
    const formFeedback = document.getElementById('form-feedback');
    const paginaFeedback = document.getElementById('feedback-pagina');
    const mensagemFeedback = document.getElementById('feedback-mensagem');
    const fecharFeedback = document.getElementById('fechar-feedback');
    const csrfFeedback = formFeedback?.querySelector('input[name="csrf"]');
    const marcarPagina = () => {
      if (paginaFeedback) paginaFeedback.value = location.pathname.slice(0, 300) || '/';
    };
    const abrirDialogo = () => {
      marcarPagina();
      if (typeof dialogoFeedback.showModal === 'function') {
        if (!dialogoFeedback.open) dialogoFeedback.showModal();
      } else {
        dialogoFeedback.setAttribute('open', '');
      }
      mensagemFeedback?.focus();
      if (csrfFeedback?.value) {
        const corpo = new URLSearchParams({
          csrf: csrfFeedback.value,
          pagina: paginaFeedback?.value || location.pathname.slice(0, 300) || '/'
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
      if (typeof dialogoFeedback.close === 'function') dialogoFeedback.close();
      else dialogoFeedback.removeAttribute('open');
    };
    abrirFeedback.addEventListener('click', abrirDialogo);
    fecharFeedback?.addEventListener('click', fecharDialogo);
    dialogoFeedback.addEventListener('click', evento => {
      if (evento.target === dialogoFeedback) fecharDialogo();
    });
  }
}());
// Formulário de encerramento: somente confirmação explícita; sem salvamento automático.
