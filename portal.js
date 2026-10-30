// AUTOSEG Portal v6: interface sem dependências externas.
(function () {
  'use strict';
  const form = document.getElementById('form-os');
  if (form) {
    const container = document.getElementById('lista-materiais');
    const add = document.getElementById('adicionar-material');
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
        const original = container.querySelector('.material-row');
        if (!original) return;
        const clone = original.cloneNode(true);
        clone.querySelectorAll('input').forEach(input => {input.value = '';input.removeAttribute('id');});
        clone.querySelectorAll('label').forEach(label => label.removeAttribute('for'));
        container.appendChild(clone);
      });
      container.addEventListener('click', e => {
        if (e.target.closest('.remover-material')) {
          const row = e.target.closest('.material-row');
          if (row && container.querySelectorAll('.material-row').length > 1) row.remove();
          else if (row) row.querySelectorAll('input').forEach(input => input.value = '');
          recalc();
        }
      });
      form.addEventListener('input', recalc);
      recalc();
    }
    const status = form.querySelector('[name="acao_status"]');
    const fotoBox = document.getElementById('anexo-encerramento');
    const motivo = form.querySelector('[name="motivo_encerramento"]');
    const relato = form.querySelector('[name="relatorio_tecnico"]');
    function atualizarEncerramento() {
      if (!status) return;
      if (fotoBox) fotoBox.hidden = !['Concluída', 'Cancelada'].includes(status.value);
      if (motivo) motivo.required = status.value === 'Cancelada';
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
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit',e => {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });
}());
// Formulário de encerramento: somente confirmação explícita; sem salvamento automático.
