#!/usr/bin/env python3
"""Mostra onde ficam banco, dados e configuração do AUTOSEG.

Não cria pastas nem abre o banco: serve para conferir a resolução dos caminhos
antes de iniciar o servidor, o site ou o aplicativo GTK.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from officina.core import runtime_config


def main() -> int:
    dev = runtime_config.is_dev()
    user = runtime_config.user_data_dir()
    local = runtime_config.local_data_dir()
    server = runtime_config.server_data_dir()
    server_db = server / ('dados_teste/autoseg_teste.db' if dev else 'dados.db')
    overrides = [
        ('AUTOSEG_BASE', os.environ.get('AUTOSEG_BASE')),
        ('GESTAO_BANCO', os.environ.get('GESTAO_BANCO')),
        ('AUTOSEG_USER_DATA', os.environ.get('AUTOSEG_USER_DATA')),
        ('AUTOSEG_SERVER_DATA', os.environ.get('AUTOSEG_SERVER_DATA')),
        ('AUTOSEG_LOCAL_DATA', os.environ.get('AUTOSEG_LOCAL_DATA')),
    ]
    print(f'Modo: {"DEV" if dev else "produção"}')
    print(f'Dados do usuário:   {user}')
    print(f'Modo local (GTK):   {local}')
    print(f'Banco local:        {local / "dados.db"}')
    print(f'Servidor (padrão):  {server}')
    print(f'Banco do servidor:  {server_db}')
    print(f'Composição:         {server / "composicao.yaml"}')
    print('Configuração GTK:   ' + str(Path.home() / '.config' / 'autoseg' / 'connection.json'))
    ativos = [(nome, valor) for nome, valor in overrides if valor]
    if ativos:
        print('Variáveis de ambiente ativas:')
        for nome, valor in ativos:
            print(f'  {nome}={valor}')
    else:
        print('Nenhuma variável de caminho definida; usando os padrões acima.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
