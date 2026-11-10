# Platform migration ledger

**Status values:** `legacy only`, `adapter read`, `adapter write`, `source of
truth`, `flavor/locale module`, `not started`.

This ledger is the single place to see what is generic, what is still legacy,
and what the next small step is. Update it in the same PR that changes a slice.

Current session handoff: `docs/HANDOFF.md`.

## Current slices

| Slice | Legacy source | Target | Status | Remaining work / next step |
|---|---|---|---|---|
| Clients | `clientes` | Workaholic `cliente` schema + `officina/integration/clientes.py` + `officina/application/local_service.py` | **adapter read/write + application slice (partial)** | GTK list/dialog/dashboard now use `LocalService`; portal still calls the adapter directly. Remove remaining direct writes from portal/desktop/importers and expose clients through the remote API. Keep legacy integer IDs as origin metadata. |
| Service catalog | `officina/core/catalogo_servicos.py` | Generic catalog/item schema + adapter | **legacy only** | Define generic service/item fields; characterize catalog CRUD; start with reads. |
| Materials / stock | `materiais_os`, `estoque_produtos`, `estoque_movimentos` | Generic materials/stock contracts + adapter | **legacy only** | Separate charged price from internal cost as generic concepts; migrate stock movement reads. |
| Service orders | `ordens_servico`, `os_encerramentos`, `os_eventos` | Generic work-order schema + adapter | **legacy only** | Dashboard/history/report/portal read summaries now live in `repositorios/ordens.py`; characterize OS detail and active-list reads before the Workaholic adapter. Do not change status semantics. |
| Finance | `financeiro`, `produtividade_rateios`, `produtividade_repasses` | Generic receivable/payment/commission contracts | **legacy only** | Separate generic receivable/payment from AUTOSEG commission rules; define locale payment adapter. |
| Providers / teams | `prestadores`, `os_prestadores`, `os_responsaveis` | Generic actor/assignment contracts | **legacy only** | Define person/provider/team boundary; migrate reads first. |
| Identity / access | `prestadores`, `v9_usuarios`, `cliente_acessos`, `v9_admin_prestadores`, web cookies/sessions, desktop/API tokens | `accounts`, `account_links`, `provider_orgs`, `ObjectPolicy` | **schema + login service (library, not wired)** | `identity.py` resolves identities; `accounts.py` adds the opt-in schema and dry-run legacy import; `auth.py` authenticates by configurable identifiers with legacy fallback and returns `LoginResult`. No route/cookie/UI change yet. Next: wire the service behind a flag and migrate sessions. |
| Portals | `flavors/autoseg/modules/portal_prestador.py`, `servidor_web.py`, `portal_cliente_v94.py` | AUTOSEG flavor modules | **flavor/locale module (current)** | Keep in AUTOSEG; later extract a generic portal module only if another flavor needs it. |
| Web/GTK presentation contract | portal templates + GTK dialogs | shared screen/action/view-model contract | **not started** | Start with a read-only OS or client list; same DTO/actions/permissions, native rendering in each adapter; contract tests for both; no UI framework or big rewrite. See `docs/planning/WEB_GTK_SHARED_CONTRACT.md`. |
| Reports / PDFs | `pdf_cliente_v9.py`, `marca.py`, report templates | Generic document contracts + AUTOSEG templates | **flavor/locale module (current)** | Define generic document metadata; keep visual templates in AUTOSEG. |
| Fiscal / NF-e / NFS-e | `officina/core/prestadores_ext.py`, `pdf`/fiscal drafts, future integrations | Brazilian locale module | **flavor/locale module (planned)** | Define tax-document provider contract; do not put fiscal rules in core. |
| Email / payments | `gmail_service.py`, future payment integrations | Generic integration contracts + adapters | **legacy only** | Define provider interfaces; keep credentials outside code. |
| GTK shell | `flavors/autoseg/modules/gtk_app.py`, `gtk_dialogos.py`, `gtk_comum.py` | Generic GTK application | **AUTOSEG UI today; server mode works** | The GTK shell uses `AppService` for clients, OS, providers, finance, history, PJ, catalog, stock, company cash, composition and PDF. In server mode it does not open the local SQLite. Web portals are owned by `WebAccessManager`. |
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
| Production integration | Clients only | `officina/integration/clientes.py` |

## Client and sync direction

This is a planning inventory, not an authorization to start all clients. The
high-level vision, cost drivers and likely infeasible parts are in
`docs/planning/VISAO_MULTICLIENTE_LOCAL_FIRST.md`.

| Capability | Status | Next step |
|---|---|---|
| GTK desktop | current AUTOSEG UI | reach web parity for provider operations; keep SQL out of the UI |
| Web provider portal | current | extract application services; keep it as a client, not the center |
| Web client portal | current | keep online-first; do not promise offline yet |
| CLI | prototype (Workaholic) | read-only commands over services; then safe writes with `--dry-run` |
| Qt desktop | not started | decide after GTK parity and real demand |
| iOS native | not started | PWA or one native platform first; protocol must be stable |
| Android native | not started | same as iOS; one mobile platform at a time |
| Local-only mode | partial | `WebAccessManager` and `--no-web` are in place; next: backup/restore, export/import and offline startup tests |
| Protocol v0 | not started | application contract + conformance tests; no network |
| Hub sync | not started | server authority; two devices + visible conflicts |
| LAN group sync | not started | only after hub sync is stable |
| P2P/WAN | not started | only if a real need is proven; relay/E2E/security review |
| Light/dark mode | partial | GTK follows the system; web is dark-only; add tokens and a manual toggle |

## Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-11-04 | Keep AUTOSEG behavior as the parity contract during platformization. | Users should not need to know the architecture changed. |
| 2026-11-04 | Treat Workaholic as a first-class workstream, not a side prototype. | Avoid orphaned engine work; every generic capability needs a consumer. |
| 2026-11-04 | Keep Brazilian fiscal/payment rules outside the generic core. | The base must remain flavorless and usable in other countries/professions. |
| 2026-11-04 | Prefer a monorepo until module contracts and release cadence are stable. | Avoid premature repository split and duplicated CI. |
| 2026-11-06 | Start the application boundary with one slice: clients + dashboard. | Prove the contract without a big-bang rewrite; keep UI and behavior unchanged. |
| 2026-11-06 | Let `WebAccessManager` own portal lifecycle. | The GTK shell must not import or start HTTP servers directly. |
| 2026-11-07 | Run DEV in server mode with no local DB fallback. | Prove the desktop/server boundary with real API data; offline reads are empty and writes fail explicitly. |
| 2026-11-07 | Require provider login in the GTK desktop. | Every API action needs an identified provider; local and server logins are separate accounts, with logout and revocable sessions. |
| 2026-11-08 | Move AUTOSEG branding/config/templates and all AUTOSEG Python modules into `flavors/autoseg/`. | Establish the flavor boundary; generic modules moved to `officina/` and tests to `tests/`. |
| 2026-11-10 | Treat AUTOSEG as the first service provider in the Officina ecosystem, not a store; current web/GTK are seeds of Officina Web/GTK. | Correct product vocabulary; keep AUTOSEG as the priority and avoid a big-bang rewrite. |
| 2026-11-10 | Target one site/login for AUTOSEG, but implement identity and object policy before the UI. | Two portals and ad-hoc permission checks cannot be safely merged without a single account/tenant/policy layer. |

## Migration bottlenecks

These are the concrete things that make the migration slower. Fixing them is
higher leverage than adding new abstractions.

| Bottleneck | Why it slows migration | Next action |
|---|---|---|
| `portal_prestador.py` monolith | HTTP, HTML, auth, SQL, OS, finance and stock change together; every extraction has a large blast radius. | Extract one read-only route/service per PR; no new SQL or business rule in handlers. |
| No single actor/permission boundary | Each surface reimplements “admin/responsible/participant”; tests cannot prove denial consistently. | Introduce `Principal` + `Resource` + `ObjectPolicy` at the service boundary; shadow mode first. |
| Money in `float`/`REAL` | Rounding and equality differ between SQLite, contracts, API and composition. | Use integer cents at the application boundary; adapt legacy `REAL` at the edges; add round-trip tests. |
| Parallel OS rules | GTK, portal, `os_write`, `portal_negocios` and `produtividade_os` can disagree on status, totals and finalizer. | Characterize one OS slice, then move all writers through one `OrderService` use case. |
| Tests that codify leaks | Some characterization tests assert that any provider can read any OS/PII; they protect the wrong behavior. | Invert them when the policy lands; do not add new tests that preserve a known leak. |
| Workaholic expansion before vertical consolidation | Generic engine work consumes time without a second real consumer and increases maintenance surface. | Freeze new generic capabilities until the AUTOSEG P0 gate is closed and a second consumer exists. |
| Docs/code divergence | Handoff, workflows and “not implemented” claims drift from reality, causing wrong decisions. | Update the ledger/handoff in the same PR; add a release check for documented status. |

## Next recommended micro-slices

1. **Authorization characterization** — inventory `s.get('admin')`,
   `responsavel_atual`, `PermissionError` and the public routes; add tests that
   describe current behavior without changing it. See
   `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` §2 and §9.
2. **Catalog read adapter** — add characterization tests for
   `officina/core/catalogo_servicos.py`, then read through a Workaholic adapter without changing
   the UI.
3. **Clients write cleanup** — move remaining direct client writes through
   `officina/integration/clientes.py`; keep the legacy table and IDs.
4. **Service-order characterization** — lock status, totals, materials and PDF
   behavior before attempting an adapter.
5. **Workaholic schema revision** — add a minimal schema/versioning mechanism
   needed by the next slice.
6. **Module contract decision** — choose entry points + manifest, document it,
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

## Deferred decisions

These decisions need human context, real usage or a prototype. They are
documented in `docs/HUMAN_CENTERED_DECISIONS.md` and are not blockers for
characterization tests or reversible cleanup.

| Decision | Status | Evidence / trigger |
|---|---|---|
| First full slice: catalog or service orders | Deferred | Coupling map, usage observation, read-only adapter spike, human review. |
| Module contract: entry points + manifest vs alternative | Deferred | A second real consumer/flavor, developer-experience test, comparative review. |
| Cadence: ~20% delta per PR vs per release | Deferred | Three or four releases of data on scope, review time and regressions. |
