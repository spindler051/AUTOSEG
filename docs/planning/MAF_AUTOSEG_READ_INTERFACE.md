# MAF ⇄ AUTOSEG read interface

**Status:** planning, priority item. No code, no schema change, no flag change.
**Owner decision (2026-11-14):** remove the filesystem coupling between Meu Auto
Financeiro and AUTOSEG, and expose every AUTOSEG fact MAF uses through a clean,
versioned interface. The migration must be **transparent to the user**: the same
numbers, the same linking flow, the same messages, no new settings.

Related: [`LOCAL_SYNC_MODES_ANALYSIS.md`](LOCAL_SYNC_MODES_ANALYSIS.md) §8,
[`../operations/MEU_AUTO_FINANCEIRO.md`](../operations/MEU_AUTO_FINANCEIRO.md).

## 1. Why

MAF is a separate product with its own process, port, database, login and store.
Its AUTOSEG bridge is still the one from the embedded era: it opens
`dados.db` directly and runs SQL.

```python
# my_auto_financeiro.py:568
def fonte_autoseg(banco, pid):
    from prestadores_ext import db as autoseg_db
    with autoseg_db(banco) as c:
        ...
```

Consequences today:

| Issue | Effect |
|---|---|
| Trust boundary | the MAF process can read the whole production database — all customers, PII, invoices, every provider's money |
| Storage coupling | needs `-wal`/`-shm` write access next to `dados.db`, which forces a writable mount |
| No revocation | unlinking a MAF account does not cut data access |
| No audit | reads are invisible |
| No portability | the database must remain a local file forever |

A read-only finance API already exists (`/api/v1`, bearer tokens, scope
`financeiro:read`, rate limit, access audit) and is already served on port 8766.
MAF simply does not use it.

**Target: `/api/v2`, not `/api/v1`.** v1 is a table-shaped finance read built for
the GTK desktop; it cannot express MAF's predicate, has no credential-to-token
exchange and no consistency token. Patching it would create permanent
compatibility debt. The boundary this item consumes is specified in
[`API_V2.md`](API_V2.md). v1 stays frozen for its existing consumers.

## 2. Dependency inventory

Every AUTOSEG fact MAF consumes, and what the API offers.

| MAF function | Reads | API equivalent | Gap |
|---|---|---|---|
| `autenticar_autoseg()` | `prestadores_ext.autenticar` — e-mail + password against `prestadores` | none | **needs a linking endpoint** |
| `fonte_autoseg()` primários | `financeiro` × `os_encerramentos` × `ordens_servico` + `produtividade_rateios` sum | `/financeiro/lancamentos` | API excludes archived OS; MAF does not |
| `fonte_autoseg()` secundários | `produtividade_rateios` × `produtividade_repasses` | `/financeiro/rateios` | API excludes archived OS; MAF does not |
| `inicializar_sync()` | same projection, used as baseline | same as above | same |
| `reconciliar_autoseg()` | calls `fonte_autoseg`, diffs against `sync_autoseg` | none needed (MAF-local) | — |
| `resumo_autoseg()` | `produtividade_os.financeiro_pessoal` | `/financeiro/resumo` | none: the API calls the same function |
| optional e-mail draft | `gmail_service` | out of scope | separate item |

Identity mapping matters: MAF keys receipts as `os:<financeiro.id>` — the
**financeiro row id**, not the OS id — and repasses as `repasse:<os_id>`.
`/financeiro/lancamentos` returns `id` (financeiro) and `/financeiro/rateios`
returns `os.id`, so both keys are derivable. This must stay true; it is the
hinge the whole reconciliation baseline hangs on.

## 3. Production evidence (snapshot 2026-11-14)

| Fact | Value | Consequence |
|---|---|---|
| OS total / archived | 37 / 4 | — |
| `financeiro` rows | 24 | — |
| `financeiro` Recebido on archived OS | **0** | primary receipts unaffected by the archived filter *today* |
| `produtividade_rateios` rows | 20 | — |
| rateios on archived OS | **2** | secondary repasses **would change** if the API filter is used as-is |
| `produtividade_repasses` rows | 20 | — |
| `os_encerramentos` rows | 32 | — |
| OS with more than one `os_encerramentos` row | **0** | no fan-out today, not guaranteed by schema |
| MAF users / linked to AUTOSEG | 4 / 2 (pid 1, pid 4) | parity must be proven for both |

The two archived rateios are the concrete reason a naive API switch is not
transparent: one technician's credited balance could move.

## 4. Transparency contract

Non-negotiable, and the acceptance criterion for the whole item:

1. For identical source data, `fonte_autoseg` returns the **same keys, the same
   cent values and the same descriptions**.
2. Linking keeps the same user experience: e-mail + AUTOSEG password, same error
   messages, no token copy/paste, no re-link prompt for accounts already linked.
3. Reconciliation keeps the same cadence (15 s) and the same baseline semantics
   (`inicializar_sync` marks the starting point so history is not credited).
4. Failures degrade exactly as today: the banner appears, the last synced values
   remain, nothing is credited twice.
5. No new user-visible screen, setting or state.

## 5. Interface requirements

These requirements target **`/api/v2`** (see [`API_V2.md`](API_V2.md)); `/api/v1`
is not the boundary for this migration.

- **Linking:** an endpoint that exchanges AUTOSEG credentials for a scoped,
  revocable token, so the password flow is unchanged for the user. A device/authorization
  code flow is acceptable only if the visible steps stay the same.
- **Receipts projection** must reproduce MAF's current predicate exactly,
  including archived OSS, unless parity proves the difference is zero for both
  linked providers. Prefer an explicit parameter (e.g. `include_archived`) over
  silently changing the default.
- **Integer cents**, `numero_os`, status, and the exact description strings MAF
  writes into `movimentos` (`OS {numero} · parcela recebida AUTOSEG`,
  `OS {numero} · repasse AUTOSEG`).
- **Pagination** must be complete: `/api/v1` caps at 200, MAF must page through
  or the balance silently truncates.
- **Versioning:** `/api/v1` + `openapi.json` already exist; additive changes only.
- **Revocation:** unlinking MAF must revoke the token immediately and be audited.

## 6. Parity plan

Before any switch:

1. Implement the API-backed adapter next to the SQL one.
2. For each linked pid, compute both projections on the production snapshot and
   require `dict_equal`, not "approximately equal".
3. Cover the edge cases: archived OS, `os_encerramentos` fan-out, rateio greater
   than received (MAF raises), status other than `Recebido`, repasse partly paid,
   and the two known archived rateios.
4. Only then switch the default.

## 7. Migration steps

1. Add the linking endpoint and any missing projection fields (AUTOSEG side).
2. Add the API adapter in MAF, SQL adapter still default.
3. Parity harness green on the production snapshot for both linked users.
4. Switch the default to the API.
5. Remove the SQL adapter and the filesystem access; restore the read-only
   sandbox or drop the mount entirely.
6. Reduce AUTOSEG privileges for the MAF unit to none.

The temporary dual adapter is a migration scaffold, not a permanent fallback.
It exists only between steps 2 and 5 and must not survive the item.

## 8. Risks

| Risk | Mitigation |
|---|---|
| archived-OS filter changes a balance | parity gate, explicit parameter |
| duplicate `os_encerramentos` rows fan out `/lancamentos` | parity check + unique constraint review, separate item |
| `financeiro.valor` string→cents conversion drift | compare cents, not floats |
| rateio greater than received | preserve the `ValueError` behavior or fail closed |
| token revoked or expired mid-sync | same banner path, no partial credit |
| 200-item pagination truncation | paginate in the adapter, assert totals |
| double credit during cutover | switch atomically, keep `sync_autoseg` baseline |

## 9. Non-goals

- no MAF write access to AUTOSEG, ever;
- no change to MAF's UI, wording or user-visible flow;
- no Workaholic extraction in this item;
- no change to the `/api/v1` contract beyond additive fields;
- no schema change outside the existing `api_tokens` tables.

## 10. Priority

**P1, immediately after the A5 security queue (A5b, A5c).** It is the last piece
of the "separate products, clean boundaries" direction, and it is what allows
AUTOSEG to stop granting filesystem access to another product.
