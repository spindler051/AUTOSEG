# AUTOSEG — Unified login rollout and rollback

**Scope:** provider portal only. The client portal and legacy provider login remain available.
This is a staged, opt-in rollout and is **not** authorization to enable production
without the security review and integration test suite.

## Preconditions

1. Review and integrate pieces 5.1–5.5 in order, including the 5.3/5.4 portal
   patch before applying the 5.5 compatibility patch. Confirm the actual
   `portal_prestador.py` diff and execute all relevant test suites.
2. Take a verified backup of the current AUTOSEG SQLite database and relevant
   configuration; confirm restore procedures on an isolated copy. Keep the
   existing provider and client login routes available.
3. On an isolated copy of the database, run `accounts.install(banco)` and
   `accounts.migrate_legacy(banco, dry_run=True)`. Review the migration report,
   especially identifier collisions, before any actual migration. No migration
   occurs automatically when the portal starts or when a flag changes.
4. After human approval and backup, explicitly migrate the chosen environment
   with `accounts.migrate_legacy(banco, dry_run=False)`. Repeat a dry-run and
   use `login_flags.activation_report(banco)` to check readiness. The report is
   read-only; do not enable the feature when it reports blockers.
5. Confirm the origin is only reachable through the intended loopback or trusted
   Cloudflare access path. `CF-Ray` and `X-Forwarded-Proto` are only safe TLS
   hints when untrusted clients cannot inject those headers at the origin.
6. While the desktop and portal still write to `prestadores` and `v9_usuarios`,
   migrated accounts read password hash, role and activation from the legacy
   record. Account identifiers are copied at migration time: after changing a
   provider/client email, CPF or phone in the legacy app, run
   `accounts.migrate_legacy(banco, dry_run=True)` again, review the report and
   re-import before relying on the new identifier. Old identifiers are not
   removed automatically.
7. Run the relevant suites before activation:
   `python -m unittest tests.test_login_compat tests.test_login_web
   tests.test_web_session tests.test_web_cookie tests.test_auth
   tests.test_login_flags tests.test_accounts -v`.

## Activation (controlled environment first)

1. Keep `AUTOSEG_UNIFIED_LOGIN` unset or set to `0` until ready. Its default is off.
2. Set `AUTOSEG_UNIFIED_LOGIN=1` for the provider-portal process and restart it.
3. Open `/entrar` and authenticate as a test provider. Check the browser gets
   the `autosseg_unified` cookie with `HttpOnly`, `SameSite=Strict`, and `Secure`
   for HTTPS/proxy traffic. Verify the authenticated provider sees only their
   authorized areas.
4. Check `/login` still authenticates with the old `autosseg_session` cookie,
   and `/entrar-pf` plus the separate client portal are unchanged.
5. Check logout clears **both** browser cookies and invalidates both server
   sessions. Confirm that replaying either old cookie does not authenticate.
6. Test provider password reset, deactivate, archive, and administrative-role
   change: each action must revoke all unified sessions for the affected
   provider. Verify the legacy password-hash and active-state protections still
   apply as before.
7. Smoke-test representative OS read/edit, documents/PDF, and financial pages
   with approved test accounts. Check CSRF protection and a rejected request
   with an invalid origin. `/entrar` shares the existing 10-attempts/10-minutes
   per-IP limiter with `/login`; confirm the rollout still behaves as expected
   behind the proxy.

## Rollback

1. Set `AUTOSEG_UNIFIED_LOGIN=0` (or remove the variable) and restart the
   provider server. `/entrar` redirects to `/login` and unified cookies are
   ignored. Legacy provider and client login remain available.
2. The in-memory unified session map disappears on restart; clear browser
   cookies by using the logout flow or normal browser cookie controls.
3. **Do not delete** `accounts` or other tables and **do not revert a database
   migration** as part of this flag-only rollback. The legacy login data stays
   available, and rollback does not rewrite financial or historical records.
4. Verify provider `/login`, client portal, OS, PDFs, and finance after rollback.
   Escalate any discrepancy for an authorized restore from the verified backup.

## Operational constraints

- Unified sessions are process-local and last at most eight hours; they do not
  survive a restart, support multi-process sharing, or provide persistent
  revocation across independent processes.
- Legacy and unified cookies coexist only during migration; the new cookie
  does not make the client portal part of a common site.
- For migrated accounts, the legacy provider/client row remains the source of
  truth for password, role and activation. The `accounts` row is the account
  identifier/ownership record; native accounts use the account store. Unified
  sessions are revoked when those legacy values change.
- The imported identifiers are a snapshot. Re-run the dry-run and migration
  after legacy identity changes; stale identifiers are not deleted.
- The new `/entrar` implementation uses the existing pre-auth origin check and
  `SameSite=Strict`, not an authenticated-session CSRF token. It shares the
  legacy per-IP rate limiter. A separate review should still assess the legacy
  origin-check behavior before production activation.
- The `activation_report` reflects database readiness, not a penetration test
  or approval to deploy. Human review of authentication/permissions is required.
