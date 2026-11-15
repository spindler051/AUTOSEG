## P0-AUTH-CLOSE-GATE-HARDENING — cobertura DEV (2026-11-12)

- `tests.test_os_effect_outbox` checks that PDF cleanup removes only a
  target owned by the same processing claim and never removes another worker's
  target or a recorded document.
- `tests.test_p0_auth_close_gate` verifies resend form without additional
  addresses (with or without outbox), fail-closed resend without outbox,
  rejected forged addresses, dispatcher failure without `recipient_refs`, and
  safe rollback rejection of unresolved references.
- REV12 retains the invoice-included email assertion, using the new outbox
  resend contract rather than direct legacy sending.
- All integration runs must use temporary `AUTOSEG_SERVER_DATA`,
  `AUTOSEG_USER_DATA`, and `AUTOSEG_LOCAL_DATA`; see the delivery's
  `TEST_RESULTS.txt` for executed commands and exact outcomes.

## P0-AUTH-CLOSE-GATE-FIXES — testes DEV (2026-11-12)

Novos casos de publicação de anexos encerrados (flags 0/1 e negativas),
TOCTOU PDF/status, rollback de destinatários reais, versão nova da projeção,
quarentena 3600 s versus restauração explicitamente imediata e resolução de
referências de e-mail por operação. Executar em banco/portas temporários.
Resultados exatos: `TEST_RESULTS.txt` da entrega correspondente.



## P0-AUTH-CLOSE-GATE — new regression modules

`tests.test_p0_auth_close_gate` covers shared attachment/invoice writers,
rollback, quarantined removal, HTTP object-denial races, duplicate-acknowledged
manual dispatch and atomic email projections. `tests.test_p0_auth_dispatcher`
covers orphan PDF rejection, unknown email outcomes and safe DEV rollback.
`tests.test_os_effect_outbox` now requires candidate regeneration and digest
comparison even when the target PDF already exists. This strengthens the
older restart expectation to reject an orphan instead of adopting it blindly.

Run focused and full suites with a temporary `AUTOSEG_SERVER_DATA` directory
and keep the actual results in the deliverable's `TEST_RESULTS.txt`.

### P0-AUTH-FINAL — outbox DEV, ativação pendente (2026-11-11)

Migração **aditiva exclusiva de DEV** `os_effect_outbox` com backup, lease,
reconciliação e publicação pós-commit. Revalidações e transações compartilhadas
foram ampliadas em escritores de OS. Não é certificação de TOCTOU totalmente
fechado: arquivos removidos/rotacionados, reenvio legado e fluxos restantes
precisam ser cobertos antes de aprovar a flag. `AUTOSEG_OBJECT_POLICY_ENFORCEMENT`
permanece `0`. Consultar `docs/operations/OBJECT_POLICY_ROLLOUT.md` e o
`BLOCKED.md` desta entrega; não habilitar na MAIN.

# Testes

## P0-AUTH (execução parcial, gate não fechado)

`tests.test_p0_auth_gate` cobre reabertura com enforcement on/off e corridas
controladas entre autorização inicial e início do writer. O teste histórico
`test_non_admin_cannot_reopen_pending_os` não foi enfraquecido.

As execuções unitárias direcionadas passaram. A execução conjunta da suíte
focada e o discovery completo ultrapassaram o tempo do ambiente sem relatório
final; **não** devem ser tratados como aprovados. O registro dos comandos,
resultados e limitações está em `TEST_RESULTS.txt` da entrega P0-AUTH.

## Suíte não visual

```bash
./autoseg test
./autoseg check   # suíte + compilação + portal.js
```

O comando cria uma pasta temporária e aponta `AUTOSEG_BASE`,
`GESTAO_BANCO`, `AUTOSEG_USER_DATA`, `AUTOSEG_SERVER_DATA` e
`AUTOSEG_LOCAL_DATA` para ela. Assim, um teste não abre o banco local nem o
banco de produção.

Para executar o discovery completo manualmente, sem tocar na MAIN:

```bash
TMP=$(mktemp -d)
AUTOSEG_DEV=1 AUTOSEG_SERVER_DATA="$TMP" AUTOSEG_USER_DATA="$TMP" \
AUTOSEG_LOCAL_DATA="$TMP" PYTHONPATH=.:tests \
python3 -m unittest discover -s tests -p 'test_*.py'
```

**Estado em 2026-11-11:** 667 testes descobertos: 665 aprovados, 1 skip e
1 falha **pré-existente** (`test_numero_publico.test_non_admin_cannot_reopen_pending_os`).
O mesmo teste falha na base `e2cfec1`; não declare a suíte integralmente verde
até essa negativa de autorização ser tratada em uma peça própria.

## P0 — uma origem, um login, uma shell

Testes novos:

- `tests/test_portal_unification.py` — origem única, aliases `308`, fluxos
  retirados `410`, rotas migradas e negativas cliente × cliente/prestador.
- `tests/test_p0_legacy_migrations.py` — comportamentos vigentes que antes
  dependiam do portal removido: perfil, OS PF, chamados, organizações,
  orçamento, links de origem e `410` sem escrita.
- `tests/test_p0_review_documents.py` — relatório, nota fiscal e PDF de
  chamado da própria OS; síndico/zelador, organização alheia e responsável
  histórico sem papel convertido.

Focada:

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  tests.test_portal_unification tests.test_officina_web tests.test_client_web \
  tests.test_client_roles_http tests.test_login_web tests.test_login_compat \
  tests.test_shared_shell tests.test_web_access tests.test_runtime_config \
  tests.test_pf_pj_responsaveis tests.test_rev05_seguro -v
```

Regressão:

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  tests.test_rev12_correcoes tests.test_admin_parity tests.test_portal_v4 -v
```

## Testes legados

Os scripts antigos que dependiam de `ServidorPortal`/`portal_cliente_v94` ou
do autocadastro removido saíram do discovery. A cobertura vigente foi migrada
para os testes P0 acima; os fluxos B1–B3 não são restaurados.

Saíram: `test_autoseg_http_novo.py`, `test_cadastro_v951.py`,
`test_fluxo_cliente_v94.py`, `test_fluxo_v5.py`, `test_fluxo_v6.py`,
`test_fluxo_v7.py`, `test_links_cliente_952.py`, `test_pf_pj_http.py`,
`test_rev03_http.py`, `test_rev09_fluxo_os.py`, `test_v94_correcoes.py` e
`test_v953_http.py`. A decisão de cada um está no `NOTES.md` da entrega da
revisão.

Continuam válidos: `test_pf_pj_responsaveis.py` (regras de responsável e
histórico organizacional) e `test_rev05_seguro.py` (túneis DEV na porta
`8866`).

## Auditores

```bash
./.venv/bin/python scripts/audit_comments.py --strict
./.venv/bin/python scripts/audit_code_rot.py
```

## Antes de produção

- backup do banco e dos anexos;
- smoke manual no macOS;
- login de prestador e cliente na origem única;
- PDF e e-mail de uma OS de teste;
- rollback descrito quando houver mudança de schema ou dados.
