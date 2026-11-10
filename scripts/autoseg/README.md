# AUTOSEG launchers

Atalhos de operação. A raiz do repositório tem `autoseg` (MAIN) e
`autoseg-dev` (DEV).

## Comandos principais

```bash
# MAIN (produção local)
./autoseg start site      # site 8765/8766; a API vai embutida
./autoseg start server    # API 8766 separada; use com o site parado
./autoseg start tunnel    # túneis 8765/8766
./autoseg stop site
./autoseg stop server
./autoseg stop tunnel
./autoseg stop all
./autoseg status

./autoseg update main    # reinicia só a MAIN
./autoseg update dev     # reinicia só a DEV
./autoseg update         # MAIN e depois DEV

# DEV (dados fictícios)
./autoseg-dev start site      # site 8865/8866
./autoseg-dev start server    # API 8766; só com a MAIN parada
./autoseg-dev start tunnel    # túneis 8865/8866
./autoseg-dev stop site
./autoseg-dev stop server
./autoseg-dev stop tunnel
./autoseg-dev stop all
./autoseg-dev status
```

`start all` sobe o site e os túneis. `stop all` para túneis, site e server.
Os PIDs e logs ficam em `~/Library/Application Support/AUTOSEG/cli`.

`update` apenas reinicia processos: não faz pull, merge, migração nem altera
código. MAIN e DEV usam o mesmo checkout; use `./autoseg update main` para
validar a MAIN primeiro e `./autoseg update dev` depois. Atualizações isoladas
são permitidas.

## Compatibilidade

Os comandos antigos continuam funcionando:

```bash
./autoseg dev        # GTK em modo servidor DEV
./autoseg app        # GTK local
./autoseg app-web    # GTK + portais locais
./autoseg app-local  # GTK sem portas
./autoseg api        # API headless produção
./autoseg server     # API headless DEV (8766)
./autoseg site       # site DEV (8865/8866), em primeiro plano
./autoseg site-prod  # site produção (8765/8766), em primeiro plano
./autoseg stop       # para os túneis DEV
./autoseg check
./autoseg paths
./autoseg test
```

Banco e dados ficam fora do repositório; ver `docs/operations/DATA_STORAGE.md`.
