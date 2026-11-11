# Officina Web — object-policy enforcement rollout

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
