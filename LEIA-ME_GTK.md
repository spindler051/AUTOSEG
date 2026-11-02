# AUTOSEG — interface GTK4/libadwaita

O frontend novo está em `gtk_app.py` e compartilha o mesmo backend, banco e
regras do app Tkinter e dos portais. Não é um fork.

- Linux: `./INICIAR_AUTOSEG_GTK.sh`
- Linux no display da VM (Wayland/DRM, sem Xwayland): `./ABRIR_NO_DRM.sh`
- macOS: `./INICIAR_AUTOSEG_GTK.command` (veja os requisitos do Homebrew)
- Guia completo em português: `docs/GTK4_LINUX_MACOS.md`
- Normas GNOME baixadas: `docs/gnome-hig/index.html`
- Rascunho de AppImage: `packaging/appimage/README.md`

Variáveis principais: `AUTOSEG_BASE`, `GESTAO_BANCO`, `CLIENTE_PORT`,
`PRESTADOR_PORT`, `AUTOSEG_DEV`.
