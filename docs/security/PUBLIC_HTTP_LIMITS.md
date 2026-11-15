# Public HTTP request limits

`officina.application.public_limits.PublicBudget` bounds unauthenticated
HTTP traffic before parsing the request body. The portal wraps `do_GET` and
`do_POST` for `/login`, `/solicitar`, `/pj-publicas` and `/api/v1/*` routes;
the headless API applies the same protection to `/api/v1/*` dispatches.

- 40 login attempts per IP per rolling 60-second window (separate from the
  existing credential-specific login failure limiter).
- 180 public POST requests per IP per 60 seconds.
- 480 public GET requests per IP per 60 seconds.
- 32 concurrent public operations per server instance.
- Rate or concurrency excess responds with `429 Too Many Requests`, a
  `Retry-After` header and JSON body, before reading the request payload.
- Socket timeout is 15 seconds. Existing `PREAUTH_MAX` limits remain in
  effect for unauthenticated forms. No security setting or permission key added.

Budgets are per process and use the raw TCP peer IP; forwarding headers do not
create a new quota. An authenticated application can still be subject to these
limits when the route is public. Deploy behind a trusted proxy/firewall with
connection-level quotas for effective **thread**, bandwidth, and distributed
resource-exhaustion protection: the application slots bound concurrent handler
work but do not bound the HTTP server's thread creation or traffic across
multiple instances. No claim of DDoS protection is made.
