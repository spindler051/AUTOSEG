#!/usr/bin/env python3
"""Generate the repository branding assets from the design source.

The source directory is intentionally outside the repository. Set
``AUTOSEG_ICON_SOURCE`` (or pass ``--source``) to the directory containing
``autoseg.png`` and ``autoseg-dev.png``. The build emits the canonical 256px
icons used by the UI/PDF and the complete size ladder 1024/512/256/64 for
other surfaces.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from PIL import Image

SIZES = (1024, 512, 256, 64)
DEFAULT_SOURCE = os.environ.get(
    'AUTOSEG_ICON_SOURCE',
    str(Path.home() / 'Projects/projects/autoseg/icon'),
)
DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / 'flavors/autoseg/branding'


def _save(im: Image.Image, size: int, target: Path) -> None:
    resized = im.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
    resized.save(target, 'PNG', optimize=True)


def build(source: Path, output: Path) -> None:
    source = Path(source)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, prefix in (('autoseg.png', 'autoseg'),
                         ('autoseg-dev.png', 'autoseg-dev')):
        path = source / name
        if not path.is_file():
            raise FileNotFoundError(f'Missing icon source: {path}')
        with Image.open(path) as im:
            for size in SIZES:
                _save(im, size, output / f'{prefix}-{size}.png')
            canonical = 'icone.png' if prefix == 'autoseg' else 'icone_devel.png'
            _save(im, 256, output / canonical)

    logo_candidates = (source / 'logo.png', output / 'logo.png')
    logo = next((path for path in logo_candidates if path.is_file()), None)
    if logo is None:
        raise FileNotFoundError(
            'Missing logo source (logo.png in the source or output directory).')
    with Image.open(logo) as im:
        im = im.convert('RGBA')
        width = 512
        height = round(im.height * width / im.width)
        im.resize((width, height), Image.Resampling.LANCZOS).save(
            output / 'logo.png', 'PNG', optimize=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Generate AUTOSEG branding assets')
    parser.add_argument('--source', default=DEFAULT_SOURCE)
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    build(Path(args.source), Path(args.output))
    print(f'Branding generated in {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
