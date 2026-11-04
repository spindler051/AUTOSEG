# OS financial correction UI

**Status:** proposal for the next DEV change. Not implemented.  
**Scope:** desktop GTK first; provider portal stays read-only for financial corrections.  
**Production:** the current MAIN server and database are not changed by this document.

## 1. Problem

Administrative corrections currently require direct database work. Example:

- OS-0024 had a separate R$ 680,00 charge for João Lucas.
- That amount was actually part of OS-0025, whose gross total is R$ 1.308,00.
- The correct internal split is Julio R$ 628,00 and João Lucas R$ 680,00.
- The duplicate OS had to be removed and a rateio inserted manually.

This is safe only for a maintainer with database access. It is not usable by the
person who operates AUTOSEG, and direct database edits are risky.

## 2. Current UI limitations

The current GTK app and portals cannot perform this correction:

- there is no “delete OS” action anywhere;
- there is no “annul concluded OS” action;
- rateios can only be entered once, at the moment of conclusion;
- `produtividade_rateios` explicitly rejects a second rateio for the same OS;
- the provider portal does not allow editing concluded OS values or shares;
- the user cannot add João Lucas as a secondary technician after OS-0025 is
  concluded;
- editing a concluded OS in GTK changes descriptive fields, but not the
  financial split.

So the current answer is: **not possible through the UI**.

## 3. Recommended UX: two explicit actions

Do not build a single “merge OS” wizard. It creates ambiguity when the two OSes
have different clients, values, PDFs or payment states. Instead, expose two
small, auditable actions.

### Action A — “Ajustar rateio” on a concluded OS

Where:

- GTK → open a concluded OS (Histórico e relatórios → Abrir OS);
- button in the “Atendimento e encerramento” section or next to “Republicar PDF”.

Dialog contents:

```text
Ajustar divisão do valor

OS: OS-0025 — Condomínio Edifício Frida
Total cobrado: R$ 1.308,00

Técnicos secundários
  [ João Lucas ▼ ]  [ R$ 680,00 ]  [ Remover ]

[ + Adicionar técnico ]

Soma distribuída: R$ 680,00
Saldo do finalizador (Julio): R$ 628,00

Motivo do ajuste: [ obrigatório ]

[ Cancelar ]  [ Salvar ajuste ]
```

Rules:

- only the desktop administrator sees this action;
- the finalizer remains the technician recorded in `os_encerramentos`;
- the finalizer receives `total - secondary shares`;
- the sum of secondary shares cannot exceed the OS total;
- each secondary technician must be active and cannot be the finalizer;
- a reason is required;
- saving replaces the rateio atomically and records an event with before/after;
- if part of the rateio was already paid, reducing a share below the paid amount
  is blocked; increasing a share is allowed;
- gross value, PDF, email and fiscal documents are not changed by a rateio
  adjustment; this is an internal split only.

Result for the example:

- Julio: R$ 628,00;
- João Lucas: R$ 680,00;
- client receivable remains R$ 1.308,00.

### Action B — “Anular OS” on a concluded OS

Where:

- GTK → open the concluded OS → destructive action “Anular OS”;
- optionally also a button in the Financeiro list after selecting a charge.

Dialog contents:

```text
Anular esta OS?

OS-0024 — R$ 680,00
Esta OS deixará de contar no financeiro.
O histórico, os eventos e os documentos serão preservados.

Motivo: [ obrigatório ]
OS onde o valor foi registrado (opcional): [ OS-0025 ▼ ]

[ Cancelar ]  [ Anular OS ]
```

Rules:

- never hard-delete the OS or its history;
- set `ordens_servico.status = 'Cancelada'` (or a future dedicated “Anulada”
  status if the model grows);
- set the finance record to `Cancelado` and remove it from receivable totals;
- keep the OS, events, attachments and PDFs available in history;
- record an `os_anulacoes` row and an event with the reason, actor, timestamp and
  optional target OS;
- block annulment when the finance record is already `Recebido`; in that case
  the money must be handled explicitly, not hidden by an annulment;
- do not infer or move money automatically. The user first creates the correct
  rateio in the target OS, then annuls the duplicate.

This is the safe UI equivalent of “delete the R$ 680 OS”: it stops the double
counting without erasing audit history.

## 4. Why not one “merge” button

A merge button would have to answer questions the system cannot safely infer:

- which OS keeps the official number and client;
- what happens to a published PDF;
- what happens if one side is already paid;
- which technician owns each part;
- what happens when clients differ;
- how to undo the merge.

Two explicit actions are easier to understand, test and reverse.

## 5. Data model and backend

No destructive schema rewrite is required.

- `financeiro.status` gains the value `Cancelado` (text column; no migration
  needed, but all totals must ignore it explicitly).
- New additive table:

```sql
CREATE TABLE IF NOT EXISTS os_anulacoes (
  os_id INTEGER PRIMARY KEY,
  motivo TEXT NOT NULL,
  os_substituta_id INTEGER,
  ator TEXT NOT NULL,
  anulado_em TEXT NOT NULL
);
```

- `produtividade_rateios` is reused. A new service must support replacing the
  split after conclusion:

```text
ajustar_rateios_os_concluida(banco, os_id, ator, motivo, parcelas)
anular_os_concluida(banco, os_id, ator, motivo, os_substituta_id=None)
```

Both services must:

- run inside `BEGIN IMMEDIATE`;
- validate status, totals, active technicians, paid repasses and concurrency;
- write one append-only audit event;
- return the resulting split for the UI to display;
- have characterization/contract tests before the GTK wiring.

## 6. Implementation order

1. **Backend contract** — add `ajustar_rateios_os_concluida` and tests.
2. **Backend contract** — add `anular_os_concluida`, `os_anulacoes`, finance
   `Cancelado`, and tests.
3. **GTK read view** — show current split on a concluded OS.
4. **GTK Action A** — “Ajustar rateio” dialog with validation and audit.
5. **GTK Action B** — “Anular OS” dialog with reason and optional target OS.
6. **Financeiro list** — show annulled/canceled state and exclude it from totals.
7. **Smoke test** — reproduce the OS-0024/OS-0025 case on a copy of the database,
   without touching production.

The provider portal is intentionally out of scope for the first version. It must
continue to show only the authenticated technician’s own share.

## 7. Acceptance criteria

- An administrator can add João Lucas with R$ 680,00 to OS-0025 from GTK.
- Julio’s own share updates to R$ 628,00; the gross remains R$ 1.308,00.
- The provider portal shows João Lucas with R$ 680,00 to receive from OS-0025.
- An administrator can annul OS-0024 from GTK.
- OS-0024 disappears from receivable totals but remains visible in history with
  its cancellation/annulment reason.
- No OS, event, PDF or finance history is hard-deleted by the UI.
- The correction is recorded with actor, timestamp and before/after values.
- Repeating the same operation is rejected or idempotent, never duplicated.
- Existing OS totals, PDFs, emails and fiscal records are unchanged.

## 8. Explicit non-goals

- No provider-side financial editing.
- No automatic “merge and delete” operation.
- No hard delete of financial or fiscal history.
- No cross-client value transfer in the first version.
- No change to the current production database as part of this plan.
