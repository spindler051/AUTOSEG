# Surface sections, order and GNOME HIG

**Status:** planning. No runtime behavior changed by this document.
**Scope:** the provider surfaces (Officina Web and GTK). Client surfaces follow
the same model later.
**Rule being implemented:** every website section exists on GTK with the same
order, the same actions and the same visibility for the same principal. Hiding
a section is resolved on the server from capabilities, never from a surface
flag.

This document defines *what* is shared, *what* stays native, how the two
surfaces are kept in sync mechanically, and the phasing.

## 1. What already exists

| Piece | Path | State |
|---|---|---|
| 1:1 feature rule | `docs/SURFACE_PARITY.md` | written (2026-11-15) |
| GNOME quality bar | `docs/PRODUCT_VISION.md` §10 | written |
| Offline HIG mirror | `docs/baixar_gnome_hig.sh` → `docs/gnome-hig/` | directory absent; script present |
| Shared section table | `flavors/autoseg/modules/autoseg_web_navigation.py::ITEMS` | used by the web |
| Generic navigation | `officina/web/navigation.py` (`navigation_for`, `active_for`) | used by the web |
| GTK navigation | `flavors/autoseg/modules/gtk_app.py:176` + `officina/application/session.py::navigation_for_session` | **separate hardcoded list** |
| GTK shell | `Adw.NavigationSplitView` (139), `Adw.ToolbarView` (167/254), `Gtk.ListBox` (173), `Adw.ViewStack` (268) | already HIG-shaped |
| Customer action registry | `flavors/autoseg/config/surface_registry.yaml` | 8 customer actions; not a section registry |
| Screen contract proposal | `docs/planning/WEB_GTK_SHARED_CONTRACT.md` | proposal, not implemented |

The automation anchor already exists. `NavItem` carries `id`, `title`, `href`,
`contexts`, `group`, `icon`, `permission`, `top` and `top_order`. The web
filters it with `navigation_for(context)`. The GTK ignores it.

## 2. Current drift (evidence)

| Section | Web | GTK |
|---|---|---|
| Estoque | `permission="*"` → admin only | visible to employees |
| Composição de valores | `permission="*"` → admin only | visible to employees |
| Prestadores | admin only | admin only |
| Order | home, clients, OS, services, **finance**, PJ, invoices, e-mail, **history**, providers, **stock**, composition | home, clients, OS, **history**, **finance**, invoices, e-mail, providers, PJ, services, composition, **stock** |
| Feedback / Configurações | present | absent |
| Conexões | absent | present (desktop configuration) |

Two different lists, two orders, two visibility rules. That is the defect this
plan closes.

## 3. Canonical decisions

1. **The website table is canonical.** `autoseg_web_navigation.ITEMS` is the
   single source of sections, groups, order and permission. The GTK does not
   keep its own list.
2. **Shared contract, native rendering.** The contract says *what*: id, title,
   group, order, permission, contexts, semantic icon. The adapters say *how*:
   web route and HTML, GTK page and widgets.
3. **Visibility is capability-based and server-resolved.** The existing
   `permission` string is evaluated against the session's permission set.
   `*` means the admin bundle. No `if gtk`, no `if web`, no new key in phase A.
4. **One order.** `group` then `top_order`, identical on both surfaces.
5. **Explicit exceptions.** A section that legitimately exists on one surface
   only must be declared in the table with a reason. Connection settings
   (`conexao`) are desktop configuration; `feedback`/`settings` are web
   administration. Nothing else may be one-sided.

## 4. The contract

`NavItem` gains two fields (implementation detail, not user-visible):

```text
gtk_page   adapter id for the GTK page factory; None for web-only sections
surfaces   ("web", "gtk") — default both; a one-sided value requires a reason
```

Everything else stays as it is. The web keeps using `href`; the GTK maps
`gtk_page` to a factory:

```text
GTK_PAGES = {
    "home": Janela._pagina_inicio,
    "customers": Janela._pagina_clientes,
    "work": Janela._pagina_os,
    ...
}
```

A section is only "done" when it has a web route, a GTK page and a permission.
The analyzer (§6) enforces that.

### Resolver

One function produces the visible, ordered tuple:

```text
navigation_for(context)  →  tuple[NavItem, ...]
```

- **Web:** already does this (`autoseg_web_navigation.top_navigation_for`).
- **GTK local:** same function, with the local principal's permissions.
- **GTK remote:** the server returns the resolved navigation with the session
  context, so the desktop never re-implements policy:
  `GET /api/v1/desktop/me` (or a dedicated `/context/navigation`) returns
  `[{id, title, group, order, icon}]` for the authenticated principal.
  The GTK renders that list and maps `id → gtk_page`.

The server is authoritative; the GTK still needs its page factory table, but
not a second policy.

## 5. GNOME HIG checklist

The HIG constrains the GTK adapter, not the contract. The app already uses the
right primitives; the checklist keeps new sections honest.

| Need | Pattern | Current |
|---|---|---|
| Sidebar + content | `Adw.NavigationSplitView` + `Adw.Breakpoint` (sidebar becomes a navigation page) | partial |
| Page chrome | `Adw.ToolbarView` + single `Adw.HeaderBar` | yes |
| Settings-like page | `Adw.PreferencesPage` / `Group` / `ActionRow` | partial |
| Section empty/error/offline | `Adw.StatusPage` / `Adw.Banner` | partial |
| Destructive confirmation | `Adw.AlertDialog` (`ui.alerta`) | yes |
| Transient feedback | `Adw.Toast` (`ui.toast`) | yes |
| Lists | `Gtk.ListBox`/`Adw.ActionRow` or `Gtk.ColumnView` | yes |
| Keyboard | `Adw.Application` actions, accelerators | partial |
| Accessibility | labels, roles, no icon-only destructive actions | review |
| Adaptive shell | explicit `Adw.Breakpoint` (`max-width: 600sp`) collapsing the sidebar | partial |
| Wide content | `Adw.Clamp` keeping the reading width bounded | partial |
| Narrow actions | primary action in a bottom toolbar, secondary in a menu | partial |
| Dialogs | `Adw.Dialog` as a bottom sheet on narrow windows | partial |

**Do not:** custom titlebar, `Gtk.HeaderBar` per page, `Gtk.Stack` as primary
navigation, custom CSS that replaces Adwaita chrome, a second sidebar style.

Restore the offline HIG for review with `docs/baixar_gnome_hig.sh`.

### Adaptive layout (mandatory)

The GNOME HIG asks for adaptive design, not a compressed desktop. The rules:

- design for the smallest window first; keep the same functionality at every
  size;
- when the sidebar no longer fits, turn it into a navigation page
  (`Adw.NavigationSplitView` collapsed by an `Adw.Breakpoint`, or
  `Adw.OverlaySplitView`);
- move section actions to a bottom toolbar or overflow menu on narrow windows;
  every action stays reachable;
- keep content readable with `Adw.Clamp`; do not stretch forms edge to edge on
  wide screens;
- `Adw.Dialog` becomes a bottom sheet on narrow windows;
- declare the layout with breakpoints, not `if width` branches in handler code.

Reference breakpoints, tuned at review: `max-width: 600sp` for the collapsed
shell and `max-width: 900sp` for compact spacing. Verify at **360, 600 and
1200 px**, with no horizontal scroll and no lost action or field.

Official references:
[GNOME HIG — adaptive](https://developer.gnome.org/hig/guidelines/adaptive.html)
and [libadwaita — adaptive layouts](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/adaptive-layouts.html).

### Observed shell defects (2026-11-15)

- the window forced `set_size_request(900, 560)`, so it advertised a desktop
  minimum and could not reach a phone-like width;
- the page `Adw.ViewStack` was not inside a scroller, so wide or tall pages
  were clipped outside the window instead of scrolling;
- the sidebar had a 220–280 px width but no explicit collapse breakpoint.

The shell now allows 360×480, collapses the sidebar below 600sp through
`Adw.Breakpoint` and scrolls the page area. Per-page refinements (`Adw.Clamp`,
bottom action bars, `Adw.Dialog` as a bottom sheet) remain part of B/C.

HIG cannot be fully automated. The mechanical part is order/visibility; the
visual part is a checklist per section at review time.

## 6. Automation

New analyzer, same shape as `scripts/surface_divergence.py`:

```sh
python scripts/surface_sections.py --check
```

It verifies:

1. every `ITEMS` entry has a web route **and** a GTK page (or a declared
   exception with `surfaces` and a reason);
2. no GTK page and no web route is orphaned (exists in code but not in `ITEMS`);
3. `id`, `group`, `top_order` are unique and identical for both surfaces (by
   construction, since both read `ITEMS`);
4. every section declares a `permission` or is explicitly public;
5. one-sided sections are listed in a reviewed exception list.

Tests: `tests/test_surface_sections.py`, plus a fixture check that an inserted
or removed page fails the analyzer. `--check` must exit 0 in every commit.

This makes the common change mechanical: add one `NavItem`, implement the two
adapters, run the check. Forgetting one side fails CI-style validation instead
of drifting silently.

## 7. Phasing

### Phase A — sections, order, visibility (next)

1. **A1 canonical table.** Align `ITEMS` with the website's actual order;
   declare `conexao`, `settings`, `feedback` exceptions; add `gtk_page` and
   `surfaces`.
2. **A2 GTK consumes it.** Delete the hardcoded `nav_itens` list; group and
   order from the shared resolver; remote GTK renders the server-provided
   navigation; local GTK resolves with the same function.
3. **A3 analyzer + tests.** `surface_sections.py`, fixture failures, exit 0.
4. **A4 HIG review.** Apply the checklist to each section; fix the obvious
   deviations (no per-page headerbar, StatusPage/Banner for empty/offline) and
   add an explicit `Adw.Breakpoint` for the collapsed shell.

**Acceptance**

- same principal → same section set and order on web and GTK;
- employee no longer sees Estoque/Composição if the web hides them (and vice
  versa);
- no orphan page/route; analyzer green;
- `surface_divergence --check` stays 0/0;
- one commit per sub-item, full suite, no schema or flags.

### Phase B — actions per section

Extend the contract from sections to actions: `id`, section, capability,
service/route, destructive/confirmation, both adapters. Start with **OS**
(list, detail, conclude, publish, assign) because it is the largest and the
most permission-sensitive. Same analyzer: every action must exist on both
surfaces and have a negative test. Every action must also be reachable at
360 px: primary in the bottom toolbar, secondary in the menu, nothing lost.

### Phase C — fields and forms

Shared view model per form: field id, label, type, validation, visibility
scope; native widgets. Start with the customer form (already partially done in
3.5/3.6) and the OS form. Forms use `Adw.Clamp` and adaptive rows, and dialogs
become bottom sheets on narrow windows; the same fields and validation exist at
every width. This is where the screen contract proposal of
`WEB_GTK_SHARED_CONTRACT.md` becomes real.

Phases are independent: A ships value alone, B and C each add a dimension.

## 8. Non-goals

- no UI framework, DSL or code generation;
- no database access from clients;
- no new permission keys in phase A;
- no surface-specific authorization;
- no rewrite of the GTK shell; it is already HIG-shaped.

## 9. How to add a section (after phase A)

1. add one `NavItem` to `ITEMS` (id, title, href, group, order, permission,
   contexts, gtk_page);
2. implement the web route and the GTK page factory;
3. if one-sided, add the exception with a reason;
4. run `surface_sections.py --check` and the section's negative test;
5. apply the HIG checklist at review.

## 10. Process

- Code changes base on `dev` after a fast-forward from `main` (the documented
  release model: work on `dev`, merge to `main` after homologation).
- This document was committed on `main` so the next work starts from the
  promoted baseline; `dev` receives it on the next sync.
- One queue item = one commit; failing test first; focused + full suite;
  `audit_comments --strict`.
- No schema, flags, MAF, Workaholic or outbox changes here.

## 11. Open decisions

1. Confirm `ITEMS` order as canonical (proposal: yes).
2. `Conexões` is a desktop-only section; `Configurações` and `Feedbacks` are
   web-only today. Accept as declared exceptions, or build the missing side?
3. Remote navigation payload: extend `/me` or add `/context/navigation`?
   (Proposal: dedicated route, so `/me` stays identity-only.)
4. Does the employee Finance page keep the module visible with personal
   content (proposal: yes), or hide it until the personal view exists?
