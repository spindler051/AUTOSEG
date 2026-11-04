## What changed

<!-- Short description of the user-visible behavior or fix. -->

## Behavior parity

- [ ] No intentional change to AUTOSEG’s visible workflow, labels, calculations, PDFs or emails.
- [ ] If behavior changed, it is explicitly requested and documented below.

## Platform delta (required)

Check exactly one:

- [ ] Small migration of one slice.
- [ ] New/updated generic contract or adapter.
- [ ] Characterization test that protects legacy behavior.
- [ ] Documentation/ledger update that unblocks the next slice.
- [ ] None — justified below.

Justification / next step:

```text
Platform delta:
Slice/contract:
Reason:
Next opportunity:
```

## Workaholic fit check

- [ ] Generic work-management concept → Workaholic core/schema
- [ ] Brazilian regulation/fiscal/payment rule → locale module
- [ ] Security/automation-specific workflow → AUTOSEG flavor
- [ ] GTK/navigation only → shell
- [ ] Still legacy for now; follow-up recorded

## Data and safety

- [ ] No production data, `dados.db`, credentials, PDFs or client files added.
- [ ] Schema/data changes have backup, migration and rollback instructions.
- [ ] No destructive rename of production columns/routes in this PR.
- [ ] Permissions/auth changes reviewed.

## Tests

Commands run:

```text
<command>
```

Result:

- [ ] Relevant suites pass.
- [ ] Manual smoke test described (if UI changed).

## Documentation

- [ ] `docs/PLATFORM_MIGRATION_LEDGER.md` updated if a slice moved.
- [ ] `CHANGELOG.md` updated for user-visible changes.
- [ ] Docs updated when a contract or workflow changed.

## Rollback

<!-- How to revert safely, especially for data/schema changes. -->
