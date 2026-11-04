# English migration plan — code, data and documentation

**Status:** planning. No mass rename has been executed. This document defines
how the codebase moves to English without changing AUTOSEG’s behavior or
breaking existing installations.

## 1. What “English codebase” means

The target is:

- English identifiers: modules, classes, functions, variables, tests;
- English comments, docstrings, commit messages and developer documentation;
- English schema/field names in the new generic core;
- English source strings for the UI, translated to `pt_BR` at runtime;
- English public API/contracts where they are new.

It does **not** mean:

- changing what users see in Portuguese;
- renaming production database columns in place;
- changing existing portal URLs;
- breaking existing YAML files or environment variables;
- translating client data, service descriptions or legal documents.

## 2. Non-negotiable compatibility rules

1. **User-visible language stays Portuguese by default.** A Brazilian user must
   not see English labels because the source code changed.
2. **Database columns stay as they are until a tested migration exists.** Code
   uses English domain names; adapters map them to legacy Portuguese columns.
3. **Existing routes stay.** `/clientes`, `/os`, `/financeiro` and friends are
   bookmarks and integrations. Add English aliases later if useful; do not
   remove Portuguese routes.
4. **Existing YAML files keep working.** New English schemas use a versioned
   converter; old files are never rejected just because keys are Portuguese.
5. **Environment variables keep working.** `AUTOSEG_BASE` and `GESTAO_BANCO`
   remain supported. English aliases can be added, not substituted.
6. **Launchers keep working.** Old `.command` names remain as compatibility
   wrappers if a file is renamed.
7. **No mass rename in one release.** Rename only a module that is already
   covered by characterization tests and preferably being touched for a
   functional reason.
8. **Do not rename and migrate the same module in the same change.** One PR
   moves the slice; another renames it.

## 3. Phases

### Phase 0 — Policy and glossary (current)

- Publish this plan.
- Maintain a Portuguese ↔ English glossary.
- Freeze the rule: new code is English; legacy code changes only when touched.
- Inventory modules, public routes, database tables, YAML models and docs.

Exit criteria:

- contributors know which names are public compatibility surfaces;
- no new module is created with Portuguese identifiers.

### Phase 1 — i18n foundation

- Extract user-facing strings from GTK, portals, PDFs and emails into a
  translation catalog (gettext or an equivalent).
- Source strings become English keys; `pt_BR` is the first complete catalog.
- Keep dates, currency and address formatting locale-aware.
- Add a test that fails when a new user-facing string has no `pt_BR` entry.

Exit criteria:

- UI behavior and wording remain identical in Portuguese;
- no hardcoded user-facing Portuguese in new code.

### Phase 2 — New code and documentation in English

- New files, classes, functions and tests use English.
- New developer docs and ADRs use English.
- Existing Portuguese comments/docstrings are translated when the file is
  touched, not in a separate mass commit.
- Commit messages use English from this point on.

Exit criteria:

- `AGENTS.md` review rule is active;
- new modules pass the glossary/naming review.

### Phase 3 — Low-risk module renames

Rename modules with small public surface and good tests first. Keep a
compatibility shim at the old path for at least one release.

Candidates:

| Current | Target | Risk |
|---|---|---|
| `versao_app.py` | `app_version.py` | low |
| `marca.py` | `brand.py` | low |
| `links_publicos.py` | `public_links.py` | low |
| `gerenciar_tuneis.py` | `tunnel_manager.py` | low |
| `tuneis_dev.py` | `dev_tunnels.py` | low |
| `importacao_yaml.py` | `yaml_import.py` | medium (public YAML behavior) |

Example compatibility shim:

```python
# old_module.py — deprecated compatibility wrapper
from new_module import *  # noqa: F401,F403
```

Do not keep shims forever. Remove them after the documented deprecation window.

### Phase 4 — Domain modules

Rename after characterization tests and preferably as part of a Workaholic
slice migration. One module at a time.

| Current | Target | Notes |
|---|---|---|
| `completude.py` | `completeness.py` | config keys stay compatible |
| `composicao.py` | `composition.py` | calculator contract |
| `catalogo_servicos.py` | `service_catalog.py` | generic catalog candidate |
| `estoque_materiais.py` | `inventory.py` | stock/material boundary |
| `prestadores_ext.py` | `providers_ext.py` | providers/actors |
| `cadastros_v9.py` | `registrations_v9.py` | organizations/people |
| `atendimento_os.py` | `service_order_attendance.py` | service-order flow |
| `fluxo_os.py` | `service_order_flow.py` | status/PDF/email |
| `produtividade_os.py` | `productivity.py` | commissions/rateios |
| `portal_negocios.py` | `business_rules.py` or `portal_business.py` | high coupling |
| `portal_prestador.py` | `provider_portal.py` | public routes unchanged |
| `servidor_web.py` | `client_portal_server.py` | public routes unchanged |
| `portal_cliente_v94.py` | `client_portal_v94.py` | public routes unchanged |
| `cliente_fluxo_v94.py` | `client_flow_v94.py` | public routes unchanged |
| `pdf_cliente_v9.py` | `client_pdf_v9.py` | PDF output unchanged |

Names are proposals, not final decisions. The module boundary matters more than
the filename.

### Phase 5 — Data and schema compatibility

- Do **not** rename existing SQLite columns/tables in the same release as a
  behavior change.
- Introduce English domain models/adapters that map to legacy columns.
- If a database rename is ever approved, use an idempotent migration with
  backup, validation, rollback and a compatibility view.
- New Workaholic schemas use English keys and a schema version.
- Old YAML models are converted by version; the user is not forced to rewrite
  their files.

### Phase 6 — Documentation and public release

Translate developer-facing docs first:

- `docs/GTK4_LINUX_MACOS.md`
- `docs/WORKAHOLIC_INTEGRACAO.md`
- `docs/MIGRACAO_MODULAR.md`
- `docs/COMPLETUDE.md`
- `docs/COMPOSICAO_VALORES.md`
- `docs/BANCO_TESTE_PRODUCAO.md`
- `docs/PLANO_EVOLUCAO_ARQUITETURA.md`

Keep user-facing guides in Portuguese, preferably under a `pt_BR` path or with
a clear language label. Do not translate historical changelogs; add a note if
needed.

Public README and contributor docs are English. A Portuguese quick-start can be
linked from the README.

## 4. Glossary

Use this as the canonical mapping. Add terms as they appear.

| Portuguese | English | Notes |
|---|---|---|
| cliente | client | |
| condomínio | condominium | |
| síndico | building manager | |
| administradora | property manager | |
| prestador | provider | contractor/technician |
| técnico | technician | |
| pessoa física | individual | |
| pessoa jurídica | legal entity / company | |
| CPF/CNPJ | tax ID | keep the Brazilian acronym in locale modules |
| ordem de serviço / OS | service order | |
| orçamento | quote / estimate | |
| serviço | service | |
| material | material | |
| estoque | inventory / stock | |
| fornecedor | supplier | |
| financeiro | finance | |
| a receber | receivable | |
| recebido | received / paid | depends on context |
| lançamento | entry / transaction | |
| vencimento | due date | |
| repasse | payout / transfer | |
| rateio | allocation / split | |
| comissão | commission | |
| produtividade | productivity | |
| encerramento | closure | |
| pendência | pending issue | |
| chamado | ticket / request | |
| solicitação | request | |
| cadastro | registration / record | |
| acompanhamento | tracking / follow-up | |
| garantia | warranty | |
| vistoria | inspection | |
| nota fiscal | invoice | NF-e/NFS-e in locale modules |
| boleto | bank slip | keep “boleto” in locale docs |
| endereço | address | |
| bairro | neighborhood | |
| cidade | city | |
| UF | state | |
| CEP | postal code | |
| observações | notes | |
| responsável | assignee / owner | |
| usuário | user | |
| senha | password | |

## 5. Automated checks

Add these gradually:

1. `python -m compileall` and the existing test suites.
2. A naming review script for new files: reject obvious Portuguese identifiers
   outside the glossary/legacy allowlist.
3. A gettext catalog coverage test for user-facing strings.
4. An import check that old module paths still work through shims.
5. A route snapshot test proving `/clientes`, `/os`, etc. still resolve.
6. A YAML compatibility test with a Portuguese legacy file.

Do not add a check that forces a mass rename. The goal is to prevent new
Portuguese identifiers, not to create a huge diff.

## 6. Definition of done for a renamed module

- Characterization tests pass before and after.
- Old import path still works through a shim (deprecation window).
- All internal imports updated.
- Public routes, env vars, YAML keys and database columns unchanged.
- Docs and ledger updated.
- No user-visible language change.
- `pt_BR` translation coverage unchanged.

## 7. Relationship to Workaholic migration

The English migration and the Workaholic slice migration must not fight each
other.

Rule:

> Rename a module only when it is being touched anyway, or after its slice has
> characterization tests. Never combine a large rename with a data migration.

New generic code starts in English. Legacy AUTOSEG code becomes English as it is
touched. This avoids a second big-bang project.

## 8. Open decisions

- Final file names for high-coupling modules.
- gettext vs another catalog tool.
- Whether to keep a permanent `legacy/` compatibility layer or remove shims
  after one or two releases.
- Whether public routes ever get English aliases.
- Whether the changelog becomes English for developers while a Portuguese
  product changelog remains for users.
- Who reviews domain translations (especially fiscal/legal terms).
