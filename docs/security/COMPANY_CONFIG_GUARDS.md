# Company configuration access: inventory and server authority

The desktop API authenticates every request and obtains the provider principal
from its session. LocalService independently checks the live provider record,
organization membership, and effective role in SQLite; it does not trust a GTK
admin boolean. Missing/inactive principal is denied. The GTK caches the
validated principal for its local LocalService instance, while remote calls
use the token and server-side authentication.

| Surface / data | Read | Write |
|---|---|---|
| Providers, admin status, config, documents | admin | admin |
| PJ organization, links and requests | admin | admin |
| Catalog and prices | provider | admin |
| Stock materials and movements | `stock.view` | admin |
| Company capital, investments and expenses | admin | admin |
| Composition parameters and recalculation | admin | admin |
| Connection settings (GTK-local) | admin UI | admin UI |
| Personal finances | `finance.view.own` | finalizer or admin for payments |

`provider.manage.all` is the existing admin capability. `stock.view` is the
existing employee read capability; no extra permissions are defined here.
The website and desktop API enforce write protection on their endpoints;
LocalService enforces it on in-process GTK local mode as well. Hiding UI
buttons is supplementary and not a security boundary.

The stock page suppresses edit buttons and company cash totals for staff.
Other company settings pages are removed from employee navigation by the
shared section projection.
