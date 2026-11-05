'use strict';
// Behavioural regression tests for portal.js without a browser.
// Run with: node test_portal_feedback.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const source = fs.readFileSync(path.join(__dirname, 'portal.js'), 'utf8');
const DRAFT_KEY = 'autoseg:feedback:draft:v1';
const SUBMITTED_KEY = 'autoseg:feedback:submitted:v1';
const FEEDBACK_IDS = [
  'dialogo-feedback',
  'abrir-feedback',
  'form-feedback',
  'feedback-pagina',
  'feedback-mensagem',
  'fechar-feedback',
  'feedback-responder-ia',
];

class FakeElement {
  constructor(id) {
    this.id = id;
    this.tagName = 'DIV';
    this.value = '';
    this.checked = false;
    this.open = false;
    this.attributes = new Map();
    this.listeners = new Map();
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(handler);
  }

  dispatch(type, event = {}) {
    for (const handler of this.listeners.get(type) || []) {
      handler({target: this, preventDefault() {}, ...event});
    }
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }

  showModal() {
    this.open = true;
  }

  close() {
    this.open = false;
    this.dispatch('close');
  }

  focus() {
    this.ownerDocument.activeElement = this;
  }
}

function createEnvironment({pathname = '/os', draft = null, submitted = false} = {}) {
  const elements = new Map();
  const storage = new Map();
  const timers = new Map();
  const documentListeners = new Map();
  const windowListeners = new Map();
  let nextTimer = 1;
  let reloads = 0;

  if (draft) storage.set(DRAFT_KEY, JSON.stringify(draft));
  if (submitted) storage.set(SUBMITTED_KEY, '1');

  const document = {
    activeElement: null,
    visibilityState: 'visible',
    getElementById(id) {
      return elements.get(id) || null;
    },
    querySelector(selector) {
      return selector === 'meta[name="autoseg-auto-refresh"]' ? meta : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener(type, handler) {
      if (!documentListeners.has(type)) documentListeners.set(type, []);
      documentListeners.get(type).push(handler);
    },
    dispatch(type, event = {}) {
      for (const handler of documentListeners.get(type) || []) handler(event);
    },
  };

  for (const id of FEEDBACK_IDS) {
    const element = new FakeElement(id);
    element.ownerDocument = document;
    elements.set(id, element);
  }
  elements.get('form-feedback').querySelector = selector => (
    selector === 'input[name="csrf"]' ? csrf : null
  );
  const csrf = new FakeElement('csrf');
  csrf.value = 'token-de-teste';

  const meta = new FakeElement('meta-auto-refresh');
  meta.setAttribute('content', '20');

  const location = {
    pathname,
    reload() {
      reloads += 1;
    },
  };

  const window = {
    location,
    setTimeout(callback, delay) {
      const id = nextTimer++;
      timers.set(id, {callback, delay});
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    addEventListener(type, handler) {
      if (!windowListeners.has(type)) windowListeners.set(type, []);
      windowListeners.get(type).push(handler);
    },
    alert() {},
    confirm() { return true; },
  };

  const context = {
    window,
    document,
    location,
    sessionStorage: {
      getItem(key) {
        return storage.has(key) ? storage.get(key) : null;
      },
      setItem(key, value) {
        storage.set(key, String(value));
      },
      removeItem(key) {
        storage.delete(key);
      },
    },
    fetch() {
      return {catch() {}};
    },
    URLSearchParams,
    Event: class {},
    console,
  };

  return {
    context,
    elements,
    storage,
    timers,
    document,
    location,
    get reloads() { return reloads; },
    runZeroTimers() {
      const zero = [...timers.entries()].filter(([, timer]) => timer.delay <= 0);
      for (const [id, timer] of zero) {
        timers.delete(id);
        timer.callback();
      }
    },
    runTimers() {
      const pending = [...timers.entries()];
      for (const [id, timer] of pending) {
        timers.delete(id);
        timer.callback();
      }
    },
  };
}

function load(options) {
  const env = createEnvironment(options);
  vm.runInNewContext(source, env.context, {filename: 'portal.js'});
  return env;
}

function testRefreshPausesAndDraftSurvivesReload() {
  const env = load({pathname: '/os'});
  assert.strictEqual(env.timers.size, 1, 'auto-refresh deve ser agendado');
  assert.strictEqual([...env.timers.values()][0].delay, 20000);

  env.elements.get('abrir-feedback').dispatch('click');
  assert.strictEqual(env.elements.get('dialogo-feedback').open, true);
  assert.strictEqual(env.timers.size, 0, 'diálogo aberto deve pausar o refresh');

  const textarea = env.elements.get('feedback-mensagem');
  textarea.value = 'Texto que não pode sumir.';
  textarea.dispatch('input');
  const saved = JSON.parse(env.storage.get(DRAFT_KEY));
  assert.strictEqual(saved.mensagem, 'Texto que não pode sumir.');
  assert.strictEqual(saved.aberto, true);

  // Simulate a reload while the dialog is open: the new page restores both
  // the text and the open dialog, and keeps the refresh paused.
  const restored = load({pathname: '/clientes', draft: saved});
  assert.strictEqual(restored.elements.get('feedback-mensagem').value,
    'Texto que não pode sumir.');
  assert.strictEqual(restored.elements.get('dialogo-feedback').open, true);
  assert.strictEqual(restored.timers.size, 0, 'diálogo restaurado deve pausar o refresh');

  env.elements.get('dialogo-feedback').close();
  assert.strictEqual(JSON.parse(env.storage.get(DRAFT_KEY)).aberto, false);
  env.runZeroTimers();
  assert.strictEqual(env.timers.size, 1, 'refresh deve voltar após fechar');
}

function testSuccessfulSubmitClearsDraftOnDetailPage() {
  const draft = {
    mensagem: 'Feedback já enviado.',
    responder_ia: true,
    aberto: false,
    atualizado_em: Date.now(),
  };
  const env = load({pathname: '/feedback/42', draft, submitted: true});
  assert.strictEqual(env.storage.has(DRAFT_KEY), false, 'rascunho deve ser limpo após envio');
  assert.strictEqual(env.storage.has(SUBMITTED_KEY), false);
  assert.strictEqual(env.elements.get('feedback-mensagem').value, '');
}

function testFailedSubmitKeepsDraft() {
  const draft = {
    mensagem: 'Texto preservado após erro.',
    responder_ia: false,
    aberto: true,
    atualizado_em: Date.now(),
  };
  const env = load({pathname: '/feedback', draft, submitted: true});
  assert.strictEqual(env.storage.has(DRAFT_KEY), true);
  assert.strictEqual(env.elements.get('feedback-mensagem').value,
    'Texto preservado após erro.');
}

function testCancelClearsDraft() {
  const draft = {
    mensagem: 'Cancelar este texto.',
    responder_ia: true,
    aberto: true,
    atualizado_em: Date.now(),
  };
  const env = load({pathname: '/os', draft});
  assert.strictEqual(env.elements.get('feedback-mensagem').value, 'Cancelar este texto.');
  assert.strictEqual(env.elements.get('feedback-responder-ia').checked, true);

  env.elements.get('fechar-feedback').dispatch('click');
  assert.strictEqual(env.elements.get('feedback-mensagem').value, '');
  assert.strictEqual(env.elements.get('feedback-responder-ia').checked, false);
  assert.strictEqual(env.storage.has(DRAFT_KEY), false, 'cancelar deve limpar o rascunho');
}

function testDraftSubmitPausesRefreshAndShowsProgress() {
  const env = load({pathname: '/os'});
  assert.strictEqual(env.timers.size, 1);
  const button = new FakeElement('salvar-rascunho');
  button.setAttribute('formaction', '/os/1/rascunho/salvar');
  env.document.dispatch('submit', {submitter: button});
  assert.strictEqual(env.timers.size, 1, 'envio deve trocar o refresh por um timer zero');
  assert.strictEqual([...env.timers.values()][0].delay, 0);
  env.runZeroTimers();
  assert.strictEqual(env.timers.size, 0);
  assert.strictEqual(button.disabled, true);
  assert.strictEqual(button.textContent, 'SALVANDO...');
}

function testFocusedFieldPausesRefresh() {
  const env = load({pathname: '/os'});
  assert.strictEqual(env.timers.size, 1);

  const field = new FakeElement('campo');
  field.tagName = 'TEXTAREA';
  env.document.activeElement = field;
  env.document.dispatch('focusin');
  assert.strictEqual(env.timers.size, 0, 'campo em uso deve pausar o refresh');

  env.document.activeElement = null;
  env.document.dispatch('focusout');
  env.runZeroTimers();
  assert.strictEqual(env.timers.size, 1, 'refresh deve voltar ao sair do campo');
}

const tests = [
  testRefreshPausesAndDraftSurvivesReload,
  testSuccessfulSubmitClearsDraftOnDetailPage,
  testFailedSubmitKeepsDraft,
  testCancelClearsDraft,
  testDraftSubmitPausesRefreshAndShowsProgress,
  testFocusedFieldPausesRefresh,
];

for (const test of tests) {
  test();
  console.log(`ok ${test.name}`);
}
