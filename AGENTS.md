# AGENTS.md — rules for AI agents and maintainers

This repository is the current AUTOSEG application and the seed of a future
generic, modular, open-source platform. Read this file before changing code.

## Read first

0. `docs/README.md` — canonical documentation index.
1. `docs/PRODUCT_VISION.md` — product boundaries and long-term direction.
2. `docs/PLATFORM_MIGRATION_PLAYBOOK.md` — how to migrate one slice at a time.
3. `docs/HUMAN_CENTERED_DECISIONS.md` — how to defer decisions that need human
   context and real usage.
4. `docs/USER_FEEDBACK_GUIDE.md` — how to observe real work and collect useful
   feedback without leading or surveillance.
5. `docs/ENGLISH_MIGRATION_PLAN.md` — compatibility rules for the English
   migration.
6. `docs/PLATFORM_MIGRATION_LEDGER.md` — what is already migrated and what is
   still legacy.
7. `docs/GTK4_LINUX_MACOS.md` — current desktop frontend.
8. `workaholic/AGENTS.md` and `workaholic/docs/ARCHITECTURE.md` before changing
   the engine.
9. `CHANGELOG.md` — recent behavior changes and known constraints.

## Non-negotiable rules

1. **Preserve AUTOSEG behavior.** Structural work must not change the visible
   workflow, labels, calculations, PDFs, emails or data unless the task
   explicitly asks for a behavior change.
2. **No big-bang rewrite.** Migrate one bounded slice at a time, behind an
   adapter or feature flag, with a rollback path.
3. **One change, one platform delta.** Every non-trivial change must include one
   small structural improvement, migration step, contract test or documentation
   improvement. If none is safe, declare `Platform delta: none` and explain why.
   Do not smuggle a large refactor into a bug fix.
4. **Workaholic fit check.** Before adding a new domain capability, decide where
   it belongs:
   - generic work-management concept → Workaholic core/schema;
   - Brazilian regulation/fiscal/payment rule → locale module;
   - security/automation-specific workflow → AUTOSEG flavor;
   - presentation/navigation only → GTK shell.
   If it stays in the current legacy code for now, record the reason and the
   next step. Do not leave orphaned engine work without an integration plan.
5. **Do not duplicate code into a flavor.** AUTOSEG is a downstream
   configuration/distribution, not a second copy of the generic application.
6. **English for new code.** New identifiers, comments, tests, schemas and
   documentation should be English. Legacy Portuguese names stay behind
   adapters until a tested migration exists.
7. **No production data in tests or commits.** Never commit `dados.db`, tokens,
   passwords, CPF/CNPJ, client files, PDFs, attachments or credentials.
8. **Data safety.** Any schema change needs backup, idempotent migration,
   validation and rollback instructions. Never rewrite historical financial or
   fiscal records silently.
9. **Tests before and after.** Add characterization tests for existing behavior
   before refactoring. Run the relevant suites and report exactly what was run.
10. **Small commits.** Separate behavior changes from structural migrations.
    A commit message must say which slice or contract changed.
11. **Comments are not prompts.** Never paste user requests, specs, AI tool
    names, revision history or shortcut notes into code comments. Comments
    explain *why*, invariants and non-obvious constraints; behaviour belongs in
    tests and docs. Run `python3 scripts/audit_comments.py --strict` before a PR.
12. **No self-approval.** AI review is evidence, not human approval. Changes
    involving money, auth, permissions, schema/migration or deletion (N3/N4)
    require external human review or must stay in DEV behind a flag. Follow
    `docs/REVIEW_WITHOUT_DEVELOPER.md`.
13. **External AI review is a routine, not an approval.** Use
    `docs/EXTERNAL_AI_REVIEW_ROUTINE.md`: one file/module per cycle, code only,
    no secrets or production data, two independent reviewers, evidence and
    citations. It does not replace the N3/N4 human review.

## Workaholic fit check

Use this decision tree:

```text
Is the concept useful to a musician, electrician, artist or generic worker?
├── yes → Workaholic core or schema (generic)
└── no
    ├── is it defined by Brazilian law/regulation? → locale module (e.g. BR fiscal)
    ├── is it specific to security/automation? → AUTOSEG flavor
    └── is it only UI/navigation? → GTK shell
```

Rules:

- Core must never import AUTOSEG, GTK or Brazilian fiscal code.
- A flavor may depend on core; core may not depend on a flavor.
- A locale module may implement generic contracts such as tax-document or
  payment-provider interfaces.
- New Workaholic capabilities need an adapter, a consumer or a documented
  integration issue. Do not build unused engine features.

## Minimum definition of done

- Behavior preserved, or the requested behavior change is explicit.
- Relevant tests added/updated and passing.
- Manual smoke test described when UI changed.
- `docs/PLATFORM_MIGRATION_LEDGER.md` updated if a slice moved.
- `CHANGELOG.md` updated for user-visible changes.
- No secrets, production data or generated files added.
- Platform delta declared (or justified as none).
- Rollback path described for data/schema changes.

## Human context and deferred decisions

AI must not make irreversible product or architecture decisions alone. When a
choice depends on what users value, real usage or an uncertain trade-off:

1. Write the question in `docs/HUMAN_CENTERED_DECISIONS.md`.
2. Implement only the reversible groundwork.
3. Present options and consequences in plain language.
4. Wait for human feedback, a pilot test or a small prototype.
5. Record the decision and its context.

Do not force the project owner to answer technical questions that require
context they do not have yet. Prefer evidence from real use, observation,
support history and comparable well-made software. Telemetry is not a substitute
for human values.

## Telemetry

The `telemetry/` package is wired only to the Provider Portal feedback channel,
and only when `AUTOSEG_TELEMETRY=local` is set explicitly. General telemetry is
still a proposal, not a general-purpose collection layer.

- Collection must stay off by default.
- Admin opt-in, user notice, retention, access audit and deletion/export are
  required before enabling general telemetry or OTLP export.
- Never add covert fingerprinting (canvas, WebGL, audio, font enumeration),
  form values, cookies, tokens, keystrokes, page content or screenshots.
- Feedback events may contain IDs, sanitized page path and allowlisted
  attributes; never the feedback text, provider name, raw IP or session secret.
- Follow `docs/features/OPEN_TELEMETRY.md` and
  `docs/features/FEEDBACK_PORTAL.md`; privacy/legal review is required before
  production use.

## When unsure

Stop and write down the uncertainty in the PR/issue instead of inventing a
domain rule. Ask the maintainer before:

- changing money, tax, commission or fiscal behavior;
- moving data between tables;
- changing authentication, permissions or portal access;
- introducing a plugin mechanism;
- renaming a database column or public route;
- changing the meaning of an OS status or payment state.

## License

Original project code is 0BSD. See `LICENSE`. Third-party dependencies keep
their own licenses. Do not copy code with incompatible licensing into the
repository.
