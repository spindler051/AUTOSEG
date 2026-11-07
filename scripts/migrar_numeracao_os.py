#!/usr/bin/env python3
"""Migrate legacy OS numbers to the configured numbering.

Default is dry-run. Use --apply to write; a backup is created first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from numeracao_migracao import ErroMigracao, migrar, planejar


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--apply', action='store_true',
                        help='grava a migração; sem isto é dry-run')
    parser.add_argument('--no-backup', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        relatorio = migrar(args.db, backup=not args.no_backup,
                           dry_run=not args.apply)
    except ErroMigracao as erro:
        print('ERRO:', erro, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
        return 0
    print('Migração de numeração —', relatorio['db'])
    if relatorio.get('ja_migrado'):
        print('Banco já migrado; nada a fazer.')
        return 0
    for item in relatorio['plano']:
        print(f"{item['id']:>4}  {item['antigo']:<12} -> {item['novo']}  ({item['dia']})")
    if not args.apply:
        print('Dry-run: nenhuma alteração gravada. Use --apply para aplicar.')
    else:
        print('Backup:', relatorio.get('backup') or '(desativado)')
        print('Migração aplicada.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
