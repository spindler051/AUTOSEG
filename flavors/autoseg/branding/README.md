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

`icone.png` and `icone_devel.png` are served at `/icone.png` and resolved by
`officina/core/prestadores_ext.py` (MAIN/DEV selection) and
`officina/core/pdf_identidade.py` (PDF seal).
