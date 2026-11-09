# ADR 0003 — Signed event ledger and signature-policy boundary

- **Status:** Proposed
- **Date:** 2026-11-09
- **Scope:** Workaholic core, Officina platform, flavors
- **Related:** [`docs/planning/PGP_MULTISIGNATURE_ARCHITECTURE.md`](../../../docs/planning/PGP_MULTISIGNATURE_ARCHITECTURE.md), [`docs/planning/ANTI_TAMPERING_FINANCIAL_LEDGER.md`](../../../docs/planning/ANTI_TAMPERING_FINANCIAL_LEDGER.md)

## Context

AUTOSEG needs verifiable integrity for service orders and financial changes.
Administrators may have source-code access and must not be able to produce a
valid operation alone when the policy requires a quorum. Signatures must be
independent, attributable and verifiable outside the application UI.

At the same time, AUTOSEG is a flavor. Workaholic must remain usable by a
musician, electrician or artist without containing "OS", "prestador", "PIX",
"ICP-Brasil" or Brazilian fiscal rules.

The project already separates Workaholic (generic engine), Officina (work
protocol/application platform) and flavors (AUTOSEG). This decision applies the
same boundary to cryptographic integrity.

## Decision

1. **Workaholic core owns the generic signed-event mechanism.** It provides
   canonical envelopes, hash-chained events, detached signature storage,
   public-key registry, M-of-N policy evaluation, schema/canonicalization
   versioning and an offline verifier. It contains no AUTOSEG terms, no
   Portuguese fiscal rules and no legal-signature policy.

2. **Officina owns the approval workflow.** Proposal, review, signing UX,
   notifications, roles, policy profiles, revocation workflow and integration
   with authentication live in the platform layer. Authentication is not a
   signature; a compromised session must not be able to sign as an
   administrator.

3. **Flavors own event types and policies.** AUTOSEG defines `os.*` and
   `finance.*` events, the initial 2-of-3 service-order policy, provider
   isolation and PDF evidence. A flavor supplies policy data, not core code.

4. **Brazilian legal signatures live in the AUTOSEG flavor/locale module.**
   ICP-Brasil, PAdES, fiscal retention and legal review must not enter
   Workaholic core. OpenPGP detached signatures are the generic mechanism; PAdES
   is an optional flavor/locale adapter.

5. **Private keys are client-side by default.** The server stores public keys,
   signatures and key metadata. Hardware OpenPGP tokens or the OS keychain are
   preferred. Encrypted private-key storage in the database is an explicit
   lower-assurance fallback, not a silent default.

6. **M-of-N means independent signatures plus policy evaluation.** OpenPGP does
   not provide native threshold cryptography. The core must not assume it does.
   Duplicate signatures from the same key never satisfy distinct-signer
   requirements.

7. **Signed content is an immutable versioned snapshot.** Signatures cover
   canonical bytes and a versioned envelope, include a stable entity ID and
   never cover a mutable database row or rendered HTML. Historical payloads are
   never re-serialized with newer code.

8. **Existing records are not retroactively signed.** A genesis checkpoint
   attests the current state at a point in time. Historical records remain
   labelled pre-ledger; new versions are signed from that point forward.

9. **Local hash chains are tamper-evident, not immutable by themselves.**
   Periodic Merkle checkpoints, external anchoring and an independent verifier
   are required to detect rollback or wholesale database rewriting.

10. **Meu Auto Financeiro remains a separate product.** It may reuse the generic
    core, but it does not import AUTOSEG rules, share AUTOSEG keys or depend on
    the AUTOSEG database.

## Consequences

### Positive

- The same ledger/key/policy mechanism can serve AUTOSEG, future flavors and
  Meu Auto Financeiro without duplicating cryptography.
- AUTOSEG can evolve 2-of-3 policies, provider signatures and PDF/legal rules
  without changing the core.
- Independent signatures and policy evaluation avoid pretending that OpenPGP is
  threshold cryptography.
- Canonical bytes and schema versioning keep old signatures verifiable after
  code and formula changes.
- The boundary keeps Workaholic free of Brazilian legal/fiscal coupling.

### Negative / risks

- More upfront design: canonicalization, versioned verifiers, key registry and
  external anchoring are non-trivial.
- Hardware signing and independent verification add UX and operational cost.
- The first phase cannot promise "immutable"; it promises detectable tampering.
- Key loss, revocation and recovery require a ceremony and a recovery quorum.
- Encrypted-in-database private keys remain a residual non-repudiation risk.
- Legal validity of PGP signatures in Brazil is not automatic; the AUTOSEG
  locale must review ICP-Brasil/PAdES separately.

## Not decided here

Thresholds per event, the three initial administrators, provider key custody,
hardware mandate, external-anchor medium, break-glass duration, PDF standard and
legal requirements remain open. They are listed in the architecture document and
must be decided with real use cases and recorded as ADRs.

## Implementation status

**Planning only.** No code, schema or database change is authorized by this ADR.
