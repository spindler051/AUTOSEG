# Audit completeness and activity view

**Status:** planning, P1. No code, no schema change yet.
**Trigger:** the tracker records some actions but cannot answer "what did this
employee do", "who created this client", or "who changed this OS" in one place.

## 1. What exists today

`portal_auditoria(prestador_id, acao, referencia, detalhes, criado_em)` is
written by `portal_negocios.audit()` and covers:

| Action | Recorded | Actor |
|---|---|---|
| client created / edited / deleted | yes | `prestador_id` |
| OS created / changed / closed / cancelled | yes (+ `os_eventos`) | id + name |
| receipt confirmed / cancelled / due date | yes | id |
| PDF generated (preview / publish) | yes | id |
| feedback triage | yes | id |

Secondary stores: `os_eventos` (per-OS, id + display name), and
`v9_historico_clientes` (client history, **name string** only).

## 2. What is missing

1. **No reader.** Nothing in the code queries `portal_auditoria`; it is
   write-only. There is no screen or report.
2. **Password reset is not recorded** (the writer is now admin-guarded, but
   silent).
3. **Admin grant/revoke is not recorded** (`definir_admin` writes only to
   `v9_admin_prestadores`).
4. **Deactivate and merge bypass the central table**; they write a name into
   `v9_historico_clientes`.
5. **Actor is inconsistent**: id in one table, display name in another. No
   role, no surface.
6. **No logins**, and client (customer) actions are not in the same stream.
7. **Not append-only.** Any process with database access can update or delete a
   row.

## 3. Target

### 3.1 One writer

```text
log_action(connection, principal, action, target_type, target_id,
           detail=None, before=None, after=None)
```

Every audited write goes through it, inside the same transaction as the change.
Fields recorded per row:

| Field | Value |
|---|---|
| `actor_id` | `prestador_id` (or client account id) |
| `actor_role` | `admin` / `employee` / `client` **at the time** |
| `client_app` | `web` / `gtk` / `api` — server-asserted |
| `action` | stable key: `customer.create`, `customer.password`, `admin.grant`, … |
| `target_type` / `target_id` | `customer`/`42`, `work_item`/`52`, `provider`/`7` |
| `detail` | human-readable diff or reason |
| `before` / `after` | optional structured snapshots for the audited fields |
| `created_at` | UTC |

The action keys follow the surface registry where one exists, so the audit and
the permissions speak the same vocabulary.

### 3.2 Coverage

The writer must be called by:

- customer: create, edit, delete, deactivate, merge, password;
- work item: create, edit, close, cancel, reopen, attachment add/remove;
- finance: receipt, cancel, due date, invoice attach;
- identity: admin grant/revoke, account link/unlink, login and failed login;
- feedback triage.

No audited operation may commit without its row.

### 3.3 Read model

- an admin-only **Activity** view: filter by user, customer, action, date;
- per-entity timeline (customer, work item, provider);
- the same view on Web and GTK — feature parity applies;
- read access follows the same object policy: an employee sees their own
  actions, admins see the organization's.

### 3.4 Integrity

- no application path updates or deletes an audit row;
- later, a per-organization hash chain (`prev_hash`, `row_hash`) makes silent
  tampering detectable;
- backup and restore must preserve the chain.

## 4. Migration

- additive columns only (`actor_role`, `client_app`, `target_type`,
  `target_id`, optional `before/after`); existing rows keep `NULL` and remain
  readable;
- backfill is not attempted for historical rows; the old `acao`/`detalhes`
  format stays valid;
- no rewrite of `portal_auditoria` in place without a verified copy.

## 5. Tests

- each audited writer emits exactly one row with the right actor, role, surface
  and target;
- a denied operation emits no row and changes nothing;
- activity filters return only what the principal may see;
- an employee cannot read another employee's activity;
- no code path issues `UPDATE`/`DELETE` on the audit table;
- legacy rows (NULL role/surface) still render.

## 6. Non-goals

- no external log shipping, SIEM or real-time alerting;
- no per-field history for every table — only the actions listed in §3.2;
- no client-side analytics;
- no change to authentication or session model in this item.

## 7. Open questions

1. Extend `portal_auditoria` or create a new `activity` table? (proposal:
   extend, because existing writers and tests already use it)
2. Is the actor for client actions `v9_usuarios.id` or the linked `clientes.id`?
3. Retention policy per organization, and who may export it?
4. Does the relay/auxiliary node ever see activity rows? (it must not)
5. Hash chain now or after coverage is complete?
