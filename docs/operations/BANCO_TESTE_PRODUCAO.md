# Separação banco de produção × banco de teste

## Arquivos

| Arquivo | Uso |
|---|---|
| `<servidor>/dados.db` | produção, somente clientes/OS reais |
| `<servidor DEV>/dados_teste/autoseg_teste.db` | teste, somente dados fictícios |
| `<local>/dados.db` | modo local do GTK |
| `dados_remoto.db` | snapshot local somente leitura do banco do Mac |
| `AUTOSEG_BACKUPS_*` | backups e quarentena |

Os caminhos completos dependem do sistema e do modo; rode `./autoseg paths`
para vê-los. Nada disso fica dentro do repositório.

## Teste local

```bash
./autoseg server   # terminal 1: banco de teste em dados_teste/
./autoseg dev      # terminal 2: GTK em modo servidor
```

O gerador `CRIAR_CADASTROS_FICTICIOS_DEV.py` cria nomes, CPFs/CNPJs e
prestadores fictícios. Não use esses dados fora de `AUTOSEG_DEV=1`.

## Limpeza de banco misto

`scripts/limpar_banco_misto.py` copia o banco de origem e remove apenas a lista
explícita de registros de teste. A origem nunca é alterada.

```bash
python3 scripts/limpar_banco_misto.py \
  --origem dados_misto.db \
  --destino dados_producao_limpa.db \
  --aplicar \
  --mover-arquivos \
  --quarentena backups/quarentena_limpeza
```

Antes de aplicar: backup, revisão da lista e conferência de OS/financeiro
preservados.

## Regra de ouro

Um único processo escreve em cada banco. Não aponte o SQLite para SSHFS, SMB
ou NFS. Para testar o banco do Mac ao vivo, use portais via túnel SSH ou o
snapshot `dados_remoto.db`; para escrita ao vivo no GTK, use a API HTTP.
