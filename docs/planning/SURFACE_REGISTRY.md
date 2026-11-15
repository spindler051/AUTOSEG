# Surface registry

**Status:** planning. No code, no schema change.
**Scope:** one authoritative table describing every user-visible action —
identity, permission, handler and I/O contract — independent of the surface that
renders it.
**Related:** [`WEB_GTK_SHARED_CONTRACT.md`](WEB_GTK_SHARED_CONTRACT.md),
[`../SURFACE_PARITY.md`](../SURFACE_PARITY.md),
[`API_V2.md`](API_V2.md), [`../CODE_ROT_CLEANUP_PLAN.md`](../CODE_ROT_CLEANUP_PLAN.md).

## 1. Why

Three problems share one root cause: there is no single place that says what an
action *is*.

| Problem | Symptom today |
|---|---|
| God file | `portal_prestador.py` mixes routing, permission checks, validation and HTML in ~4.7k lines |
| Duplication | GTK and web each decide which actions exist and who may run them |
| Authorization drift | permission strings like `customer.delete.all` appear in code and in no policy |

`docs/SURFACE_PARITY.md` states the rule: **permission belongs to the role, not
to the surface.** A registry is that rule made executable.

## 2. The row

```yaml
- id: customer.deactivate
  family: customer
  permission: customer.delete
  risk: destructive            # normal | financial | destructive | read
  confirmation: required
  handler: officina.modules.customer.deactivate
  input:
    path: {customer_id: int}
    body: {reason: {type: string, max: 500, optional: true}}
  output:
    fields: {ok: bool}
  audit: {action: "Cliente desativado", target: customer_id}
  surfaces: [web, gtk, api]
```

| Field | Meaning |
|---|---|
| `id` | stable business identity; never renamed once released |
| `family` | grouping used to split the god file and to scope reviews |
| `permission` | policy key resolved by role; absence of a match means denied |
| `risk` | drives confirmation UI and which generated tests apply |
| `handler` | the single function that performs the action |
| `input` / `output` | the contract both surfaces validate against |
| `audit` | what must be recorded, with which target |
| `surfaces` | where it is exposed; an action may be `api`-only |

The registry contains **no HTML, no CSS, no widget names and no SQL**.

## 3. What it enables

### 3.1 The router

```python
action = registry.match(method, path)           # one lookup
require(action.permission, principal)           # one check, inside the writer
payload = action.validate(request)              # one validation
result = action.handler(banco, principal, payload)
```

`portal_prestador.py` becomes an adapter that renders `result`. Every
`if path == ...` branch disappears from it.

### 3.2 Surface parity

```python
registry.for_surface('gtk', principal)   # actions this role may run, already filtered
registry.for_surface('web', principal)
```

Neither surface hardcodes `if admin` again. The action declares the permission;
the policy resolves it; the surface only renders what it is given.

### 3.3 Generated authorization tests

For every action, the suite derives:

```text
denied without principal
denied with a role that lacks the permission
denied with a revoked role
allowed with the declared role
denied leaves no mutation when risk is destructive or financial
```

That is how A5, A5b, A5c and A5b-2 stop being four manual patches and become one
generated suite.

### 3.4 The god-file split

`family` is the seam. Extracting `customer`, then `finance`, then `orders`, each
becomes a mechanical move of declared handlers plus their renderers, with the
registry proving nothing was lost: an action without a handler fails fast.

## 4. Inventory snapshot

A slice of what the registry would describe today. Permission names in
parentheses do **not** exist in `policy.yaml` yet — that gap is precisely what
the registry makes visible.

| id | permission | handler | risk |
|---|---|---|---|
| `customer.create` | `customer.create` | `cliente_salvar` (create) | normal |
| `customer.edit` | `customer.edit.involved` | `cliente_salvar` (edit) | normal |
| `customer.deactivate` | `customer.delete` (missing) | `desativar_cliente` | destructive |
| `customer.delete` | `customer.delete` (missing) | `cliente_excluir` | destructive |
| `customer.merge` | `customer.delete` (missing) | `mesclar_clientes` | destructive |
| `customer.password` | `customer.password` (missing) | `definir_senha_cliente` | destructive |
| `receipt.confirm` | `finance.receipt` (missing) | `financeiro_receber` | financial |
| `receipt.cancel` | `finance.receipt` (missing) | `financeiro_cancelar` | financial |
| `pj.accept` | `pj.decide` (missing) | `pj_publico.aceitar` | financial |
| `pj.reject` | `pj.decide` (missing) | `pj_publico.recusar` | financial |
| `attachment.download` | `document.download.involved` | `read_anexo` | read |
| `attachment.thumbnail` | `document.download.involved` | `read_anexo_thumb` | read |
| `report.publish` | `report.publish.own` | `publicar_relatorio` | financial |

Three observations that are invisible in the current code:

1. four destructive actions share one permission (`customer.delete`) that the
   policy does not define;
2. financial actions have no permission key at all — they are enforced by ad hoc
   admin queries;
3. every row currently exists in up to three surfaces, each with its own copy of
   the rule.

## 5. Phases

| Phase | Deliverable | Behavior change |
|---|---|---|
| **0** | registry describing existing routes; completeness test | none |
| 1 | dispatcher uses the registry for described routes | low |
| 2 | generated negative authorization tests | none |
| 3 | GTK reads `for_surface` instead of hand-coded checks | low |
| 4 | split `portal_prestador` by `family` | mechanical |
| 5 | API v2 exposes the same `id`s with HTTP shapes | later |

Phase 0 is the important one: it is description, not refactor. It produces the
inventory that does not exist today, and it cannot break a running system.

### 5.1 Phase-0 completeness test

```python
def test_every_route_is_registered():
    for method, path in discover_routes(portal_prestador, api_desktop):
        assert registry.match(method, path) is not None, (method, path)

def test_every_handler_exists(registry):
    for action in registry:
        assert importable(action.handler), action.id

def test_every_permission_is_defined(registry, policy):
    for action in registry:
        assert policy.allows_some_role(action.permission), action.id
```

The third test alone would have caught the `customer.delete.all` gap that hid
the GTK button for remote admins.

## 6. Surface responsibility

| Layer | Owns |
|---|---|
| registry | action id, permission, handler, input/output, risk, audit |
| policy | role → permission mapping |
| handler | business rule and transaction |
| web adapter | HTML, forms, redirects |
| GTK adapter | widgets, dialogs, shortcuts |
| API adapter | JSON shapes, status codes |
| tests | generated matrix from `risk` and `permission` |

The registry decides **what**; adapters decide **how**. A change in a field or a
permission is one edit, and every surface follows.

## 7. Non-goals

- no UI framework, no declarative screen layout;
- no GraphQL, no dynamic query language;
- no replacement for `ObjectPolicy` — the registry *declares* the permission,
  the policy *decides* it;
- no automatic code generation for handlers;
- no behavior change in phase 0.

## 8. Open questions

1. Registry in Python constants or YAML? (proposal: YAML under
   `flavors/autoseg/config/`, loaded and validated into typed objects)
2. Does `permission` allow an expression (own vs involved), or is the
   relationship resolved by the handler through `ObjectPolicy`? (proposal:
   registry stores the permission key; the handler resolves the relationship)
3. How do read-only actions declare field scopes (`customer.pii`)?
4. Does the web adapter keep any route outside the registry (static assets,
   health, login)? (proposal: login and health are infrastructure, not actions)
5. When does an action get a new `id` versus a new field? (proposal: new `id`
   only when permission or risk changes)

## 9. Relationship to the queue

This is not part of A5. It is the prerequisite for two items already planned:

```text
surface registry
   ├── god file: supplies the seams for splitting portal_prestador
   └── GTK/web contract: supplies the action list and permissions
```

Phase 0 can start after A5b-2 is merged, and it does not block API v2 or the
party model.
