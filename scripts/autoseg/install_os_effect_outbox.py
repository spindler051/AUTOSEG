"""Install, inspect or safely roll back the additive DEV outbox migration."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from officina.core import os_effect_outbox as outbox
from officina.core import prestadores_ext as ext
from officina.core import produtividade_os as prod


def main(argv=None):
    parser=argparse.ArgumentParser(description='Manage DEV-only OS effect outbox')
    parser.add_argument('--database',required=True)
    parser.add_argument('--backup')
    actions=parser.add_mutually_exclusive_group()
    actions.add_argument('--status',action='store_true')
    actions.add_argument('--rollback',action='store_true')
    args=parser.parse_args(argv)
    if os.environ.get('AUTOSEG_DEV')!='1':
        parser.error('Migration is authorized only with AUTOSEG_DEV=1')
    source=Path(args.database).resolve()
    if not source.is_file() or not source.stat().st_size:
        parser.error('DEV SQLite source does not exist')
    if any(part.lower() in ('gestaoservicos_main','autoseg_main')
           for part in source.parts):
        parser.error('Refusing a known MAIN database path')
    with ext.db(source) as c:
        present=outbox.installed(c)
        if present:
            rows=c.execute('''SELECT state,COUNT(*) FROM os_effect_outbox
                GROUP BY state''').fetchall()
            counts={state:count for state,count in rows}
        else:
            counts={}
    if args.status:
        print({'installed':present,'states':counts})
        return 0
    if args.rollback and not present:
        print('Outbox is already absent.')
        return 0
    if args.rollback and any(counts.get(state,0) for state in
                             ('pending','processing','unknown')):
        parser.error('DRAIN_OR_RECONCILE: pending, processing or unknown operations remain')
    if not args.backup:
        parser.error('A new verified backup is required for migration or rollback')
    backup=Path(args.backup).resolve()
    if source==backup or backup.exists():
        parser.error('Backup must be a new, different file')
    outbox.backup_database(source,backup)
    if args.rollback:
        with ext.db(source) as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='produtividade_email'").fetchone():
                rows=c.execute('SELECT os_id,destinatarios_json FROM produtividade_email').fetchall()
                references={'cliente','sindico','administradora'}
                for item in rows:
                    try:
                        addresses=json.loads(item['destinatarios_json'] or '[]')
                    except (TypeError,ValueError):
                        raise ValueError('Cannot roll back: invalid recipient projection.') from None
                    if not isinstance(addresses,list):
                        raise ValueError('Cannot roll back: invalid recipient projection.')
                    if any(not isinstance(value,str) or value in references
                           or not prod._email_validado(value) for value in addresses):
                        raise ValueError('Cannot roll back: recipient references require operational reconciliation.')
            for index in ('idx_os_effect_state','idx_os_effect_os',
                          'idx_os_effect_pdf_version'):
                c.execute('DROP INDEX IF EXISTS '+index)
            c.execute('DROP TABLE os_effect_outbox')
        print(f'DEV outbox removed; OS and attachments unchanged. Backup: {backup}')
    else:
        outbox.install(source)
        print(f'Outbox installed on DEV database. Verified backup: {backup}')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
