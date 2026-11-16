<p align="center">
  <img src="flavors/autoseg/branding/icone-readme.png" width="128" alt="AUTOSEG">
</p>

# AUTOSEG

**Run your service business, not your paperwork.**

AUTOSEG is an open-source workspace for security and automation
professionals. Clients, service orders, maintenance, quotes, technical
reports, finance and stock live in one place — in a native desktop app and a
shared web portal.

**What it wants to be.** AUTOSEG is the first real application of **Officina**,
an open ecosystem for work management, built on **Workaholic**, a generic
engine for work records. The goal is one platform that can run **centralized**
on a server or **decentralized**, local-first, on your own machine — the same
data, the same rules, and your choice of infrastructure.

**Where it is today.** Not there yet, and we say so. AUTOSEG is the part that
already runs a real business in production. Officina and Workaholic are being
built around it one slice at a time; Workaholic powers only the customer slice
today, and the decentralized model is a direction, not the current state.

**How we move.** Production first, architecture second. Small changes, tested
against a real business, with no big rewrite and no lost data. It is slow on
purpose.

**Security.** Security is part of every change, not a later pass. If you find
a concern, please open an issue or contact the maintainers — responsible
reports and contributions are very welcome. See [`SECURITY.md`](SECURITY.md).

## Current status

AUTOSEG is already used in production. The version on `main` is
`9.6.0-dev.73`.

- native GTK4 + libadwaita desktop app; provider login works locally or
  against a server, and client login in the desktop app is planned;
- one Officina Web site with a single login for providers and clients; the
  legacy provider form remains as a rollback;
- SQLite data lives outside the repository, in a local or server data
  directory;
- the test suite covers the current behavior; exact counts are in
  [`TESTES.md`](TESTES.md);
- some hardening flags are still opt-in while the remaining authorization
  review is finished;
- Brazilian fiscal and payment rules are still part of AUTOSEG, not yet
  isolated as locale modules;
- Workaholic is a prototype today and powers only the customer slice.

Next: finish the authorization review and the remote client slice. The ordered
plan is in [`docs/ROADMAP.md`](docs/ROADMAP.md); the client-mode analysis is in
[`docs/planning/GTK_CLIENT_MODE.md`](docs/planning/GTK_CLIENT_MODE.md).

## Long-term direction

The project is moving toward a modular, open-source platform:

- **Workaholic**: generic work-record engine, schemas, validation, versioning
  and storage.
- **Generic GTK application**: a GNOME/GTK4 app for work management, usable by
  artists, stagehands, electricians, musicians, DJs and other professionals.
- **AUTOSEG flavor**: a security/automation distribution built on the generic
  application, preserving current behavior.
- **Locale/vertical modules**: Brazilian rules such as CPF/CNPJ, NF-e/NFS-e,
  PIX and municipal tax.

The full product vision, boundaries, licensing and roadmap are documented in
[`docs/PRODUCT_VISION.md`](docs/PRODUCT_VISION.md).

## Repository layout

The monorepo is transitioning from a flat prototype to clear layers:

- `workaholic/` — generic engine.
- `officina/` — generic application platform and contracts.
- `flavors/autoseg/` — AUTOSEG branding, configuration and templates.
- `officina/application/` — generic application services.
- `flavors/autoseg/modules/` — AUTOSEG GTK, portals, API, auth and fiscal modules.
- `scripts/autoseg/` — launchers and automation.
- `tests/` — test suite.

Runtime data (database, attachments, reports, logs) is kept outside the
repository in a user or system data directory.

See [`docs/REPOSITORY_LAYOUT.md`](docs/REPOSITORY_LAYOUT.md) for the target tree
and the migration rules.

## License

Original project code is released under the **BSD Zero Clause License
(0BSD)**. See [`LICENSE`](LICENSE). Third-party dependencies keep their own
licenses. The Workaholic subproject has its own
[`workaholic/LICENSE`](workaholic/LICENSE).

## Running the current app

Common MAIN (production) / DEV (development) operations:

```bash
# MAIN
./autoseg start site      # site on 8766; the API is embedded
./autoseg start tunnel    # tunnels for 8766
./autoseg status
./autoseg stop all

# DEV
./autoseg-dev start site      # site on 8866
./autoseg-dev start tunnel    # tunnels for 8866
./autoseg-dev status
./autoseg-dev stop all
```

`start site` on MAIN already starts the embedded API; for a separate API,
stop the site and use `./autoseg start server`. On DEV, `server`/API uses port
8766 and requires MAIN to be stopped. PIDs and logs live in
`~/Library/Application Support/AUTOSEG/cli`.

`./autoseg update` only restarts processes; it does not pull, merge or change
code. MAIN and DEV share the same checkout, so use `./autoseg update main` to
validate production first and `./autoseg update dev` afterwards, when the change
is ready for both.

macOS desktop (local, no server):

```bash
./autoseg app
```

Desktop with the local portals enabled (legacy behavior):

```bash
./autoseg app-web
```

Linux/GTK development:

```bash
./autoseg app
```

DEV in server mode (start the server first):

```bash
./autoseg server   # terminal 1
./autoseg dev    # terminal 2
```

The DEV app opens with the server selected by default. The login screen also
offers Local mode; the local database is only opened if you choose it. In the
DEV fixture database, use the credentials from
`CREDENCIAIS_FICTICIAS_DEV.txt` in the DEV server data directory. Run
`./autoseg paths` to see the exact path. If the server is stopped, the app shows
the login screen with an unavailable-server warning.

Local-only GTK (no web server and no tunnel):

```bash
./autoseg app-local
```

Headless server in the terminal (API, no HTML, no GTK, no Cloudflare):

```bash
./autoseg api
```

Site GUI in the terminal:

```bash
./autoseg site-prod       # production: 8766
./autoseg site            # DEV: Officina Web on the single port 8866
```

Today the site GUI still shares the process with the embedded API; fully
separating server and site is a later phase. The GTK data server is
`./autoseg server` (port 8766). The DEV site uses only the fixture database and
port 8866, in a process separate from MAIN.

The desktop default is now local-only. Use `AUTOSEG_WEB_ACCESS=1` or
`./autoseg app-web` only if you want the GTK app itself to start the portals.

## Where the data lives

No database, attachment or log lives in the repository. The server uses the
system directory (`/var/lib/autoseg` on Linux,
`/Library/Application Support/AUTOSEG` on macOS); DEV and local mode use user
directories. See
[`docs/operations/DATA_STORAGE.md`](docs/operations/DATA_STORAGE.md) and run
`./autoseg paths` to see the effective paths.

Business identity: set `AUTOSEG_COMPANY_CNPJ` and `AUTOSEG_WHATSAPP` in the
server environment. The public repository uses fictitious values; never commit
a real CNPJ or phone number.

## Documentation

- [Documentation index](docs/README.md) — canonical entry point.
- [Current handoff](docs/HANDOFF.md) — state and next steps.
- [Roadmap](docs/ROADMAP.md)
- [Client GTK plan — 6.5](docs/planning/GTK_CLIENT_MODE.md)
- [Product vision](docs/PRODUCT_VISION.md)
- [Tests](TESTES.md)
- [Data locations](docs/operations/DATA_STORAGE.md)
- [Security policy](SECURITY.md)
- [Agent rules](AGENTS.md)
- [Changelog](CHANGELOG.md)
- [Archived documentation](docs/archive/README.md) — historical, not current.

## Key files

```text
flavors/autoseg/modules/gtk_app.py           GTK desktop frontend
flavors/autoseg/modules/portal_prestador.py  Officina Web origin (provider + client dispatch)
flavors/autoseg/modules/client_web.py        client routes inside the unified site
flavors/autoseg/modules/autoseg_web_navigation.py  AUTOSEG navigation and routes
flavors/autoseg/modules/client_extended_web.py   client-only modules in shared shell
flavors/autoseg/modules/client_features.py       authenticated client services
officina/web/                                generic shell and presentation contracts
officina/core/portal_negocios.py, fluxo_os.py  business rules
officina/core/runtime_config.py               runtime paths, bind and ports
workaholic/                                 generic engine prototype
officina/integration/                       adapters to Workaholic
docs/                                       current docs; features/, operations/, planning/
docs/archive/                               historical docs, not current
```

The unified site still runs through `portal_prestador.py` for historical
reasons; its name is a migration artifact. The former `servidor_web.py` and `portal_cliente_v94.py` were deleted;
all retained customer flows now run inside the unified origin.

The codebase is gradually being migrated to English. Legacy Portuguese module
and database names remain behind compatibility layers until a tested migration
is available.
