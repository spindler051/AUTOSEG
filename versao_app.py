"""Leitura única da versão em execução (bundle e pasta MAIN/DEV)."""
import json
import os
from pathlib import Path


def versao_local(padrao='9.6.0-dev.6'):
    candidatos = []
    base_env = os.environ.get('AUTOSEG_BASE')
    if base_env:
        candidatos.append(Path(base_env).expanduser())
    candidatos.append(Path(__file__).resolve().parent)
    if os.environ.get('AUTOSEG_BASE'):
        candidatos.append(Path.home() / 'gestaoservicos_MAIN')
    for base in candidatos:
        try:
            dados = json.loads((base / 'versao.json').read_text(encoding='utf-8'))
            versao = str(dados.get('versao') or '').strip()
            if versao:
                return versao
        except (OSError, ValueError, TypeError):
            continue
    return padrao
