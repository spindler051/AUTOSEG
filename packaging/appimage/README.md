# Empacotamento AppImage — rascunho

Este diretório prepara a distribuição Linux em AppImage. **Ainda não foi
validado em uma máquina limpa.** Trate como ponto de partida, não como
artefato pronto para clientes.

## Por que não é só copiar `gtk_app.py`

Um AppImage autônomo precisa levar:

- Python e a aplicação;
- PyGObject e as typelibs (`Gtk-4.0`, `Adw-1`, `Gdk-4.0`, `Gio-2.0` etc.);
- GTK4, libadwaita, GdkPixbuf, Pango, Cairo, gdk-pixbuf loaders e temas de
  ícones;
- `reportlab` (e Pillow), que hoje fica em `.vendor/` no Linux;
- arquivos do projeto (`web/`, `portal.js`, `flavors/autoseg/branding/logo.png`, `flavors/autoseg/branding/icone.png`,
  `versao.json`).

O PyInstaller coleta parte disso por meio dos hooks de `gi`, mas bibliotecas
nativas e dados do GTK precisam ser conferidos no AppDir.

## Pré-requisitos

```bash
python3 -m venv .venv-build
.venv-build/bin/pip install pyinstaller
# appimagetool: https://github.com/AppImage/appimagetool/releases
export PATH="$PWD:$PATH"   # se o appimagetool estiver na pasta atual
```

O script `build_appimage.sh` usa o `python3` do ambiente ativo. Se o
`reportlab` estiver instalado no sistema, não é necessário o `.vendor/`.

## Gerar

```bash
./packaging/appimage/build_appimage.sh
```

Saída esperada:

```
build/appimage/AUTOSEG-<versão>-x86_64.AppImage
```

## Teste antes de distribuir

```bash
chmod +x build/appimage/AUTOSEG-*.AppImage
./build/appimage/AUTOSEG-*.AppImage
# Em máquina sem FUSE:
APPIMAGE_EXTRACT_AND_RUN=1 ./build/appimage/AUTOSEG-*.AppImage
```

Teste em uma VM Ubuntu limpa, sem GTK4/libadwaita instalados. Verifique:

1. a janela abre e o tema Adwaita carrega;
2. ícones simbólicos aparecem;
3. os diálogos de arquivo abrem (portal XDG ou fallback);
4. PDF é gerado e aberto;
5. banco/PDFs/anexos ficam em `$AUTOSEG_BASE`, não dentro do AppImage;
6. os portais 8765/8766 iniciam e o navegador abre.

## Alternativa recomendada para GNOME

Para distribuição oficial no ecossistema GNOME, Flatpak costuma ser mais
adequado que AppImage porque o runtime já inclui GTK4/libadwaita e recebe
atualizações de segurança. O AppImage continua útil para uso rápido em
Linux sem instalação.

## Limitações conhecidas

- O script não assina o AppImage.
- Não há atualização automática.
- A coleta de bibliotecas nativas do GTK4/libadwaita precisa ser revisada.
- O AppImage não foi testado em macOS (macOS usa o lançador `.command`).
