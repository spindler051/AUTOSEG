# AUTOSEG GTK4/libadwaita — Linux e macOS

Este documento descreve a interface desktop (`gtk_app.py`), que usa o
**mesmo backend**, o **mesmo banco SQLite** e as **mesmas regras** dos portais.
Não é um fork: nenhum módulo de regra de negócio foi duplicado para Linux ou
macOS.

- Branch de desenvolvimento: `develop`
- Versão vigente: `versao.json` (fonte única)
- Backend compartilhado: `banco.py`, `cadastros_v9.py`, `prestadores_ext.py`,
  `fluxo_os.py`, `atendimento_os.py`, `estoque_materiais.py`,
  `catalogo_servicos.py`, `portal_negocios.py`, `client_web.py`,
  `portal_prestador.py`
- Frontend desktop: `gtk_app.py` — GTK4 + libadwaita. O frontend Tkinter foi
  removido do código.

> A captura de tela do painel não é publicada no repositório público para
> evitar qualquer dado operacional. Gere uma captura local com dados fictícios
> se precisar ilustrar a documentação.

## Princípio de convivência

Há um único frontend desktop (GTK). Os portais do cliente e do prestador usam
portas fixas e o mesmo SQLite. Recursos novos entram no backend primeiro e
ficam disponíveis para o GTK, o portal do cliente e o portal do prestador.

Variáveis úteis:

| Variável | Efeito |
|---|---|
| `AUTOSEG_BASE` | pasta de dados (banco, anexos, PDFs, rascunhos). Modo local: `~/Library/Application Support/AUTOSEG/local` (macOS) ou `~/.local/share/autoseg/local` (Linux). Servidor: pasta do sistema |
| `GESTAO_BANCO` | caminho explícito do SQLite; tem prioridade sobre `AUTOSEG_BASE` |
| `PRESTADOR_PORT` / `PRESTADOR_BIND` | site único Officina Web (padrão 8766 / 127.0.0.1). Use `PRESTADOR_BIND=0.0.0.0` para a rede local |
| `AUTOSEG_DEV=1` | porta 8866, banco de teste e túneis de desenvolvimento |
| `GTK_USE_PORTAL=0` | evita a espera de ~25 s do portal XDG em ambientes sem sessão gráfica completa |
| `AUTOSEG_SMOKE=1` | abre e fecha a janela em 3 s; usado em teste de fumaça |

## Código compartilhado × específico de plataforma

Prioridade: **um único frontend GTK** e um único backend. Nada de `if macOS`
dentro das telas, validações, banco ou regras.

| Compartilhado | Específico |
|---|---|
| `gtk_app.py`, `gtk_dialogos.py`, `gtk_comum.py` | `INICIAR_AUTOSEG_GTK.command` (macOS) |
| `completude.py`, validações, banco, PDF, e-mail | `ABRIR_NO_DRM.sh` (Linux/VM) |
| `servidor_backend.py`, portais, scripts | `packaging/appimage/`, `packaging/macos/` |
| temas, claro/escuro e ícones via libadwaita | instalação de dependências do SO |

O app não define família de fonte. No macOS, o GTK usa a fonte padrão do
sistema; no Linux, a fonte configurada no desktop. O `Adw.StyleManager` fica
em `DEFAULT`, então claro/escuro segue o sistema. Os ícones são nomes
simbólicos Adwaita resolvidos pelo tema; não há ícones KDE no código.

O `./autoseg app` delega ao GTK. Não existe mais fallback Tkinter.

## Trabalho em equipe Linux + macOS

- O código é um só: `develop` (ou uma branch de feature no mesmo repositório).
  Não há fork de backend nem cópia de regras por sistema.
- Cada desenvolvedor usa um banco local. **Não** coloque o mesmo `dados.db`
  em pasta de rede/Dropbox/iCloud: SQLite com WAL não é seguro para escrita
  concorrente entre máquinas.
- Para trocar massa de teste, use o gerador fictício
  `CRIAR_CADASTROS_FICTICIOS_DEV.py`; ele é bloqueado fora de `dados_teste/`.
- Cada máquina tem sua pasta de dados local; o macOS usa
  `~/Library/Application Support/AUTOSEG/local` e o Linux usa
  `~/.local/share/autoseg/local`. `AUTOSEG_BASE` pode apontar para outra pasta.

## Linux

### Dependências

Requisitos mínimos: GTK >= 4.10, libadwaita >= 1.5 (por causa de `Adw.Dialog`/`Adw.AlertDialog`) e PyGObject >= 3.42.

Em Ubuntu/Debian com GTK4 e libadwaita instalados:

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
  libgtk-4-1 libadwaita-1-0 python3-pil
```

O `reportlab` é usado apenas para gerar PDFs. Neste ambiente ele foi extraído
do pacote `python3-reportlab` para `.vendor/` (sem `sudo`). Em uma instalação
normal:

```bash
python3 -m pip install --user 'reportlab>=4.2,<5' 'pillow>=10,<13' 'PyYAML>=6,<7'
```

O `gtk_comum.py` adiciona `.vendor/usr/lib/python3/dist-packages` ao
`sys.path` quando essa pasta existe.

### Executar direto

```bash
./autoseg app
```

### Executar no display da VM, sem Xvfb/Xwayland

```bash
./scripts/autoseg/ABRIR_NO_DRM.sh
```

Esse é o caminho nativo: `cage` usa DRM (`/dev/dri/card1`), o VT ativo e
libinput (`WLR_BACKENDS=drm,libinput`); o `gtk_app.py` roda como cliente
**Wayland**. Não há Xvfb nem
Xwayland no meio. O script usa `sudo` para aplicar ACLs em DRM, VT, seatd e
dispositivos de entrada; em uma VM isso é aceitável, mas as ACLs podem ser
perdidas após reiniciar.

Para conferir que o app está em Wayland:

```bash
# dentro de outro terminal, com o Cage em execução
ls -l "$XDG_RUNTIME_DIR"/wayland-*
grim /tmp/autoseg.png   # screenshot Wayland nativo
```

> O `grim` é opcional; foi usado apenas para validar o display.

### Teste de fumaça

```bash
AUTOSEG_SMOKE=1 python3 gtk_app.py
```

Para testar com dados fictícios no modo servidor:

```bash
./autoseg server    # terminal 1
./autoseg dev       # terminal 2
./autoseg paths     # confira banco e dados efetivos
```

O app DEV não abre o banco local. Sem o servidor, as listas ficam vazias e a
janela mostra o aviso de servidor indisponível.

## macOS

O GTK4 e o libadwaita são multiplataforma. A mesma árvore e o mesmo
`gtk_app.py` rodam no macOS; não há código de negócio específico de Linux.

```bash
# MacPorts (Intel)
sudo port install gtk4 +quartz libadwaita py-gobject3 adwaita-icon-theme
# ou Homebrew, quando disponível para a arquitetura
brew install python3 gtk4 libadwaita pygobject3 adwaita-icon-theme

./autoseg app
```

O lançador encontra o Python com GTK4/PyGObject, cria `.venv-gtk`, instala
reportlab/Pillow/PyYAML e configura `XDG_DATA_DIRS`/`GI_TYPELIB_PATH` para os
prefixos do MacPorts/Homebrew.

O lançador `.command` usa a pasta local do usuário para que banco, PDFs,
anexos e rascunhos fiquem fora do bundle e possam ser backupeados. O caminho
padrão é `~/Library/Application Support/AUTOSEG/local`; confira com
`./autoseg paths`. O app usa `Gtk.UriLauncher` para abrir PDFs,
pastas e URLs no aplicativo padrão do macOS.

Não há Cage no macOS: a janela é nativa. O frontend Tkinter foi removido.

### Status validado no macOS (02/11/2026)

- MacPorts 2.12.7 com `gtk4 4.22.4 +quartz`, `libadwaita 1.9.3`,
  `py313-gobject3` e `adwaita-icon-theme`.
- `/opt/local/bin/python3.13` importa GTK 4.22 e Adw; o `python3.14` do
  MacPorts ainda não tem `gi`, e o lançador cai automaticamente para o 3.13.
- `.venv-gtk` criado em `~/GestaoServicos_DEV` e `~/gestaoservicos_MAIN`;
  ambos importam GTK/Adw e têm reportlab/Pillow/PyYAML.
- Teste de fumaça com o banco de teste e com um snapshot da produção: exit 0.
- Diálogo de cliente exercitado no GTK do Mac: listou 10 clientes, editou um
  (versão 2) e criou outro (total 11) usando o adaptador Workaholic.
- Render offscreen das telas Início, Clientes, OS, Financeiro e Catálogo:
  fonte `.AppleSystemUIFont 12`, tema de ícones Adwaita, modo escuro do
  sistema e todos os ícones usados presentes.
- PDF gerado no Mac com reportlab: `%PDF-` válido, 2,8 KB.
- Registro histórico de produção anterior à P0 em `~/gestaoservicos_MAIN`,
  460 clientes e 3 OS. O backend antigo (`servidor_backend.py`) foi encerrado.
- Pendente: conferir a janela no desktop após desbloquear a tela e exercitar
  os diálogos nativos de arquivo. A validação acima foi feita por render
  offscreen porque a tela do Mac estava bloqueada.

## Teste remoto com o macOS

O código é o mesmo; o banco fica no Mac. Há dois modos seguros:

### Portais ao vivo via túnel SSH

No Mac, com o repositório DEV e o banco do servidor DEV:

```bash
cd ~/GestaoServicos_DEV
./autoseg server
```

Se estiver usando dados legados da MAIN, mantenha o `AUTOSEG_BASE` e o
`GESTAO_BANCO` antigos **somente durante a janela de migração**; o padrão novo
não lê mais `~/gestaoservicos_MAIN`.

No Linux:

```bash
./scripts/tunel_mac.sh
# site único: http://127.0.0.1:8766
```

Isso usa os dados ao vivo e permite escrita nos portais. A interface GTK
local continua usando o banco local.

### Snapshot somente leitura para a interface GTK

```bash
./scripts/sincronizar_db_mac.sh
GESTAO_BANCO="$HOME/autoseg/dados_remoto.db" python3 gtk_app.py
```

O script usa `sqlite3 .backup` no Mac, então o snapshot é consistente. Ele não
é atualizado automaticamente; rode de novo antes de testar. Escritas feitas no
GTK local ficam no snapshot e **não** voltam para o Mac.

### O que não fazer

Não aponte `GESTAO_BANCO` para SSHFS/SMB/NFS. SQLite com WAL não é seguro em
sistema de arquivos de rede. Para o frontend GTK escrever no banco do Mac em
tempo real, o caminho correto é separar um backend HTTP (API) do frontend; isso ainda
não está implementado no app atual.

## AppImage

O empacotamento está preparado em `packaging/appimage/` e documentado em
`packaging/appimage/README.md`. O script é um **rascunho funcional** de
PyInstaller + AppImage; ele precisa ser validado em uma VM Ubuntu limpa,
porque GTK4/libadwaita, typelibs, loaders do GdkPixbuf e bibliotecas nativas
precisam ser incluídos no AppDir.

## Validação de CPF/CNPJ

A validação é local e matemática, sem serviço de identidade:

- CPF: 11 dígitos, bloqueio de sequências repetidas e dois dígitos
  verificadores;
- CNPJ: 14 dígitos, mesmo bloqueio e dois verificadores;
- o documento é salvo sem pontuação;
- duplicidade de CPF/CNPJ em outro cliente é bloqueada;
- o GTK mostra aviso em tempo real e o backend do portal também valida antes
  de gravar;
- cadastros antigos com documento inválido continuam editáveis enquanto o
  documento não for alterado;
- CPF/CNPJ vazio continua permitido no cadastro (validação só quando informado).

Isso não confirma que o documento existe ou pertence à pessoa. CNPJ
alfanumérico ainda não é suportado porque o campo/banco atuais trabalham com
dígitos.

## Mínimo configurável de cliente e OS

O arquivo `completude.yaml` define os campos mínimos para um cliente ou OS
não ser marcado como **Incompletos**. Ele é relido a cada salvamento; veja
`docs/COMPLETUDE.md`.

## Importação e modelos YAML

O GTK importa YAML para **pré-preencher** formulários; nada é gravado sem o
botão de salvar e sem as validações normais.

- **Clientes → Importar YAML**: abre o cadastro preenchido para revisão.
- **Ordens de serviço → Importar YAML**: abre uma OS nova preenchida;
  o cliente é localizado por `cliente_id` ou `cliente_documento`.
- **Materiais e estoque → Importar YAML**: lote de produtos para revisão.
- **OS → Materiais YAML**: adiciona itens à lista de materiais da OS.

Cada tela tem **Modelo YAML**, que salva um arquivo vazio para preencher. O
modelo de OS aceita:

```yaml
versao: 1
ordem_servico:
  cliente_id: 123
  cliente_documento: ""
  tecnico: ""
  descricao: ""
  forma_pagamento: PIX
  mao_obra: 0
  observacoes: ""
  urgencia: Normal
  materiais: []
```

Regras: `versao: 1`, UTF-8, até 64 KB, sem aliases/âncoras YAML. A importação
não ignora CPF/CNPJ, duplicidade, limite de materiais nem validação de OS.

## OS com dados incompletos

A OS pode ser salva sem a descrição do serviço. Nesse caso ela recebe
`dados_incompletos=1`, aparece com a coluna **Dados = Incompletos** e não pode
ser encerrada até a descrição ser preenchida. O banco recebe a coluna por
migração aditiva (`banco.criar_banco`), sem apagar OS existentes.

## Aparência do sistema (fora do app)

O app não tem seletor de tema claro/escuro nem de cor de destaque. Ele segue o
sistema. No Linux/GTK4:

```bash
gsettings set org.gnome.desktop.interface icon-theme 'Adwaita'
gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita'
gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'
gsettings set org.gnome.desktop.interface accent-color 'purple'
```

Para remover as cores do Breeze/KDE que sobrescreviam o GTK4, o arquivo
`~/.config/gtk-4.0/settings.ini` deve ter:

```ini
gtk-application-prefer-dark-theme=true
gtk-icon-theme-name=Adwaita
gtk-theme-name=Adwaita
```

E o `~/.config/gtk-4.0/gtk.css` do usuário pode fixar o roxo do GNOME quando o
libadwaita da distribuição não aplica `accent-color` sozinho:

```css
@define-color accent_bg_color #9141ac;
@define-color accent_fg_color #ffffff;
@define-color accent_color #c061cb;
```

Isso é configuração de sistema/usuário, não do AUTOSEG.

> **Planejado:** um seletor explícito de tema claro/escuro no app e no portal
> web, com preferência do sistema + opção manual. A direção multicliente e os
> limites estão em `docs/planning/VISAO_MULTICLIENTE_LOCAL_FIRST.md`.

## Normas GNOME

A Human Interface Guidelines é baixada para `docs/gnome-hig/` (espelho
estático de `developer.gnome.org/hig/`, incluindo `index.html`). A pasta não é
versionada; reproduza com:

```bash
./docs/baixar_gnome_hig.sh
```

Mapeamento usado no app:

| Norma | Uso |
|---|---|
| `Adw.NavigationSplitView` | navegação lateral adaptativa com conteúdo |
| `Adw.HeaderBar` | título e menu principal |
| `Adw.PreferencesPage` / `PreferencesGroup` | formulários e grupos de campos |
| `Adw.PreferencesDialog` / `Adw.Dialog` | cadastros em diálogo |
| `Adw.ActionRow` | status, links, contadores e ações |
| `Adw.AlertDialog` | confirmações destrutivas |
| `Adw.ToastOverlay` | feedback de salvar, PDF e portais |
| `Gtk.ColumnView` | tabelas de clientes, OS, financeiro, estoque etc. |
| `Gtk.SearchEntry` | pesquisa nas listas |
| `Adw.Clamp` | largura máxima do painel |
| `Adw.ViewStack` + `ViewSwitcherBar` | abas de chamados e organizações |
| `Gtk.CssProvider` | apenas espaçamento/raio de cartões; cores do tema do sistema |

Não foi recriado o tema preto/amarelo do app anterior: o app usa as cores do
libadwaita, o modo claro/escuro do sistema e as classes de status
(`.success`, `.warning`, `.error`, `.accent`).

## Evolução futura

Plano de modularização e deploy (sem mudanças de código):
`docs/archive/PLANO_EVOLUCAO_ARQUITETURA.md` (histórico).

## Limitações conhecidas

- O AppImage ainda não foi construído nem testado em máquina limpa.
- O cursor de hardware de GPUs virtuais pode exigir `WLR_NO_HARDWARE_CURSORS=1`
  (já aplicado em `ABRIR_NO_DRM.sh`).
- O macOS não foi testado neste ambiente (sem hardware macOS).
- O envio real de e-mail/nota fiscal continua fora do escopo: o desktop gera
  rascunhos, como no app anterior.
- O portal do cliente e o do prestador continuam sendo aplicações web; o app
  GTK só os inicia, monitora e abre no navegador.
