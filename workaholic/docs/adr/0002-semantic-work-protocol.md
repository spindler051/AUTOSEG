# ADR 0002 — Semantic work protocol and presentation profiles

- **Status:** Proposed
- **Date:** 2026-11-08
- **Scope:** Workaholic core, Officina platform, flavors
- **Related:** [`docs/planning/WORK_PROTOCOL_TERMINOLOGY_AND_WORKFLOW.md`](../../../docs/planning/WORK_PROTOCOL_TERMINOLOGY_AND_WORKFLOW.md)

## Context

Workaholic currently exposes profession-agnostic records, but its examples and
schema use application-specific names (`ordem_servico`, `projeto`) and workflows
with free-form state names. The AUTOSEG application needs “ordem de serviço”,
“cliente” and “prestador”; an arts flavor may need “comissão”, “cliente” and
“artista”; a repair shop may need “reparo” and “técnico”.

Hardcoding these words in Workaholic, Officina, database columns, routes or UI
would force every flavor to fork code. Renaming strings is not enough: labels
affect grammar, links, documents, permissions, workflow and completion rules.

## Decision

1. **Workaholic remains presentation-agnostic.** It may know semantic
   primitives such as `work_item`, `party`, `assignment`, `workflow`, `state`,
   `state_kind`, `transition`, `requirement` and `evidence`. It must not contain
   localized product terms, flavor roles, fiscal terms or UI labels.

2. **Officina owns the work protocol.** The platform layer composes profiles:
   lexicon, field groups, workflow definitions, completion requirements, role
   presets and application effects. Profiles are declarative, validated and
   versioned.

3. **Flavors provide profile data.** AUTOSEG, arts and future distributions
   supply labels, states, fields, requirements and branding. A flavor must not
   need a conditional in Workaholic or Officina core.

4. **Semantic identity is separate from presentation.** Code, APIs, audit
   events and persisted data use stable IDs and `state_kind`; user-facing text
   is resolved at the edge by a lexicon. Routes, public identifiers and old
   links are stable; labels never generate identifiers.

5. **Compatibility is incremental.** No table, column, route or document is
   renamed as part of this decision. Existing `/os` APIs, `ordens_servico` and
   PDFs remain valid through adapters until a tested migration says otherwise.

6. **Completion requirements are declarative and server-side.** A transition
   can declare requirements and waivers; the UI presents the result, but cannot
   be the authority. Flavor-specific evaluators live in Officina/modules.

## Consequences

### Positive

- A flavor can rename the work item and roles without changing core code.
- Different workflows and completion policies can coexist.
- Reports and integrations can use `state_kind` instead of translated strings.
- Old documents, links and clients remain compatible.
- Tests can assert semantic behavior instead of UI copy.

### Negative / risks

- The profile format becomes a new contract that needs validation, review and
  versioning.
- There is a risk of building an over-general workflow DSL; the first version
  must use a small set of closed requirement types.
- Legacy tables and APIs require adapters for a long transition period.
- Term changes need grammar-aware messages, not string concatenation.
- Workflow migrations and waivers need careful audit and rollback.

## Follow-up (not implemented by this ADR)

1. Define the profile schema and validation limits.
2. Map AUTOSEG states to `state_kind` in a read-only adapter.
3. Prove the model with a second flavor (arts/commission) before broadening it.
4. Keep Workaholic tests independent of AUTOSEG terms.
5. Record migration and rollback in the platform migration ledger.
