# Relative file storage

**Status:** planning, priority P1. No code, no schema change.
**Trigger:** two relocations in one day — macOS → nura, and `/home/beyond1lte` →
`/home/s10` — each requiring a manual `UPDATE` over every stored path.

## 1. The problem

The database stores **absolute paths** for files:

| Table | Column | Rows today |
|---|---|---|
| `os_anexos` | `caminho` | 80 |
| `os_documentos` | `caminho` | 70 |
| `os_notas_fiscais` | `caminho` | 13 |

`163` rows, each pointing at a full filesystem path. Consequences:

- moving the data root, renaming the OS user, restoring on another machine or
  changing the disk layout requires a SQL rewrite and a file-verification pass;
- a wrong remap silently produces dangling rows (`missing files`), or worse,
  serves a file that happens to exist at the new path;
- backups carry paths that are valid only on the machine that produced them.

The runtime root is already configurable (`AUTOSEG_BASE`, `GESTAO_BANCO`,
`MEU_AUTO_FINANCEIRO_DB`). The coupling is in the stored values, not the config.

## 2. Target

```text
DB:      anexos_os/2026/foo.jpg        (relative to the data root)
docs:    relatorios_pdf/261114001_relatorio_v3.pdf
fiscal:  notas_fiscais/nf-123.pdf
runtime: resolve against AUTOSEG_BASE at read time
unit:    WorkingDirectory=/srv/autoseg   (no username anywhere)
```

- the data root is neutral (`/srv/autoseg` or `/var/lib/autoseg`), never a home
  directory;
- `$HOME` is not used in service units: `%h` in a system unit expands to the
  manager's home (`/root`), not the service user's, and `EnvironmentFile` does
  not expand `~`;
- the path a consumer sees is still an absolute path — resolution happens at the
  boundary, not in the database.

## 3. Resolver

One function, used by every reader and writer:

```text
resolve_file_path(value) -> Path
  - if value is absolute and inside AUTOSEG_BASE: keep (legacy rows)
  - if value is relative: join with AUTOSEG_BASE
  - reject absolute paths outside AUTOSEG_BASE
  - reject '..' segments and empty values
```

Properties:

- **containment is preserved.** The existing check in `read_anexo`
  (`is_relative_to(ext.ANEXOS)`) must keep working; the resolver is not a
  replacement for it;
- legacy absolute rows keep working during and after the migration;
- writes always produce relative values.

## 4. Migration

1. Add the resolver and use it on read paths only; no write change yet.
2. Migrate a **copy** of the database: rewrite `AUTOSEG_BASE`-prefixed values to
   relative, then verify every resulting file exists and hashes match where a
   hash column exists.
3. Enable relative writes on the writers (attachment, PDF publication, invoice).
4. Run both modes in shadow: after a write, resolve and confirm equality with
   the legacy behaviour.
5. Cut over, keep the legacy absolute handling for old rows indefinitely.

No row may be rewritten in place without a verified copy.

## 5. Tests

- resolve: relative, absolute-in-root, absolute-outside-root, `..`, empty, symlink
  pointing outside the root;
- read path: legacy absolute row and relative row return the same bytes;
- write path: new rows are relative;
- migration: row count before/after equal, zero missing files, hashes unchanged;
- traversal: `../../etc/passwd` is rejected in both forms.

## 6. Non-goals

- no change to the storage layout of the files themselves;
- no rename of the current directories during this item;
- no schema migration in the same step as the read resolver;
- no touch to MAF, which stores its own receipts separately.

## 7. Open questions

1. Neutral root: `/srv/autoseg` now, or after a dedicated disk/partition exists?
2. Do we keep supporting old absolute rows forever, or time-box them?
3. Should the resolver be shared with MAF (`officina/core` vs its own tree)?
4. What happens to attachment URLs that embed absolute paths anywhere? (grep
   before cutover)
