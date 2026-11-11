"""Bootstrap do AUTOSEG DEV.app (GTK4/libadwaita).

Aponta para a pasta local de DEV (<dados do usuário>/local/dev), com banco
próprio e porta local 8866, isolado do MAIN.
"""
import sys as _sys
from pathlib import Path as _Path
if __package__ in (None, ''):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))
import os
import sys
from pathlib import Path

from officina.core import runtime_config
BASE = runtime_config.local_data_dir() / 'dev'
os.environ['AUTOSEG_BASE'] = str(BASE)
os.environ['GESTAO_BANCO'] = str(BASE / 'dados.db')
os.environ['AUTOSEG_DEV'] = '1'
os.environ['PRESTADOR_PORT'] = '8866'
os.environ['PRESTADOR_BIND'] = '127.0.0.1'

from . import autoseg_app  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(autoseg_app.main())
