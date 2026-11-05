# Human-centered decision process

**Status:** working agreement. This document exists because important product
and architecture decisions cannot be made by AI alone, and because the project
owner does not need to answer every technical question before there is real
usage context.

## 1. Principle

AI can inspect code, propose options, build reversible prototypes and document
trade-offs. It must not pretend to know what users value, which workflow is
acceptable, or which irreversible architecture is “right” without human
context.

The project owner’s role is to provide:

- real usage context;
- what humans value and what causes friction;
- priorities, risk tolerance and product direction;
- approval for irreversible changes.

The AI’s role is to:

- reduce the decision to understandable options;
- explain consequences in plain language;
- build small reversible experiments;
- record evidence and assumptions;
- stop before making a high-impact decision alone.

## 2. Decision classes

Not every decision needs the same process.

| Class | Examples | Who decides | Method |
|---|---|---|---|
| Reversible implementation detail | variable name, internal helper, test structure | AI/maintainer | Just do it, with tests. |
| Reversible product experiment | prototype screen, read-only adapter, feature flag | AI proposes; human reviews | Small spike, pilot feedback, rollback. |
| Product/UX direction | navigation, terminology, workflow defaults | Human, informed by users | Observation, interviews, prototypes. |
| Irreversible architecture | database migration, plugin contract, repository split | Human + technical review | ADR, alternatives, evidence, rollback plan. |
| Legal/licensing | 0BSD, contribution policy, trademarks | Human/legal review | Explicit approval. |

## 3. Evidence before commitment

Prefer evidence from:

1. **Watching real work** — ask a user to perform a real task and note where
   they hesitate, ask questions, or work around the software.
2. **Support and issue history** — recurring bugs, confusing labels, repeated
   manual steps.
3. **Pilot users** — a small group with different professions: security,
   electrician, artist, musician, stagehand, administrator.
4. **Prototypes** — clickable GTK mockups or small technical spikes before a
   large commitment.
5. **Comparative review** — study well-made GNOME apps, modular systems and
   comparable work-management tools. Copy principles, not code.
6. **Usage data, carefully** — opt-in, local, aggregate and privacy-respecting.
   Numbers explain behavior; they do not define values.

## 4. Feedback loop

### Continuous

- Issues and support conversations are tagged by user impact.
- Pull requests must state the human workflow affected.
- UI changes require a manual smoke test and, when possible, observation with a
  real user.
- Architecture changes require a short decision record.

### Per milestone

- Review `docs/PLATFORM_MIGRATION_LEDGER.md` with a human.
- Ask: what caused friction? What was ignored? What did users work around?
- Choose one small next slice based on evidence, not only code aesthetics.

### Before a public alpha/beta

- Recruit pilot users outside the original author’s environment.
- Test clean installation and data recovery with a non-developer.
- Review security, privacy and licensing with a human.
- Decide what support level is honest to promise.

## 5. Deferred decisions

These decisions are intentionally deferred. They are not blockers for
documentation, characterization tests or reversible cleanup.

| Decision | Why deferred | Evidence needed | Default until decided | Review trigger |
|---|---|---|---|---|
| First migration slice: catalog vs service orders | Depends on coupling, risk and actual usage; no sufficient evidence yet. | Coupling map, bug/change frequency, a timeboxed read-only adapter spike, user impact. | Do not commit to a full slice; only add characterization tests and reversible groundwork. | Before the next structural migration; after a short spike. |
| Module contract: Python entry points + manifest vs another mechanism | Designing a plugin system with only one real consumer risks overengineering. | A second real consumer/flavor, developer-experience test, comparative review of modular apps. | Keep Python packages and adapters; no plugin framework. | When a second flavor or module has a concrete need. |
| Cadence: ~20% platform delta per PR vs one structural delta per release | Depends on team size, release rhythm and risk tolerance. | Three or four releases of data on scope, review time and regressions. | Keep ~20% as a guideline, not a hard rule. | After three releases or if the rule causes scope creep. |

The table is deliberately written so the project can keep moving without
pretending these questions are answered.

## 6. How AI agents must behave

1. Do not make an irreversible product/architecture decision alone.
2. If a task depends on human values or real usage, implement only the
   reversible part and document the open question.
3. Present options with trade-offs, not a single “correct” answer.
4. Separate facts (code behavior, tests) from assumptions (what users want).
5. Use prototypes and feature flags before broad changes.
6. Never treat telemetry or issue counts as the only source of truth.
7. Ask a human before changing money, tax, permissions, privacy, licensing or
   data ownership.
8. Record decisions and their context, not just the final code.

## 7. Decision record template

```markdown
# ADR: <short title>

Status: proposed | accepted | rejected | deferred
Date:
Owner:
Context:
Human need / user impact:
Options:
  1. ...
  2. ...
Evidence:
Reversibility:
Decision:
Consequences:
Rollback:
Review date / trigger:
```

Use an ADR for irreversible choices. Use a short note in the playbook or issue
for reversible experiments.

## 8. Open privacy decision — feedback support record

**Status:** deferred; DEV only until reviewed.

**Context:** the Provider Portal feedback channel stores the authenticated
provider, page, coarse device, session hash and minimized IP so support can
investigate a report. The person sees a notice in the dialog and can submit
without requesting an AI answer. The original text stays local; only an
anonymized version is sent to the configured AI provider (the local OpenCode
chat in DEV, or another API selected by configuration).

**Options:**

1. Keep the support record with the current notice, access control and
   documented retention; require legal review before production.
2. Remove the session hash and reduce the device fields to browser family only.
3. Keep the channel but disable AI replies until a data-processing agreement and
   retention policy exist.
4. Disable the channel in production while keeping it in DEV.

**Evidence needed:** LGPD/privacy review, real support use in DEV, and a clear
retention/deletion owner. **Reversibility:** tables are additive and the routes
can be removed without touching OS, finance, stock or fiscal records. **Trigger
for decision:** before the first production deployment.

## 8.1 What this means for the current questions

The three open questions from the migration plan are not forgotten. They are
recorded as deferred with explicit evidence triggers. Until then:

- no plugin framework is built;
- no database column is renamed;
- no large migration is started just to satisfy an architecture diagram;
- characterization tests, documentation, small adapters and reversible
  improvements are still welcome.

## 9. Related documents

- `AGENTS.md`
- `docs/PRODUCT_VISION.md`
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md`
- `docs/USER_FEEDBACK_GUIDE.md`
- `docs/features/FEEDBACK_PORTAL.md`
- `docs/features/OPEN_TELEMETRY.md`
- `docs/PLATFORM_MIGRATION_LEDGER.md`
- `docs/GTK4_LINUX_MACOS.md`
