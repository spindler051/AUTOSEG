# macOS — GTK4/libadwaita

O frontend GTK é o mesmo código de Linux. Não há uma cópia específica de UI
para macOS. O que muda fica nos lançadores e no empacotamento.

## Dependências

```bash
brew install python3 gtk4 libadwaita pygobject3 adwaita-icon-theme
```

Depois:

```bash
./INICIAR_AUTOSEG_GTK.command
```

O lançador:

- usa `AUTOSEG_BASE` (padrão `~/gestaoservicos_MAIN`);
- cria `.venv-gtk` com `--system-site-packages` para enxergar o PyGObject do
  Homebrew;
- instala `reportlab`, `Pillow` e `PyYAML` no venv;
- copia `completude.yaml` para a pasta de dados, se ainda não existir;
- executa `gtk_app.py`.

O Tkinter continua disponível apenas como fallback manual:

```bash
./INICIAR_AUTOSEG_TK.command
```

## Aparência

- **Fonte:** nenhuma família é forçada pelo app; o GTK usa a fonte padrão do
  macOS.
- **Ícones:** Adwaita (`adwaita-icon-theme` do Homebrew). O app usa nomes
  simbólicos do libadwaita, não ícones do KDE.
- **Claro/escuro:** o `Adw.StyleManager` fica em `DEFAULT`, seguindo a
  aparência do macOS em Tempo de execução → Aparência.
- **Logo:** `logo.png` e `icone.png` do projeto.

Não há código `if macOS` nas telas: cores, fontes, ícones e tamanhos vêm do
libadwaita e do sistema.

## App bundle (planejado)

Ainda não testado porque o Mac está desligado. O caminho recomendado é primeiro
validar o `.command`; depois empacotar com PyInstaller ou py2app.

O bundle precisa incluir:

- `gtk_app.py`, `gtk_comum.py`, `gtk_dialogos.py` e backend Python;
- `completude.yaml`, `versao.json`, `logo.png`, `icone.png`;
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
