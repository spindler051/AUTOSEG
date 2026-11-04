# Open telemetry and transparent session context — proposal

**Status:** feature request / skeleton only.  
**Default:** disabled. Nothing is collected or transmitted by this proposal.  
**Scope:** operational diagnostics, abuse investigation and security review.

This document describes a future, optional telemetry subsystem for AUTOSEG and
the generic platform. The implementation must remain public and auditable. No
hidden collection, third-party advertising, cross-site tracking or covert
browser fingerprinting is acceptable.

## 1. Why

Operators need enough context to:

- diagnose a bug reported by a specific user/session;
- distinguish a genuine error from abuse or trolling;
- investigate suspicious requests, repeated login failures or scraping;
- understand which page/flow was active when a failure occurred;
- decide whether to rate-limit or block a session.

This is **operational telemetry**, not surveillance for advertising or profiling.

## 2. Non-goals

The system must **not**:

- sell, share or monetize data;
- build cross-site profiles;
- use canvas, WebGL, audio, font enumeration, battery or hardware fingerprinting;
- capture keystrokes, form values, passwords, cookies, tokens or clipboard;
- record page content, screenshots, camera, microphone or files;
- track users outside the application;
- hide collection behind unrelated consent;
- send data to a third party by default.

## 2.1 Legal reality

This is not legal advice. Fingerprinting is **not a crime by itself**, and the
items above are not all crimes. Legality depends on jurisdiction, purpose,
legal basis, notice, consent, data minimization, retention, security and the
relationship with the person (customer, employee, contractor, anonymous
visitor).

In Brazil, the LGPD applies to personal data and requires a legal basis,
purpose limitation, necessity, transparency, security and respect for data
subject rights. Some conduct can also engage the Marco Civil da Internet,
consumer law, labour law, secrecy of communications or unauthorized-access
rules. In the EU, the GDPR and ePrivacy rules apply; cross-site tracking and
many cookies require consent. The US has a patchwork of state privacy and
wiretap laws. Other countries have their own rules.

Examples:

| Signal / technique | Is it a crime? | Main issue |
|---|---|---|
| First-party session ID | No | Must be necessary, documented and retained briefly. |
| Page path and timestamps | No | Personal data when linked to a person/session; transparency and purpose. |
| IP address | No | Personal data in many jurisdictions; minimize, truncate/hash, define retention. |
| Browser/OS/viewport | No | Low sensitivity, but still part of a fingerprint; declare it. |
| Canvas/WebGL/audio/font fingerprint | Usually not by itself | High privacy risk; may require consent/DPIA and transparency; browsers may block it. |
| Analytics/marketing cookies | No | Regulated; consent/notice and opt-out depending on jurisdiction. |
| Cross-site tracking/profile | Not automatically a crime | Strongly regulated; consent, transparency and transfer rules; high legal/reputational risk. |
| Capturing passwords/tokens | Not a normal “collection” issue | Security failure and potential secrecy/unauthorized-access liability; never store secrets in telemetry. |
| Keystrokes/screen/content capture | Not automatically a crime | Wiretap/recording/employee-monitoring and privacy law; consent is complex; high risk. |
| Sending to a third party | No | Processor contracts, international transfer, transparency and security obligations. |

Scale does not create immunity. Large platforms have legal teams, consent
frameworks, incident response and still face regulators and lawsuits. A
self-hosted open-source application has a different risk profile: the operator
is usually the data controller, and the code authors may also carry
responsibilities depending on the deployment and jurisdiction.

Open implementation makes collection auditable; it does **not** replace a legal
basis, notice or security controls.

### Risk tiers

- **Tier 0 — off (default):** no collection.
- **Tier 1 — diagnostics:** page path, timestamps, auth state, coarse
  browser/OS, error codes, request ID. Short retention, no raw IP.
- **Tier 2 — security:** Tier 1 plus truncated/hashed IP, login failures,
  rate-limit events, admin actions. Audited access and retention.
- **Tier 3 — high-risk:** full IP, precise screen/device signals, client-side
  fingerprint signals, longer retention or external export. Requires explicit
  purpose, DPIA/legal review, notice/consent where applicable, access control
  and an incident plan.
- **Prohibited by project policy:** passwords, tokens, form values, clipboard,
  keystrokes, page content, screenshots, cross-site profiles and covert
  collection. These are excluded because they create disproportionate security
  and legal risk, not because every one of them is automatically a crime.

## 3. Principles

1. **Off by default.** Installation starts with telemetry disabled.
2. **Administrator opt-in.** An explicit admin action enables each mode.
3. **User notice.** Users see what is collected, why, for how long and how to
   ask for access/deletion. The notice version is stored with the setting.
4. **Local-first.** Default mode stores data only in the local installation.
   External export is a separate, explicit mode.
5. **Data minimization.** Collect only the fields needed for diagnosis/security.
6. **Open implementation.** The code, schema, retention and access rules are in
   this repository.
7. **Short retention.** Default 30 days; configurable with a documented limit.
8. **Access control.** Only authorized admins can view/export; every access is
   audited.
9. **Pseudonymization.** Session IDs are random; IP is truncated or hashed by
   default.
10. **Deletion/export.** A documented path for data subject requests.
11. **No dark patterns.** Consent/notice cannot be bundled with unrelated
    actions; disabling telemetry must be as easy as enabling it.
12. **Legal review.** LGPD/GDPR/employment-law review is required before
    enabling in production, especially for employee monitoring.

## 4. Proposed data schema

### Always avoided

Never collect:

- names, emails, CPF/CNPJ, phone numbers, addresses;
- passwords, tokens, cookies, session secrets;
- form field values or search queries;
- page HTML/DOM, keystrokes, clipboard, screenshots;
- precise geolocation, camera/microphone;
- canvas/WebGL/audio/font fingerprints;
- cross-site identifiers or advertising IDs.

### Optional fields

| Field | Purpose | Default | Notes |
|---|---|---|---|
| `event` | Event name | required | Allowlist only (page_view, login_success, login_failure, logout, error, security_event, admin_action). |
| `occurred_at` | Time | required | UTC ISO-8601. |
| `session_id` | Correlate a visit | required | Random, rotated per session; not a permanent user ID. |
| `page` | Flow context | required | Path only; strip query/fragment. No form values. |
| `authenticated` | Logged-in state | required | Boolean. |
| `actor_type` | Role context | optional | anonymous, user, admin, system. |
| `ip` | Security/rate-limit | off | If enabled: truncate IPv4 to /24 and IPv6 to /48, or store a keyed hash. Raw IP requires explicit high-risk mode. |
| `browser_family` | Compatibility | optional | Coarse: Firefox/Chrome/Safari/Other. |
| `browser_major` | Compatibility | optional | Major version only. |
| `os_family` | Compatibility | optional | Coarse. |
| `device_type` | Layout/debug | optional | desktop/tablet/mobile. |
| `screen_width` / `screen_height` | Layout bugs | optional | Integers; no device fingerprint. |
| `viewport_width` / `viewport_height` | Layout bugs | optional | Integers. |
| `status_code` | Error diagnosis | optional | HTTP status. |
| `duration_ms` | Performance | optional | Integer. |
| `error_code` | Diagnosis | optional | Internal code, not a stack trace with PII. |
| `request_id` | Correlate logs | optional | Random per request. |
| `notice_version` | Transparency | required when enabled | Version of the user-facing notice. |

### OpenTelemetry mapping

Future export should use standard OTel concepts:

- resource: `service.name=autoseg`, `service.version`, `deployment.environment`;
- spans for HTTP requests, with route template rather than raw URL;
- events/logs for login/security events;
- metrics for request count/latency/error rate;
- no high-cardinality or personal attributes;
- OTLP endpoint configured by the admin; no vendor lock-in.

## 5. Modes

| Mode | Behavior |
|---|---|
| `off` | Default. No event creation, no local storage, no export. |
| `local` | Store events in the local SQLite database with retention. |
| `otlp` | Export to an admin-configured OpenTelemetry endpoint, in addition to or instead of local storage. |

Enabling `otlp` must be a separate explicit action with endpoint and retention
shown to the admin.

## 6. Admin and user experience

- Settings page: “Diagnostics and security telemetry”.
- Clear list of collected fields and retention.
- “Disable and delete local telemetry” action.
- Export for a specific session/date range.
- Access audit: who viewed/exported what.
- User-facing notice at first login after enabling; link to full documentation.
- A visible “telemetry is on” status in the admin area.
- No collection before the admin confirms the notice version.

## 7. Security requirements

- Admin-only access with existing authentication/roles.
- CSRF protection and audit logging for settings/export.
- Encryption in transit for OTLP; local database protected by OS permissions.
- Rate limits on export and query endpoints.
- No raw IP in dashboards by default.
- Retention job with dry-run and deletion logs.
- Incident response procedure for accidental PII capture.
- Tests proving disabled mode emits nothing.

## 8. Implementation skeleton (not wired)

The repository contains a standalone skeleton under `telemetry/`:

- configuration defaults to disabled;
- event allowlist and sensitive-key rejection;
- path sanitization (strip query/fragment);
- IP truncation helper;
- no-op sink by default;
- in-memory sink for tests only.

It is **not imported by the portals or GTK app** and does not collect anything.
Wiring is a future feature request after policy/legal review.

## 9. Phases

1. **Policy and legal review** — retention, notice, lawful basis, employee vs
   customer distinction, data subject requests.
2. **Local-only skeleton** — schema, off-by-default client, tests.
3. **Admin settings and notice** — explicit enable, retention, delete/export.
4. **Diagnostics dashboards** — error/session correlation, no raw PII.
5. **Optional OTLP export** — endpoint configuration, redaction, tests.
6. **Abuse controls** — rate limit/block workflows, separate from telemetry.

## 10. Open questions

- Is the data collected from employees, customers or both? The legal basis and
  notice differ.
- Is raw IP ever necessary, or is truncated IP + rate limiting enough?
- Who can view/export telemetry in a multi-operator installation?
- Retention: 7, 30 or 90 days? Who can change it?
- Should users be able to opt out, or is this an operator/security setting?
- Which OTLP backend, if any, will be supported first?
- How are data subject access/deletion requests handled?
- What is the incident process if PII is captured accidentally?

## 11. Feature request summary

> Add an optional, off-by-default, open-source telemetry subsystem for
> diagnostics and abuse/security investigation. Store only declared, minimized
> session context; never capture content, form values or covert fingerprint
> signals. Admin opt-in, user notice, short retention, audited access, local-first
> storage, optional OTLP export. Implementation and schema fully public.
