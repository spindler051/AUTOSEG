# Security architecture — AUTOSEG

**Status:** living document. It describes the current implementation, the
target boundaries and the known gaps. It is **not** a certification, a
penetration test or a promise that every route is covered.

**Last reviewed:** 2026-11-10, against `main` at `4eb4145`.

**Related documents:**

- `SECURITY.md` — private vulnerability reporting and public-repository data
  policy.
- `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` — target identity,
  tenant and object-policy model, with the current-state audit.
- `docs/operations/SECURITY_AUDIT_2026-11-08.md` — previous action list; it
  covers specific findings, not the complete authorization model.
- `docs/PERMISSIONS_P0.md` — target permission matrix and negative tests.
- `AGENTS.md` — change gates and non-negotiable engineering rules.
- `docs/planning/WEB_GTK_SHARED_CONTRACT.md` — shared presentation contract;
  it does not replace server-side authorization.

---

## 1. Scope and honesty about evidence

This document covers:

- the GTK desktop app;
- the client portal (default port 8765);
- the provider portal (default port 8766);
- the embedded finance API and the desktop JSON API;
- SQLite storage and file storage for attachments, PDFs and drafts;
- Cloudflare tunnels used for remote access;
- authentication, sessions, authorization, PII, money, uploads, logs and
  backups.

Evidence level:

- static review of the modules listed in the planning document;
- existing automated tests (characterization and regression);
- no fuzzing, no dynamic penetration test, no infrastructure review;
- no complete dependency audit (`pip-audit` is not installed in the current
  environment);
- deployment assumptions must be verified per installation.

When this document says “current”, it means the code at the review commit.
When it says “target”, it means the direction in the planning documents, not
implemented behavior.

---

## 2. Assets

| Asset | Why it matters |
|---|---|
| Provider credentials and sessions | Account takeover, impersonation, financial actions |
| Client credentials and sessions | Access to OS history, documents, PII |
| Desktop/API bearer tokens | Full provider API surface if stolen |
| OS data | Client PII, addresses, technical reports, photos, values |
| Financial data | Receivables, payments, rateio, repasses, company cash |
| Attachments, invoices and PDFs | PII, fiscal documents, client-visible reports |
| SQLite database and backups | Complete operational history |
| Secrets/configuration | Gmail, tunnels, tokens, company identity |
| Audit/event history | Investigation and accountability |

---

## 3. Actors and trust boundaries

### 3.1 Actors

| Actor | Authentication today | Scope today |
|---|---|---|
| Anonymous | none | Public pages, PJ quick request, existence/number redirects |
| Client (PF) | CPF + password (`v9_usuarios`) | Own OS, own documents, own requests |
| Client organization responsible | CPF + password + `v9_responsaveis` | Client organization OS |
| Legacy client | ID + password (`cliente_acessos`) | Read-only own OS/PDF |
| Provider | E-mail + password (`prestadores`) | Broad provider portal; admin flag global |
| Provider admin | Provider login + `v9_admin_prestadores` | Global installation administration |
| Desktop API client | Bearer `autoseg_desk_` token | Desktop routes; authorization gaps remain |
| Finance API client | Bearer `autoseg_fin_` token | Read-only `financeiro:read` |
| Platform/local operator | Local GTK session | Local database and services |

### 3.2 Trust boundaries

```text
Internet
  │  HTTPS (Cloudflare tunnel)
  ▼
Cloudflare edge
  │  HTTP to loopback (expected deployment)
  ▼
Client portal :8765 / Provider portal :8766
  │
  ├── in-memory sessions
  ├── CSRF/origin checks
  └── SQLite + files (attachments, PDFs, drafts)

GTK desktop
  ├── LocalService (in-process, local SQLite)
  └── HttpService (HTTPS/JSON to a remote server)

Desktop API / Finance API
  └── bearer tokens -> same SQLite and domain modules
```

The most important boundary is **not** the login page. It is the service layer:
every route, desktop call, API call and GTK action must pass through the same
authorization decision. Today that is not true.

---

## 4. Authentication and sessions

### 4.1 Current controls

- Passwords use PBKDF2-HMAC-SHA256 with random salt; hashes are compared in
  constant time.
- Provider and client web sessions use random tokens, `HttpOnly` and
  `SameSite=Strict` cookies.
- Authenticated POSTs in both portals validate CSRF tokens.
- Provider web sessions revalidate the provider’s active flag and password
  hash on each request.
- Client sessions revalidate the user’s active flag and password hash.
- Desktop API tokens are stored as SHA-256 hashes in `desktop_sessoes`; finance
  API tokens are hashed in `api_tokens`.
- Login attempts have in-memory rate limits; pre-auth bodies are capped at
  64 KB.

### 4.2 Known gaps

- Web sessions and rate-limit maps are **in memory**: a restart clears them and
  multiple processes do not share them.
- There is no persistent account lockout or progressive backoff.
- Client login, client signup and public PJ request do not have a CSRF token;
  they rely on `Origin`/`Referer` and `SameSite`. This is lower risk than an
  authenticated action but remains a gap.
- Provider password reset invalidates web sessions through the stored
  credential hash, but **does not revoke desktop API tokens**.
- The client cookie has no `CLIENTE_HTTPS` equivalent; `Secure` depends on
  Cloudflare/forwarded headers.
- There is no self-service password recovery for providers or clients.
- Session inactivity expiry and durable login audit are not complete.

---

## 5. Authorization

### 5.1 Current state

Authorization is implemented as a collection of per-handler checks, domain
helpers and, in some paths, no check at all:

- `v9_admin_prestadores` is a **global** admin flag, not scoped to a provider
  organization.
- `responsavel_atual`, `os_prestadores`, `os_encerramentos` and
  `produtividade_rateios` are read in different places with slightly different
  fallbacks.
- The desktop API authenticates the provider but does not pass the actor to
  OS/PJ/finance operations.
- Provider portal reads are broader than writes: any authenticated provider
  can open any OS and see client contact/PII in several routes.
- Participation in `os_prestadores` is effectively permanent;
  `prod.participou` ignores the `ativo` flag.
- `ObjectPolicy` exists as a skeleton but is not wired into production.

### 5.2 Target

```text
Principal (account + role + provider/client + active)
  + Resource (object + owner + participants + client + provider org)
  + Action (view/read/edit/assign/conclude/cancel/publish/...)
  -> ObjectPolicy.can/require -> decision + reason + field scope + audit
```

Rules:

- deny by default;
- explicit deny wins over grant;
- admin is scoped to a provider organization, never global by accident;
- client sees only own/client-organization resources;
- provider sees only own/involved resources unless a role grants more;
- PII and finance are field-level permissions;
- the service is the authority; UI hiding is not authorization;
- every sensitive decision is auditable.

### 5.3 Known P0/P1 gaps

| Gap | Impact | Status |
|---|---|---|
| Provider reads any OS, PDF preview, YAML and client contact | PII/financial leakage across providers | Open |
| Desktop API has no actor/object check for OS/PJ | Any provider token can act on any OS/PJ | Open |
| No provider-org/tenant boundary; admin is global | Cross-company leakage in multi-org use | Open |
| Participation is permanent | Removed provider keeps PDF/photo/NF access | Open |
| Password reset does not revoke desktop tokens | Old token remains valid | Open |
| `GET /organizacoes/responsaveis` lacks admin gate | Organization/PF PII leak to any provider | Open |
| `POST /os/<id>/publicar` lacks responsibility check | Any provider can publish a report | Open |
| Tests assert some leaks as expected behavior | Future regressions look “green” | Open; invert with policy |

The finalizer-attribution bug (admin concluding another provider’s OS) was
fixed in `d0186cb`: the current responsible is the financial finalizer, the
admin remains the audit actor, and a stale secondary share is absorbed. This is
covered by regression tests.

---

## 6. Network exposure and transport

- Default bind is loopback (`127.0.0.1`) through `runtime_config` and the CLI.
- `ServidorPortal.__init__` still defaults to `0.0.0.0`; direct instantiation
  without an explicit host is a footgun.
- Cloudflare tunnels provide HTTPS at the edge and forward to loopback HTTP.
  This is acceptable only if the origin remains loopback and the tunnel is the
  only remote path.
- Direct remote HTTP with credentials is prohibited.
- `Secure` cookies depend on `PRESTADOR_HTTPS`, Cloudflare headers or
  `X-Forwarded-Proto`; forwarding headers must only be trusted from a trusted
  proxy.
- The finance API and desktop API are additional surfaces; they must not be
  exposed without TLS, token scope and rate limits.

**Rule:** remote exposure requires HTTPS, a trusted reverse proxy/tunnel,
request-size limits, rate limits and human security review. HTTP is for
loopback/development only.

---

## 7. Files, attachments and documents

### 7.1 Current controls

- Attachments on disk use random names (`secrets.token_hex(16) + extension`);
  the original name is stored in the database, not used as the path.
- PDF report names are sanitized from the OS number.
- YAML import uses `yaml.safe_load`.
- Operational data lives outside the repository with restricted permissions.
- Image upload validates image content before storing.

### 7.2 Gaps and rules

- Validate real content/magic, not only extension/MIME.
- Keep per-operation size limits, quotas and a global upload concurrency cap.
- Store files outside public directories.
- Validate paths against traversal/symlinks before reading or deleting.
- Do not log attachment content or original filenames with PII.
- Keep backups encrypted/access-controlled and test restore.
- A published PDF is a client-visible document; publishing requires
  responsibility/admin authorization and audit.

---

## 8. Money and financial integrity

- The legacy schema uses SQLite `REAL`; application contracts use `float` in
  places; the finance API uses integer cents.
- This mixed representation is a correctness risk for discounts, rounding,
  rateio, repasses and partial payments.
- Target: integer cents at the application boundary (or `Decimal` with explicit
  rounding), with adapters for legacy `REAL`.
- The final OS total is authoritative; discounts/visit fees must be explicit
  and persisted, not hidden by redistributing labor.
- Financial mutations need audit events, concurrency control and negative
  tests.
- Money/authorization changes are N3/N4 and require human review.

---

## 9. Secrets and configuration

- No secrets in the repository; company identity and integrations come from
  environment/configuration.
- Tokens are stored as hashes where the design supports it.
- Private signing keys are not stored in plaintext. The preferred modes are OS
  keychain or hardware. If an encrypted signing key is stored server-side, the
  convenience mode is opt-in, uses an Argon2id-derived KEK, keeps the unlocked
  key only in memory and warns that the login password becomes a signing input.
  See `docs/planning/PGP_MULTISIGNATURE_ARCHITECTURE.md` §3.2.
- Never log tokens, cookies, passwords, private keys or full request bodies.
- Rotate provider/API tokens after exposure; revoke old tokens.
- Password reset must revoke desktop/API sessions (currently a gap for desktop
  tokens).
- Backups must not contain credentials in plaintext or be committed.

---

## 10. Logging, audit and privacy

- OS events, feedback events and access logs exist, but there is no single
  durable security audit stream for every permission decision.
- Logs must minimize PII: IDs, action, result, reason and timestamps; not
  names, CPF/CNPJ, phone, e-mail, address, attachment content or tokens.
- The shadow policy log (`policy_shadow.jsonl`, when enabled) is an example of
  the intended privacy-safe format.
- Define retention, access control and export/deletion rules before production.
- Denied authorization decisions should be auditable without leaking the
  object’s sensitive content.

---

## 11. Backup, availability and recovery

- SQLite uses WAL; backups must use a consistent backup mechanism, not a raw
  file copy of a live WAL database.
- Test restore, not only backup.
- Protect backups with the same or stronger access control as the live data.
- Upload limits, thread limits and request timeouts need a global policy; a
  per-request 90 MB limit alone does not bound aggregate memory/disk use.
- Rate-limit maps and sessions are process-local; horizontal scaling requires
  a shared store or sticky sessions.

---

## 12. Incident response

1. **Report privately:** use GitHub private vulnerability reporting; do not
   open a public issue with real data.
2. **Contain:** stop the exposed process/tunnel, revoke tokens/sessions, rotate
   secrets, preserve logs and database snapshots.
3. **Assess:** identify affected accounts, OS, clients, files and financial
   records; check audit/event history.
4. **Notify:** follow applicable legal/contractual duties; do not publish real
   client data.
5. **Recover:** restore from a verified backup, re-enable access gradually,
   monitor.
6. **Learn:** write a postmortem with timeline, root cause, detection gap and
   follow-up tests; update this document and the change gates.

---

## 13. Security invariants

1. The server/service is the authorization boundary; the UI is not.
2. No client/provider sees another provider’s OS or PII without an explicit
   relationship or grant.
3. No cross-provider/tenant access by accident.
4. Money uses one canonical representation at the boundary.
5. Remote access uses HTTPS; HTTP is loopback/development only.
6. Uploads are content-validated, size-limited, quota-limited and stored
   outside public paths.
7. Secrets and PII never appear in logs, commits, tests or examples.
8. Admin changes and sensitive financial actions are audited; the last admin is
   protected.
9. Backup and restore are tested; a backup is not a raw copy of a live WAL
   database.
10. No new route/service without actor, permission, object/tenant and a
    negative test.

---

## 14. Verification status and next reviews

| Area | Status |
|---|---|
| Static authorization review | Done for the modules in the planning audit; not exhaustive |
| Negative authorization tests | Partial; some existing tests assert leaks |
| Dynamic penetration test | Not done |
| Dependency audit | Not done (`pip-audit` absent) |
| Remote deployment/TLS review | Per installation; not certified here |
| Backup/restore drill | Pending |
| Logs/PII review | Partial; retention undefined |
| Multi-tenant isolation | Not implemented |

Review triggers:

- before any public/remote exposure;
- before enabling multi-provider/multi-tenant;
- before changing authentication, sessions, permissions, money, uploads or
  backups;
- after a security incident;
- when a new surface (API, portal, client, plugin) is added.

This document must be updated in the same PR as any security-relevant change.
