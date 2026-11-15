# Meu Auto Financeiro — product and architecture

**Status:** planning. No code, no schema, no migration.
**Scope now:** personal and family finances. Company finances later, as a mode
of the same core, not a second product.
**Relationship:** MAF is a separate product that inherits the good parts of
AUTOSEG/Officina and none of the shortcuts. It is not part of AUTOSEG, and it
does not read the AUTOSEG database.

> This document is a design direction, not a specification of someone else's
> manifesto. Names and buzzwords from external drafts were dropped; only the
> principles that survive contact with this codebase are kept.

## 1. What MAF is

A self-hostable financial management platform for one person, one family, or
(someday) one small company. It consolidates accounts, transactions, budgets and
recurring commitments, imports statements from institutions that have no API,
and optionally connects to banks through replaceable adapters.

What it is **not**:

- a bank, a payment institution, or a licensed data aggregator;
- a blockchain or a P2P ledger;
- an "open finance" product — that term belongs to regulation, not to this
  software;
- a company ERP in the first phase.

## 2. What MAF inherits from Officina

The good parts, all already proven in AUTOSEG:

| Inherit | Why |
|---|---|
| server-authoritative domain | one place decides money, balances and rules |
| one versioned HTTP API | every client uses it; nothing reads the database |
| CLI over the same services | scripting and recovery without a GUI |
| declared UI contract | GTK, Qt, Swift, Compose render the same actions |
| capability-based authorization | role is a bundle; clients get grants |
| audited actions | who did what, with role and client, append-only |
| relative file storage | data root can move; no absolute paths in the DB |
| explicit migrations | schema changes are tested and reversible |
| offline-first clients | local cache, queue, reconcile; server is authority |

What it must **not** inherit:

- reading another product's SQLite file (the current AUTOSEG bridge);
- HTML builders tangled with business rules;
- per-surface permission branches;
- absolute paths stored in rows;
- a monolith where routing, rendering and domain live in one file.

## 3. Layers

```text
clients      GTK · Qt · Swift · Compose · Web · CLI
                    │  one HTTP contract (JSON, versioned, OpenAPI)
api          resources + actions; no HTML, no SQL
application  use cases: post, reconcile, budget, report
domain       accounts, transactions, ledger, categories, budgets, goals
adapters     banking, imports, payments, payroll — replaceable
storage      SQLite now; PostgreSQL when multi-user demands it
```

Rules:

- clients never see SQL, table names or internal ids beyond stable public ids;
- the CLI is a first-class client, not a debug tool;
- adapters never leak provider fields into the domain model;
- the domain never imports an adapter.

## 4. The ledger is the source of truth

External data is not the truth. Four distinct things:

| Concept | Meaning |
|---|---|
| **external transaction** | what the bank or provider reported, as received |
| **normalized transaction** | the internal financial event, deduplicated and categorized |
| **ledger entry** | the accounting representation (double-entry or single-entry, one convention) |
| **reconciliation** | the act of matching external against internal |

Why: bank entries arrive late, change, duplicate, reverse or get corrected.
History must survive a provider change. A bank balance and the calculated ledger
balance are allowed to differ, and the difference is a visible state, not a bug.

Consequences:

- money is integer cents; currency is explicit; no floats anywhere;
- every mutation of the ledger is an event, never an in-place overwrite;
- a correction is a new entry that references the original, not an edit;
- reconciliation state is per account and per period.

## 5. Integration contract

Every external source is an adapter behind one interface:

```text
capabilities()            what this provider can and cannot give
authorize()               user consent / credentials / token exchange
sync(cursor)              incremental pull, idempotent by external id
handle_webhook(payload)   optional
health()                  status, quota, last successful sync
```

Requirements:

- **capabilities are declared**, because providers differ: balances or not,
  investments or not, holder data or not. The UI shows what is missing instead
  of pretending everything is uniform;
- **credentials live in a vault**, are revocable, and never enter the domain
  model or logs;
- **sync is idempotent**: the same external transaction twice is one row;
- **adapters are optional**: the product is fully usable with manual entry and
  file import;
- **file import is the universal baseline**: OFX, CSV, CAMT, QIF — every
  institution can export something;
- **provider failures degrade** to "last synced at", never to data loss.

Brazil is the first localization, not the architecture: PIX, boleto, CPF/CNPJ,
BRL formats and Open Finance adapters belong to a `br` module. Another country
adds its module without touching the core.

## 6. Identity, family, and permissions

- a **user** is a person with an account;
- a **household** groups users who share accounts and budgets;
- roles are bundles: owner, adult member, viewer; a role is never tied to a
  client application;
- a **client app** (GTK, CLI, future mobile) receives a grant at login;
- the effective capability set is the session grant, as in Officina;
- per-user exceptions (e.g. "admin only in the desktop app") are configuration,
  resolved server-side from the token family.

## 7. Audit

Every sensitive action writes one row in the same transaction: actor, role,
client app, action, target, before/after when relevant. No update or delete path
for audit rows. A later hash chain makes tampering detectable.

Who created an account, who changed a budget, who imported a statement, who
granted access — all answerable, per user and per entity.

## 8. Data ownership

- full export in documented formats (JSON + the original imports);
- no provider-specific export required to leave;
- deleting an adapter never deletes history;
- self-hosting is a first-class deployment: one binary or one container, a data
  directory, a backup command.

## 9. Deployment

| Phase | Storage | Notes |
|---|---|---|
| personal / family | SQLite | single file, WAL, backup by copy of a consistent snapshot |
| shared household | SQLite first | server per household |
| company mode | PostgreSQL | multi-user, migrations, roles |

Container image is optional; a systemd unit and a CLI are enough.

## 10. Phases

| Phase | Deliverable |
|---|---|
| 0 | this document; inventory of what MAF already does |
| 1 | API contract + CLI over the current core (extract from `servidor_maf.py`) |
| 2 | one real client (GTK or web) rendered from the UI contract |
| 3 | imports (OFX/CSV) and the ledger/reconciliation model |
| 4 | bank adapters behind the capability interface |
| 5 | company mode on the same core |
| 6 | sync/relay, only if a real need appears |

Each phase is independently useful. No phase depends on a proprietary provider.

## 11. Non-goals for now

- company finance, payroll and accounting (later mode, not now);
- any specific aggregator contract or banking licence;
- real-time market data, investments beyond manual records;
- AI features (optional and replaceable if they ever exist);
- mobile apps (the contract comes first);
- blockchain, P2P, or any distributed ledger.

## 12. Open questions

1. Single-entry or double-entry ledger for personal finance? (proposal:
   double-entry internally, simplified projection for the UI)
2. One database per household, or one database with tenant ids? (proposal: per
   household for personal, tenant ids for company mode)
3. Does the CLI authenticate as a device, like a mobile client?
4. Where does the UI contract live — same registry format as Officina?
5. How much of AUTOSEG's `ObjectPolicy` is worth reusing versus simplifying for
   a two-role household model?
