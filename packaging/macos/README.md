# macOS — GTK4/libadwaita

O frontend GTK é o mesmo código de Linux. Não há uma cópia específica de UI
para macOS. O que muda fica nos lançadores e no empacotamento.

## Dependências

O lançador detecta MacPorts ou Homebrew e procura o Python que já tenha
PyGObject/GTK4.

MacPorts (Intel):

```bash
sudo port install gtk4 +quartz libadwaita py-gobject3 adwaita-icon-theme
```

Homebrew (quando disponível para a arquitetura):

```bash
brew install python3 gtk4 libadwaita pygobject3 adwaita-icon-theme
```

Depois:

```bash
./INICIAR_AUTOSEG_GTK.command
```

O lançador:

- procura `/opt/local/bin/python3.14`, `python3.13` e Homebrew;
- define `XDG_DATA_DIRS`/`GI_TYPELIB_PATH` para ícones e typelibs do MacPorts;
- usa `AUTOSEG_BASE` (padrão `~/gestaoservicos_MAIN`);
- cria `.venv-gtk` com `--system-site-packages` para enxergar o PyGObject do
  Homebrew;
- instala `reportlab`, `Pillow` e `PyYAML` no venv;
- copia `flavors/autoseg/config/completude.yaml` para a pasta de dados, se ainda não existir;
- executa `gtk_app.py`.

## Aparência

- **Fonte:** nenhuma família é forçada pelo app; o GTK usa a fonte padrão do
  macOS.
- **Ícones:** Adwaita (`adwaita-icon-theme` do Homebrew). O app usa nomes
  simbólicos do libadwaita, não ícones do KDE.
- **Claro/escuro:** o `Adw.StyleManager` fica em `DEFAULT`, seguindo a
  aparência do macOS em Tempo de execução → Aparência.
- **Logo:** `flavors/autoseg/branding/logo.png` e `flavors/autoseg/branding/icone.png` do projeto. No ambiente de desenvolvimento
  (`AUTOSEG_DEV=1`), o ícone usado é `icone_devel.png` para diferenciar
  visualmente o DEV do MAIN (selo dos PDFs, favicon dos portais e ícone da janela).

Não há código `if macOS` nas telas: cores, fontes, ícones e tamanhos vêm do
libadwaita e do sistema.

## App bundle (planejado)

Ainda não testado porque o Mac está desligado. O caminho recomendado é primeiro
validar o `.command`; depois empacotar com PyInstaller ou py2app.

O bundle precisa incluir:

- `gtk_app.py`, `gtk_comum.py`, `gtk_dialogos.py` e backend Python;
- `flavors/autoseg/config/completude.yaml`, `versao.json`, `logo.png`, `icone.png`;
- `web/` e `portal.js`;
- bibliotecas GTK4, libadwaita, GdkPixbuf, Pango, typelibs e temas de ícones;
- `reportlab`, Pillow e PyYAML no venv do bundle.

PyInstaller no macOS não é garantido para GTK4/PyGObject; testar em um Mac
limpo antes de distribuir. Assinatura/notarização também são necessárias para
abrir sem aviso do Gatekeeper.

## O que falta validar no Mac

- abertura do GTK no Quartz;
- fonte padrão do sistema;
- ícones Adwaita;
- modo claro/escuro automático;
- diálogos nativos de arquivo;
- impressão/PDF;
- abertura de PDFs e pastas no Finder;
- portais 8765/8766 e túnel SSH.
