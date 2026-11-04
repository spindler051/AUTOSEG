# Platform migration ledger

**Status values:** `legacy only`, `adapter read`, `adapter write`, `source of
truth`, `flavor/locale module`, `not started`.

This ledger is the single place to see what is generic, what is still legacy,
and what the next small step is. Update it in the same PR that changes a slice.

## Current slices

| Slice | Legacy source | Target | Status | Remaining work / next step |
|---|---|---|---|---|
| Clients | `clientes` | Workaholic `cliente` schema + `integracao/clientes.py` | **adapter write (partial)** | Remove remaining direct writes from portal/desktop/importers; keep legacy integer IDs as origin metadata. |
| Service catalog | `catalogo_servicos` | Generic catalog/item schema + adapter | **legacy only** | Define generic service/item fields; characterize catalog CRUD; start with reads. |
| Materials / stock | `materiais_os`, `estoque_produtos`, `estoque_movimentos` | Generic materials/stock contracts + adapter | **legacy only** | Separate charged price from internal cost as generic concepts; migrate stock movement reads. |
| Service orders | `ordens_servico`, `os_encerramentos`, `os_eventos` | Generic work-order schema + adapter | **legacy only** | High-value, high-coupling slice. Start with read adapter and characterization tests; do not change status semantics. |
| Finance | `financeiro`, `produtividade_rateios`, `produtividade_repasses` | Generic receivable/payment/commission contracts | **legacy only** | Separate generic receivable/payment from AUTOSEG commission rules; define locale payment adapter. |
| Providers / teams | `prestadores`, `os_prestadores`, `os_responsaveis` | Generic actor/assignment contracts | **legacy only** | Define person/provider/team boundary; migrate reads first. |
| Portals | `portal_prestador.py`, `servidor_web.py`, `portal_cliente_v94.py` | AUTOSEG flavor modules | **flavor/locale module (current)** | Keep in AUTOSEG; later extract a generic portal module only if another flavor needs it. |
| Reports / PDFs | `pdf_cliente_v9.py`, `marca.py`, report templates | Generic document contracts + AUTOSEG templates | **flavor/locale module (current)** | Define generic document metadata; keep visual templates in AUTOSEG. |
| Fiscal / NF-e / NFS-e | `prestadores_ext.py`, `pdf`/fiscal drafts, future integrations | Brazilian locale module | **flavor/locale module (planned)** | Define tax-document provider contract; do not put fiscal rules in core. |
| Email / payments | `gmail_service.py`, future payment integrations | Generic integration contracts + adapters | **legacy only** | Define provider interfaces; keep credentials outside code. |
| GTK shell | `gtk_app.py`, `gtk_dialogos.py`, `gtk_comum.py` | Generic GTK application | **AUTOSEG UI today** | Keep AUTOSEG-specific screens in flavor; extract generic shell only when a second flavor exists. |
| CLI | `workaholic/src/workaholic/cli` | Workaholic CLI | **prototype** | Keep tests; add commands only when a real consumer exists. |

## Workaholic adoption

| Capability | Status | Notes |
|---|---|---|
| Schema/fields/validation | Prototype | `workaholic/src/workaholic/domain` |
| YAML/SQLite repositories | Prototype | Same contract, separate state; no sync |
| Optimistic versioning | Prototype | Used by clients adapter |
| Generic GTK shell | Not started | Needs module/boundary decisions |
| Module/plugin system | Not started | Decide Python entry points vs manifest |
| ADR/architecture docs | Started | `workaholic/docs/` |
| Production integration | Clients only | `integracao/clientes.py` |

## Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-11-04 | Keep AUTOSEG behavior as the parity contract during platformization. | Users should not need to know the architecture changed. |
| 2026-11-04 | Treat Workaholic as a first-class workstream, not a side prototype. | Avoid orphaned engine work; every generic capability needs a consumer. |
| 2026-11-04 | Keep Brazilian fiscal/payment rules outside the generic core. | The base must remain flavorless and usable in other countries/professions. |
| 2026-11-04 | Prefer a monorepo until module contracts and release cadence are stable. | Avoid premature repository split and duplicated CI. |

## Next recommended micro-slices

1. **Catalog read adapter** — add characterization tests for
   `catalogo_servicos`, then read through a Workaholic adapter without changing
   the UI.
2. **Clients write cleanup** — move remaining direct client writes through
   `integracao/clientes.py`; keep the legacy table and IDs.
3. **Service-order characterization** — lock status, totals, materials and PDF
   behavior before attempting an adapter.
4. **Workaholic schema revision** — add a minimal schema/versioning mechanism
   needed by the next slice.
5. **Module contract decision** — choose entry points + manifest, document it,
   and implement only what the first two modules need.

## Update rule

When a slice changes:

1. change its status in this table;
2. list the entry points migrated;
3. list the tests that prove parity;
4. list remaining direct legacy writes;
5. write the next small step.

Do not mark a slice `source of truth` while any production writer still bypasses
the adapter.
