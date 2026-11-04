# Naming and CLI contract

**Status:** proposal. No rename was executed. This document records the
current working names, the terminal behavior we want and the name-collision
concerns to resolve before a public release.

## 1. Working names

| Piece | Working name | Status |
|---|---|---|
| Engine | **Workaholic** | Prototype at `workaholic/`; 0BSD. |
| Engine CLI | `workaholic` / `workaholic-cli` | Prototype. |
| Generic GTK app | **TBD** | Not named; not started as a separate app. |
| Security/automation flavor | **AUTOSEG** | Current production app. |
| Brazilian locale modules | **TBD** (`autoseg-br` working name) | Planned. |

## 2. Recommendation: do not make `workaholic` ambiguous

I would **not** make `workaholic` a symlink that sometimes opens the GUI and
sometimes runs the CLI depending on the environment. That surprises scripts,
terminal users and documentation.

Recommended contract if the umbrella name stays **Workaholic**:

```text
workaholic          # CLI: help, status, schema and record commands
workaholic-cli      # explicit CLI alias
workaholic-gtk      # GTK4/libadwaita application
workaholic gui      # optional explicit convenience command
```

- `workaholic` without arguments shows help/status; it does **not** open a GUI.
- The desktop entry launches `workaholic-gtk`.
- `workaholic gui` is an explicit choice; no auto-detection by display/TTY.
- Scripts can rely on `workaholic` being non-interactive.

If the platform gets a different name (recommended, see below), then:

```text
workaholic          # engine CLI only
<app>               # generic GTK application
<app>-cli           # optional generic app CLI
```

The engine name and the application name do not need to be the same.

## 3. Why not auto-select GUI vs CLI

Auto-detection seems convenient but creates problems:

- cron jobs and SSH sessions behave differently;
- documentation becomes conditional (“sometimes this opens a window”);
- packaging and bug reports become ambiguous;
- users cannot predict whether a command blocks the terminal;
- a GUI dependency leaks into headless/engine installations.

Explicit commands are boring and reliable. Boring is good for a work tool.

## 4. Name collision concerns

A preliminary scan on 2026-11-04 found:

- GitHub search for “workaholic”: about **300 repositories**, including
  unrelated active projects;
- GitHub user `workaholic` and organization `workaholic-app` already exist;
- PyPI names `workaholic`, `workaholic-core`, `workaholic-cli` and
  `workaholic-gtk` appeared **free** at that moment;
- “workaholic” is a common English word with a negative meaning (work
  addiction), which is not ideal for a healthy, broad work-management platform.

PyPI availability is not enough. Before public release we need:

- GitHub organization/repository availability;
- domain and social-handle check;
- trademark search in the relevant jurisdictions (INPI, USPTO, EUIPO as
  applicable);
- package-name search in other ecosystems;
- a legal review of the chosen name.

This is not legal advice.

## 5. What makes a good name

The name should:

- be pronounceable in Portuguese and English;
- be short enough for a terminal command;
- not sound like a security-only product;
- not imply surveillance, addiction or exploitation;
- work for artists, electricians, musicians, DJs and administrators;
- have low collision risk in GitHub, PyPI and trademark databases;
- be available as a domain/handle, if possible;
- not depend on the AUTOSEG niche.

## 6. Exploration shortlist

These are **exploration candidates**, not decisions. Availability must be
checked properly before use.

| Candidate | Why it might fit | Preliminary concern |
|---|---|---|
| **Officina** | Italian for workshop; broad craft/trades feeling; short and GNOME-ish; PyPI package names appeared free. | GitHub organization `officina` already exists; about 614 repositories in the quick search; not unique. Needs trademark/domain/Flathub check. |
| **Craftbase** | Craft/work base; broad; PyPI appeared free; few GitHub repositories in the quick scan. | Needs trademark/domain check. |
| **Jobsmith** | Artisan/smith metaphor; work + craft; PyPI appeared free. | Could sound like a job board. |
| **Workroom** | Neutral, collaborative, easy to say. | Common word; many GitHub repositories; PyPI free. |
| **Tradespace** | Trades + workspace; broad. | Needs collision/domain check. |

Other directions worth testing: `craftdesk`, `jobdeck`, `workdeck`.

### A promising split if Officina passes the checks

```text
workaholic          # engine CLI
officina            # generic GTK application
officina-gtk        # optional explicit GUI alias
autoseg             # security/automation flavor
```

This separates the engine, the generic app and the vertical flavor without
making `workaholic` ambiguous. It still needs proper trademark, domain,
Flathub and GitHub namespace verification before becoming a decision.

### Flatpak/Flathub app ID

`io.github.burtvadr.Officina` is a valid shape **if**:

- `burtvadr` is the GitHub account that controls the project;
- the project repository is reachable at `https://github.com/burtvadr/Officina`;
- the Metainfo/AppStream ID is exactly `io.github.burtvadr.Officina`;
- the name/icon do not violate trademarks.

Flathub **does not require GitHub**. It requires a unique reverse-DNS
application ID and control over the domain or code-hosting namespace used by
that ID. GitHub is only a convenient namespace.

Examples:

| App ID | What it commits you to |
|---|---|
| `io.github.burtvadr.Officina` | Project repository at `github.com/burtvadr/Officina`. |
| `io.gitlab.burtvadr.Officina` | Project repository at GitLab under the same namespace. |
| `page.codeberg.burtvadr.Officina` | Project repository at Codeberg. |
| `app.officina.Officina` | Control over the domain `officina.app`. |
| `dev.officina.Officina` | Control over the domain `officina.dev`. |
| `br.com.officina.Officina` | Control over the domain `officina.com.br`. |

Rules that matter:

- the domain portion is lowercase;
- the last component may be capitalized (`Officina`);
- the ID must match the Metainfo file exactly;
- Flathub may verify domain/repository control;
- renaming an app ID later is possible but conservative and needs re-review;
- `burtvadr` ties the app to a personal account. If the project becomes a team,
  a domain or organization namespace may be better from the start.

Flathub also requires a complete English localisation, a stable graphical app,
source builds, Metainfo, license and no trademark conflicts. Those are separate
gates from the app ID; the current Portuguese-only app is not ready for a
Flathub submission yet.


## 7. Recommendation for now

1. Keep **Workaholic** as the engine/prototype name.
2. Do **not** rename the engine or the CLI yet.
3. Choose the generic app/platform name as a separate decision, after proper
   availability and trademark checks.
4. Until then, document the intended CLI behavior:
   - `workaholic` = CLI;
   - `workaholic-gtk` = GUI;
   - no ambiguous symlink.
5. Keep **AUTOSEG** as the security/automation flavor name; it is a strong
   vertical brand and should not be renamed as part of this decision.

## 8. Open decisions

- Is Workaholic the engine name, the platform name, or only a codename?
- Does the generic app get its own name and CLI?
- Is `workaholic` a real installed entry point or only a developer alias?
- Do we want `workaholic gui` as a convenience command?
- Which name passes trademark/domain/package checks?
- Who approves the final name and branding?
