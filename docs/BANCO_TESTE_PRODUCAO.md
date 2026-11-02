# Separação banco de produção × banco de teste

O banco do Mac (`~/gestaoservicos_MAIN/dados.db`) estava misturando registros
reais com registros de teste. A separação foi feita em arquivos distintos.

## Arquivos

| Arquivo | Uso |
|---|---|
| `dados.db` | produção, somente clientes/OS reais |
| `dados_teste/autoseg_teste.db` | teste, somente dados fictícios |
| `dados_remoto.db` | snapshot local somente leitura do banco do Mac |
| `AUTOSEG_BACKUPS_*` | backups e quarentena dos arquivos removidos |

## Teste local

```bash
AUTOSEG_DEV=1 \
GESTAO_BANCO="$PWD/dados_teste/autoseg_teste_limpo.db" \
CLIENTE_PORT=8865 PRESTADOR_PORT=8866 \
python3 gtk_app.py
```

O gerador `CRIAR_CADASTROS_FICTICIOS_DEV.py` cria nomes, CPFs/CNPJs e
prestadores fictícios. Não use esses dados fora de `AUTOSEG_DEV=1`.

## Limpeza do banco misto

O script `scripts/limpar_banco_misto.py` copia o banco bruto e remove apenas a
lista explícita de registros de teste. A origem nunca é alterada.

```bash
python3 scripts/limpar_banco_misto.py \
  --origem dados_misto.db \
  --destino dados_producao_limpa.db \
  --aplicar \
  --mover-arquivos \
  --quarentena backups/quarentena_limpeza
```

Registros removidos nesta revisão:

- clientes 2 (`Cond. Palermo`) e 4 (`pessoa da silva`);
- OS 1–9, 13 e 14; preservadas as OS reais 10, 11 e 12;
- usuários V9 1, 3 e 4; preservada Pricila (2);
- organizações V9 2 e 444; preservadas as demais;
- chamados V9 1, 2, 3, 4, 6 e 7; preservado o chamado 5;
- vínculos, notificações, eventos, anexos, PDFs, financeiro e estoque ligados
  aos registros acima.

Resultado: **460 clientes, 3 OS, 1 lançamento financeiro, 1 prestador, 443
organizações, 1 usuário V9, 1 chamado V9** e estoque operacional zerado.

## Revisão manual

O cliente **3 (Daniel)** foi mantido porque tem CPF válido e e-mail do
proprietário, mas não tem mais OS após a limpeza. Se for cadastro de teste,
remova-o manualmente com backup.

Também foi mantida uma única duplicidade de nome com CNPJs diferentes:
`CONDOMÍNIO EDIFÍCIO VILLA BELLA` (IDs 44 e 104). Como os CNPJs são distintos,
não foram mesclados automaticamente.

## Regra de ouro

Um único processo escreve em cada banco. Não aponte o SQLite para SSHFS, SMB
ou NFS. Para testar o banco do Mac ao vivo, use portais via túnel SSH ou o
snapshot `dados_remoto.db`; para escrita ao vivo no GTK, é necessária a API
HTTP.
