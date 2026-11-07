# Feedback backlog — DEV workflow

This ledger records real problems and improvements reported through the
Provider Portal feedback channel. It is the human-reviewed link between a
runtime report and a documented change in `develop`.

**Scope:** DEV only. Nothing here is deployed automatically, and no feedback
record is written to `main` by the application.

## 1. Why a separate ledger

Runtime feedback lives in the local SQLite database, not in Git. It may contain
personal data and must not be committed. The ledger keeps only the durable
engineering outcome:

- what was reported (in anonymized form);
- why it matters;
- the decision (fix, clarify, discard or not a problem);
- the commit/test that closed it;
- what still needs human or legal review.

A feedback item is **not** a task until an administrator marks it
**Pendente na DEV**. The AI classification is advisory and can be wrong.

## 2. Triage states

| State | Meaning |
|---|---|
| `Aguardando triagem` | New report; no human decision yet. |
| `Pendente na DEV` | Confirmed real problem or necessary improvement; belongs in the DEV backlog. |
| `Em correção` | A change is being implemented in `develop`. |
| `Corrigido na DEV` | Implemented and covered by a test; not yet promoted to `main`. |
| `Descartado` | Duplicate, spam, out of scope or not actionable. |
| `Não é problema` | Misunderstanding or the feature already exists elsewhere; the provider should receive an explanation. |

Only a provider with the admin flag can change these states. The change is
audited in `portal_auditoria`.

## 3. Runtime to DEV

1. A provider submits feedback in the Provider Portal, optionally requesting an
   answer from the configured AI provider.
2. The record is stored in `portal_feedback`; the original text stays local.
   Only `mensagem_anonimizada` is sent to the AI.
3. An administrator opens `/feedback/recebidos`, reads the report and checks
   the screen/flow in `develop`.
4. The administrator chooses:
   - **Pendente na DEV** when the report identifies a real defect or a necessary
     improvement;
   - **Não é problema** when the feature exists under another name or the report
     is a misunderstanding;
   - **Descartado** for duplicates, spam or out-of-scope requests.
5. The administrator writes a short neutral note explaining the decision. Do
   not paste CPF/CNPJ, e-mail, phone, address, client names or production
   screenshots.
6. Before starting the fix, export the current backlog:

   ```bash
   # As an authenticated administrator:
   curl -b cookies.txt -o pendencias_feedback_dev.md \
     http://127.0.0.1:8766/feedback/pendencias.md
   ```

   The export contains only the anonymized message, page, category, urgency,
   suggested improvement, AI answer and triage note. It excludes provider name,
   IP, session hash and original message.
7. Copy only the relevant items into the cycle section below, with a stable
   `FB-0000` identifier.
8. Implement the fix in `develop` as a small commit. Add or update a test.
9. Change the state to **Em correção** while working and **Corrigido na DEV**
   when the test passes. Record the commit hash and test command in the triage
   note.
10. Close the cycle when the items are promoted to `main` by the normal daily
    decision. Promotion is manual and separate from the feedback feature.

The application never commits, deploys or edits this file. The export is a
snapshot; this ledger is curated by a human.

## 4. Ledger rules

- Use the anonymized report, not the original message.
- Keep one section per feedback cycle (date or release).
- Each item must have: ID, page, observed behavior, expected behavior,
  decision, fix reference and test.
- If an item changes money, tax, commission, fiscal data, authentication,
  permissions or the meaning of an OS/payment status, stop and ask the
  maintainer first (see `AGENTS.md`).
- If the report is a misunderstanding, document the explanation so support can
  reuse it.
- Do not delete history. Mark superseded items as such.
- Do not include production data, secrets or personal documents.

## 5. Current cycle

## Cycle 2026-11 — DEV

| ID | Page | Report (anonymized) | Decision | Fix / test |
|---|---|---|---|---|
| FB-0001 | `/financeiro` | Add a due date for receipt; if the date passes without confirming receipt, show it in red as overdue. | Corrigido na DEV | `efc7e3c`; `test_financeiro_vencimento.py` |

### FB-0001 — Prazo de recebimento e destaque de atraso

- **Page:** `/financeiro`
- **Reported:** the provider asked for an optional due date on receivables.
  When the date passes without the “recebido” confirmation, the item should be
  visibly overdue.
- **Expected:** each open receivable can store a due date; open items past the
  date show “Atrasado” in red; received or cancelled items are not marked
  overdue.
- **Category / urgency:** product improvement / P2. No change to money,
  commission, tax or payment state.
- **Decision:** Corrigido na DEV.
- **Human note:** the date is optional and stored in the existing
  `financeiro.vencimento` column. Only the finalizer or an administrator can
  change it. The operation is audited.
- **Fix:** `efc7e3c` — `portal_negocios.py`, `portal_prestador.py`,
  `test_financeiro_vencimento.py`.
- **Test:** `.venv/bin/python -m unittest -v test_financeiro_vencimento.py`
  (4 OK); related portal tests also pass.
- **Promotion:** pending `main`.

Open follow-ups before production:

- legal/privacy review of the support record, full-IP mode and retention;
- live AI test with the configured provider in a controlled environment;
- define who receives and triages feedback in each installation;
- add an automatic retention job for opening records and telemetry events;
- review the anonymization regexes against real Portuguese support text.

## 6. Item template

```markdown
### FB-0001 — short neutral title

- **Page:** `/path`
- **Reported:** what the provider observed, in anonymized form.
- **Expected:** what should happen instead.
- **Category / urgency:** AI suggestion or human classification.
- **Decision:** pending DEV / not a problem / discarded / duplicate.
- **Human note:** explanation, scope or question.
- **Fix:** commit hash, files changed.
- **Test:** command and result.
- **Promotion:** pending `main` / promoted on YYYY-MM-DD.
```

## 7. Privacy and retention

- The runtime database is the system of record for feedback. Back it up before
  schema work; never commit it.
- The Markdown export is safe to review but still operationally sensitive.
  Store it outside Git until the cycle is curated.
- Feedback records are support records and are not deleted automatically.
  Opening records can be pruned with
  `feedback_portal.limpar_aberturas_antigas()`.
- Full IP is stored only with `AUTOSEG_FEEDBACK_IP_MODE=full`; the default is a
  truncated network plus a keyed hash.
- Legal/privacy review is required before production use. This ledger does not
  replace that review.

## 8. Related documents

- [`docs/features/FEEDBACK_PORTAL.md`](../features/FEEDBACK_PORTAL.md) — design,
  routes, schema, AI prompt, telemetry and rollback.
- [`docs/features/OPEN_TELEMETRY.md`](../features/OPEN_TELEMETRY.md) — telemetry
  policy and current wiring.
- [`docs/USER_FEEDBACK_GUIDE.md`](../USER_FEEDBACK_GUIDE.md) — human-centered
  feedback practice.
- [`AGENTS.md`](../../AGENTS.md) — data safety and change rules.
