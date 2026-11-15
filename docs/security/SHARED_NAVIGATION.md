# One section registry for Web and GTK

The provider section registry is `flavors/autoseg/modules/autoseg_web_navigation.py::ITEMS`.
Each `NavItem` declares web path, semantic icon, GTK page adapter, group,
order, permission, surfaces, and an explicit reason for single-surface items.
The two renderers both filter these same items with the session capabilities.
The GTK does not define a second section/permission table. The flavor adapter
passes the ordered sections into the generic session projection; core never
imports the AUTOSEG flavor.

The desktop `/api/v1/desktop/me` endpoint returns the server-filtered navigation
list. Login saves the granted item IDs; the GTK intersects them with the local
presentation registry and the permissions snapshot. Local mode derives the
same projection from the authenticated principal; all backend operations
still verify permissions independently of navigation visibility.

`provider.manage.all` is required for company/provider/composition/PJ management;
`stock.view` grants read-only stock visibility. In both GTK and Web, employee
stock pages hide write controls and the handlers deny write attempts.

`feedback` and account settings are web-only in this phase. Device connections
and the launcher for the local web service are GTK-only. The client portal
remains web-only, as stated in the planning document. These are annotated
explicitly in the registry, not inferred from the surface.

Verification:

```sh
python scripts/surface_sections.py --check
python scripts/surface_divergence.py --check
python -m unittest tests.test_security_shared_navigation -v
```

GNOME HIG visual review remains a separate manual acceptance check; the
mechanical registry test does not certify HIG compliance.
