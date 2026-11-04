# Platform migration playbook

**Purpose:** turn AUTOSEG into a flavor of a generic, modular platform without
changing its current usability. This is a working method for humans and AI
agents, not a feature roadmap.

Related documents:

- `docs/PRODUCT_VISION.md`
- `AGENTS.md`
- `docs/HUMAN_CENTERED_DECISIONS.md`
- `docs/USER_FEEDBACK_GUIDE.md`
- `docs/PLATFORM_MIGRATION_LEDGER.md`
- `workaholic/docs/ARCHITECTURE.md`
- `docs/MIGRACAO_MODULAR.md`

## 1. The core rule: one small platform delta per change

Every non-trivial change must include **one** of these:

- a small migration of one slice;
- extraction of one stable contract;
- an adapter that removes one direct legacy dependency;
- a characterization test that protects current behavior;
- a documentation/ledger update that unblocks the next slice.

If none is safe, the change must say:

```text
Platform delta: none
Reason: <why a structural change would add risk>
Next opportunity: <issue or slice>
```

This is a **boy-scout rule with a scope limit**, not permission to refactor
everything. A bug fix must not become a 2,000-line migration. Prefer a separate
commit/PR for the structural delta.

### Suggested budget

- Keep the structural delta below roughly 20% of the change.
- If the delta is larger, split it into its own PR.
- One PR must not mix a UX redesign, a database migration and a new module.
- Every release should move at least one ledger item or explicitly record why
  the release was maintenance-only.

Numbers are guidance, not a ritual. The important part is that platform work
does not become an occasional “big project” that is abandoned for months.

## 2. Workaholic fit check

Before implementing a domain feature, classify it:

| Question | Destination |
|---|---|
| Useful to any worker/business? | Workaholic core + schema |
| Defined by Brazilian law/regulation? | Brazilian locale module |
| Specific to security/automation? | AUTOSEG flavor |
| Only presentation/navigation? | GTK shell |
| Still unclear? | Keep legacy for now; record a decision and next step |

Rules:

- Core does not import AUTOSEG, GTK or fiscal modules.
- A flavor/locale module may depend on core contracts.
- New Workaholic work must have a consumer, adapter or integration issue.
- “We will integrate it later” is not a plan; write the follow-up issue in the
  same PR.

## 3. The migration recipe

### Step 0 — choose a bounded slice

Good first slices are small, well-defined and low-coupling. Avoid starting with
the entire service-order workflow or the entire financial system.

Recommended candidates, in discussion order:

1. `catalogo_servicos` / service catalog and materials.
2. `ordem_servico` / service orders (high value, high coupling).
3. `financeiro` / receivables and payments.
4. `prestadores` / providers and assignments.
5. `estoque` / stock.
6. Portals and fiscal documents (likely flavor/locale modules, not core).

The order is a decision, not a fixed law. Record the choice in the ledger.

### Step 1 — write characterization tests

Before changing the implementation, capture current behavior:

- create/list/update/archive;
- validation and error messages that users see;
- money and percentage rounding;
- status transitions;
- relations and permissions;
- PDF/email/financial side effects.

These tests are the parity contract.

### Step 2 — define the generic contract

If the slice is generic, define its Workaholic schema and application service.
If it is vertical/locale, define the interface the flavor will consume.

Do not put Portuguese field labels or AUTOSEG business rules in the core.

### Step 3 — build an adapter around the legacy table

Use the existing tables as the source of truth at first. The adapter maps a
generic record to legacy columns and back. Preserve legacy integer IDs as
origin metadata.

### Step 4 — switch reads first

Read through the adapter while writes remain legacy. Compare results in tests.
Do not change the UI.

### Step 5 — switch writes

Move writes behind the adapter, one entry point at a time:

- desktop GTK;
- provider portal;
- client portal;
- importers/CLI;
- background jobs.

Keep the old path available behind a feature flag until parity is proven.

### Step 6 — verify parity

- run characterization tests;
- run the relevant regression suites;
- test a backup/restore cycle;
- test an old database and a new database;
- verify PDFs, emails and financial records are byte/semantic compatible where
  required.

### Step 7 — remove the old path carefully

Only after the adapter is the only writer for the slice. Keep a migration note
and a rollback tag. Do not rename production columns in the same release as the
behavior change.

### Step 8 — update the ledger

Record:

- slice name;
- status before/after;
- legacy source;
- target contract;
- entry points migrated;
- tests;
- remaining legacy writes;
- next step.

## 4. Status vocabulary for the ledger

Use one of these labels consistently:

- **legacy only** — no adapter, no Workaholic contract.
- **adapter read** — reads go through the adapter; writes still legacy.
- **adapter write** — reads and writes go through the adapter; old path may
  still exist behind a flag.
- **source of truth** — Workaholic/contract owns the slice; legacy table is a
  compatibility view or has been migrated.
- **flavor/locale module** — intentionally outside the generic core.
- **not started** — no decision yet.

## 5. Anti-patterns

Avoid:

- rewriting the whole app to “make it modular”;
- moving AUTOSEG rules into Workaholic core;
- copying code into a flavor and fixing bugs twice;
- building Workaholic features with no consumer;
- changing UX while migrating data;
- renaming database columns before an adapter exists;
- mixing a security fix with a large refactor;
- treating a prototype as production architecture without a contract;
- leaving a migration half-done without an issue, owner and next step.

## 6. AI-agent protocol

An agent working on this repository must:

1. Read `AGENTS.md`, the product vision, the playbook and the ledger.
2. Inspect the real code and data model; do not infer from filenames only.
3. State the slice/contract being touched and the behavior being preserved.
4. Add or update characterization tests before refactoring.
5. Make the smallest reversible change.
6. Run the relevant tests; report commands and results.
7. Update the ledger, changelog and docs when applicable.
8. Declare the platform delta (or justify `none`).
9. Stop and ask before changing money, tax, permissions, auth or data migration.

## 7. Cadence and review

- **Every PR:** one platform delta, one parity statement, tests.
- **Every release:** update the ledger; list migrated slices and remaining
  legacy paths.
- **Every month (or milestone):** review the ledger and choose the next slice;
  remove abandoned branches/prototypes.
- **Every architecture decision:** add a short ADR or a note in the playbook
  rather than relying on conversation history.

## 8. What “generic” must not break

The user experience remains AUTOSEG’s. The generic engine and module boundaries
are internal architecture. A user must not need to understand Workaholic,
schemas, modules or flavors to create a client, open an OS, issue a report or
receive a payment.

Parity is more important than architectural purity.

## 9. Decisions that need humans

Some decisions cannot be settled by code inspection alone. They are tracked in
`docs/HUMAN_CENTERED_DECISIONS.md` and stay deferred until there is evidence
from real use, prototypes or pilot users.

Until a decision is made:

- do not build a plugin framework;
- do not rename production database columns;
- do not start a large migration just to satisfy an architecture diagram;
- keep adding characterization tests, documentation and reversible adapters.

The project owner is not required to answer technical questions in advance.
The expected behavior is to reduce the question to understandable options,
show consequences and gather human evidence.
