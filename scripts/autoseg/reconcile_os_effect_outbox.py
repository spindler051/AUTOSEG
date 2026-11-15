"""DEV-only manual recovery of committed PDF/attachment outbox intents.

Intentionally never sends email. Operators reconcile unknown email outcomes
with the provider before submitting a distinct acknowledged manual operation.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from officina.core import os_effect_outbox as effects


def main(argv=None):
    parser = argparse.ArgumentParser(description='Recover DEV OS external files')
    parser.add_argument('--database', required=True)
    args = parser.parse_args(argv)
    if os.environ.get('AUTOSEG_DEV') != '1':
        parser.error('Recovery is authorized only with AUTOSEG_DEV=1')
    source = Path(args.database).resolve()
    if not source.is_file() or any(part.lower() in ('gestaoservicos_main', 'autoseg_main')
                                   for part in source.parts):
        parser.error('Not a permitted DEV database')
    processed = effects.dispatch_retryable(source)
    print(f'PDF/file operations reconciled: {len(processed)}. '
          'Email unknown states require manual provider verification.')


if __name__ == '__main__':
    main()
