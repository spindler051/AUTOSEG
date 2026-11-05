# Provider finance API v1

**Status:** implemented as `9.6.0-dev.24` and promoted to MAIN. Read-only.
**Scope:** one authenticated AUTOSEG provider. It exposes that provider's own
OS receivables, secondary-technician shares and repasses. It does not expose the
personal-finance module, other providers, stock, clients of other providers or
any write operation.

## 1. Design principles

The API follows the small-tool Unix style: one resource per endpoint, plain
JSON, stable identifiers, integer money, ISO dates and composable `curl`/`jq`
workflows. It is not another web page and never returns HTML.

Financial APIs have specific requirements that were considered here:

- money is always an integer in minor units (`valor_centavos`, `BRL`), never a
  float;
- lists use cursor pagination, not offset, so concurrent inserts do not shift
  pages;
- the contract is published as OpenAPI 3.1;
- bearer tokens are high-entropy, stored only as SHA-256 hashes, revocable and
  never logged;
- the API is read-only, so idempotency keys are not needed yet; any future
  mutating endpoint must require `Idempotency-Key`;
- every authenticated request is recorded in `api_acessos` without the token;
- TLS is mandatory outside localhost; Cloudflare Quick Tunnel is not a
  production security boundary.

References used for the contract: Stripe-style integer minor units and cursor
pagination, OpenAPI 3.1, RFC 6750 (Bearer Token), RFC 9700/OAuth 2.0 security
guidance and the OWASP OAuth2 cheat sheet.

## 2. Authentication

Create a token for a provider:

```bash
GESTAO_BANCO=~/gestaoservicos_MAIN/dados.db \
  python3 api_financeiro.py token criar --prestador-id 1 --nome "Sistema financeiro"
```

The raw token is printed **once** on stdout; the database stores only its
SHA-256 hash. Send it in the header:

```bash
curl -H "Authorization: Bearer autoseg_fin_..." \
  https://seu-servidor/api/v1/financeiro/resumo
```

List and revoke:

```bash
python3 api_financeiro.py token listar --prestador-id 1
python3 api_financeiro.py token revogar --id 3
python3 api_financeiro.py openapi > openapi.json
```

A token is automatically rejected when the provider is inactive, excluded or
the token is revoked. Tokens have the `financeiro:read` scope. The API does not
accept session cookies, query-string tokens or anonymous access.

## 3. Endpoints

Base path: `/api/v1`. All responses use `Content-Type: application/json`.

| Method | Path | Meaning |
|---|---|---|
| GET | `/health` | Public health check. |
| GET | `/openapi.json` | Public OpenAPI 3.1 contract. |
| GET | `/me` | Authenticated provider identity. |
| GET | `/financeiro/resumo` | Totals in cents. |
| GET | `/financeiro/lancamentos` | OS financial entries where the provider is the finalizer. |
| GET | `/financeiro/rateios` | The provider's shares as a secondary technician. |
| GET | `/financeiro/repasses` | Repasses the provider owes to secondary technicians. |

### Envelope

Success:

```json
{
  "data": {},
  "meta": {
    "limit": 50,
    "has_more": false,
    "next_cursor": null,
    "generated_at": "2026-11-05T13:00:00"
  }
}
```

Error:

```json
{
  "error": {"code": "unauthorized", "message": "Informe um token Bearer válido em Authorization."},
  "request_id": "1a2b3c4d5e6f"
}
```

### Money and dates

- `valor_centavos = 35000` means **R$ 350,00**.
- `moeda` is always `BRL` in this version.
- Date-only fields use `YYYY-MM-DD`.
- Timestamps use ISO 8601 without timezone suffix, matching the local database.
  Clients that need a timezone should treat them as `America/Sao_Paulo` until a
  timezone field is added.

### `GET /financeiro/resumo`

```json
{
  "data": {
    "prestador_id": 1,
    "moeda": "BRL",
    "gerado_em": "2026-11-05T13:00:00",
    "os_a_receber_centavos": 25000,
    "os_recebido_centavos": 70000,
    "repasses_a_receber_centavos": 10000,
    "repasses_recebidos_centavos": 0,
    "repasses_a_pagar_centavos": 10000,
    "repasses_aguardando_confirmacao_centavos": 0,
    "total_a_receber_centavos": 35000,
    "total_recebido_centavos": 70000
  }
}
```

`os_recebido_centavos` is the provider's own share after rateios. A repasse only
counts as received after the secondary technician confirms it.

### `GET /financeiro/lancamentos`

Query parameters:

| Parameter | Meaning |
|---|---|
| `limit` | 1–200, default 50. |
| `cursor` | Opaque value from `meta.next_cursor`. |
| `status` | `Recebido`, `Aguardando pagamento`, etc. |
| `desde` / `ate` | Date filter on `data_lancamento` (`YYYY-MM-DD`). |
| `os_id` | Restrict to one OS. |

Each item contains the gross value, the rateio total and the provider's own
share:

```json
{
  "id": 18,
  "os": {"id": 12, "numero": "OS-0012"},
  "cliente": {"id": 18, "nome": "Condomínio Exemplo"},
  "descricao": "OS OS-0012 - ...",
  "moeda": "BRL",
  "valor_centavos": 35000,
  "rateios_centavos": 10000,
  "minha_parcela_centavos": 25000,
  "status": "Aguardando pagamento",
  "forma_pagamento": "Transferência",
  "data_lancamento": "2026-11-04",
  "vencimento": null,
  "data_pagamento": null
}
```

### `GET /financeiro/rateios`

The provider as secondary technician. `status` is `a_receber`,
`aguardando_confirmacao` or `recebido`. `restante_centavos = valor − pago`.

### `GET /financeiro/repasses`

The provider as finalizer. `status` is `a_enviar`,
`aguardando_confirmacao` or `confirmado`. `a_enviar_centavos = valor − pago −
enviado`.

## 4. Pagination

Never request unbounded history. Use `limit` plus `cursor`:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://seu-servidor/api/v1/financeiro/lancamentos?limit=2" | jq .
```

Take `meta.next_cursor` from the response and send it as `cursor`. Cursors are
opaque; do not parse or construct them. `has_more=false` means the end.

## 5. Security and operations

- Serve only behind HTTPS. Localhost is the only acceptable HTTP case.
- For external access, use a fixed Cloudflare Tunnel with **Cloudflare Access**
  or another authenticated reverse proxy. Do not publish real financial data
  through a bare Quick Tunnel.
- Set allowed browser origins only when necessary:
  `AUTOSEG_API_ORIGINS=https://app.example`.
- The API has an in-memory limit of 120 requests/minute per token.
- `api_tokens` stores hashes, scopes, creation, last use and revocation.
- `api_acessos` stores token id, provider, method, route, status, IP and time.
  Define a retention window and include it in the privacy review.
- Never log the `Authorization` header or the raw token.
- Back up `dados.db` before issuing or revoking tokens; the table is additive.

## 6. Tests

```bash
.venv/bin/python test_api_financeiro.py
```

The suite covers public health/OpenAPI, missing/invalid/revoked tokens,
inactive providers, provider isolation, cents and own-share math, cursor
pagination without duplicates, status filters, the two-step repasse
confirmation, read-only POST rejection and CORS preflight.

## 7. Future

- Add write endpoints only with mandatory `Idempotency-Key`, conflict handling
  and an audit trail.
- Add OAuth 2.0/OIDC or per-client credentials when third-party software needs
  delegated access.
- Add webhooks for `recebimento_confirmado` and `repasse_confirmado`.
- Add CSV/NDJSON export endpoints only if a real consumer needs them.
- Keep the API contract versioned; never change the meaning of an existing
  field or status silently.
