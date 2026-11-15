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

## 2. Three tiers, and where each one happens

"Data-driven" is not a single decision. The tiers differ in cost and in the
moment they belong to:

| Tier | What becomes data | Where |
|---|---|---|
| 1. Centralize | one module owns "what a PJ is" | Python, first |
| 2. Declare the shape | required fields, link cardinality, role→capability | Python, this item |
| 3. Declare the behavior | conditions, hooks, computed rules, workflows | Rust rewrite |

Tier 3 is where a data-driven system turns into an interpreter that must be
maintained, tested and versioned itself. It should not be improvised in Python:
it belongs to the core/protocol rewrite in Rust, which is also the right moment
to sweep the whole codebase for other hardcoded variation.

### 2.1 Tier 2 is bigger than party types

Party types are the first case, not the only one. The same pattern applies
wherever a business rule is duplicated as branches instead of declared once.
While we are still on Python, the audit should cover at least:

- customer kinds and their required relationships (this document);
- work-item statuses and the transitions each one allows;
- document kinds and which surface may publish, download or retain them;
- composition and pricing rules that live in code today;
- fiscal variations that belong in `flavors/autoseg/br/`;
- surface actions and their permissions (the surface registry, phases 0B–1).

Each one becomes a declaration plus a generic evaluator. The list is a starting
point for an audit, not a commitment to implement all of them at once, and it is
not limited to it: the question to ask of every module is "is this variation a
rule that should be declared, or a genuine piece of behavior?".

### 2.2 The declarations are the Officina contract

The purpose is not only AUTOSEG maintainability. Every declaration is data that a
consumer can read without importing AUTOSEG Python: another flavor, the GTK and
Web clients, API v2, and eventually the Rust implementation itself. That is what
makes Officina a product with consumers instead of a rename of one deployment.

The rewrite in Rust is also a review pass: it is the point where remaining
hardcoded variation is easiest to see, because the contract has to be restated
outside Python. Finding those cases there is expected, not a failure.


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
