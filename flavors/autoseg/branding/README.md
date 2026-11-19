# AUTOSEG branding

| File | Use |
|---|---|
| `icone.png` | application icon (MAIN) — favicon, portal, PDF seal |
| `icone_devel.png` | same, for DEV (`AUTOSEG_DEV=1`) |
| `logo.png` | horizontal logo, used in PDFs and the portal header |
| `icone-readme.png` | 256×256 optimized icon for the README; not used by the app |

## Artwork

The current icon is **hand-made in Blender**, re-exported as
2048×2048 PNG on 2026-11-15. It replaces the previous hand-made render and the
earlier AI-generated icon, which were rejected on visual grounds.

The square banners exported in the same session are design assets, not this
horizontal `logo.png`; they stay outside the repository until a layout uses
them.

The Blender source is **intentionally not versioned**: `.blend`/`.blend1` are in
`.gitignore` because the file is large and binary. Keep the project with the
design assets outside the repository; only the exported PNGs belong here.

The canonical `icone.png`/`icone_devel.png` are **256×256** and `logo.png` is
**512 px wide**. Do not commit the 2048×2048 source exports here: the PDF
embeds the image at native resolution, so a 7 MB source makes every report
large and slow to download.

## Build generation

At build time, generate the size ladder from the external design source:

```bash
AUTOSEG_ICON_SOURCE=/home/desktop/Projects/projects/autoseg/icon \
  python3 scripts/autoseg/build_branding.py
```

The script writes `autoseg-1024.png`, `autoseg-512.png`, `autoseg-256.png`,
`autoseg-64.png` and the dev equivalents, plus the canonical `icone.png`,
`icone_devel.png` and a 512-wide `logo.png`. The source directory is not copied
into Git.

`icone.png` and `icone_devel.png` are served at `/icone.png` and resolved by
`officina/core/prestadores_ext.py` (MAIN/DEV selection) and
`officina/core/pdf_identidade.py` (PDF seal).
