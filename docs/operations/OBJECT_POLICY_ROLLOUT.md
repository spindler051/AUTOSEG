# Officina Web — object-policy enforcement rollout

## P0-AUTH-CLOSE-GATE-HARDENING — DEV freeze (2026-11-12)

- Branch `feat/p0-auth-close-gate`, commit `fafcd8e`; suíte completa 724 OK ·
  1 skip. MAIN em `3892e7b`, intocada; flag `0`.
- Manual e-mail resend now has one outbox path. Without the DEV outbox the
  request fails before queueing or contacting Gmail. The resend form has no
  free-form address field; only registered contact references are accepted.
- Email dispatch requires `payload_json.recipient_refs`; a missing list fails
  before the provider and is recorded as `failed`. The projection is not a
  fallback recipient source.
- DEV rollback refuses reference-only projections and aborts without dropping
  the outbox; it no longer converts them silently.
- PDF cleanup after a failed publication checks the same `claim_token` and the
  absence of a registered document under `BEGIN IMMEDIATE` before removing a
  newly linked target. A replacement worker's file is preserved.
- Remaining outside this hardening: the conclusion/save form still renders
  `emails_adicionais` (the handler rejects it with the outbox installed), the
  `not use_outbox` automatic-send branch, and direct service calls without a
  shared `connection`. See
  [`P0_AUTH_DEV_FREEZE.md`](P0_AUTH_DEV_FREEZE.md).

## P0-AUTH-CLOSE-GATE-FIXES — DEV review (2026-11-12)

- Evidence publication through `/os/<id>/anexo/<aid>/publico` is permitted on
  closed orders when the responsible provider/admin passes the existing
  transactional object/archival guard; the visibility event stays in the
  writer's transaction. Archived orders and unrelated providers are denied.
- PDF status, archival check, hard-link, document insert, delivery projection
  and outbox `done` now execute under the **same `BEGIN IMMEDIATE`**. A failed
  DB commit removes a newly created target; a crash may leave an orphan, which
  can only be reconciled after candidate SHA-256 verification. A newer PDF
  version resets the delivery's email status; reprocessing the same document
  does not reset it.
- Email outbox payloads carry only `recipient_refs` (`cliente`, `sindico`,
  `administradora`). `produtividade_email.destinatarios_json` remains a list
  of validated e-mail addresses for a safe DEV rollback; manual resend is
  outbox-only. Dispatcher resolves the references from current contacts per
  operation; an unresolvable contact fails before calling Gmail.
- DEV downgrade refuses reference-only projections from earlier installs
  instead of converting them. Unresolvable references abort the entire
  rollback transaction; the outbox is not dropped.
- Immediate orphan-quarantine recovery can be requested explicitly with
  `--cleanup-trash --minimum-age 0`; the default remains 3600 seconds.
  Confirm DB status and file hash before restoring; never use against MAIN.
- `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` remains **0** by default. Human review
  and DEV homologation are still required before any production rollout.

## P0-AUTH-CLOSE-GATE — DEV review (2026-11-11)

The provider attachment commands `mover`, `remover`, `girar`, `publico` and
`nota-fiscal/remover` now share the command's `BEGIN IMMEDIATE` connection
and object guard. Moving and visibility changes have no filesystem effect.
Rotation writes a private stage, commits the new digest/event, then atomically
promotes the staged bytes. Removal moves the managed file to a recoverable
quarantine during the transaction, restores it on rollback, and deletes the
quarantine only after commit. A crash before commit is recovered with
`dispatch_os_effect_outbox.py --cleanup-trash` after checking the database;
a committed intent is reconciled without duplicating its effect.

Email outbox operations persist only stable recipient references. The Gmail
adapter resolves the current contacts before the provider request, and
`os_effect_outbox.finish` commits delivery status and both legacy projections
in one transaction. The manual UI requires a fresh operation key and explicit
duplicate-delivery acknowledgment. An uncertain result becomes `unknown`,
which the worker **never** resends automatically. Message-ID alone does not
guarantee provider-side idempotency; this is at-most-once automatic dispatch
under uncertain outcomes, not exactly-once delivery.

PDF publication now generates a candidate and compares its SHA-256 against
the deterministic target before accepting any orphan. Conflicts are retained
for manual reconciliation; no published PDF is overwritten. Generation that
is nondeterministic across attempts may require manual reconciliation.

Operational commands (DEV only):

```sh
AUTOSEG_DEV=1 PYTHONPATH=. python3 scripts/autoseg/dispatch_os_effect_outbox.py \
  --database /path/to/dev.db --status --json
AUTOSEG_DEV=1 PYTHONPATH=. python3 scripts/autoseg/dispatch_os_effect_outbox.py \
  --database /path/to/dev.db --once --limit 100
AUTOSEG_DEV=1 PYTHONPATH=. python3 scripts/autoseg/dispatch_os_effect_outbox.py \
  --database /path/to/dev.db --reconcile
AUTOSEG_DEV=1 PYTHONPATH=. python3 scripts/autoseg/dispatch_os_effect_outbox.py \
  --database /path/to/dev.db --cleanup-trash --minimum-age 0
AUTOSEG_DEV=1 PYTHONPATH=. python3 scripts/autoseg/install_os_effect_outbox.py \
  --database /path/to/dev.db --status
AUTOSEG_DEV=1 PYTHONPATH=. python3 scripts/autoseg/install_os_effect_outbox.py \
  --database /path/to/dev.db --rollback --backup /path/to/new-backup.db
```

Rollback refuses unresolved pending/processing/unknown effects; it never
changes orders or their attachments. Reconcile the effects and verify a fresh
backup before removing only the DEV outbox and indexes. Keep
`AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0` until explicit deployment approval;
this change does not activate the flag or touch MAIN.


**Scope:** provider portal OS/document operations and client role administration.
The unified-login flag is separate.

## Flag

```text
AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0   # default: legacy behavior
AUTOSEG_OBJECT_POLICY_ENFORCEMENT=1   # enable ObjectPolicy/work_item_access
```

- `0`: the portal keeps the extracted OS command writers and the existing
  legacy validations, but does not apply the new object policy to OS actions,
  lists, documents or `/contas`. `/contas` returns 404.
- `1`: every provider OS action and document read goes through
  `work_item_access`; `/contas` is available to authorized admins.
- `AUTOSEG_UNIFIED_LOGIN` is independent and does not control this flag.

## Preconditions

1. Review and integrate the 6.2 slice in a clean checkout.
2. Back up the database; confirm restore on an isolated copy.
3. Run `accounts.install` and the focused/regression suites. The migration adds
   `account_links.client_role` with default `customer`.
4. Confirm the converted client accounts and their roles; an unconverted client
   is explicitly denied at unified login and has no client-service access.
5. Review `flavors/autoseg/config/policy.yaml` with the provisional role matrix.
   The matrix is data and can be changed without code changes.
6. Keep the flag `0` for the first deployment.

## Activation

1. Enable `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=1` in a controlled environment and
   restart the provider server.
2. Smoke-test:
   - provider admin, responsible employee, participant and unrelated employee
     on OS detail, PDF, YAML and each write action;
   - client customer/porteiro/zelador/sindico on own/organization OS,
     documents and requests;
   - `/contas` role change with CSRF, audit and session revocation;
   - denied actions show no object metadata and do not mutate the database.
3. Check logs for authorization failures and unexpected `500`s.
4. Only then consider production activation.

## P0-AUTH: reopen gate and partial transactional checks

`POST /os/<id>/abrir` checks the `work_item.reopen` ObjectPolicy decision
for a `Pendente` order with **both** `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`
and `=1`. Only the admin role is granted reopen. The writer repeats this
check using current relationships and current status inside its own
`BEGIN IMMEDIATE` transaction, before any order/client/event change.
For an `Aberta` order the existing edit action continues to apply.

With enforcement enabled, additional guards run *inside their writers'*
transactions for `atribuir`, `assumir`, `arquivar`, both route toggles,
`cancelar` and the transactional photo writer. The guard is injected into
legacy core writers; core does not import the policy or the flavor.

**This is not complete TOCTOU closure.** `iniciar`, `salvar` (including
conclude/cancel), `publicar`, the `em-rota` client-form update, attachment,
invoice, rateio, and certain draft/side-effect paths still execute multiple
transactions or filesystem operations. Some inputs to `abrir` that create a
new provisional client also require transactional service integration.
See the delivery's `BLOCKED.md` and `NOTES.md` before enabling enforcement.

`AUTOSEG_OBJECT_POLICY_ENFORCEMENT` remains **0** by default; do not enable
it in production until the remaining gap is fixed or explicitly accepted.
An in-process lock is not a replacement for a single SQLite transaction.

## P0-AUTH-FINAL — DEV outbox (2026-11-11)

**Estado: implantação somente DEV; enforcement permanece desligado.**
O schema autorizado adiciona exclusivamente `os_effect_outbox` e seus índices;
nenhuma tabela existente é alterada pela instalação. Uma intenção (`operation_key`
SHA-256 de OS/revisão/ação/tipo) é inserida no mesmo `BEGIN IMMEDIATE` do
writer. A execução de PDF, nota/arquivo ou e-mail só começa após commit.

### Instalação autorizada e backup

Na cópia DEV, com o site parado e uma cópia testável do banco:

```sh
AUTOSEG_DEV=1 PYTHONPATH=. python3 scripts/autoseg/install_os_effect_outbox.py \
  --database /caminho/DEV/dados.db \
  --backup /caminho/DEV/backup-before-outbox.db
```

O comando exige backup **novo** com `sqlite3.Connection.backup` e `PRAGMA
quick_check` antes do `CREATE TABLE IF NOT EXISTS`. Reexecutar `install` é
idempotente. É responsabilidade do operador manter o backup em volume seguro,
validar restauração numa cópia e não apontar o comando para a MAIN.

### Recuperação e rollback

Após reinício, reconciliar efeitos `pdf/file` pendentes/falhos por
`os_effect_outbox.dispatch_retryable(banco)` em uma operação de manutenção DEV:

```sh
AUTOSEG_DEV=1 PYTHONPATH=. python3 scripts/autoseg/reconcile_os_effect_outbox.py \
  --database /caminho/DEV/dados.db
```
Duas instâncias competem por lease com `BEGIN IMMEDIATE`; PDF usa nome de versão
reservada, arquivo via hard-link e digest SHA-256. Stages órfãos de transações
revertidas são removidos somente após a idade mínima pelo
`cleanup_orphan_stages`; não apagar arquivos ainda referenciados.

Um envio de e-mail em `processing` com lease expirado torna-se `unknown`.
**Nunca reenviar automaticamente `unknown`:** SQLite + SMTP/Gmail não oferecem
`exactly-once`. O `Message-ID` estável é metadado, não garantia do provedor.
Conciliação manual deve checar o provedor, informar possibilidade de duplicata
e usar uma nova `operation_key` para novo pedido consciente. O destinatário e o
corpo não são persistidos na outbox; devem ser resolvidos no banco no despacho.

Rollback DEV: interromper site e reconciliador, documentar intenção pendente,
reconciliar ou cancelar pendências com auditoria operacional e testar restore
do backup isoladamente. Depois, **manter a tabela dormente** é opção segura;
se for indispensável remover após drenagem, com backup verificado executar
`DROP TABLE os_effect_outbox` somente na DEV. Não reverter OS/eventos válidos.

### Limites restantes

Os caminhos HTTP migrados de mover/publicar/girar/remover anexo e remover
nota fiscal revalidam a OS e registram alterações/eventos na mesma transação.
Staging/quarentena mantêm o filesystem recuperável, mas não fazem dele uma
transação SQLite: quedas de processo ainda podem deixar órfãos para
reconciliação. Chamadas legadas diretamente aos serviços sem `connection` e
operações externas não compartilhadas exigem revisão separada antes da
ativação do enforcement.

## Rollback

1. Set `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0` and restart.
2. `/contas` becomes unavailable; OS operations return to the legacy
   validation path. The extracted command writers remain in place.
3. Do not drop `account_links.client_role` or revert the database migration.
   The column is additive and the default is `customer`; keeping it preserves
   role data for a later activation.
4. Verify provider `/os`, clients, finance, PDFs and the old client portal.

## Validation commands

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_client_roles tests.test_client_roles_http \
  tests.test_object_permissions tests.test_client_web \
  tests.test_officina_web tests.test_login_web \
  tests.test_web_session tests.test_web_cookie tests.test_auth \
  tests.test_accounts tests.test_identity tests.test_object_policy \
  tests.test_policy_shadow tests.test_os_commands -v
```

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_rev12_correcoes tests.test_admin_parity tests.test_portal_v4 -v
```

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  tests.test_autoseg_http_novo tests.test_fluxo_cliente_v94 \
  tests.test_pf_pj_http tests.test_v953_http -v
```

This document is operational guidance, not a security certification.
