# Separação banco de produção × banco de teste

## Arquivos

| Arquivo | Uso |
|---|---|
| `dados.db` | produção, somente clientes/OS reais |
| `dados_teste/autoseg_teste.db` | teste, somente dados fictícios |
| `dados_remoto.db` | snapshot local somente leitura do banco do Mac |
| `AUTOSEG_BACKUPS_*` | backups e quarentena |

## Teste local

```bash
AUTOSEG_DEV=1 \
GESTAO_BANCO="$PWD/dados_teste/autoseg_teste.db" \
CLIENTE_PORT=8865 PRESTADOR_PORT=8866 \
python3 gtk_app.py
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
