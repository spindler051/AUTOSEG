# Company cash ledger — contributions and expenses

**Status:** implemented as `9.6.0-dev.20` and promoted to MAIN after validation.
**Scope:** desktop GTK app, inside **Materiais e estoque**. Not exposed by the
Provider or Client portals.
**Product goal:** keep a lightweight, honest record of investor capital and
company expenses without mixing them with OS revenue, stock or technician
rateios.

## 1. Why it is separate

The existing `financeiro` table records what a client owes for an OS. That is
revenue/receivable, not capital and not profit. The company ledger is a
different concept:

| Movement | Meaning | Effect on the company ledger |
|---|---|---|
| Aporte de investidor | Permanent capital contributed by an investor | Increases available capital; not revenue and not repayable |
| Compra de material | Material bought with company money | Expense/cash-out; may reference an OS only for context |
| Despesa com API | Operating cost, e.g. DeepSeek API | Expense/cash-out |
| Outra despesa | Any other company cost | Expense/cash-out |

OS revenue stays in **Financeiro**. It is not summed into the company ledger,
because that would mix revenue with capital and distort the balance. The ledger
shows a note explaining this.

The three concepts that must never be merged:

1. **Capital** — the investors' permanent contribution.
2. **Revenue** — the amount a client pays for an OS.
3. **Expense** — material, API, bank fees and other costs.

## 2. Rules

- Contributions are permanent capital; the system does not create a debt or a
  repayment schedule for them.
- A contribution requires an active provider/investor.
- A material purchase may reference an OS, but the reference is informational.
  It does **not** change `ordens_servico.custo_materiais`, `materiais_os`,
  `estoque_produtos`, `estoque_movimentos`, `financeiro` or the OS PDF.
- No SKU is required for the ledger. The existing stock form now labels SKU as
  optional, matching the underlying schema.
- Entries are archived, not deleted. Archiving preserves the row, timestamp and
  author and removes it from active totals.
- Values are stored as integer cents. Dates are stored as `YYYY-MM-DD` and
  accepted as `dd/mm/aaaa` or ISO in the UI.
- Contributions carry an optional **finalidade** (purpose) so the investor can
  record what the capital is for.
- The label is **Saldo do controle**, not “saldo em caixa”. It means
  `contributions − recorded expenses`; it is not a bank balance and does not
  include OS revenue. A negative balance means expenses exceeded contributions;
  it is shown, not hidden.

## 3. Data model

New additive table:

```sql
CREATE TABLE empresa_movimentos(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL CHECK(tipo IN ('aporte','material','api','despesa')),
    data TEXT NOT NULL,
    descricao TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT '',
    finalidade TEXT NOT NULL DEFAULT '',
    valor_centavos INTEGER NOT NULL CHECK(valor_centavos > 0),
    prestador_id INTEGER,
    os_id INTEGER,
    observacao TEXT NOT NULL DEFAULT '',
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    criado_por TEXT NOT NULL DEFAULT 'Desktop',
    arquivado_em TEXT,
    arquivado_por TEXT,
    FOREIGN KEY(prestador_id) REFERENCES prestadores(id),
    FOREIGN KEY(os_id) REFERENCES ordens_servico(id)
);
```

No existing table is altered.

## 4. UI

Path: desktop app → **Materiais e estoque**.

- A summary line shows capital, expenses and **saldo do controle**.
- **Caixa e investimentos** opens the ledger.
- **Novo lançamento** offers the four types.
- Contributions show a **finalidade** column; the form asks for it only for
  contributions.
- **Arquivar selecionado** preserves history.
- The form has no SKU field. The OS field is visible only for material
  purchases and is optional.
- The screen explicitly says the balance is not a bank balance.

## 5. Tests

`test_empresa_financeiro.py` covers:

- contributions by three investors and the per-investor totals;
- API, material and other expense totals;
- balance calculation;
- material linked to an OS without changing OS values;
- contribution requiring an active investor;
- OS link rejected for non-material entries;
- archiving preserving history and changing active totals;
- invalid types, values and dates;
- `dd/mm/aaaa` and ISO date input.

Run:

```bash
.venv/bin/python test_empresa_financeiro.py
```

## 6. Migration and rollback

The table is created with `CREATE TABLE IF NOT EXISTS` on app startup. Back up
the database before deploying to a copy with real data:

```bash
cp dados.db ~/AUTOSEG_BACKUPS_REV12/dados_antes_caixa_empresa_$(date +%Y%m%d_%H%M%S).db
```

Rollback:

- hide/remove the **Caixa e investimentos** button and the module import;
- the `empresa_movimentos` table can remain without affecting existing
  workflows;
- to remove the data deliberately, back up first and drop `empresa_movimentos`.

No OS, finance, stock, PDF, e-mail or fiscal record is modified by this feature.

## 7. Platform delta

The feature lives in the legacy AUTOSEG desktop and is intentionally isolated
behind `empresa_financeiro.py`. If the platform later gains a generic
cash/expense domain in Workaholic core, this module can be adapted behind the
same functions without changing the GTK dialogs or the database contract.
