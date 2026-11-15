#!/usr/bin/env python3
"""Offline customer-surface divergence report and explicit baseline management."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Run from the checkout root OR by absolute script path without installation.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from officina.surface.divergence import analyze, compare_baseline, render_report

BASELINE_PATH = 'flavors/autoseg/config/surface_divergence_baseline.json'
REPORT_PATH = 'docs/planning/SURFACE_DIVERGENCE_REPORT.md'


def _read_baseline(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f'Baseline missing: {path}')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Invalid baseline version')
    accepted = data.get('accepted')
    if not isinstance(accepted, list) or any(
            not isinstance(row, dict) or not isinstance(row.get('id'), str)
            or not isinstance(row.get('justification'), str) or not row['justification'].strip()
            for row in accepted):
        raise ValueError('Baseline must contain accepted IDs and justifications')
    ids = [row['id'] for row in accepted]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate baseline finding ID')
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument('--check', action='store_true', help='fail on new or disappeared findings')
    commands.add_argument('--write', action='store_true', help='regenerate deterministic Markdown report')
    commands.add_argument('--update-baseline', action='store_true', help='explicitly accept current findings')
    parser.add_argument('--root', type=Path, default=ROOT, help='checkout root (useful for isolated fixtures)')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    baseline_file = root / BASELINE_PATH
    report_file = root / REPORT_PATH
    try:
        baseline = (_read_baseline(baseline_file) if baseline_file.exists() else
                    {'version': 1, 'accepted': []})
        findings = analyze(root)
        highs = tuple(item.id for item in findings if item.severity == 'high')
        if args.update_baseline and highs:
            raise ValueError('HIGH findings cannot be baselined: ' + ', '.join(highs))
        if args.update_baseline:
            old = {row['id']: row['justification'] for row in baseline['accepted']}
            updated = {
                'version': 1,
                'accepted': [
                    {'id': finding.id, 'justification': old.get(finding.id,
                        f'Review required: {finding.kind} in {finding.action}/{finding.surface}.')}
                    for finding in sorted(findings, key=lambda f: f.id)
                ],
            }
            baseline_file.parent.mkdir(parents=True, exist_ok=True)
            baseline_file.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + '\n',
                                     encoding='utf-8')
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(render_report(findings, updated), encoding='utf-8')
            print(f'BASELINE UPDATED: {len(findings)} accepted IDs; report regenerated')
            return 0
        if not baseline_file.is_file():
            print(f'BASELINE MISSING: {baseline_file}', file=sys.stderr)
            return 1
        fresh, resolved = compare_baseline(findings, baseline)
        if args.check:
            if fresh or resolved:
                print('BASELINE DRIFT', file=sys.stderr)
                for ident in fresh:
                    print(f'NEW {ident}', file=sys.stderr)
                for ident in resolved:
                    print(f'RESOLVED {ident}', file=sys.stderr)
                return 1
            # A hand-edited accepted baseline must never hide a high finding.
            if highs:
                print('HIGH FINDINGS NOT BASELINEABLE: ' + ', '.join(highs), file=sys.stderr)
                return 1
            # Also prevent reporting obsolete findings in committed Markdown.
            if not report_file.is_file() or report_file.read_text(encoding='utf-8') != render_report(findings, baseline):
                print('REPORT STALE: run --write after reviewing baseline', file=sys.stderr)
                return 1
            print(f'CHECK OK: {len(findings)} baselined findings; report identical')
            return 0
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(render_report(findings, baseline), encoding='utf-8')
        print(f'REPORT WRITTEN: {len(findings)} findings; new={len(fresh)} resolved={len(resolved)}')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'DIVERGENCE ERROR: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
