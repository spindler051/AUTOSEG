# Telemetry contracts

**Status:** contracts and local sink only; collected only when explicitly
enabled. Disabled by default.

**Wired consumer:** the Provider Portal feedback channel (see
[`../docs/features/FEEDBACK_PORTAL.md`](../../docs/features/FEEDBACK_PORTAL.md)).
The GTK desktop app is still not wired.

This package contains the contracts, privacy helpers and local sink for the
transparent telemetry feature described in
[`../docs/features/OPEN_TELEMETRY.md`](../../docs/features/OPEN_TELEMETRY.md).

It currently provides:

- `TelemetryConfig` — off by default; explicit modes (`off`, `local`, `otlp`);
  `from_env()` reads `AUTOSEG_TELEMETRY*` variables and stays inert with none
  set;
- `TelemetryEvent` — allowlisted event names/attributes, no free-form metadata;
- `page_path()` — strips query strings and fragments;
- `truncate_ip()` / `hash_ip()` — pseudonymization helpers;
- `TelemetryClient` — no-op unless explicitly enabled;
- `SQLiteSink` — local `telemetria_eventos` table, used only in `local` mode;
- `NoopSink` and test-only `MemorySink`.

## Feedback events

The Provider Portal emits five allowlisted events through the same contract:

| Event | When | Attributes |
|---|---|---|
| `feedback_open` | The dialog is opened | `prestador_id`, `abertura_id` |
| `feedback_submit` | The feedback is saved | `prestador_id`, `feedback_id`, `ai_requested` |
| `feedback_ai_reply` | Configured AI provider answered | `prestador_id`, `feedback_id`, `ai_status`, `category`, `urgency` |
| `feedback_ai_error` | AI unavailable/limit/disabled | same as above |
| `feedback_triage` | An admin changes the DEV state | `prestador_id`, `feedback_id`, `triage_status` |

Events never contain the feedback text, provider name, IP, session cookie or
browser fingerprint. They are written only when `AUTOSEG_TELEMETRY=local`. OTLP
export is not installed yet; the local table is the stable source for a future
exporter.

The feedback channel stores its own support record (who, page, device, session
hash and minimized IP) because that context is necessary to investigate the
report. That record is described in `docs/features/FEEDBACK_PORTAL.md`; it is
not the same as general telemetry and does not depend on `AUTOSEG_TELEMETRY`.

It does **not**:

- read HTTP requests or sessions outside the feedback routes;
- export to OTLP;
- expose admin telemetry settings;
- collect browser fingerprints, form values, cookies or tokens;
- collect data when `AUTOSEG_TELEMETRY` is unset or `off`.

Privacy/legal review is still required before production use, especially for
the full-IP mode and retention.
