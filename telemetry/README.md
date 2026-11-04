# Telemetry skeleton

**Status:** proposal only. Not imported by the application. Disabled by default.

This package contains the contracts and privacy helpers for the future
transparent telemetry feature described in
[`../docs/features/OPEN_TELEMETRY.md`](../docs/features/OPEN_TELEMETRY.md).

It currently provides:

- `TelemetryConfig` — off by default; explicit modes (`off`, `local`, `otlp`);
- `TelemetryEvent` — allowlisted event names/attributes, no free-form metadata;
- `page_path()` — strips query strings and fragments;
- `truncate_ip()` / `hash_ip()` — pseudonymization helpers;
- `TelemetryClient` — no-op unless explicitly enabled;
- `NoopSink` and test-only `MemorySink`.

It does **not**:

- read HTTP requests or sessions;
- store anything in SQLite;
- export to OTLP;
- expose admin settings;
- collect browser fingerprints, form values, cookies or tokens.

Wiring into the portals/GTK app is a future feature after privacy/legal review.
