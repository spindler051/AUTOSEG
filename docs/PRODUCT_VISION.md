# Product vision — AUTOSEG, Workaholic and the generic work platform

**Status:** planning document. This file records direction, boundaries and
distribution intent. It does **not** describe code that has already been
implemented, and it does not authorize a big-bang rewrite.

**Last updated:** 2026-11-04

## 1. One-sentence vision

Build a local-first, modular, open-source work-management platform — powered by
the **Workaholic** engine and a GNOME/GTK4 desktop app — where **AUTOSEG** is
one flavored distribution for security and automation professionals, while the
same foundation can serve artists, stagehands, electricians, musicians, DJs and
any other independent worker or small team.

## 2. Product family

The long-term product is not a single monolithic application. It is a family of
pieces with clear responsibilities.

| Layer | Working name | Responsibility | Current state |
|---|---|---|---|
| Engine | **Workaholic** | Generic records, schemas, fields, states, relations, validation, versioning, storage, search and audit contracts. UI-agnostic and local-first. | Prototype `0.1.0`; CLI, YAML/SQLite repositories and tests exist. Only the `cliente` slice is integrated into AUTOSEG. |
| Generic desktop app | **TBD** | GNOME/GTK4 + libadwaita application for work management: clients, jobs, items, schedules, payments, commissions, documents and reports. Flavorless and schema-driven. | Planned. No separate generic app exists yet. |
| Flavor layer | **AUTOSEG** | Security/automation vocabulary, workflows, reports, portals and defaults. A downstream configuration/distribution of the generic app. | Current production application; must keep its behavior during platformization. |
| Locale/vertical modules | **TBD** (`autoseg-br` working name) | Brazilian-specific rules and integrations: CPF/CNPJ, NF-e/NFS-e, municipal tax, PIX, boleto, Brazilian addresses and similar. | Planned modules; not part of the generic core. |
| Integrations | **TBD** | Email, files, calendars, payment providers, tax providers, storage and external APIs behind replaceable interfaces. | Partly present in AUTOSEG today, coupled to the current app. Future home: modules/adapters. |

### 2.1 What “fork” means here

AUTOSEG should be a **downstream flavor/distribution**, not a hard fork with
copied code. The preferred model is:

```text
Workaholic core
      │
      ├── generic GTK application
      │         │
      │         ├── AUTOSEG flavor (security/automation)
      │         └── other flavors (music, arts, trades, ...)
      │
      └── locale/vertical modules (Brazil, fiscal, payments, ...)
```

A real Git fork may be used for release cadence or branding, but divergence
must stay small. Bug fixes and generic features should flow upstream. A flavor
should add configuration, schemas, modules, translations and branding — not a
second copy of the application.

### 2.2 Multi-client and local-first direction

The family is expected to grow beyond GTK and the web portals: CLI, Qt, native
iOS and native Android are candidates, with local-only, local-group, central
server and peer-to-peer modes. The high-level direction, cost drivers and the
parts that are likely infeasible are documented in
`docs/VISAO_MULTICLIENTE_LOCAL_FIRST.md`. That document is planning only and
does not authorize a big-bang rewrite.

## 3. Design principles

1. **Engine is not UI.** Workaholic owns records and rules; GTK, CLI and future
   clients consume the same application services.
2. **Flavorless core.** The core must not know “condomínio”, “síndico”, “OS”,
   “NFS-e” or “portão automático”. Those belong to flavors or locale modules.
3. **Local-first by default.** The app must work without a mandatory cloud
   account or remote server. Sync, when added, is an optional capability.
4. **Schema-driven.** A profession or business changes through schemas,
   modules and configuration — not through branches in the core.
5. **One-way dependencies.** Core must never import a flavor. Flavors and
   modules may depend on stable core contracts.
6. **Behavior parity for AUTOSEG.** Platformization must not change AUTOSEG’s
   visible functionality until an intentional, tested replacement is ready.
7. **Incremental migration.** One slice at a time, with regression tests and
   backups. No big-bang database rewrite.
8. **English source code.** New identifiers, tests, schemas and documentation
   are written in English. Portuguese legacy code is migrated slice by slice.
9. **Translation is not the same as code language.** UI strings go through
   gettext (or an equivalent); `pt_BR` remains a first-class locale.
10. **GNOME quality bar.** GTK4 + libadwaita, GNOME HIG, adaptive layout,
    keyboard access, accessibility, native dialogs, light/dark support and
    restrained theming. “GNOME Circle-style” means this quality bar, not a
    promise of acceptance into the GNOME Circle program.
11. **Open by default.** Public source, public issue tracker, reproducible
    builds where practical, and no hidden dependency on the author’s machine.
12. **Data ownership.** The user’s database, attachments and exports remain
    portable and usable without the original developer.

### 3.1 Human-centered decisions

AI can inspect code, propose alternatives and build reversible prototypes. It
must not make irreversible product or architecture decisions alone. Decisions
that depend on what users value, real workflows or an uncertain trade-off are
deferred until there is evidence from actual use, pilot users, observation,
support history or comparable well-made software.

The project owner is not expected to answer technical questions before the
context exists. The expected process is documented in
`docs/HUMAN_CENTERED_DECISIONS.md`: reduce the question to understandable
options, show consequences, run a small reversible experiment, then decide.

## 4. What belongs where

### Workaholic core

- Entity and field schemas.
- Record identity, versioning and archival.
- Validation and state transitions.
- Relations and referential checks.
- Repository contracts (SQLite, YAML, future backends).
- Search, audit/event contracts and import/export primitives.
- Module registry and stable application-service interfaces (future).

The core must remain usable by a CLI, a GTK app, a web app or an automation
script. It is closer to a local data/engine layer — conceptually similar to
what Evolution Data Server is for personal information — than to a screen.

### Generic GTK application

- GNOME application shell and navigation.
- Schema-driven list/detail/editor screens.
- Generic dashboards, search, filters and command palette.
- Generic settings, backups, imports and exports.
- Module discovery and composition.
- Accessibility, keyboard shortcuts and translations.

### AUTOSEG flavor

- Security/automation vocabulary and defaults.
- Service orders, maintenance workflows and approval chains.
- Condominium/company relationships.
- Client and provider portals.
- Budgets, technical reports, productivity, commissions and repasses.
- Security-specific PDFs, checklists and operational rules.
- Branding and packaging.

### Brazilian locale/vertical modules

- CPF/CNPJ validation and formatting.
- NF-e/NFS-e and municipal tax documents.
- PIX, boleto and Brazilian payment integrations.
- Brazilian address/phone conventions.
- Fiscal and accounting exports.
- Any integration whose behavior is defined by Brazilian regulation.

These modules may be shipped with AUTOSEG, but they must not leak into the
generic core. The core should expose generic contracts such as “tax document
provider”, “payment provider” and “identity document”, with Brazilian
implementations living outside it.

## 5. Current state — honest assessment

### AUTOSEG today

- Desktop frontend: GTK4/libadwaita (`gtk_app.py`).
- The Tkinter frontend was removed in `9.6.0-dev.12`.
- Client portal and provider portal share the same SQLite database.
- Service orders, finance, PDFs, email drafts, productivity/rateios, clients,
  catalog, stock and Brazilian fiscal drafts exist and are in use.
- The application is still largely organized around legacy tables and
  Portuguese module names.

### Workaholic today

Workaholic has **not** been abandoned, but it has also **not** become the engine
of the whole application yet.

Current facts:

- It exists as a separate prototype, version `0.1.0`, under `workaholic/`.
- It has a CLI, YAML and SQLite repositories, schemas, validation, optimistic
  versioning and tests.
- It is already licensed under 0BSD (`workaholic/LICENSE`).
- AUTOSEG integrates it for the **cliente** slice through
  `integracao/clientes.py` and `integracao/schema_autoseg.yaml`.
- Recent work on portals, PDFs, finance and GTK did not expand Workaholic; those
  features were delivered in the current AUTOSEG codebase.
- The generic GTK shell, module system, schema versioning, full audit and
  migration of the remaining entities are still future work.

This is a deliberate but incomplete state. The next architectural investment is
to make Workaholic the real engine, not a side prototype.

### Migration ledger

The current slice-by-slice plan and known shortcuts are documented in:

- `docs/WORKAHOLIC_INTEGRACAO.md`
- `docs/MIGRACAO_MODULAR.md`
- `workaholic/docs/ARCHITECTURE.md`
- `workaholic/docs/MIGRATION_LEDGER.md`

## 6. Distribution and licensing

### License

The project’s original code will be released under the **BSD Zero Clause
License (0BSD)**. This applies to:

- the Workaholic engine;
- the generic GTK application;
- the AUTOSEG flavor and its original modules;
- documentation and schemas created for the project.

Third-party dependencies keep their own licenses. A dependency audit is
required before each public release. Historical code or contributions with
unclear provenance must be reviewed before relicensing.

A root `LICENSE` file records the 0BSD text. The existing
`workaholic/LICENSE` remains the license for that subproject. SPDX headers and
contribution policy are open decisions.

### Source and releases

- Public source on GitHub.
- Public issue tracker and pull-request workflow.
- Tagged releases with source archives.
- Linux: Flatpak is the preferred GNOME distribution path; AppImage remains a
  possible secondary artifact.
- macOS: signed/notarized bundle if practical; otherwise a documented
  `.command` launcher.
- No mandatory cloud service. Optional integrations must be replaceable.

### Repository strategy

The final split is not decided. The recommended path is:

1. Start with a **monorepo** containing `workaholic/`, the generic GTK app,
   AUTOSEG flavor and modules, so contracts can evolve together.
2. Split into separate repositories when the module contracts and release
   cadence are stable.

A possible future layout, if the **Officina** name is confirmed:

```text
<org>/workaholic          engine, protocol, engine CLI, contracts, tests
<org>/officina            generic platform/meta: contracts, docs, design
<org>/officina-gtk        GTK4/libadwaita client
<org>/officina-qt         Qt client (only if justified)
<org>/officina-winui      Windows/WinUI client
<org>/officina-web        generic web client
<org>/officina-cli        application CLI
<org>/officina-crane      Android/Jetpack Compose client (internal codename)
<org>/officina-swiftui    Apple client
<org>/autoseg             AUTOSEG flavor/distribution
<org>/autoseg-br          Brazilian locale/fiscal modules
```

Names, organization and repository boundaries remain open. Start with a
monorepo; split only when contracts, API and release engineering justify it.
See `docs/NAMING_AND_CLI.md` section 9.

## 7. Roadmap — phases, not dates

### Phase 0 — Document and freeze boundaries (current)

- Publish this vision.
- Record the Workaholic status honestly.
- Keep AUTOSEG running without functional changes.
- Define the first stable contracts and naming decisions.

### Phase 1 — Make Workaholic real

- Stabilize schema/versioning/event contracts.
- Expand tests and documentation.
- Add schema revisions and migration tooling.
- Migrate the next AUTOSEG slices behind adapters.
- Keep legacy tables and compatibility paths until parity is proven.

### Phase 2 — Generic GTK shell

- Build a schema-driven GTK4/libadwaita application.
- Support generic entities, lists, forms, relations, search and settings.
- Add module discovery and composition.
- Reach GNOME HIG quality: adaptive layout, keyboard, accessibility, native
  dialogs, light/dark and translations.

### Phase 3 — Module system and locale modules

- Define the module contract (Python package entry points or equivalent).
- Move Brazilian fiscal/payment/document rules into locale modules.
- Move security/automation workflows into the AUTOSEG flavor.
- Keep the core free of profession-specific terms.

### Phase 4 — Migrate AUTOSEG without changing behavior

- Move one slice at a time: clients, service orders, catalog/materials,
  finance, providers, portals, reports.
- Maintain regression tests and production backups.
- Keep AUTOSEG fully usable throughout the migration.
- Switch the default implementation only after parity.

### Phase 5 — English codebase and i18n

- New code and schemas in English.
- Rename legacy modules incrementally, with compatibility shims.
- Extract UI strings to gettext; ship `pt_BR` first.
- Do **not** rename production database columns without a tested migration;
  adapters may keep legacy names while the code speaks English.

### Phase 6 — Public release

- Dependency/license audit.
- Root license, contributing guide, code of conduct and security policy.
- CI, reproducible builds, release notes.
- Flatpak/macOS packaging.
- Public GitHub release.

## 8. Guardrails and non-goals

- No big-bang rewrite.
- No change to AUTOSEG’s visible behavior as part of “modularization”.
- No data migration without backup, validation and rollback.
- No production database schema rename just to satisfy English naming.
- No core import of AUTOSEG, fiscal or GNOME UI code.
- No premature plugin framework before the contracts are stable.
- No decision on the generic app’s name in this document.

## 9. Open questions

1. **Name and namespace:** what is the generic app called, and which GitHub
   organization owns the repositories?
2. **Repository split:** monorepo first (recommended) or separate repositories
   immediately?
3. **Module mechanism:** Python entry points, a declarative manifest, or both?
4. **Core scope:** how much of “work, commissions and services” is generic
   core versus flavor? For example, are commissions a core concept or an
   AUTOSEG/vertical module?
5. **Portals:** are client/provider portals part of the generic app, a module,
   or an AUTOSEG-only feature?
6. **Database naming:** keep Portuguese legacy columns behind adapters, or plan
   a full English schema migration later?
7. **GNOME Circle:** is it only a quality reference, or is applying to the
   program a goal?
8. **Contribution policy:** DCO, CLA or neither? SPDX headers?
9. **Trademark:** who owns the AUTOSEG name and branding, separately from the
   code license?

## 10. Glossary

- **Workaholic:** the generic, local-first work-record engine.
- **Flavor/distribution:** a configured product built on the generic app, such
  as AUTOSEG.
- **Module:** a replaceable package that adds vertical or locale behavior.
- **Schema:** the declarative definition of entities, fields, states and
  relations for a flavor.
- **Locale module:** a module whose rules are defined by a country/region,
  such as Brazilian fiscal documents.
- **Parity:** the point at which a migrated implementation matches the current
  AUTOSEG behavior closely enough to become the default.

## 11. Related documents

- `AGENTS.md`
- `docs/HUMAN_CENTERED_DECISIONS.md`
- `docs/USER_FEEDBACK_GUIDE.md`
- `docs/ENGLISH_MIGRATION_PLAN.md`
- `docs/NAMING_AND_CLI.md`
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md`
- `docs/PLATFORM_MIGRATION_LEDGER.md`
- `workaholic/README.md`
- `workaholic/docs/ARCHITECTURE.md`
- `workaholic/docs/MIGRATION_LEDGER.md`
- `docs/WORKAHOLIC_INTEGRACAO.md`
- `docs/MIGRACAO_MODULAR.md`
- `docs/GTK4_LINUX_MACOS.md`
- `docs/PLANO_EVOLUCAO_ARQUITETURA.md`
- `docs/VISAO_MULTICLIENTE_LOCAL_FIRST.md`
- `docs/GTK_SERVER_DECOUPLING.md`
- `docs/MULTI_PLATFORM_GUI_GUIDELINE.md`
