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

## 4.1 Quality gate — no test hacks

A feedback item is only **Corrigido na DEV** when the fix is in the production
path and the test proves it. The following are review blockers.

1. **Failing test first.** Reproduce the report with a test that fails on the
   current code. The same test must pass after the fix without changing its
   expected behavior.
2. **No test-only branches.** Do not add `if TESTING`, `if DEBUG`, hidden test
   flags or code paths that exist only for the suite. Tests create real rows,
   real users and call the real function. Mock only external services (Gmail,
   Cloudflare, PDF provider, clock).
3. **Do not mock the boundary under test.** For permissions, state transitions
   and SQL scoping, do not patch the policy, the query or the helper. Create
   provider A/B, admin, revoked membership and assert the real result.
4. **Hide at the source.** If a field or row is restricted, the SQL/service must
   not fetch or serialize it. Removing it only from HTML while the JSON still
   returns it is not a fix. `SELECT *` followed by `del` is not a fix.
5. **One rule, one place.** Role and state rules belong in the policy or a
   transition guard, not scattered `if role == ...` checks. A new exception
   must be written where the next change can find it.
6. **No silent failure.** No `except: pass`, no “saved” page after a required
   write failed, no partial success presented as complete. Fail closed or report
   the partial result explicitly.
7. **Classify before coding.**
   - visibility/permission detail → policy entry + read helper + test;
   - state transition (for example reopen) → domain rule + transactional guard
     + test;
   - data bug → regression test + root-cause fix;
   - temporary workaround → explicit debt entry (see item 9).
8. **Negative cases are mandatory.** Test unauthorized access, revoked
   membership, flag off and on, empty/invalid input and the “not found” path.
   A happy-path test alone does not close a feedback item.
9. **Temporary workaround is explicit debt.** If a proper fix is genuinely too
   large, record it in the item as:

   ```text
   HACK(area): what is temporary
   Why: why the proper fix is deferred
   Risk: what can leak or break
   Owner: who removes it
   Remove by: condition or date
   ```

   No untracked `TODO`, no silent bypass.
10. **Full validation.** Run the focused tests and the full suite; record exact
    pass/fail/error/skip counts. Also run `py_compile`, `git diff --check` and
    `audit_comments --strict`. State explicitly that `main`, schema, flags and
    data were not changed.

### Review checklist

- [ ] Does this patch change production behavior, or only the test?
- [ ] Did a failing test exist before the fix?
- [ ] Is any authorization, state or SQL rule bypassed for convenience?
- [ ] Is any restricted field still fetched, serialized or logged?
- [ ] Is the negative case covered, not only the happy path?
- [ ] Is any temporary workaround recorded with owner and removal condition?
- [ ] Is the rule in one place, or duplicated in the UI and the service?

If any answer is unclear, the item stays **Em correção**, not **Corrigido na
DEV**.

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
| FB-0063 | `/financeiro` (web + GTK) | Personal per-user visual mask stored **on the server**: a checkbox on each received entry hides that value and removes it from the user's own “Recebido” card only. The item stays **Recebido**; admin/reports/ledger and other users are unchanged. Not the global 144/145 toggle. | Pendente na DEV | — |
| FB-0064 | `/os/{id}/pdf-preview`, `/os/{id}/pdf`, `/icone.png` | The PDF is 9.8 MB and its download times out; a 2048×2048, ~7 MB icon is embedded as a 22×22 seal on every page, while the photos are already compressed. | Pendente na DEV | — |
| FB-0065 | `/os/{id}` | The edit form kept showing old Solicitação original, Diagnóstico, Serviço executado and Resultado because an old `os_rascunhos_web` draft overrode the current database values. | Pendente na DEV | — |
| FB-0066 | GTK OS edit | The GTK OS dialog has no fields for Solicitação original, Diagnóstico, Serviço executado and Resultado e testes; only the Web admin form exposes them. | Pendente na DEV | — |
| FB-0067 | `/os/{id}` | A live admin cannot attach an invoice PDF to an OS whose responsible provider is somebody else; the Web guard accepts the admin, but the domain writer rejects it. | Pendente na DEV | — |
| FB-0068 | `/financeiro` | After confirming a receipt/payment, the page returns to the top instead of preserving the current finance section/scroll. MAIN 162 is the same report, marked Incompleto. | Pendente na DEV | — |
| FB-0069 | `/os` | Add an installment checkbox + number of installments; show Parcela 1 on conclusion and release each next installment only after the previous one is received. | Pendente na DEV | — |

### FB-0063 — Mascarar valor por item recebido

**Confirmed by the maintainer: a personal visual setting, not an admin
option.** The signed-in provider masks their own received values. It does not
change the server data, the reports, the PDF, the admin view or any other
user's view.

**Scope**

- per signed-in provider, for their own received entries;
- Web and GTK, same behavior;
- the entry remains listed and keeps the status **Recebido**;
- its value is hidden as `•••` and excluded from that user's “Recebido” card
  only;
- the real `financeiro`/`produtividade_repasses` rows, the company ledger, the
  reports and the admin view stay untouched;
- no permission key, no admin toggle, no audit entry;
- one additive server-side preference table, approved with this item.

**Behavior**

- each received row gets a checkbox/action **Mascarar valor**;
- masked: the row stays, the value is displayed as `•••`, and the card is
  reduced by exactly that value;
- unmask restores the value and the total;
- the choice is remembered per user.

**Persistence (server-side, per user)**

The preference is stored on the server, so it follows the provider across
devices and clients. Proposed additive table (approval is this item):

```text
financeiro_mascaras(
  prestador_id INTEGER NOT NULL,
  item_kind   TEXT NOT NULL,   -- 'finalizador' | 'rateio'
  item_key    TEXT NOT NULL,   -- financeiro.id or os_id
  masked_em   TEXT NOT NULL,
  PRIMARY KEY (prestador_id, item_kind, item_key)
)
```

- only the owner reads and writes their own rows; the server derives
  `prestador_id` from the authenticated principal, never from the request;
- the personal finance endpoint returns `masked` per item and computes that
  user's “Recebido” total excluding the masked ones;
- admin, reports, PDF and the real ledger are not affected;
- unmasking deletes the row;
- an alternative is a generic `prestador_preferencias` table if more visual
  preferences appear; do not hide this in a business config blob.

**Why it is not 144/145**

144/145 are a **global** visual toggle for the whole finance page. FB-0063 is
**per item** and changes only the signed-in user's rendered “Recebido” card.
The two can coexist.

**Resolved decisions**

1. who: the signed-in provider, own rows only;
2. scope: personal view only, never admin/global;
3. display: value as `•••`, excluded from the card; the real amount stays in
   the data;
4. entries: all received entries in the personal list (finalizador and
   secondary);
5. legacy rows (`confirmado_por = NULL`, e.g. the 680,00 consolidation) are
   maskable like any other;
6. persistence: server-side per provider; one additive table, no changes to
   the ledger;
7. reports/PDF/admin: unaffected.

**Non-goals**

- do not delete the received row;
- do not alter `financeiro` or `produtividade_repasses` amounts;
- do not change company totals, reports or the admin view;
- do not confuse this with the global visual mask (144/145);
- the only schema addition is the per-user preference table above; no flags,
  no migration of existing data.

**Acceptance tests (when implemented)**

- masking one received row keeps it as Recebido, shows `•••`, and reduces the
  card by exactly its value;
- unmasking restores the exact total;
- the choice survives a reload (web), an app restart (GTK) and a login on
  another device, because it is stored on the server;
- another provider still sees the full value and the full total, and cannot
  read or change this provider's mask;
- company totals, reports, PDF and admin view are unchanged;
- no `financeiro`/`produtividade_repasses` row or amount is modified;
- unmasking deletes only the preference row.

### FB-0064 — PDF bloat and download timeout

- **Page:** `/os/{id}/pdf-preview`, `/os/{id}/pdf`, `/icone.png`
- **Reported:** the PDF download failed after F5 and repeated attempts. The
  generated PDF was 9.8 MB. Raising `Handler.timeout` was rejected as a
  workaround; the request is to fix the cause.
- **Evidence:** `pdfimages` showed a 2048×2048 image object (~7.2 MB) embedded
  as the 22×22 page seal. The five OS photos were already compressed to
  roughly 128–280 KB each (~900 KB total). The source `/icone.png` is
  2048×2048 RGBA, 6.9 MB.
- **Expected:** generate a small cached seal (64×64 or 96×96) and use it in
  the PDF; serve a resized icon at `/icone.png`; keep photo compression. The
  final PDF should be around 1 MB and download without a timeout. Streaming
  and a size-appropriate timeout can be added later as robustness, but must
  not be the only fix.
- **Category / urgency:** defect / P1.
- **Decision:** Pendente na DEV.
- **Fix:** —
- **Test:** generate a PDF with photos and assert that it stays below a small
  size bound, that no 2048×2048 image is embedded, and that a real download
  completes. Check `/icone.png` response size and dimensions.
- **Promotion:** pending `main`.

### FB-0065 — Stale autosaved draft overrides current OS data

- **Page:** `/os/{id}`
- **Reported:** after an administrator updated the original request and the
  three technical fields directly in the database, F5 still showed the old
  text. The form was loading an old `os_rascunhos_web` row for the current
  provider and merging it over the current OS data.
- **Expected:** the current server data wins when the OS is newer than the
  draft. A stale draft must be discarded or shown as an explicit conflict; it
  must never silently replace admin/server changes. Saving must use the
  current OS version.
- **Category / urgency:** defect / P1.
- **Decision:** Pendente na DEV.
- **Fix:** —
- **Test:** save an OS, leave an older draft for the same provider, update the
  OS server-side, reload the form and assert that the current values appear;
  save and assert the current version is used and no old text is restored.
- **Promotion:** pending `main`.

### FB-0066 — GTK OS edit lacks the technical report fields

- **Page:** GTK OS edit
- **Reported:** the user wanted to edit the OS and could not see the fields
  “Solicitação original”, “Diagnóstico”, “Serviço executado” and “Resultado e
  testes” in the GTK dialog. Only the Web admin form exposes them.
- **Expected:** if GTK is allowed to edit the OS, it must show the same fields
  and submit them through the same Step 0 writer. Otherwise the surface
  exception must be explicit in the navigation/registry and the user must be
  directed to Web.
- **Category / urgency:** parity defect / P2.
- **Decision:** Pendente na DEV.
- **Fix:** —
- **Test:** open the GTK OS dialog, verify the fields and labels, save and
  reload, then confirm the values in the database and in the PDF.
- **Promotion:** pending `main`.

### FB-0067 — Admin cannot attach an invoice PDF to another provider's OS

- **Page:** `/os/{id}`
- **Reported:** the live MAIN admin could not attach the invoice PDF to an OS
  whose responsible provider was somebody else.
- **Evidence:** `os_commands._write_attach_invoice` accepts the admin, but then
  calls `ext.salvar_nota_fiscal(banco, oid, pid, ...)`; the domain function
  still rejects any `pid` that is not the current responsible provider.
  The Web guard and the domain guard disagree.
- **Expected:** an active administrator can attach the invoice through the same
  domain writer, with the admin actor recorded in the event. Non-admin
  non-responsible providers remain denied.
- **Category / urgency:** defect / P1.
- **Decision:** Pendente na DEV.
- **Fix:** —
- **Test:** admin attaches an invoice to another provider's OS and the file is
  linked; responsible provider still can; unrelated employee is denied; the
  event records the admin actor.
- **Promotion:** pending `main`.

### FB-0068 — Finance scroll position resets after a receipt/payment action

- **Page:** `/financeiro`
- **Reported:** after confirming a payment or a transfer, the page reloads and
  jumps back to the top; the user wants to stay in the same finance section and
  scroll position. MAIN 162 is the same report, marked Incompleto.
- **Expected:** preserve the active finance tab and the scroll position across
  the AJAX/refresh cycle; 162 is closed as a duplicate.
- **Category / urgency:** defect / P1.
- **Decision:** Pendente na DEV.
- **Fix:** —
- **Test:** open A receber, scroll to an item, confirm it, and assert the page
  remains in A receber at the same relative position; also test Recebidos and
  Repasses.
- **Promotion:** pending `main`.

### FB-0069 — Installment plan for the OS

- **Page:** `/os`
- **Reported:** add a checkbox and a number-of-installments field in the
  Situação e relatório section. Applying is automatic, without a confirm
  button. On conclusion, A receber shows Parcela 1; the next installment is
  released only after the previous one is received.
- **Expected:** checkbox + installment count; Parcela 1 created with the
  concluded OS; sequential release in A receber; no change to the Step 0
  writer or to the existing finance rules.
- **Category / urgency:** product feature / P2.
- **Decision:** Pendente na DEV.
- **Fix:** —
- **Test:** conclude an OS with N installments and assert only Parcela 1 is
  visible; confirm Parcela 1 and assert Parcela 2 appears; repeat through the
  last installment; no duplicate receivable rows.
- **Promotion:** pending `main`.

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
