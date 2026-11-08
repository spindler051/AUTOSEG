# AUTOSEG launchers

Atalhos de operação. A raiz do repositório tem apenas o comando `autoseg`:

```bash
./autoseg dev        # GTK em modo servidor DEV
./autoseg app        # GTK local
./autoseg app-web    # GTK + portais locais
./autoseg app-local  # GTK sem portas
./autoseg api        # API headless produção
./autoseg server     # API headless DEV (8766)
./autoseg site       # site DEV (8865/8866)
./autoseg site-prod  # site produção (8765/8766)
./autoseg stop       # para portais/túneis DEV
./autoseg check      # compila e valida o código
./autoseg paths      # mostra onde ficam banco e dados
./autoseg test       # suíte completa
```

Banco e dados ficam fora do repositório; ver `docs/operations/DATA_STORAGE.md`.

Os arquivos `.command` continuam aqui para uso direto no macOS.
