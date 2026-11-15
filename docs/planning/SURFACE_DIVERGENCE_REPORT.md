# Surface divergence report

## Summary

- High: 0
- Medium: 1
- Low: 0
- Total: 1

Static source evidence only; not a behavioral penetration test.

## High

| Finding ID | Action | Surface | Kind | Evidence (`file:marker`) | Negative test |
|---|---|---|---|---|---|

## Medium

| Finding ID | Action | Surface | Kind | Evidence (`file:marker`) | Negative test |
|---|---|---|---|---|---|
| `customer.detail:gtk_local:read_scope_divergence` | `customer.detail` | `gtk_local` | `read_scope_divergence` | officina/application/local_service.py:clientes_core.obter( versus flavors/autoseg/modules/portal_prestador.py:require_customer_read | tests/test_p0_read_auth.py |

## Low

| Finding ID | Action | Surface | Kind | Evidence (`file:marker`) | Negative test |
|---|---|---|---|---|---|

## Accepted gaps

| Finding ID | Justification |
|---|---|
| `customer.detail:gtk_local:read_scope_divergence` | GTK local detail uses generic client lookup; Web/API require scoped access. |
