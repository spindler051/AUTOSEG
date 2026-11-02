# AUTOSEG — Changelog

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
