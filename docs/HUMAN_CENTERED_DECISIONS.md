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

### 5.1 Deferred multi-client and local-first decisions

The long-term multi-client direction (CLI, Qt, native iOS/Android, local-only,
LAN group, central server and P2P) is documented in
`docs/planning/VISAO_MULTICLIENTE_LOCAL_FIRST.md`. The following choices remain deferred
until there is evidence: reference client, Qt/mobile scope, P2P versus central
authority, E2E encryption versus server-side document generation, and the Rust
scope. Reversible groundwork and documentation are allowed; no new client or
sync implementation should start before GTK/web parity and a protocol v0 exist.

### 5.2 Deferred identity, single-site and permission decisions

The target model is documented in
`docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` and
`docs/planning/OFFICINA_WEB_AND_GTK.md`. The following product decisions are
deferred; the recommended defaults are documentation/test defaults only and do
not authorize production behavior.

| Decision | Why deferred | Evidence needed | Default until decided | Review trigger |
|---|---|---|---|---|
| Login identifier: e-mail, CPF, or both | Clients use CPF today; providers use e-mail. Changing this affects recovery, privacy and legacy accounts. | Real login/support history, client and provider interviews, migration cost. | Accept either e-mail or CPF; the account stores both. | Before the unified login flag is enabled. |
| Same account for client and provider roles | This is the core UX request, but it changes identity, recovery and context selection. | A small prototype with one person who is both client and provider; support review. | Yes: one account, separate links and an explicit context selector. | Before phase 2. |
| One account across multiple service providers | AUTOSEG is the first provider; multi-provider is an Officina Web goal, not a first-release requirement. | A second real provider or a concrete pilot. | One provider (AUTOSEG); model the provider link from day one. | Before Officina Web multi-provider work. |
| Anonymous OS: target, proof, photos, moderation, retention | Abuse, privacy and support cost depend on real use. | Pilot with real anonymous requests; spam/quality data; privacy review. | Allowed by AUTOSEG policy, protocol + tracking link, contact required, no photos in phase 1, manual triage. | Before phase 6. |
| Roles at launch | More roles create UI and training cost before there is usage evidence. | Time observation with providers; support tickets. | Admin, provider, finance, read, client; dispatcher/field later. | Before phase 5. |
| Staff access to the full client base and PII | Legal/privacy and trust decision; current code exposes everything. | LGPD review, provider interviews, support needs. | Staff sees only clients involved in their OS; no CPF/CNPJ search or export. | Before phase 4. |
| Client can approve budget or close an OS | Changes responsibility and legal exposure. | Pilot with real clients; contract review. | Client can respond/approve, not edit or close the technical OS. | Before phase 5. |
| Who can change permissions and roles | Self-approval and last-admin lockout are high-impact. | Security review and a recovery drill. | Provider admin; platform admin audits; last admin protected. | Before phase 5. |
| Audit retention and export | Legal/support decision. | LGPD review and storage cost. | Keep sensitive decisions; define retention before production. | Before production. |
| Per-provider branding, CNPJ and fiscal identity | Needed for Officina Web, not for the first AUTOSEG-only release. | A second provider or a real white-label need. | AUTOSEG branding as default; model the fields. | Before multi-provider. |
| Signing-key unlock: login-password convenience vs OS keychain/hardware vs manual passphrase | The convenient mode makes the login password an input to signing; weak/reused passwords and shared devices reduce the assurance. The right balance depends on real signing frequency, device policy and tolerance for friction. | A pilot with real OS signing, support data, a security review, and observed password/device behavior. | Convenience mode is opt-in only, never silent; recommend OS keychain/hardware; warn that the password protects signing. If a server-side envelope is required, use a separate unlock secret or PAKE/OPAQUE. | Before production signing or any legally relevant OS signature. |

Technical choices that follow from these decisions (shared database versus
database per provider, table names, token format) do not need the product owner
to choose directly, but auth/permission/data migration still require N3/N4
review.

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

## 9. OS interactions save automatically

**Decision (product owner):** in the OS screen, edits apply automatically.
Do not add an explicit "Salvar" button for fields that can be auto-saved.
New interactions must follow the same pattern: debounce while typing, save on
blur/Enter or selection, and update the list and totals in place.

**Prohibited design anti-pattern:** a button whose only job is to confirm or
apply something the system can already apply automatically. This includes
"Salvar", "Aplicar", "Confirmar alteração" and similar controls. Do not add
extra action controls — including an "undo last change" control — unless the
product owner explicitly requests them. Destructive actions that are genuinely
necessary, such as removing a collaborator, may ask for confirmation.

**Consequence for new features:** if a new OS section is added, it must behave
like the existing auto-save fields, not like a separate form with its own
submit button. The OS event history remains the audit trail.

### 9.1 The visit fee is optional per work item

**Decision (product owner):** the final OS total is authoritative. The minimum
visit fee can be charged or waived per OS. When it is waived, percentage costs
still apply to the final total and labor receives the remainder after materials
and percentage costs. The chosen mode and the negotiated total must be persisted
and restored when the OS is reopened.

Example with three 10% costs: total R$ 230.00, materials R$ 89.00, percentage
costs R$ 69.00, labor R$ 72.00, visit R$ 0.00. If labor falls below the
configured minimum, the OS saves with a warning; it must not refuse the save or
silently change the total.

### 9.2 Negotiated value must be an explicit discount

**Decision (product owner, proposed UX):** the OS has a nominal calculated
total and an optional negotiated final total. A single checkbox reveals the
negotiated field. The report/PDF shows `Subtotal`, `Desconto negociado` and
`Total`, instead of silently redistributing labor and costs to hide the
difference.

Example: calculated total R$ 260.00, negotiated total R$ 230.00, discount
R$ 30.00. The composition is calculated on R$ 260.00; the discount is a
separate negative line. The checkbox, negotiated value and discount must be
persisted and restored.

**Open decision before implementation:** who absorbs the discount in the
rateio? Options: (A) the total distributable is the final total and collaborator
shares are proportional; (B) the provider/responsible absorbs the discount and
collaborator shares remain based on the nominal total; (C) the discount is
deducted only from the responsible person's share. This changes third-party
money and needs an explicit human decision.

Other open points: whether the nominal total includes materials, who can apply
the discount, and whether the client PDF shows the discount line. The proposed
UX and test matrix are in `docs/planning/OS_NEGOTIATED_VALUE_UX.md`.

### 9.3 The financial finalizer follows the current responsible

**Decision (product owner):** when an administrator concludes an OS on behalf
of another provider, the financial finalizer is the **current responsible**,
not the administrator who clicked. The administrator remains the audit actor in
`os_encerramentos.ator` and in the event history.

The finalizer receives `total − other participants`. If the new responsible had
an old secondary share, it is absorbed into the finalizer remainder and must
not be counted twice. A repasse already sent or confirmed blocks the automatic
absorption and requires an explicit rateio adjustment.

### 9.4 Share the web/GTK presentation contract, not the widgets

**Decision (product owner):** the web site and the GTK app should share a
presentation contract for screens, fields, labels, actions, permissions,
validation messages and view models. Each platform keeps its native widgets,
navigation, dialogs and layout. The goal is to stop implementing the same
product behavior twice, not to build a UI framework.

**Scope guardrails:**

- documentation and contract tests first; no big rewrite;
- start with one read-only list (OS or clients) and one form, behind a flag;
- the contract references `AppService`; it must not contain business rules,
  SQL, HTML or GTK imports;
- the service remains the permission authority; the contract only describes
  what the UI may show;
- no UI DSL, no code generation and no plugin framework;
- platform-specific layout and interaction remain native.

The proposed contract and incremental path are in
`docs/planning/WEB_GTK_SHARED_CONTRACT.md`. This is separate from Workaholic:
it has two real consumers today (web and GTK) and should be adopted before
expanding the generic engine.

### 9.5 Consolidation before platform expansion

**Decision (product owner):** freeze new generic-platform scope until the
AUTOSEG P0 consolidation is closed. This is a scope decision, not a feature
freeze: bug fixes, authorization, OS consolidation, money correctness, portal
thinning, backup/restore and tests continue.

Do not start multi-provider/Officina Web tenancy, new Workaholic domains, a
plugin system, new portals, or new role-dependent features while authorization
by object and tenant isolation are not enforced in the service.

Exit criteria: object policy in the service, negative authorization tests,
single OS writer, canonical money at the boundary, thin portals, backup/restore
tested, and a second real consumer before extracting a generic capability.

## 10. Related documents

- `AGENTS.md`
- `docs/PRODUCT_VISION.md`
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md`
- `docs/USER_FEEDBACK_GUIDE.md`
- `docs/features/FEEDBACK_PORTAL.md`
- `docs/features/OPEN_TELEMETRY.md`
- `docs/PLATFORM_MIGRATION_LEDGER.md`
- `docs/GTK4_LINUX_MACOS.md`
- `docs/planning/VISAO_MULTICLIENTE_LOCAL_FIRST.md`
- `docs/REVIEW_WITHOUT_DEVELOPER.md`
- `docs/planning/CONDO_SHARING_AND_TENANCY.md`
