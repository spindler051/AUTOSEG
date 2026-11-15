# Centralization profiles and change disclosure

**Status:** planning. No implementation, schema, flag or migration.
**Scope:** how much authority a company keeps over a work item, and what the
client can see of the changes made to it.
**Related:** [`LOCAL_SYNC_MODES_ANALYSIS.md`](LOCAL_SYNC_MODES_ANALYSIS.md) §8
(opt-in relay), [`VISAO_MULTICLIENTE_LOCAL_FIRST.md`](VISAO_MULTICLIENTE_LOCAL_FIRST.md),
[`SIGNED_OS_TWO_PARTY_AND_VERSIONING.md`](SIGNED_OS_TWO_PARTY_AND_VERSIONING.md).

## 1. The idea

"Centralized" and "decentralized" are not two products. They are a dial: a
company can keep full control over its own work items, share control with the
client, or hand scope decisions to the client. The dial is a business choice and
belongs to the company, not to the software.

The dial must not, however, be able to switch off the client's ability to know
what they are paying for. That is a legal floor, not a preference.

This document defines the dial, its hard limits, and what "history" means once a
client has already seen something.

## 2. Three axes, not one switch

The common design mistake is one toggle such as "allow changes without asking
and hide the history". That conflates three independent questions:

| Axis | Values | Question it answers |
|---|---|---|
| **Approval** | `auto` / `notify` / `require_acceptance` | Does the change block until the client acts? |
| **Visibility** | `full_diff` / `state_only` / `hidden` | What does the client see *after* the change? |
| **Authority** | `company` / `shared` / `client` | Who may make this class of change at all? |

Mapping the usual product wording:

| Product wording | Axis value |
|---|---|
| "ask the client" | `approval = require_acceptance` |
| "auto allow" | `approval = auto` |
| "allow history" | `visibility = full_diff` |
| "doesn't allow history" | `visibility = state_only` or `hidden` for a class |
| "client decides" | `authority = client` |

`approval = auto` combined with low `visibility` is a legal combination, but it
means "we changed it and we are not volunteering the diff". It does **not** mean
"the client cannot find out". The UI must say that plainly.

## 3. Disclosure is not a security boundary

The decisive observation:

> **Once a client has seen a state, it cannot be unseen.**

A client can photograph the screen, keep an old PDF, or simply remember the
price. History on the client side is nothing more than data that was or was not
written to the client's disk. At the security level, hiding it changes nothing.

Therefore:

- `visibility = hidden` is a **product and conflict-management choice**;
- it is **not** confidentiality and must never be sold as protection;
- it cannot stop the client from proving what they already received;
- it must not hide material changes (scope, price, deadlines), only internal
  churn — see §4.

What the system *can* guarantee is consistency and proof:

- the client always sees the **current** state;
- every published state is **signed**, so the client can prove what they saw;
- the provider can prove what it published and when;
- hiding a diff only means the server does not volunteer the in-between steps.

This replaces an unwinnable secrecy argument with an auditable one, and protects
both sides.

## 4. Change classes and the legal floor

Not every field may be auto-approved or hidden. Define classes first, then let
the dial move within each class.

| Class | Examples | Minimum approval | Minimum visibility |
|---|---|---|---|
| **C0 internal** | internal notes, assignee, internal stage | `auto` | hideable |
| **C1 logistics** | schedule, arrival window, technician | `notify` | visible |
| **C2 scope** | items, quantities, description, extras | `require_acceptance` | visible |
| **C3 financial** | price, discount, payment terms | `require_acceptance` | visible |
| **C4 termination** | cancellation, warranty, liability | `require_acceptance` | visible |

The dial is clamped: `configured >= floor`, never below.

Reason: an approved budget (orçamento aprovado) binds the provider. Changing
scope or price afterwards without client acceptance is exposed regardless of
what the company configured. The company chooses how supervised it is, not
whether the law applies.

Consequence: **hiding applies to C0 only**. A company may hide internal churn;
it may not hide the fact that the price or the scope changed. `state_only` at
the work-item level still shows material deltas.

## 5. Profiles

Nobody configures a matrix. Expose a few named profiles that set it, with
overrides only inside the legal band.

| Profile | Approval | Visibility | Authority | Typical use |
|---|---|---|---|---|
| **Centralized** (default) | `auto` for C0/C1, `require_acceptance` for C2+ | `full_diff` for material classes, `hidden` for C0 | `company` | small shop, one owner |
| **Supervised** | `notify` for C0/C1, `require_acceptance` for C2+ | `full_diff` | `company` | shop with formal clients |
| **Co-managed** | `require_acceptance` from C1 up | `full_diff` | `shared` | maintenance contracts |
| **Client-sovereign** | `require_acceptance` for C1+ | `full_diff` | `client` for C2 | facilities, condo, corporate client |

Per-contract override: a company may run `Centralized` by default and
`Co-managed` for one demanding client.

## 6. Signed snapshots (the receipt)

Because disclosure cannot be revoked, the useful guarantee is provability.

- Each published version of a work item gets a snapshot: canonical payload,
  version number, timestamp, hash, signature.
- The client stores its own copy; the server keeps its own.
- The PDF publication path already versions documents; the snapshot is the
  machine-readable sibling of the published PDF.
- A dispute resolves by comparing hashes, not memories.

This is what makes "history hidden" honest: the server withholds intermediate
diffs, while any snapshot the client already holds remains valid evidence.

## 7. Two histories, two stores

Separate them explicitly, because they have different owners and lifetimes.

| Store | Owner | Contents | Retention |
|---|---|---|---|
| **Internal journal** | provider | every change, actor, reason, signature | append-only, permanent |
| **Client-visible history** | client | published states and approved diffs | configurable, may be zero |

Consequences:

- hiding something from the client never deletes it from the internal journal;
- deleting an internal audit row is itself an event, and must be impossible
  through normal application paths;
- the client-visible store may expire; the internal one may not.

The relay is transport only: it never reads, rewrites or synthesizes either
store, and never signs policy.

## 8. Change lifecycle

```text
proposed ──auto──────────────► applied ──► published(snapshot)
   │                              ▲
   ├──notify──────────────────────┘
   │
   └──require_acceptance──► pending_client
                               │
                     accept ───┴──► applied
                     reject ──────► closed(rejected)
                     expire ──────► closed(expired)
```

Rules:

- a rejected or expired proposal never mutates the published version;
- `notify` never blocks, but the notification is part of the client-visible
  history;
- a change to an already approved scope creates a **new proposal**, not an
  in-place edit;
- C2/C3 changes cannot skip `pending_client`, whatever the profile says.

## 9. Abuse cases to design against

| Attempt | Expected behavior |
|---|---|
| Edit price after approval, claim the client accepted | blocked by C3 floor; acceptance is signed |
| Client denies having seen a change | signed snapshot + delivery record |
| Admin deletes audit rows to clean history | append-only journal; deletion is an event |
| Hide a material change behind `C0` classification | class is derived from the field, not chosen by the user |
| Relay forges or replays a policy update | policy is signed by the authority; relay is opaque |
| Company hides everything by choosing `hidden` | clamp at class level; material diffs always visible |

Classification is the new attack surface: if the UI lets an admin label a price
change as an "internal note", the whole model collapses. Class must come from
the mutated field, not from a free-form choice.

## 10. Where it lives

| Layer | Responsibility |
|---|---|
| **Officina** | change classes, legal floor, journal, snapshot signing, lifecycle |
| **Workaholic** | profile/policy engine, identity, delivery, sync, relay transport |
| **`flavors/autoseg/br/`** | the Brazilian floor (CDC-style acceptance for scope and price) |
| **`workaholic/locales/pt_BR/`** | Portuguese legal text, once a second consumer exists |

The jurisdiction-specific floor must not leak into the generic engine: the
engine takes a floor as input, the flavor supplies it.

## 11. Non-goals

- no encryption of client-visible history as a substitute for consent;
- no "history hidden" presented as confidentiality;
- no free-form classification of change classes;
- no client-side deletion that pretends to revoke knowledge;
- no relay with authority over policy or history.

## 12. Open questions

1. Retention defaults for client-visible history per profile.
2. Whether `notify` requires an acknowledgement to count as delivered.
3. Whether a client may export their visible history at any time (proposal: yes).
4. How a profile change applies to contracts already in flight.
5. Whether `Client-sovereign` allows a company to refuse a change it considers
   unsafe, and how that refusal is recorded.
