# Client grants and capabilities

**Status:** planning. No code, no schema change, no flag.
**Scope:** replace “role per surface” with “capability grant per client”, so a
person can hold different authority in different clients without either client
being defined as lesser.
**Related:** [`../SURFACE_PARITY.md`](../SURFACE_PARITY.md),
[`SURFACE_REGISTRY.md`](SURFACE_REGISTRY.md), [`API_V2.md`](API_V2.md).

## 1. The problem with the surface model

The current rule says permission belongs to the role, not the surface, with an
implied hierarchy: the desktop is trusted, the web is second-class. Requiring
“admin only in the GTK app” under that model needs an exception, and exceptions
to authorization rules are where privilege bugs live.

The correct statement is:

> **Authority is the grant attached to the session, not a property of the
> person and not a property of the screen.**

The web is not “only ever employee”. Its grant simply does not include the
elevated capabilities. If the grant changes, the behaviour changes — with no
code path that says “if web then deny”.

## 2. Concepts

```text
Identity     the human / provider              prestadores
Client app   who is asking                     gtk, web, api, future mobile
Grant        capabilities issued to that       per device, per login
             client session
Capability   one named operation               customer.delete, finance.receipt
```

`role` survives as a **bundle of capabilities** for readability and migration,
not as a special case in the policy engine.

## 3. policy.yaml

```yaml
versao: 2
roles:                       # bundles, not the authority source
  admin:
    capabilities: ['*']
  employee:
    capabilities:
      - work_item.view.own
      - work_item.edit.involved
      - customer.create
      - customer.edit.involved
      - document.download.involved
  customer:
    capabilities:
      - work_item.view.own
      - document.view.own

clients:                     # what each client may ever exercise
  gtk:
    capabilities: ['*']
  web:
    capabilities:
      - work_item.*
      - customer.*
      - document.*
      - report.view.*
  api:
    capabilities: ['*']

fields:                      # unchanged
  ...
```

`clients` is the ceiling; `roles` is the bundle; per-account overrides come
later (§9). A capability is allowed only if it passes all of them.

## 4. Principal

`officina/application/object_policy.py` already has `grants` and `denies`.
It does **not** have a client app — `client_id` there is the *customer* id, not
the callee. Add one field, not a second role:

```python
@dataclass(frozen=True)
class Principal:
    account_id: int
    role: str
    organization_id: str | None = None
    provider_id: int | None = None
    client_id: int | None = None          # customer identity (unchanged)
    client_app: str = 'web'               # new: gtk | web | api
    grants: frozenset[str] = frozenset()  # per-session additions
    denies: frozenset[str] = frozenset()
    active: bool = True
    client_org_ids: frozenset[int] = frozenset()
```

`client_app` is set by the authentication adapter, never by the request body or
headers.

## 5. Resolution

```text
bundle   = policy.roles[principal.role].capabilities
ceiling  = policy.clients[principal.client_app].capabilities
allowed  = ((bundle | principal.grants) ∩ ceiling) − principal.denies
```

Properties:

- deny always wins, including over `'*'`;
- a grant cannot exceed the client ceiling, so a per-user grant cannot leak into
  a weaker client;
- a role cannot be widened by the client either; both must agree;
- the result is a plain `frozenset[str]` stored on the session at login, so
  authorization does not recompute policy on every check.

## 6. ObjectPolicy change

Today `officina/application/object_policy.py:143` short-circuits:

```python
if principal.role == "admin":
    return Decision(True, "Administrador da organização.", ...)
```

That bypass is the thing to remove. Replace it with a capability test:

```text
if capability in principal.capabilities: allow
```

`admin` keeps working because its bundle is `['*']` and the clients that allow
`*` still pass. The difference is that a client whose ceiling excludes `*`
cannot borrow admin authority, even if the role says admin.

## 7. Where the client app is asserted

Server-side, from the token family — the same signal A5 already relies on:

| Login path | Token | `client_app` |
|---|---|---|
| Web `/login` (unified) | `autosseg_unified` cookie | `web` |
| Desktop API login | `desktop_sessoes` token | `gtk` |
| Headless API | `api_tokens` bearer | `api` |

Never derive it from `User-Agent`, `Host`, a query parameter, or a field the
client can set. If a browser ever presents a desktop token, the boundary is
gone; that is why device binding matters (§10).

## 8. The concrete requirement

“This person is admin in the GTK app and a regular employee on the web” becomes
one line of configuration, not a code branch:

```yaml
clients:
  gtk:
    capabilities: ['*']
  web:
    capabilities:
      - work_item.view.own
      - work_item.view.involved
      - work_item.edit.involved
      - customer.view.involved
      - customer.edit.involved
      - document.download.involved
```

The web session of an admin resolves to that ceiling, so the elevated
capabilities are absent, the controls are absent, and the service denies them
inside the transaction. The person is not “downgraded”; their web session was
never granted those capabilities.

## 9. Per-account overrides

The client ceiling is per deployment, not per person. When one specific user
must be admin on `gtk` but not on `web`, the override lives beside the account:

```text
account_client_grants(account_id, client_app, capability, granted_at, granted_by)
```

Resolution adds that set to `bundle`, still intersected with the client ceiling.
This is the only place a per-user exception exists, and it is auditable.

## 10. Security requirements

1. `client_app` is server-asserted by token family (§7).
2. Desktop tokens are device-bound (key in the GTK), short-lived, refreshable.
3. Revocation is per grant/device and takes effect on the next request.
4. Deny beats `*`; ceiling beats grant.
5. Audit records **capability + client_app + account**, so “admin through the
   desktop” is distinguishable from “admin through the web”.
6. No capability is inferred from UI state; the UI reads capabilities, never the
   reverse.

## 11. Affordance rule

`SURFACE_REGISTRY.md` §3.5 already says: a control the principal cannot use must
not exist. With this model the renderer asks the session, not the role:

```python
if 'customer.delete' in session.capabilities: show
```

That is the same line for web, GTK and API, and it cannot drift from the
service check because both read the same set.

## 12. Migration

| Step | Change | Visible behaviour |
|---|---|---|
| 1 | Add `client_app` to `Principal`, set it at each login path | none |
| 2 | Add `clients:` to `policy.yaml` with `*` for every client | none |
| 3 | Replace the `role == 'admin'` bypass with a capability test | none (bundle still `*`) |
| 4 | Add resolution and store `capabilities` on the session | none |
| 5 | Narrow the `web` client ceiling | **the requested behaviour** |
| 6 | Move locked helpers from `require_admin_locked` to `require_capability_locked` | none |
| 7 | Add `account_client_grants` for per-person exceptions | opt-in |

Steps 1–4 are invisible and testable in isolation. Step 5 is a policy edit, not
a patch to authorization code — which is the point.

## 13. Non-goals

- no second role per user;
- no `if gtk` / `if web` branch in any writer;
- no capability learned from the UI;
- no schema change before step 7;
- no change to `SURFACE_PARITY.md`'s core statement, which is superseded by a
  stronger one: *authority is the grant of the session*.

## 14. Open questions

1. Is `clients` global per deployment or per organization? (proposal: global,
   overridden by `account_client_grants`)
2. Do capabilities share the registry's action ids one-to-one, or can one
   action require several capabilities? (proposal: one capability per action
   in phase 1)
3. Does the web client ceiling ship as a default, or is it empty until
   configured? (proposal: explicit default, never empty)
4. How are capability names versioned when an action splits in two?
5. Does the GTK local mode get `client_app = 'gtk'` without a token, and if so,
   what proves that? (today it opens the database directly — that is an open
   trust question, not solved by this document)
