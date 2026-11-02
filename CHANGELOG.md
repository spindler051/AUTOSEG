# AUTOSEG — Changelog

## 9.6.0-dev.3 — REV09 — 2026-11-02 — develop (validação local)

Fluxo de OS separado em ações independentes:

- **ASSUMIR OS** atribui responsável e horário sem iniciar o atendimento.
- **EM ROTA** registra o deslocamento em `os_deslocamentos`, é idempotente, aparece no Portal Prestador e no Portal Cliente e pode ser cancelado pelo responsável.
- **INICIAR OS** registra o início efetivo, encerra o deslocamento ativo e permite retomada de OS pendente. O fluxo antigo "INICIAR OS — ASSUMIR AUTOMATICAMENTE" foi removido.
- **SALVAR RASCUNHO** no Portal Prestador e no desktop, com persistência dos campos técnicos, materiais, valores e fotos em `produtividade_rascunhos` e `os_rascunhos_web`. Recuperação após reiniciar o servidor testada.
- Portal Prestador exibe Em rota na lista; Portal Cliente exibe Em rota na lista e no detalhe.
- Importação/rateio financeiro e financeiro pessoal do REV07 preservados, incluindo bloqueio de rateio fora da conclusão.
- Importação YAML, pré-visualização, desfazer, catálogo e estoque mantidos dos REV06/REV08.
- Testes novos em `test_rev09_fluxo_os.py` cobrem assumir, em rota, início, rascunho após reinício, conclusão, pendência, cancelamento, YAML sem gravação, PDF autorizado e bloqueio de terceiros.

Pendente: homologação manual das interfaces no Mac, envio Gmail real (depende de OAuth), nota fiscal (somente rascunho) e itens ainda parciais descritos em `ROADMAP.md`.

## 9.6.0-dev.2 — REV08 — 2026-11-02 — develop (validação local pendente)

- Importação YAML de materiais transacional, sem gravações parciais em falhas.
- Materiais de Serviços e Valores integrados ao catálogo único sem alterar estoque ou preços já cadastrados.
- Busca normalizada por nome/código e alertas de estoque negativo/mínimo na interface desktop.
- Prévia e desfazer YAML no Portal Prestador, com proteção dos campos preenchidos na aba; fotos não enviadas continuam exigindo novo upload.
- Correção de teste antigo do Portal Cliente e bloqueio de disparo acidental de Gmail durante descoberta de testes.
- Testes unitários novos; nenhum banco real foi acessado na validação.

Pendente: homologar interfaces no Mac; não estão implementados integralmente os 78 requisitos. Não atualizar main.

## 9.6.0-dev.1 — REV08 — 2026-11-02 — develop

Introduzidos metadados de versão, versionador com controle de branch, testes, CI no develop e checklist de 78 requisitos.

Estado: PREPARAÇÃO. Não há migrações SQLite ou mudanças nos módulos operacionais. Os 78 requisitos continuam em homologação pendente. O branch main não deve ser atualizado antes de testes.

Bloqueio: reconciliar alterações e arquivos não publicados do Mac antes de sincronizar o código remoto com o DEV local.
