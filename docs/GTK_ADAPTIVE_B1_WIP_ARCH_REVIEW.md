# AUTOSEG — adaptive GTK correction, B1/C1 WIP

**NOT HOMOLOGATED — FOR REVIEWER CONTINUATION.** This follows WIP commit
`9bf287a` (and can be merged after the independent reviewer commit `ccbe895`).
It is **not** a Phase B/C delivery. No OS writer, policy, schema, Web, or backend
function was modified here.

## Why

The Arch/libadwaita 1.10 probe reported an unwanted `1088px` minimum from the
stock page, enlarged to `1308px` with the sidebar. The 600sp navigation breakpoint
was switching correctly, but fixed-width action bars, a homogeneous ViewStack,
wide tables and an outer page scroller forced an over-wide minimum.

## Changes in this patch

1. **Page boundary:** each GTK section now has a bounded, vertically scrollable
   page. The top-level `Adw.ViewStack` is horizontally non-homogeneous and no
   longer has one outer scroller determining its minimum from the widest child.
   The already-scrollable home page is reused. A page has a minimum scroller
   content request of 280px (before the sidebar is added, when expanded).
2. **One adaptive action bar:** the section header/menu and narrow bottom bar
   own page toolbar actions. Buttons from older `ui.barra` toolbars are removed
   from the page layout and their existing `clicked` handlers are available in
   `Outras ações` within the section overflow. Actions already represented by
   a resolved canonical label are not duplicated. This **temporary WIP bridge**
   keeps the pre-existing service authorization; B1 should replace individual
   legacy entries with working canonical action adapters.
3. **Tables:** each `Adw.BreakpointBin` now requests 240x120; the internal
   `Gtk.Stack` is not horizontally homogeneous. The wide `ColumnView` scrolls
   **inside the table only**. Compact cards remain selected under 600sp, on the
   same `Gtk.SingleSelection` model as the wide table. No global horizontal
   scroller is added.
4. **Cards and text:** summary cards and home shortcuts use wrapping
   `Gtk.FlowBox`; descriptive GTK labels wrap at small widths. The PJ subview
   stack no longer uses the widest child for its width.
5. **OS selection:** refresh section actions on both `selected` and
   `selected-item` changes and after OS model refresh. The server still resolves
   allowed actions with the selected real `object_id`.

The shell breakpoint is **600sp**, with a minimum window and shell request of
**360x480**. At 360/600 the sidebar is collapsed and the bottom action toolbar
is visible; at 1200 the sidebar is expanded and actions appear in the header.
The threshold is expressed in `sp` by libadwaita and must not be treated as an
unconditional count of physical pixels under scaled display settings.

## Arch reviewer — validation still required

**No suite, analyzer, GTK launch or live width measurement was run here.**
The reported post-change minimum width is therefore **unknown**, not asserted
as <=360. Please obtain actual measurements of every page after realization:

| Window width | Intended behavior | Post-change page minimums |
|---|---|---|
| 360px | collapsed, bottom bar, compact tables | **not measured** |
| 600px | collapsed, bottom bar, compact tables | **not measured** |
| 1200px | expanded, header actions, wide tables | **not measured** |

Review each page from `Adw.ViewStack.get_pages()` and record the allocated/min
horizontal width, and check no warning for either `AdwNavigationSplitView
exceeds AdwBreakpointBin width` or `AdwBreakpointBin ... minimum size`.
Check customer, OS, stock, composition, PJ and the home dashboard first.

**Action reachability:** no known *existing toolbar callback* is deliberately
removed. Legacy callbacks appear in `Outras ações`; however actual operation
at 360px is **not visually verified**. When selecting an OS in either table
variant, check that `work.open`, `work.edit`, `work.conclude`, `work.cancel`, and
other grants appear only as authorized for that OS. Re-run with a different
provider and an unowned OS to ensure object-level denials remain intact.

Suggested validation in the Arch worktree:

```sh
python -m unittest discover -s tests -p 'test_*.py' -q
python scripts/surface_sections.py --check
python scripts/surface_divergence.py --check
python scripts/audit_comments.py --strict
git diff --check 9bf287a..HEAD
```

Then run the live GTK probe at 360, 600 and 1200px with a temporary database,
checking every page's calculated minimum, action menus, table selection,
keyboard accessibility, and scrolling. If a toolbar action is duplicated,
mislabelled, inaccessible or incorrectly authorized, report it with section ID
and the selected OS/customer ID.

## Boundary

This branch only addresses the Arch adaptive-layout findings. The wider B1/C1
WIP remains **not homologated** and requires a separate functional review.
