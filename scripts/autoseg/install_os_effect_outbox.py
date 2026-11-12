"""Explicit DEV-only outbox migration, with a verified SQLite backup.

Usage (in a DEV checkout, never on production data):
    AUTOSEG_DEV=1 python scripts/autoseg/install_os_effect_outbox.py \
        --database /path/to/dev.db --backup /path/to/dev-before-outbox.db
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from officina.core import os_effect_outbox as outbox


def main(argv=None):
    parser = argparse.ArgumentParser(description='Install DEV-only OS effect outbox')
    parser.add_argument('--database', required=True)
    parser.add_argument('--backup', required=True)
    args = parser.parse_args(argv)
    if os.environ.get('AUTOSEG_DEV') != '1':
        parser.error('Migration is authorized only with AUTOSEG_DEV=1')
    source = Path(args.database).resolve()
    backup = Path(args.backup).resolve()
    if not source.is_file() or not source.stat().st_size:
        parser.error('DEV SQLite source does not exist')
    if source == backup or backup.exists():
        parser.error('Backup must be a new, different file')
    # Check the authorization surface before writing backup bytes.
    if any(part.lower() in ('gestaoservicos_main', 'autoseg_main')
           for part in source.parts):
        parser.error('Refusing a known MAIN database path')
    outbox.backup_database(source, backup)
    outbox.install(source)
    print(f'Outbox installed on DEV database. Verified backup: {backup}')


if __name__ == '__main__':
    main()
