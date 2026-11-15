# P0-AUTH — estado DEV e congelamento

**Atualizado:** 2026-11-12
**Branch:** `feat/p0-auth-close-gate`
**Commit:** `fafcd8e`
**Base do hardening:** `2ba7d46`
**MAIN:** `3892e7b`, intocada.
**Flag:** `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`.

## 1. Validação

- patch do hardening aplicado sobre `2ba7d46`: OK;
- `changed-files/`: 10/10 idênticos;
- foco: 63 OK;
- REV12: 63 OK · 1 skip;
- suíte completa: **724 OK · 1 skip**;
- `py_compile`, `audit_comments --strict` e `git diff --check`: OK.

## 2. O que está fechado no código

- **B6:** mover, publicar, girar e remover anexos, e remover nota fiscal, usam
  a transação do writer; `publico` funciona em OS encerrada; arquivada e
  prestador não relacionado continuam negados.
- **PDF:** status, lease, `os.link`, `os_documentos`, `os_entregas` e `done`
  ficam na mesma `BEGIN IMMEDIATE`. Cleanup pós-falha só remove o target se o
  worker ainda tiver o mesmo `claim_token` e não houver documento registrado.
- **Reenvio manual:** um único caminho, dependente da outbox. Sem outbox, a
  requisição falha antes de enfileirar ou chamar o Gmail. O formulário de
  reenvio não tem campo de e-mail avulso; a seleção usa
  `cliente|sindico|administradora`.
- **Dispatcher:** exige `recipient_refs`; operação sem refs falha antes do
  provedor e não lê a projeção como endereço.
- **Rollback DEV:** recusa projeções com referências simbólicas; não converte
  nem altera o histórico. Exige reconciliação operacional.
- **Quarentena:** `--cleanup-trash --minimum-age 0` restaura imediatamente um
  arquivo não commitado; o padrão continua 3600 s.

## 3. Caminhos antigos que ainda existem

Estes pontos não fazem parte do contrato do reenvio manual, mas continuam no
código e precisam de decisão antes de produção:

1. O formulário de **conclusão/salvar** ainda mostra `emails_adicionais`. Com a
   outbox instalada, o handler rejeita o campo; a UI ainda o exibe.
2. `_write_action_salvar` ainda tem o envio automático no caminho
   `not use_outbox` (sem outbox). Ele mantém o comportamento anterior para
   bancos sem a tabela.
3. Chamadas diretas aos serviços de anexo/nota sem `connection` continuam fora
   da garantia transacional do caminho HTTP. Estão documentadas no
   `OBJECT_POLICY_ROLLOUT.md`.

Se o objetivo for um único caminho em todo o produto, esses três itens são a
próxima limpeza. Eles não bloqueiam a homologação DEV deste hardening.

## 4. Antes da MAIN

1. Rodar a branch no DEV 8866 com backup do banco DEV.
2. Instalar a outbox no banco DEV e validar `--status` e reconciliação.
3. Smoke: login prestador/cliente, OS, anexos em OS encerrada, PDF v1/v2,
   reenvio com confirmação, `unknown`, rollback e quarentena.
4. Ensaiar migração e rollback em cópia da MAIN.
5. Autorizar explicitamente a outbox em produção; o instalador atual recusa
   caminhos da MAIN por padrão.
6. Liberar código + outbox juntos, com a flag `0`; a ativação da flag é uma
   decisão posterior.

**Não** fazer merge direto na MAIN antes disso: o reenvio manual depende da
outbox e a branch inclui a pilha P0 do portal, não apenas a outbox.

## 5. GTK cliente

A peça 6.5 não foi iniciada. O GTK continua provider-only. O pré-requisito de
código do P0-AUTH está completo para DEV, mas ainda faltam homologação e
migração da outbox. O que falta no GTK está em
[`../planning/GTK_CLIENT_MODE.md`](../planning/GTK_CLIENT_MODE.md):

- login desktop que aceite cliente via `auth.authenticate`;
- sessão desktop com `identity_kind`, `client_id`, organizações e permissões;
- `/api/v1/desktop/me` com contexto cliente;
- endpoints client-safe para home e próprias OS, com autorização no serviço;
- bloqueio das rotas de prestador para cliente;
- projeção cliente da `Janela`, sem menus financeiros/administrativos;
- flag `AUTOSEG_GTK_CLIENT_LOGIN` desligada por padrão e testes de revogação;
- modo local cliente fora do MVP 6.5 (remote-only).
