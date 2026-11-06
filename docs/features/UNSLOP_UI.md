# Unslop experimental interface

**Status:** experimental in `develop` as `9.6.0-dev.27`.
**Scope:** Provider Portal web interface only. The Client Portal and the
desktop GTK app are unchanged.
**Default:** classic interface. The experimental interface is opt-in per
browser.

## 1. Toggle

The login page offers **Ativar unslop**. When the experimental interface is
active, the login page and the authenticated sidebar show **Desativar unslop**.
The preference is a `SameSite=Lax` cookie named `autosseg_ui`, valid for one
year. It contains only `classic` or `unslop`, never identity or business data.

Routes:

| Route | Effect |
|---|---|
| `GET /ui/unslop?next=/page` | Sets the experimental preference and returns to `/page`. |
| `GET /ui/classic?next=/page` | Restores the classic preference and returns to `/page`. |

The `next` parameter is optional and must be a local path. When it is absent,
the route falls back to the `Referer` header. The sidebar link always includes
`next`, so **Desativar unslop** returns to the same OS or page even though the
portal sends `Referrer-Policy: no-referrer`.

## 2. Direction

- **Product.** Work and service orders for security and automation providers,
  from the client request to the technical report and the technician's payment.
- **Character.** Exact, calm, field-ready. A job sheet, not a marketing page.
- **World.** Graphite tools, warm paper notes and a service ticket on a bench.
- **Moments.** The perforated **Ficha da OS** ticket and the section-index tabs
  on the OS editor.
- **Signature.** The quiet OS ticket (number, status, client, responsible,
  total and photos) followed by three workflow cards: Andamento, Rascunho and
  Importação.

## 3. Shell

- Fixed sidebar, 264 px, warm graphite surfaces and a hairline border.
- Navigation grouped into Operação, Gestão and Registros, with one line icon
  set at 18 px and a single amber selection marker.
- User, feedback, logout and interface switch in the sidebar footer.
- Quiet chrome: primary actions use an off-white surface with dark text; amber
  is reserved for the active item, the selected tab, one key figure and status
  dots.
- No gradients, glows, colored shadows, emoji or uppercase tracked labels.
- Type: Avenir Next for the interface and SF Mono for dates, IDs, meta and
  figures; fallbacks keep the same hierarchy. Spacing follows the 4 px scale.
- Responsive: the sidebar becomes a horizontal navigation bar; the OS ticket,
  workflow and editor stack; tables keep their own horizontal scroll. There is
  no page-level horizontal overflow.

## 4. Pages

### 4.1 Login

A two-column split: product statement and a short list of what the portal does
on the left; the login form on the right. The interface switch is a quiet text
row above the form. The primary **Entrar** button is off-white, not amber.

### 4.2 Visão geral

- Factual meta line with the provider and date, no greeting headline.
- Four compact operational figures: OS abertas, iniciadas, pendentes and
  concluídas.
- **Ordens recentes** table with status dots, consistent dates and a direct
  link to each OS.
- Finance panel with **A receber** (the one amber figure) and **Recebido**.
- Quiet shortcut rows and the public-link disclosure.

### 4.3 Ordem de serviço

The page is composed in three layers:

1. **Ficha da OS** — a ticket with the OS number, status, client, opening date,
   responsible, total and photo count, plus **Preview do PDF**.
2. **Workflow** — Andamento (status, responsible, participants, assumir, em rota
   and iniciar), Rascunho and Importação de relatório.
3. **Editor and rail** — the form on the left and context on the right.

The editor uses four tabs generated from the existing fieldsets:

| Tab | Content |
|---|---|
| Identificação | Service model, client, payment, values, description and notes |
| Materiais | Material lines, stock picker and the expected total |
| Situação e relatório | Diagnosis, executed service, tests, internal report, status, recipients, rateio and **Fechamento** |
| Fotos e legendas | Existing photos, new photos and individual captions |

**Fechamento** contains the NF upload and the **Não precisa de nota fiscal**
checkbox. It lives in the Situação tab, not in Fotos, so the conclusion steps
are together. For a non-responsible provider, save/conclude actions stay
hidden and the photo/legend collaboration form remains available in the rail.

The action bar is sticky at the bottom of the editor: **Salvar rascunho** as a
secondary action and **Confirmar situação da OS** as the single primary action.
The draft button uses `formnovalidate`; the form uses `novalidate` in unslop
mode, and a capture-phase submit handler:

- switches to the tab of the first invalid field;
- focuses the field and shows a toast with its label;
- checks status, technical report and cancellation reason before confirming;
- keeps the AJAX error handling and never navigates to a full error page.

The classic form keeps native browser validation.

### 4.4 Financeiro

Two compact figures, a quiet PIX warning, the main receivables table and a
two-column secondary grid. Table actions are outlined and small; amber is not
repeated on every row. The bank data, transfers and technician-share cards use
the same surface and type hierarchy.

### 4.5 Lists and documents

OS, clients, services, invoices, e-mails and history reuse the shell and the
shared table/card styles. Search and filter buttons are secondary; only the
page's real creation action is primary. Tables use quiet headers, hairline row
separators and tabular figures.

## 5. What does not change

- No database schema or data migration.
- No change to OS, finance, stock, feedback or API behavior.
- No change to the Client Portal.
- No change to the classic interface. `/ui/classic` restores it immediately
  and returns to the same page through `next`.

## 6. Tests and manual checks

`test_rev12_correcoes.py` covers the cookie toggle, the `next` redirect, the
unslop login, the shell, the OS ticket/workflow/rail, the server-rendered
summary and the classic fallback. Current result: **32 tests, OK, 1 skipped**.
`test_feedback_portal.py`: **22 OK**. `test_api_financeiro.py`: **8 OK**.

Manual checks in DEV (Playwright, 1440×1000 and 390×844):

1. Enable unslop on the login and open an OS.
2. Confirm the ticket, workflow, tabs and rail are visible.
3. Click **Confirmar situação** without a status: the Situação tab opens, the
   field is focused and the toast says `Preencha: Situação do atendimento`.
4. Open the Situação tab and confirm **Fechamento** contains the NF upload and
   the **Não precisa de nota fiscal** checkbox.
5. Open the sidebar feedback button: the existing dialog opens.
6. Click **Desativar unslop**: the classic OS page loads on the same URL.
7. Check the dashboard, finance, OS, lists and login at 390 px wide with no
   page-level horizontal overflow.

## 7. Rollback

Remove the `/ui/unslop` and `/ui/classic` routes, the `layout_unslop` branch in
`pagina()`, `CSS_UNSLOP`, `ICONES`/`icone`, the unslop branches in `inicio`,
`os_form`, `financeiro` and `login`, the `next` handling and the unslop block
in `portal.js`. Existing cookies become inert; no data needs cleanup.

## 8. Credit

The experimental interface was designed with guidance from
[unslop](https://github.com/heydamir/unslop), created by Damir Sokolovsky and
licensed under CC BY 4.0. The skill is installed outside the repository at
`~/.agents/skills/unslop`; the credit is also shown in the experimental page
footer.
