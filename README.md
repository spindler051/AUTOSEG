# AUTOSEG

AUTOSEG is a work-management application for security and automation
professionals: clients, service orders, maintenance, budgets, technical reports,
finance, stock and client/provider portals.

The desktop application uses **GTK4 + libadwaita** (`flavors/autoseg/modules/gtk_app.py`). Client and
provider portals run on the same local SQLite database. The Tkinter frontend
was removed in `9.6.0-dev.12`.

## Current status

Versão de desenvolvimento: `9.6.0-dev.71` (`develop`).

- Working vertical application for security/automation.
- GTK4 desktop application with provider login (local or server), identity and logout.
- Two local web portals.
- SQLite storage outside the repository, in local or server mode.
- Suíte não visual: **338 testes, 0 falhas, 1 skip**.
- Brazilian fiscal/payment features are still part of the AUTOSEG application,
  not yet isolated as locale modules.
- **Workaholic** is the generic engine project under `workaholic/`. It is a
  prototype (`0.1.0`) and is currently integrated only for the `cliente`
  slice. It has not been abandoned; making it the engine of the whole platform
  is a planned architectural phase.

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

macOS desktop (local, sem servidor):

```bash
./autoseg app
```

Desktop com os portais locais ligados (comportamento antigo):

```bash
./autoseg app-web
```

Linux/GTK development:

```bash
./autoseg app
```

DEV em modo servidor (abra o servidor primeiro):

```bash
./autoseg server   # terminal 1
./autoseg dev    # terminal 2
```

O app DEV abre com servidor selecionado por padrão. A tela de login também oferece o modo Local; o banco local só é aberto se você escolher essa opção.
No banco fictício de DEV, use as credenciais de
`CREDENCIAIS_FICTICIAS_DEV.txt` na pasta de dados do servidor DEV. Execute
`./autoseg paths` para ver o caminho exato. Se o servidor estiver parado, o app
mostra a tela de login com aviso de servidor indisponível.

Local-only GTK (no web server and no tunnel):

```bash
./autoseg app-local
```

Servidor headless no terminal (API, sem HTML, sem GTK, sem Cloudflare):

```bash
./autoseg api
```

GUI do site no terminal:

```bash
./autoseg site-prod       # produção: 8765/8766
./autoseg site   # DEV: cliente 8865, prestador 8866
```

Hoje a GUI do site ainda compartilha o processo com a API embutida; a separação
completa entre servidor e site é uma fase posterior. O servidor de dados do GTK
é o `./autoseg server` (porta 8766). O site DEV usa o mesmo banco de
teste, mas em processo e portas separados.

O padrão do desktop agora é local-only. Use `AUTOSEG_WEB_ACCESS=1` ou
`./autoseg app-web` somente se quiser que o próprio GTK suba os
portais.

## Onde ficam os dados

Nada de banco, anexo ou log fica no repositório. O servidor usa a pasta do
sistema (`/var/lib/autoseg` no Linux, `/Library/Application Support/AUTOSEG` no
macOS); DEV e o modo local usam pastas do usuário. Consulte
[`docs/operations/DATA_STORAGE.md`](docs/operations/DATA_STORAGE.md) e rode
`./autoseg paths` para ver os caminhos efetivos.

## Documentation

- [Documentation index](docs/README.md) — ponto de entrada canônico.
- [Current handoff](docs/HANDOFF.md) — estado e próximos passos.
- [Roadmap](docs/ROADMAP.md)
- [Product vision](docs/PRODUCT_VISION.md)
- [Tests](TESTES.md)
- [Data locations](docs/operations/DATA_STORAGE.md)
- [Agent rules](AGENTS.md)
- [Changelog](CHANGELOG.md)
- [Archived documentation](docs/archive/README.md) — histórico, não vigente.

## Repository layout

```text
flavors/autoseg/modules/gtk_app.py           GTK desktop frontend
flavors/autoseg/modules/portal_prestador.py  provider portal
flavors/autoseg/modules/servidor_web.py      client portal
officina/core/portal_negocios.py, fluxo_os.py  business rules
officina/core/runtime_config.py               runtime paths, bind and ports
workaholic/                                 generic engine prototype
officina/integration/                       adapters to Workaholic
docs/                                       current docs; features/, operations/, planning/
docs/archive/                               historical docs, not current
```

The codebase is gradually being migrated to English. Legacy Portuguese module
and database names remain behind compatibility layers until a tested migration
is available.
