# AGENTS.md — rules for AI agents and maintainers

This repository is the current AUTOSEG application and the seed of a future
generic, modular, open-source platform. Read this file before changing code.

## Read first

1. `docs/PRODUCT_VISION.md` — product boundaries and long-term direction.
2. `docs/PLATFORM_MIGRATION_PLAYBOOK.md` — how to migrate one slice at a time.
3. `docs/PLATFORM_MIGRATION_LEDGER.md` — what is already migrated and what is
   still legacy.
4. `docs/GTK4_LINUX_MACOS.md` — current desktop frontend.
5. `workaholic/AGENTS.md` and `workaholic/docs/ARCHITECTURE.md` before changing
   the engine.
6. `CHANGELOG.md` — recent behavior changes and known constraints.

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
