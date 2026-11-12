"""DEV-only inspection and recovery dispatcher for committed OS effects."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from officina.core import os_effect_outbox as effects
from officina.core import prestadores_ext as ext


def summary(database):
    with ext.db(database) as c:
        effects.require_installed(c)
        rows=c.execute('''SELECT effect_type,state,COUNT(*) AS count,MIN(created_at) AS oldest,
            MAX(attempts) AS attempts FROM os_effect_outbox
            GROUP BY effect_type,state ORDER BY effect_type,state''').fetchall()
        pending=c.execute('''SELECT MIN(created_at) AS oldest FROM os_effect_outbox
            WHERE state IN ('pending','failed')''').fetchone()
        errors=c.execute('''SELECT operation_key,effect_type,action,state,attempts,last_error
            FROM os_effect_outbox WHERE last_error!='' ORDER BY updated_at DESC LIMIT 10''').fetchall()
    return {'states':[dict(r) for r in rows],
            'oldest_pending':pending['oldest'],
            'last_errors':[dict(r) for r in errors]}


def run_once(database, *, limit=100, reconcile_only=False, dry_run=False):
    if limit <= 0 or limit > 1000: raise ValueError('Limit must be between 1 and 1000.')
    with ext.db(database) as c:
        effects.require_installed(c)
        rows=c.execute('''SELECT operation_key,effect_type,state,attempts
            FROM os_effect_outbox WHERE state IN ('pending','failed','processing')
            ORDER BY id LIMIT ?''',(limit,)).fetchall()
    if dry_run:
        return [{'operation_key':r['operation_key'],'effect_type':r['effect_type'],
                 'action':'would_inspect','state':r['state']} for r in rows]
    # Reconciliation expires processing email as unknown before any claim.
    keys=set(effects.reconcile(database))
    results=[]
    for row in rows:
        operation=row['operation_key']
        if operation not in keys: continue
        kind=row['effect_type']
        if kind=='email' and (reconcile_only or (row['state']=='processing') or
                              row['attempts']):
            continue
        try:
            if kind=='pdf':
                result=effects.publish_pdf(database,operation)
            elif kind=='file':
                result=effects.publish_file(database,operation)
            else:
                from flavors.autoseg.modules import gmail_service
                result=effects.deliver_email(database,operation,
                    lambda oid,key: gmail_service.enviar_operacao_outbox(database,oid,key))
            status=result['state'] if result else 'skipped'
        except Exception as error:
            status=effects.get(database,operation)['state']
            results.append({'operation_key':operation,'effect_type':kind,
                            'action':'dispatch','state':status,
                            'error_code':type(error).__name__})
            continue
        results.append({'operation_key':operation,'effect_type':kind,
                        'action':'dispatch','state':status})
    return results


def main(argv=None):
    parser=argparse.ArgumentParser(description='DEV-only OS outbox dispatcher')
    parser.add_argument('--database',required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--status',action='store_true')
    mode.add_argument('--once',action='store_true')
    mode.add_argument('--reconcile',action='store_true')
    mode.add_argument('--cleanup-stages',action='store_true')
    mode.add_argument('--cleanup-trash',action='store_true')
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--minimum-age',type=int,default=3600,
                        help='Minimum age in seconds for explicit orphan cleanup (default 3600)')
    args=parser.parse_args(argv)
    if args.minimum_age < 0:
        parser.error('Minimum age must be non-negative')
    if args.minimum_age != 3600 and not (args.cleanup_stages or args.cleanup_trash):
        parser.error('--minimum-age applies only to cleanup operations')
    if os.environ.get('AUTOSEG_DEV')!='1':
        parser.error('Dispatcher is DEV-only')
    database=Path(args.database).resolve()
    if (not database.is_file() or any(part.lower() in ('gestaoservicos_main','autoseg_main')
                                      for part in database.parts)):
        parser.error('Invalid DEV database')
    try:
        if args.status:
            output=summary(database)
        elif args.once or args.reconcile:
            output=run_once(database,limit=args.limit,reconcile_only=args.reconcile,
                            dry_run=args.dry_run)
        elif args.dry_run:
            output={'dry_run':True,'action':'cleanup'}
        else:
            roots=(ext.ANEXOS,ext.NOTAS)
            cleanup=(effects.cleanup_orphan_stages if args.cleanup_stages
                     else effects.cleanup_orphan_trash)
            output={'removed_or_restored':sum(cleanup(database,root,minimum_age=args.minimum_age)
                                              for root in roots)}
    except (ValueError,RuntimeError,FileNotFoundError) as error:
        output={'error_code':type(error).__name__}
        print(json.dumps(output,sort_keys=True))
        return 2
    if args.json:
        print(json.dumps(output,sort_keys=True))
    else:
        print(output)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
