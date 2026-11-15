# Party types and representation model

**Status:** planning. Lowest priority — last entry of the priority list.
**Scope:** replace the scattered `tipo_pessoa` branching with a declared party
type (fields, links, capabilities) validated and enforced by a generic engine.

Related: [`API_V2.md`](API_V2.md),
[`CONDO_SHARING_AND_TENANCY.md`](CONDO_SHARING_AND_TENANCY.md),
[`MAF_AUTOSEG_READ_INTERFACE.md`](MAF_AUTOSEG_READ_INTERFACE.md).

## 1. Why

"PJ" is not a tag today; it is three rules in one field, spread across the
codebase:

| Dimension | What it decides | Today |
|---|---|---|
| Tax identity | CPF vs CNPJ validation, formatting, duplicates | `cadastros_v9` |
| Party shape | an organization needs an organization row and a representative | `v9_organizacoes`, `sincronizar_cliente_pj` |
| Authorization | representatives accept/reject for the organization | `solicitacoes_pj`, `portal_v9` |
| Commercial rules | condo sharing, billing, service classification | `CONDO_SHARING_AND_TENANCY` |

Measured spread at the time of writing:

```text
tipo_pessoa occurrences   61   in 17 files
'Jurídica' branches       29
top files                 cadastros_v9 (17), integration/clientes (8),
                          gtk_dialogos (7), portal_negocios (5),
                          importacao_yaml (4), solicitacoes_pj (3)
```

The rule exists 29 times. Adding a third kind (supplier, condo, tenant) means
editing 29 places and hoping none is missed. That is the maintenance cost this
item removes.

## 2. Three tiers, not one

"Data-driven" is not a single decision. The three tiers have very different
cost/benefit:

| Tier | What becomes data | Decision |
|---|---|---|
| 1. Centralize | one module owns "what a PJ is" | do first, cheapest |
| 2. Declare the shape | required fields, link cardinality, role→capability | **this item** |
| 3. Declare the behavior | conditions, hooks, computed rules, workflows | only with a second real consumer |

Tier 3 is where a data-driven system turns into an interpreter that must be
maintained, tested and versioned itself. Tier 2 is a bounded declaration and is
what this document specifies.

## 3. Invariant ≠ authorization

The distinction must survive the refactor, or the model becomes unsafe.

- **Invariant** — "an organization is well-formed": required fields present,
  at least one active representative. Data completeness.
- **Authorization** — "may *this* person accept *this* request": a query over
  the specific link, its role, validity and scope.

If only the invariant exists, "has a representative" silently becomes "any
representative can do anything" — a billing contact could accept a budget. The
capability map below is the bridge: the type declares *which role* may perform
*which action*, and enforcement checks the specific link inside the writer
transaction.

## 4. Declaration

```yaml
# flavors/autoseg/br/party-types.yaml
organization:
  fields:
    legal_name: {required: true}
    tax_id:     {required: true, kind: cnpj}
  links:
    representative: {min: 1, active: true}
  capabilities:
    accept_request:  [representative]
    reject_request:  [representative]
    manage_members:  [representative]

individual:
  fields:
    full_name:  {required: true}
    tax_id:     {required: true, kind: cpf}
  capabilities:
    accept_request:  [self]
```

Rules of the declaration:

- additive and versioned; a missing capability means "denied", never "allowed";
- every declared capability must have a handler, and a test fails when it does
  not;
- error messages are part of the contract: the validator must produce the same
  quality of message the imperative code produced, with stable codes for the UI.

## 5. Target layout

```text
officina/party/types.py       load and validate declarations
officina/party/rules.py       invariant check + capability → role lookup
officina/party/representation.py   link queries used by authorization
flavors/autoseg/br/           AUTOSEG declaration (CPF/CNPJ, roles)
workaholic/locales/pt_BR/     promoted tax-id rules, once a second consumer exists
```

`tipo_pessoa` becomes a storage detail mapped by an adapter. Call sites stop
branching on `'Jurídica'` and ask the engine instead.

## 6. Migration path

1. **No storage change.** The declaration validates the existing `clientes`
   columns and `v9_organizacoes` rows. Nothing is renamed, nothing is dropped.
2. Replace the 29 branches with capability lookups, one call site per commit.
3. Add the invariant check behind a shadow mode first: report violations, do not
   block. Measure how many existing rows fail.
4. Only after the shadow report is clean, enforce.
5. Storage migration (`Party` / `PartyLink` tables) is a **separate** item, and
   should follow API v2's `/me` design so representation is modeled once.

Do not rename and migrate in the same change. Do not enable enforcement before
the shadow report exists.

## 7. Costs to accept

- versioning of the declaration file;
- validation of the declaration itself (schema + completeness test);
- discoverability: the rule moves from `grep` to data, so the engine must give
  good error codes and the tests must be generated from the declaration;
- a second place to look during debugging, mitigated by logging which capability
  and which link decided the outcome.

## 8. Non-goals

- no workflow engine, no expression language, no hooks — tier 3 stays out;
- no storage migration in the same item;
- no change to AUTOSEG's user-visible behavior or messages;
- no effect on the A5 security queue: A5b and A5c keep their current form.

## 9. Priority

**Last item of the priority list.** It is a maintainability change, not a
correctness or security fix. It should start only after the A5 queue and the
API v2 contract, and its first executable step is the declaration + shadow
report, with no enforcement.
