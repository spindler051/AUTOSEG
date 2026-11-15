# AUTOSEG / Officina API 2.0 — design plan

**Status:** planning. Not scheduled, no code, no schema change.
**Trigger:** Meu Auto Financeiro needs a clean read boundary. Patching `/api/v1`
would produce permanent compatibility debt, so the boundary is redesigned as v2
and the database read is removed entirely.

Related: [`MAF_AUTOSEG_READ_INTERFACE.md`](MAF_AUTOSEG_READ_INTERFACE.md),
[`LOCAL_SYNC_MODES_ANALYSIS.md`](LOCAL_SYNC_MODES_ANALYSIS.md) §8.

## 1. Why a version, not a patch

`/api/v1` was built for one consumer — the GTK desktop in server mode — and it
shows:

- responses shaped like SQL rows (`lancamentos`, `rateios`, `repasses`), which
  force every consumer to re-implement joins and business rules;
- filters baked into the endpoint (archived OS excluded) with no way to express
  the consumer's real predicate;
- no way to exchange credentials for a token, so a separate product cannot link
  an account without copying tokens by hand;
- no consistency token, so a consumer can never tell whether two reads saw the
  same database state;
- one auth model for all consumers.

Adding `include_archived=1` and a link endpoint to v1 would work — and would
leave v1 as a permanently ambiguous contract with two meanings per field. That
is the wrong trade. v2 is introduced alongside, v1 stays frozen until its
consumers move, then v1 is removed.

**Hard rule that comes out of this:** no product reads `dados.db` directly. The
API is the only boundary. The embedded-MAF read was the exception that survived
too long.

## 2. Principles

1. **Use-case projections, not tables.** Consumers ask for "the receipts I am
   owed", not for a join across four tables.
2. **One identity per item.** Every ledger item has a stable, opaque key that
   survives recomputation, so consumers can diff without heuristics.
3. **Explicit semantics.** No hidden default filters. Archived, cancelled and
   partially paid are addressable states, never silent exclusions.
4. **Integer cents, ISO-8601 UTC, opaque cursors.** No floats, no local time,
   no offsets.
5. **Deterministic reads.** Every response carries the snapshot it was computed
   from; consumers can request deltas since a snapshot.
6. **Scoped, revocable, audited access.** Per device, per consumer, no shared
   token, no password retention.
7. **Additive evolution.** v2 grows by adding fields and endpoints; breaking
   changes require v3 and a deprecation window.

## 3. Resource model

Minimal surface for the first real consumer (MAF), designed so a second
consumer does not need a new dialect.

```text
POST /api/v2/authorize          credentials → single-use link code (60 s)
POST /api/v2/token              link code → device token + refresh token
GET  /api/v2/me                 identity, scopes, linked provider

GET  /api/v2/finance/ledger     the consumer's own money movements
GET  /api/v2/finance/summary    totals over the same predicate
GET  /api/v2/sync/checkpoint    current snapshot id and counters
GET  /api/v2/health             liveness, no auth, no data

POST /api/v2/token/revoke       revoke this device
GET  /api/v2/tokens             list devices, no secrets
```

### `finance/ledger`

The core projection. One row per movement the consumer is entitled to see, with
the composition already resolved server-side.

| Field | Type | Notes |
|---|---|---|
| `key` | string | stable identity, e.g. `os:8241` / `repasse:9981` |
| `kind` | enum | `receipt`, `repasse_in`, `repasse_out`, `adjustment` |
| `status` | enum | `received`, `pending`, `partial`, `cancelled` |
| `amount_cents` | integer | signed, already net of rateios where applicable |
| `gross_cents` | integer | face value before splits |
| `os` | object | `{id, numero}` — no customer PII unless scoped |
| `customer_name` | string | only if the token carries `finance:read:customer` |
| `description` | string | server-owned, stable wording |
| `occurred_at` | string | ISO-8601 UTC |
| `settled_at` | string \| null | ISO-8601 UTC |
| `archived` | boolean | explicit, never a hidden filter |
| `snapshot` | integer | snapshot at which this row was computed |

Query parameters, all explicit:

```text
?since=<snapshot>        delta mode
?include_archived=true   default false, but visible in the response meta
?kind=receipt,repasse_in
?limit=200&cursor=…
```

The response always states the effective predicate in `meta`, so a consumer can
never be surprised by a filter it did not ask for.

### `finance/summary`

Totals computed from the **same** predicate as `ledger`, in the same snapshot,
so a consumer can never show a total that disagrees with its list. Fields:
`receivable_cents`, `received_cents`, `awaiting_confirmation_cents`,
`currency`, `snapshot`.

## 4. Identity and auth

```text
1. consumer collects e-mail + password (same screen as today)
2. POST /api/v2/authorize      → {code, expires_in: 60}
3. POST /api/v2/token          → {access_token, refresh_token, scopes, provider}
4. consumer discards the password
```

- access token: 15 min, bearer, bound to device id
- refresh token: long-lived, rotatable, revocable per device
- scopes: `finance:read`, `finance:read:customer`, later `orders:read`
- every token has an audit trail: created, used, revoked
- password verification stays server-side and is never part of a read endpoint
- rate limit and lockout per account and per device

Why not keep "verify password per sync": it forces the consumer to store or
re-prompt for a secret, which is exactly the coupling we are removing.

## 5. Consistency model

Full re-reads are O(n) and racy. v2 exposes a monotonic `snapshot`:

- the server increments `snapshot` inside the write transaction that changes
  finance or productivity data;
- every read reports the snapshot it used;
- `since=<snapshot>` returns only items created or changed after it, plus
  `tombstones` for deletions and cancellations;
- the consumer stores `last_snapshot` and can prove it is current.

This turns reconciliation from "poll everything every 15 s" into a bounded,
deterministic delta — and makes double-crediting impossible to reach by
accident.

## 6. Errors, limits, versioning

- error envelope: `{error: {code, message, details}, request_id}`; stable codes,
  human text is not an API surface
- `429` with `Retry-After`; per-token quota
- `meta.limit`, `meta.has_more`, `meta.next_cursor` on every list
- OpenAPI 3.1 kept in sync; a contract test compares it to the handler
- v2 lives beside v1; v1 is frozen (security fixes only) and removed only after
  its consumers move

## 7. Compatibility and deprecation

| Phase | v1 | v2 |
|---|---|---|
| now | active | — |
| v2 shipped | frozen, documented as legacy | active |
| MAF + GTK migrated | security fixes only | active |
| after window | removed | active |

Deprecation requires: a named replacement, a migration guide, and at least one
release cycle of overlap. No silent removal.

## 8. Consumers and what each needs

| Consumer | Needs | Notes |
|---|---|---|
| MAF | ledger, summary, checkpoint, authorize | first migration target |
| GTK desktop | orders, customers, finance, stock | broad; may stay on v1 longer |
| future client portal | own orders and documents | different scopes |
| relay / auxiliary node | never | relay is transport, not an API consumer |

## 9. Migration plan

1. Define v2 contract + OpenAPI, no implementation.
2. Implement `authorize`/`token` and `finance/ledger` + `summary` + `checkpoint`.
3. Build the MAF adapter against v2; keep the SQL adapter until parity is proven
   on the production snapshot (see the MAF item's parity matrix).
4. Switch MAF; remove its filesystem access.
5. Freeze v1; migrate GTK when it next changes.
6. Delete v1 and the direct-read path.

## 10. Non-goals

- no GraphQL, no streaming, no webhooks in v2.0;
- no write endpoints for third-party consumers yet;
- no P2P or relay semantics;
- no public exposure of finance endpoints without a named tunnel and Access;
- no schema change beyond the token/snapshot tables.

## 11. Open questions

1. Snapshot source: a dedicated counter table, or `max(rowid)` per family?
2. Do cancelled items ship as tombstones or as `status=cancelled`? (proposal: both, with `since`)
3. Is `customer_name` in scope by default, or a separate scope from day one?
4. Does GTK keep local DB access as an internal component, or become a pure API client?
5. Rate-limit budget for a 15 s polling consumer vs a delta consumer.

## 12. Relation to the queue

This is **not** part of A5b/A5c. It is the prerequisite for the MAF read
interface item, which is P1 after the security queue. Nothing here authorizes
implementation; the first executable step would be a contract-only delivery
(OpenAPI + examples + parity fixtures), reviewed before any handler exists.
