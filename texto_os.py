"""Runtime-configurable free text carried by a service order.

The application does not assign a business meaning to this field. The label,
PDF section title and initial value live in ``texto_os.yaml`` so the same field
can hold warranty terms, payment conditions, a notice or any other note.
"""
from __future__ import annotations

import os
from pathlib import Path

PASTA_APP = Path(__file__).resolve().parent

PADRAO = {
    'versao': 1,
    'campo': {
        'rotulo': 'Texto adicional',
        'titulo_pdf': 'Texto adicional',
        'padrao': '',
        'ajuda': '',
    },
}


def _arquivo():
    base = os.environ.get('AUTOSEG_BASE')
    if base:
        candidato = Path(base).expanduser() / 'texto_os.yaml'
        if candidato.is_file():
            return candidato
    candidato = PASTA_APP / 'texto_os.yaml'
    return candidato if candidato.is_file() else None


def carregar():
    """Return a validated configuration, falling back to neutral defaults."""
    caminho = _arquivo()
    if caminho is None:
        return {'versao': 1, 'campo': dict(PADRAO['campo'])}
    try:
        import yaml
        dados = yaml.safe_load(caminho.read_text(encoding='utf-8'))
        if not isinstance(dados, dict) or dados.get('versao') != 1:
            raise ValueError('versao: 1 obrigatória')
        campo = dados.get('campo')
        if not isinstance(campo, dict):
            raise ValueError('campo deve ser um mapa')
        resultado = {}
        for chave, valor in PADRAO['campo'].items():
            texto = campo.get(chave, valor)
            if not isinstance(texto, str):
                raise ValueError(f'campo.{chave} deve ser texto')
            limite = 5000 if chave == 'padrao' else (500 if chave == 'ajuda' else 80)
            resultado[chave] = texto.strip()[:limite]
        return {'versao': 1, 'campo': resultado}
    except Exception as erro:
        print(f'texto_os.yaml inválido ({caminho}): {erro}; usando padrão.')
        return {'versao': 1, 'campo': dict(PADRAO['campo'])}


def rotulo() -> str:
    return carregar()['campo']['rotulo'] or PADRAO['campo']['rotulo']


def titulo_pdf() -> str:
    return carregar()['campo']['titulo_pdf'] or PADRAO['campo']['titulo_pdf']


def padrao() -> str:
    return carregar()['campo']['padrao']


def ajuda() -> str:
    return carregar()['campo']['ajuda']
