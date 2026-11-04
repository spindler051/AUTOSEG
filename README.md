# AUTOSEG

AUTOSEG is a work-management application for security and automation
professionals: clients, service orders, maintenance, budgets, technical reports,
finance, stock and client/provider portals.

The desktop application uses **GTK4 + libadwaita** (`gtk_app.py`). Client and
provider portals run on the same local SQLite database. The Tkinter frontend
was removed in `9.6.0-dev.12`.

## Current status

- Working vertical application for security/automation.
- GTK4 desktop application and two local web portals.
- Local-first SQLite storage.
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

## License

Original project code is released under the **BSD Zero Clause License
(0BSD)**. See [`LICENSE`](LICENSE). Third-party dependencies keep their own
licenses. The Workaholic subproject has its own
[`workaholic/LICENSE`](workaholic/LICENSE).

## Running the current app

macOS:

```bash
./INICIAR_AUTOSEG.command
```

Linux/GTK development:

```bash
./INICIAR_AUTOSEG_GTK.sh
```

Development database and ports:

```bash
./INICIAR_AUTOSEG_DEV.command
```

## Documentation

- [Product vision](docs/PRODUCT_VISION.md)
- [Agent rules](AGENTS.md)
- [Human-centered decisions](docs/HUMAN_CENTERED_DECISIONS.md)
- [User feedback guide](docs/USER_FEEDBACK_GUIDE.md)
- [English migration plan](docs/ENGLISH_MIGRATION_PLAN.md)
- [Naming and CLI contract](docs/NAMING_AND_CLI.md)
- [Open telemetry proposal](docs/features/OPEN_TELEMETRY.md)
- [Platform migration playbook](docs/PLATFORM_MIGRATION_PLAYBOOK.md)
- [Migration ledger](docs/PLATFORM_MIGRATION_LEDGER.md)
- [GTK4/libadwaita guide](docs/GTK4_LINUX_MACOS.md)
- [Workaholic integration](docs/WORKAHOLIC_INTEGRACAO.md)
- [Modular migration ledger](docs/MIGRACAO_MODULAR.md)
- [Architecture evolution plan](docs/PLANO_EVOLUCAO_ARQUITETURA.md)

## Repository layout

```text
gtk_app.py, gtk_dialogos.py, gtk_comum.py   GTK desktop frontend
portal_prestador.py, servidor_web.py        provider and client portals
portal_negocios.py, fluxo_os.py, ...        business rules
workaholic/                                 generic engine prototype
integracao/                                 AUTOSEG adapters to Workaholic
docs/                                       product, architecture and operations
```

The codebase is gradually being migrated to English. Legacy Portuguese module
and database names remain behind compatibility layers until a tested migration
is available.
