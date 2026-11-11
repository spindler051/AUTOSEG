# Officina Web — durable web sessions rollout

**Scope:** unified web session storage for the provider/client site. Desktop
bearer sessions (`desktop_sessoes`) are not migrated in this slice.

## Flag

```text
AUTOSEG_WEB_SESSION_DURABLE=0   # default: process-local memory sessions
AUTOSEG_WEB_SESSION_DURABLE=1   # SQLite web_sessions, shared and persistent
```

- `0`: `web_session` keeps sessions in memory, exactly as before. Any
  `web_sessions` rows are ignored.
- `1`: `PortalPrestador.iniciar()` runs `web_session.install(banco)`, and all
  unified web sessions use SQLite.
- `AUTOSEG_UNIFIED_LOGIN` and `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` are separate
  flags. This flag only changes where web sessions live.

## Storage invariants

- The opaque token is never stored; only its SHA-256 hash.
- The password hash is never stored; only its SHA-256 fingerprint.
- No name, e-mail, CPF, document content or file path is stored in
  `web_sessions`.
- CSRF and telemetry IDs are random and private; `SessionData`/`SessionContext`
  redact their repr.
- `resolve` reloads identity, membership, role, organization scope and
  `client_org_ids`, then revalidates the credential fingerprint.
- Expiry, account revocation and identity revocation are database operations.
- Sessions are shared across local processes using the same database file and
  survive a restart.

## Activation

1. Review/integrate the slice and run the focused, regression and old-client
   portal suites.
2. Back up the database and confirm restore on an isolated copy.
3. Enable the flag in a controlled environment and restart the provider
   process. `web_session.install` is idempotent.
4. Smoke-test provider and client login, `/sair`, role change, password reset,
   deactivation and restart.
5. Verify that a second local process sees the same session and that revoking
   it invalidates both.

## Transition and rollback

- Existing in-memory sessions are **not** migrated when the flag changes.
  Users log in again after the switch.
- Reverting to `0` ignores durable rows and returns to in-memory sessions; it
  does not delete `web_sessions`.
- Do not drop or rewrite `web_sessions` as part of a flag-only rollback.
- A restart does not revoke valid durable sessions; use `/sair`, password
  reset, deactivation or explicit revocation when needed.

## Tests

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_web_session_durable tests.test_session_context \
  tests.test_web_session tests.test_login_compat tests.test_login_web \
  tests.test_client_roles tests.test_object_permissions \
  tests.test_officina_web tests.test_auth tests.test_accounts -v
```

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_rev12_correcoes tests.test_admin_parity tests.test_portal_v4 -v
```

GTK visual behavior requires `gi`; if unavailable, record the exact error and
do not claim a visual pass. Contract/navigation tests run without GTK.

This document is operational guidance, not a security certification.
