# AUTOSEG

AUTOSEG is a work-management application for security and automation
professionals: clients, service orders, maintenance, budgets, technical reports,
finance, stock and client/provider portals.

The desktop application uses **GTK4 + libadwaita** (`gtk_app.py`). Client and
provider portals run on the same local SQLite database. The Tkinter frontend
was removed in `9.6.0-dev.12`.

## Current status

Versão de desenvolvimento: `9.6.0-dev.55` (`develop`).

- Working vertical application for security/automation.
- GTK4 desktop application and two local web portals.
- Local-first SQLite storage.
- Suíte não visual: **306 testes, 0 falhas, 1 skip**.
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

macOS desktop (local, sem servidor):

```bash
./INICIAR_AUTOSEG.command
```

Desktop com os portais locais ligados (comportamento antigo):

```bash
./INICIAR_AUTOSEG_COM_WEB.command
```

Linux/GTK development:

```bash
./INICIAR_AUTOSEG_GTK.sh
```

DEV em modo servidor (abra o servidor primeiro):

```bash
./INICIAR_SERVIDOR_DEV.command   # terminal 1
./INICIAR_AUTOSEG_DEV.command    # terminal 2
```

O app DEV não abre o banco local. Se o servidor estiver parado, as listas ficam
vazias e a janela mostra um aviso de servidor indisponível.

Local-only GTK (no web server and no tunnel):

```bash
./INICIAR_AUTOSEG_SEM_WEB.command
```

Servidor headless no terminal (API, sem HTML, sem GTK, sem Cloudflare):

```bash
./INICIAR_SERVIDOR_API.command
```

GUI do site (Officina Web) no terminal:

```bash
./INICIAR_SITE.command
```

Hoje a GUI do site ainda compartilha o processo com a API; a separação completa
entre servidor e site é uma fase posterior. O servidor de dados é o
`INICIAR_SERVIDOR_API.command`.

O padrão do desktop agora é local-only. Use `AUTOSEG_WEB_ACCESS=1` ou
`INICIAR_AUTOSEG_COM_WEB.command` somente se quiser que o próprio GTK suba os
portais.

## Documentation

- [Documentation index](docs/README.md) — ponto de entrada canônico.
- [Current handoff](docs/HANDOFF.md) — estado e próximos passos.
- [Roadmap](docs/ROADMAP.md)
- [Product vision](docs/PRODUCT_VISION.md)
- [Tests](TESTES.md)
- [Agent rules](AGENTS.md)
- [Changelog](CHANGELOG.md)
- [Archived documentation](docs/archive/README.md) — histórico, não vigente.

## Repository layout

```text
gtk_app.py, gtk_dialogos.py, gtk_comum.py   GTK desktop frontend
portal_prestador.py, servidor_web.py        provider and client portals
portal_negocios.py, fluxo_os.py, ...        business rules
runtime_config.py                           runtime paths, bind and ports
workaholic/                                 generic engine prototype
integracao/                                 AUTOSEG adapters to Workaholic
docs/                                       current docs; features/, operations/, planning/
docs/archive/                               historical docs, not current
```

The codebase is gradually being migrated to English. Legacy Portuguese module
and database names remain behind compatibility layers until a tested migration
is available.
