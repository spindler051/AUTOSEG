# Surface divergence report

## Summary

- High: 0
- Medium: 6
- Low: 0
- Total: 6

Static source evidence only; not a behavioral penetration test.

## High

| Finding ID | Action | Surface | Kind | Evidence (`file:marker`) | Negative test |
|---|---|---|---|---|---|

## Medium

| Finding ID | Action | Surface | Kind | Evidence (`file:marker`) | Negative test |
|---|---|---|---|---|---|
| `customer.create:web:create_preflight_outside_writer` | `customer.create` | `web` | `create_preflight_outside_writer` | flavors/autoseg/modules/portal_prestador.py:read_access.require_customer_create(actor); officina/core/portal_negocios.py:BEGIN IMMEDIATE without require_customer_create | tests/test_p0_direct_auth.py |
| `customer.detail:gtk_local:read_scope_divergence` | `customer.detail` | `gtk_local` | `read_scope_divergence` | officina/application/local_service.py:clientes_core.obter( versus flavors/autoseg/modules/portal_prestador.py:require_customer_read | tests/test_p0_read_auth.py |
| `customer.list:gtk_local:read_scope_divergence` | `customer.list` | `gtk_local` | `read_scope_divergence` | officina/application/local_service.py:clientes_core.listar( versus flavors/autoseg/modules/portal_prestador.py:involved_customer_field_scopes | tests/test_p0_read_auth.py |
| `customer.merge:api:missing_surface` | `customer.merge` | `api` | `missing_surface` | flavors/autoseg/modules/api_desktop.py:[] (no registered api marker) | tests/test_p0_customer_destructive_a5b2.py |
| `customer.merge:gtk:missing_surface` | `customer.merge` | `gtk` | `missing_surface` | flavors/autoseg/modules/gtk_app.py:[] (no registered gtk marker) | tests/test_p0_customer_destructive_a5b2.py |
| `customer.password:gtk:affordance_mismatch` | `customer.password` | `gtk` | `affordance_mismatch` | flavors/autoseg/modules/gtk_app.py:ui.botao("Acesso web / senha", self._senha_cliente) / no enclosing admin condition | tests/test_p0_customer_password_a5d.py |

## Low

| Finding ID | Action | Surface | Kind | Evidence (`file:marker`) | Negative test |
|---|---|---|---|---|---|

## Accepted gaps

| Finding ID | Justification |
|---|---|
| `customer.create:web:create_preflight_outside_writer` | Customer create permission is checked before the writer transaction, not within it. |
| `customer.detail:gtk_local:read_scope_divergence` | GTK local detail uses generic client lookup; Web/API require scoped access. |
| `customer.list:gtk_local:read_scope_divergence` | GTK local list reads clients via generic LocalService; Web/API use scoped views. |
| `customer.merge:api:missing_surface` | Customer merge exists on Web only; Desktop API has no registered endpoint. |
| `customer.merge:gtk:missing_surface` | Customer merge has no registered GTK action or dialog. |
| `customer.password:gtk:affordance_mismatch` | GTK password button is enclosed by web.enabled, not the admin session condition. |
