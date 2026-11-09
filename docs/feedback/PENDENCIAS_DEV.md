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
| FB-0057 | `/os` | The client selector was a long list. It should search while typing and allow creating a client with only a name, marked incomplete. The area below “Atendido por” was empty. | Corrigido na DEV | `6b2366c`; `test_feedback_dev.py` (`test_os_form_busca_cliente_e_cria_novo_por_nome`) |
| FB-0058 | `/clientes` | A client with only a name appeared as Ativo instead of Dados incompletos. | Corrigido na DEV | `6b2366c`; `test_feedback_dev.py` (`test_lista_clientes_mostra_dados_incompletos`) |
| FB-0059 | `/os` | It was not possible to conclude an OS without choosing an e-mail recipient. | Corrigido na DEV | `6b2366c`; `test_feedback_dev.py` (`test_conclusao_sem_destinatario_nao_exige_email`) |
| FB-0060 | `/os` | The OS could be concluded without a payment method. | Corrigido na DEV | `6b2366c`; `test_feedback_dev.py` (`test_conclusao_exige_forma_de_pagamento`) |
| FB-0062 | `/login` | Login errors appeared as a full page and lost what the user had typed. All form errors should be toast/inline without navigation. | Corrigido na DEV | `6b2366c`; `test_feedback_dev.py` (`test_login_erro_fica_inline_e_preserva_email`) |

### FB-0057 — Busca e criação de cliente na OS

- **Page:** `/os`
- **Reported:** the client selector was a long list; the provider wanted to search while typing and create a new client when the name did not exist. The area below “Atendido por” was visually empty.
- **Expected:** filter existing clients as the provider types; if the name is new, create an active client explicitly marked `dados_incompletos=1`; keep the OS editable while the cadastro is completed.
- **Decision:** Corrigido na DEV.
- **Fix:** full OS form now uses a `datalist` search field with a hidden client id; the server resolves an existing exact name or creates a minimal incomplete client. The identification layout was balanced.
- **Commit:** `6b2366c`.
- **Test:** `test_os_form_busca_cliente_e_cria_novo_por_nome`.

### FB-0058 — Cliente incompleto na lista

- **Page:** `/clientes`
- **Reported:** a client created with only a name appeared as “Ativo”.
- **Expected:** the list shows “Dados incompletos” while the record is provisional.
- **Decision:** Corrigido na DEV.
- **Fix:** `clientes.dados_incompletos` is selected by the paginated query and takes precedence over the raw status in the list; the GTK summary also honors the persisted flag.
- **Commit:** `6b2366c`.
- **Test:** `test_lista_clientes_mostra_dados_incompletos`.

### FB-0059 — Concluir sem destinatário

- **Page:** `/os`
- **Reported:** the conclusion required at least one report recipient.
- **Expected:** an explicit “Não precisa de destinatário” option allows concluding without an e-mail.
- **Decision:** Corrigido na DEV.
- **Fix:** the checkbox is shown below the recipient fields; when checked, recipient validation and e-mail registration are skipped. The GTK closing dialog has an explicit switch to disable the automatic e-mail.
- **Commit:** `6b2366c`.
- **Test:** `test_conclusao_sem_destinatario_nao_exige_email`.

### FB-0060 — Forma de pagamento obrigatória

- **Page:** `/os`
- **Reported:** an OS could be concluded without a payment method.
- **Expected:** conclusion is refused with an inline/toast message until a payment method is selected.
- **Decision:** Corrigido na DEV.
- **Fix:** validation moved to `portal_negocios.os_salvar` and `os_write.salvar_os`, after the responsibility check; the same rule applies to the web portal and GTK. Quick OS creation remains allowed without payment.
- **Commit:** `6b2366c`.
- **Test:** `test_conclusao_exige_forma_de_pagamento`; unauthorized conclusion still returns 403.

### FB-0062 — Erros de formulário sem navegação

- **Page:** `/login`
- **Reported:** an invalid login was rendered as a new error page, losing the typed e-mail and password.
- **Expected:** errors appear as toast or inline feedback, preserving every field and the user’s context.
- **Decision:** Corrigido na DEV.
- **Fix:** the login form has an inline alert and the server returns JSON for Ajax; a generic submit handler now sends the remaining POST forms by `fetch`, reads JSON/HTML error markers and shows toast/inline without navigation. Forms whose success is a page or file declare `data-no-ajax`.
- **Commit:** `6b2366c`.
- **Test:** `test_login_erro_fica_inline_e_preserva_email`; full suite exercises the affected forms.

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
