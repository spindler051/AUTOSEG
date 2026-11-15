#!/usr/bin/env python3
"""Check one provider section registry and GTK/Web adapter parity."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from flavors.autoseg.modules.autoseg_web_navigation import ITEMS

ROOT = Path(__file__).resolve().parent.parent


def findings():
    issues = []
    keys = set()
    provider_order = set()
    provider_gtk = set()
    for item in ITEMS:
        if item.id in keys:
            issues.append(f'Duplicate item id: {item.id}')
        keys.add(item.id)
        if not item.surfaces or not set(item.surfaces) <= {'web', 'gtk'}:
            issues.append(f'Invalid surfaces: {item.id}')
        if item.surfaces != ('web','gtk') and not item.surface_reason:
            issues.append(f'Missing exception reason: {item.id}')
        if 'web' in item.surfaces and not item.href:
            issues.append(f'Missing web route: {item.id}')
        if 'gtk' in item.surfaces and not item.gtk_page:
            issues.append(f'Missing GTK page: {item.id}')
        if 'provider' in item.contexts:
            if 'gtk' in item.surfaces:
                if item.gtk_page in provider_gtk:
                    issues.append(f'Duplicate GTK page: {item.gtk_page}')
                provider_gtk.add(item.gtk_page)
            key = (item.group,item.top_order)
            if key in provider_order:
                issues.append(f'Duplicate group/order: {key}')
            provider_order.add(key)
    code = (ROOT / 'flavors/autoseg/modules/gtk_app.py').read_text()
    pages = set(re.findall(r'self\.stack\.add_titled\(self\._pagina_\w+\(\),\s*"(\w+)"', code))
    if pages != provider_gtk:
        issues.append('Mismatch GTK page factories: registry_only='
                      f'{sorted(provider_gtk-pages)}, gtk_only={sorted(pages-provider_gtk)}')
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    errors = findings()
    for error in errors:
        print('SECTION ERROR:',error)
    if not errors:
        print('CHECK OK: section registry and GTK factories agree')
    return 1 if args.check and errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
