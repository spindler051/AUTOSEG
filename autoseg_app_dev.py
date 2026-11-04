"""Bootstrap do AUTOSEG DEV.app (GTK4/libadwaita).

Aponta para a pasta de desenvolvimento (~/GestaoServicos_DEV), banco de teste
(dados_teste/autoseg_teste.db) e portas locais 8865/8866, isolado do MAIN.
"""
import os
import sys
from pathlib import Path

BASE = Path.home() / 'GestaoServicos_DEV'
os.environ['AUTOSEG_BASE'] = str(BASE)
os.environ['GESTAO_BANCO'] = str(BASE / 'dados_teste' / 'autoseg_teste.db')
os.environ['AUTOSEG_DEV'] = '1'
os.environ['CLIENTE_PORT'] = '8865'
os.environ['PRESTADOR_PORT'] = '8866'
os.environ['CLIENTE_BIND'] = '127.0.0.1'
os.environ['PRESTADOR_BIND'] = '127.0.0.1'

import autoseg_app  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(autoseg_app.main())
