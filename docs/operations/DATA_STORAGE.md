# Onde ficam banco, anexos e dados

O repositório guarda código, configuração versionada e documentação. **Banco,
anexos, PDFs, rascunhos, notas fiscais, logs e credenciais de teste ficam fora
do repositório.**

## Resumo por modo

| Modo | Linux | macOS | Windows |
| --- | --- | --- | --- |
| Servidor em produção | `/var/lib/autoseg` | `/Library/Application Support/AUTOSEG` | `%PROGRAMDATA%\AUTOSEG` |
| Servidor DEV | `~/.local/share/autoseg/server-dev` | `~/Library/Application Support/AUTOSEG/server-dev` | `%LOCALAPPDATA%\AUTOSEG\server-dev` |
| GTK local | `~/.local/share/autoseg/local` | `~/Library/Application Support/AUTOSEG/local` | `%LOCALAPPDATA%\AUTOSEG\local` |
| Dados do usuário | `~/.local/share/autoseg` | `~/Library/Application Support/AUTOSEG` | `%LOCALAPPDATA%\AUTOSEG` |

No Linux, `XDG_DATA_HOME` substitui `~/.local/share` quando definido.

## Banco de dados

- Servidor em produção: `<pasta do servidor>/dados.db`.
- Servidor DEV: `<pasta do servidor DEV>/dados_teste/autoseg_teste.db`.
- GTK local: `<pasta local>/dados.db`.

O banco é criado no primeiro uso, com permissão `600`. As pastas novas são
criadas com permissão `700`. O diretório do servidor precisa pertencer ao
usuário que executa o serviço.

## Configuração versionada x dados locais

| Conteúdo | Onde fica |
| --- | --- |
| Modelos, políticas e numeração padrão | `flavors/autoseg/config/` (Git) |
| `composicao.yaml` efetivo | `<pasta de dados do modo>/composicao.yaml` (fora do Git) |
| Preferência de conexão do GTK | `~/.config/autoseg/connection.json` |
| Configuração local do feedback com IA | `<dados do usuário>/feedback_ia.local.json` |
| Credenciais fictícias de DEV | `<pasta do servidor DEV>/dados_teste/CREDENCIAIS_FICTICIAS_DEV.txt` |
| Anexos, relatórios, rascunhos, notas e logs | subpastas da pasta de dados do modo |

> O Meu Auto Financeiro é um produto separado, com banco, login e túnel
> próprios em `~/AUTOSEG_MAF`. O bridge de empréstimos usa esse banco para
> exibir e operar os empréstimos no financeiro do prestador; ele não faz parte
> dos dados do AUTOSEG.

## Conferir os caminhos

```bash
./autoseg paths          # produção
AUTOSEG_DEV=1 ./autoseg paths
```

O comando não cria pastas nem abre o banco.

## Variáveis de ambiente

Precedência: variável específica > `AUTOSEG_BASE` > padrão do modo.

| Variável | Efeito |
| --- | --- |
| `AUTOSEG_USER_DATA` | raiz dos dados do usuário (local e servidor DEV) |
| `AUTOSEG_SERVER_DATA` | pasta do servidor |
| `AUTOSEG_LOCAL_DATA` | pasta do GTK local |
| `AUTOSEG_BASE` | pasta de dados efetiva; sobrepõe o padrão do modo |
| `GESTAO_BANCO` | caminho exato do arquivo SQLite |
| `AUTOSEG_COMPANY_CNPJ` | CNPJ exibido em PDFs e orçamentos; o padrão público é fictício |
| `AUTOSEG_WHATSAPP` | número comercial dos links `wa.me`; o padrão público é fictício |
| `AUTOSEG_DEV=1` | portas 8866 e banco `dados_teste/autoseg_teste.db` |

Exemplo para um servidor de teste rodando com o usuário comum:

```bash
AUTOSEG_DEV=1 AUTOSEG_SERVER_DATA="$HOME/autoseg-server" ./autoseg server
```

## Permissões no macOS (servidor em produção)

`/Library/Application Support/AUTOSEG` é uma pasta do sistema. Crie-a uma vez
com o usuário que vai executar o serviço:

```bash
sudo mkdir -p "/Library/Application Support/AUTOSEG"
sudo chown -R "$(id -un):staff" "/Library/Application Support/AUTOSEG"
chmod 700 "/Library/Application Support/AUTOSEG"
```

Se preferir não usar o caminho do sistema, defina `AUTOSEG_SERVER_DATA` para
uma pasta gravável. Não existe fallback para o repositório.

## Permissões no Linux (systemd)

Exemplo de unidade:

```ini
[Service]
User=autoseg
StateDirectory=autoseg
StateDirectoryMode=0700
Environment=AUTOSEG_SERVER_DATA=/var/lib/autoseg
ExecStart=/opt/autoseg/.venv/bin/python /opt/autoseg/flavors/autoseg/modules/servidor_backend.py --api
```

`StateDirectory=autoseg` cria `/var/lib/autoseg` com o dono correto. O serviço
não deve rodar como `root` quando `StateDirectory` já resolve a permissão.

## Backup e restauração

Backup mínimo: a pasta inteira do servidor (banco, `-wal`, `-shm`, anexos,
relatórios, notas e `composicao.yaml`). Para copiar o SQLite com segurança:

```bash
sqlite3 "/var/lib/autoseg/dados.db" ".backup '/backup/autoseg-dados.db'"
```

Depois copie as subpastas de anexos e documentos. Restaure com o servidor
parado. Os arquivos `*.db-wal` e `*.db-shm` pertencem ao banco e não devem ser
misturados com um backup antigo.

## Migração feita na DEV (2026-11-08)

O conteúdo que estava em `data/` na raiz foi movido para:

```text
~/Library/Application Support/AUTOSEG/server-dev/
  dados_teste/
  anexos_os/
  relatorios_pdf/
  rascunhos/
  notas_fiscais/
  logs/
  tuneis/ e tuneis_dev/
  composicao.yaml

~/Library/Application Support/AUTOSEG/
  feedback_ia.local.json
```

O banco do Meu Auto Financeiro não fica mais na pasta do AUTOSEG; o produto
separado usa `~/AUTOSEG_MAF/meu_auto_financeiro.db`.

A pasta `data/` deixou de existir. As entradas `data/` e `dados_teste/` no
`.gitignore` ficam como proteção contra recriação acidental.

## Dados legados da MAIN

O checkout `~/gestaoservicos_MAIN` continua intacto e **não é lido
automaticamente** pela nova pasta local. O banco de produção antigo
(`~/gestaoservicos_MAIN/dados.db`, 463 clientes e 23 OS em 2026-11-08) só deve
ser copiado para o modo local durante uma janela de migração, com o app
fechado.

Exemplo de cópia conservadora no macOS (a origem não é alterada):

```bash
ORIGEM="$HOME/gestaoservicos_MAIN"
DESTINO="$HOME/Library/Application Support/AUTOSEG/local"
mkdir -p "$DESTINO"
sqlite3 "$ORIGEM/dados.db" ".backup '$DESTINO/dados.db'"
rsync -a "$ORIGEM/anexos_os/" "$DESTINO/anexos_os/"
rsync -a "$ORIGEM/relatorios_pdf/" "$DESTINO/relatorios_pdf/"
rsync -a "$ORIGEM/notas_fiscais/" "$DESTINO/notas_fiscais/"
cp "$ORIGEM/composicao.yaml" "$ORIGEM/completude.yaml" "$DESTINO/"
chmod -R go-rwx "$DESTINO"
```

Para testar sem migrar, aponte o modo local para a pasta antiga apenas na
sessão:

```bash
AUTOSEG_BASE="$HOME/gestaoservicos_MAIN" ./autoseg app
```

Enquanto a cópia não for validada, mantenha o backup da MAIN e não apague a
origem.

## Identidade comercial no repositório público

O repositório público usa valores **fictícios** para CNPJ e WhatsApp:

- `AUTOSEG_COMPANY_CNPJ` padrão `12.345.678/0001-95`;
- `AUTOSEG_WHATSAPP` padrão `5500000000000`.

Cada instalação real deve definir essas variáveis no serviço, no Keychain ou no
arquivo de ambiente do deploy. Nunca grave o CNPJ/telefone real no código
versionado. Os PDFs e links de WhatsApp são gerados em runtime com o valor
configurado.

## Regra para novas telas e módulos

Todo caminho de dado novo deve vir de `officina/core/runtime_config.py`
(`base_dir()`, `server_data_dir()` ou `local_data_dir()`). Não use
`Path(__file__)` para gravar banco, anexo, log ou configuração de runtime.
