"""Branding asset size guards and build generator coverage."""
import tempfile
from pathlib import Path
import unittest

from PIL import Image

from scripts.autoseg import build_branding


ROOT = Path(__file__).resolve().parents[1]


class BrandingAssetsTest(unittest.TestCase):
    def test_repository_branding_is_bounded(self):
        with Image.open(ROOT / 'flavors/autoseg/branding/icone.png') as icon:
            self.assertLessEqual(max(icon.size), 256)
        with Image.open(ROOT / 'flavors/autoseg/branding/icone_devel.png') as dev_icon:
            self.assertLessEqual(max(dev_icon.size), 256)
        with Image.open(ROOT / 'flavors/autoseg/branding/logo.png') as logo:
            self.assertLessEqual(logo.width, 512)
        for name in ('icone.png', 'icone_devel.png', 'logo.png'):
            self.assertLess(
                (ROOT / 'flavors/autoseg/branding' / name).stat().st_size,
                200_000)

    def test_builder_generates_the_size_ladder(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            output = Path(tmp) / 'branding'
            source.mkdir()
            Image.new('RGBA', (300, 300), (20, 30, 40, 255)).save(
                source / 'autoseg.png')
            Image.new('RGBA', (300, 300), (30, 40, 50, 255)).save(
                source / 'autoseg-dev.png')
            Image.new('RGBA', (800, 300), (40, 50, 60, 255)).save(
                source / 'logo.png')
            build_branding.main([
                '--source', str(source), '--output', str(output)])
            for prefix in ('autoseg', 'autoseg-dev'):
                for size in (1024, 512, 256, 64):
                    path = output / f'{prefix}-{size}.png'
                    self.assertTrue(path.is_file(), path)
                    with Image.open(path) as im:
                        self.assertEqual(im.size, (size, size))
            with Image.open(output / 'icone.png') as im:
                self.assertEqual(im.size, (256, 256))
            with Image.open(output / 'icone_devel.png') as im:
                self.assertEqual(im.size, (256, 256))
            with Image.open(output / 'logo.png') as im:
                self.assertEqual(im.size, (512, 192))
