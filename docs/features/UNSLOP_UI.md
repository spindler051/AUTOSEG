# Unslop experimental interface

**Status:** experimental in `develop` as `9.6.0-dev.27`.
**Scope:** Provider Portal web interface only. The Client Portal and the
desktop GTK app are unchanged.
**Default:** classic interface. The experimental interface is opt-in per
browser.

## 1. Toggle

The login page has a small interface switch:

- **Atual** — keeps the existing layout and CSS.
- **Ativar unslop** — sets `autosseg_ui=unslop` and reloads the current page.

When the experimental interface is active, the login page and the authenticated
portal show **Desativar unslop**. The preference is a `SameSite=Lax` cookie,
valid for one year; it contains only `classic` or `unslop`, never identity or
business data. Logout does not erase the preference.

Routes:

| Route | Effect |
|---|---|
| `GET /ui/unslop` | Sets the experimental preference and redirects back. |
| `GET /ui/classic` | Restores the classic preference and redirects back. |

## 2. Direction

Derived from the product, not from a template:

- **Product:** work and service orders for security/automation providers.
- **Character:** field-ready, exact, calm.
- **World:** graphite tools, job sheets and technical reports, with a warm
  amber accent retained from the AUTOSEG identity.
- **Moments:** the OS summary ticket and the tabbed job sheet.
- **Signature:** the quiet “OS” summary with status, responsible, total and
  photo count before the editable sections.

The experimental shell uses a fixed sidebar (navigation rows, user, logout),
graphite surfaces, amber only for primary actions/selection, no glows, no
gradient text and no emoji decoration. Body copy is sentence case and figures
use tabular numerals.

## 3. OS page

In unslop mode the OS page adds:

- a summary card with OS number, client, status, responsible, total and photo
  count;
- **Preview do PDF** and **Editar OS** actions;
- the existing fieldsets rendered as tabs: identification, materials,
  attendance/report, photos and delivery details;
- a sticky action bar for **Salvar rascunho** and **Confirmar situação**.

The form, routes, CSRF, permissions, storage and PDF generation are the same as
the classic interface. The tabs only hide/show existing fieldsets; all fields
still submit. For a provider who is not the responsible technician, save and
conclude actions remain hidden; photo/legend collaboration remains available.

## 4. What does not change

- No database schema or data migration.
- No change to OS, finance, stock, feedback or API behavior.
- No change to the Client Portal.
- No change to the classic interface. `/ui/classic` restores it immediately.

## 5. Tests and manual check

`test_rev12_correcoes.py` covers the cookie toggle, the unslop shell on the OS
page, the summary, and the classic fallback.

Manual check in DEV:

1. Open `/login` and click **Ativar unslop**.
2. Log in and open an OS: verify the summary and tabs.
3. Click **Desativar unslop**: the classic layout must return.
4. Open the Client Portal: it must remain unchanged.

## 6. Rollback

Remove the `/ui/unslop` and `/ui/classic` routes, the `layout_unslop` branch in
`pagina()`, `CSS_UNSLOP`, and the tab block in `portal.js`. Existing cookies
become inert; no data needs cleanup.

## 7. Credit

The experimental interface was designed with guidance from
[unslop](https://github.com/heydamir/unslop), created by Damir Sokolovsky and
licensed under CC BY 4.0. The skill is installed outside the repository at
`~/.agents/skills/unslop`; the credit is also shown in the experimental page
footer.
