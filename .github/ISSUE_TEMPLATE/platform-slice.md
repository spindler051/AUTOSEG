---
name: Platform migration slice
about: Plan one small, reversible migration step
title: "slice: "
labels: architecture, migration
assignees: ""
---

## Slice

- Legacy source:
- Target contract/module:
- Current ledger status:
- Desired status after this issue:

## Behavior to preserve

- User-visible flows:
- Calculations/rounding:
- PDFs/emails/financial side effects:
- Permissions/auth:

## Characterization tests

- [ ] Tests added for current behavior.
- [ ] Tests run against a temporary database.

## Migration plan

1. Adapter/read path:
2. Write path:
3. Feature flag/rollback:
4. Data backup/migration:
5. Entry points migrated:

## Workaholic fit

- [ ] Generic core
- [ ] Brazilian locale module
- [ ] AUTOSEG flavor
- [ ] GTK shell only

Reason:

## Definition of done

- [ ] Parity tests pass.
- [ ] Ledger updated.
- [ ] Changelog/docs updated.
- [ ] Rollback documented.
- [ ] Remaining legacy writes listed.
