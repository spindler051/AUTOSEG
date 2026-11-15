"""A4: an attachment must be authorized against the exact row served."""
from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from flavors.autoseg.modules import os_commands
from officina.application.object_policy import Principal
from officina.core import prestadores_ext as ext
from tests import test_p0_desktop_auth as base_tests


class _BytesResponse:
    def __init__(self):
        self.calls = []

    def send_bytes(self, data, mime, **kwargs):
        self.calls.append((data, mime, kwargs))
        return data

    def erro(self, message, code, session):
        return code, message


class AttachmentReadConsistencyTest(unittest.TestCase):
    setUp = base_tests.DesktopObjectAuthorizationTest.setUp

    def _principal(self, name):
        return Principal(account_id=self.users[name], role='employee',
                         organization_id='autoseg', provider_id=self.users[name])

    def _photo(self, folder, name, color):
        path = folder / name
        Image.new('RGB', (12, 12), color).save(path)
        return path

    def _seed(self, directory):
        folder = Path(directory) / 'attachments'
        folder.mkdir()
        own = self._photo(folder, 'allowed.png', 'green')
        other = self._photo(folder, 'restricted.png', 'red')
        with ext.db(self.db) as connection:
            aid = connection.execute('''INSERT INTO os_anexos
                (os_id,prestador_id,nome_original,caminho,tipo,criado_em)
                VALUES (?,?,?,?,?,?)''',
                (self.own,self.users['first'],own.name,str(own),'image/png',ext.agora())).lastrowid
        return folder, aid, own, other

    def _read(self, kind, aid, principal):
        response = _BytesResponse()
        reader = os_commands.read_anexo if kind == 'original' else os_commands.read_anexo_thumb
        return reader(self.db, principal, aid, ui=response,
                      session={'pid':self.users['first']}), response

    def _relink_at_later_db_open(self, aid, other):
        original_db = ext.db
        opened = [0]
        relinked = [False]

        @contextmanager
        def intercepted_db(db_path):
            opened[0] += 1
            # On the original reader, the fourth connection fetches the file
            # after the OS read and document authorization have completed.
            if opened[0] == 4:
                with original_db(db_path) as writer:
                    writer.execute('''UPDATE os_anexos SET os_id=?,caminho=?,nome_original=?
                                      WHERE id=?''',
                                   (self.other,str(other),other.name,aid))
                relinked[0] = True
            with original_db(db_path) as connection:
                yield connection

        return intercepted_db, relinked

    def test_relink_between_authorization_and_original_fetch_cannot_serve_other_file(self):
        with tempfile.TemporaryDirectory(prefix='a4_original_') as directory:
            folder, aid, own, other = self._seed(directory)
            intercepted, relinked = self._relink_at_later_db_open(aid, other)
            with patch.object(ext, 'ANEXOS', folder), patch.object(ext, 'db', intercepted):
                data, _ = self._read('original', aid, self._principal('first'))
            self.assertEqual(data, own.read_bytes())

    def test_relink_between_authorization_and_thumb_fetch_cannot_serve_other_file(self):
        with tempfile.TemporaryDirectory(prefix='a4_thumb_') as directory:
            folder, aid, own, other = self._seed(directory)
            intercepted, relinked = self._relink_at_later_db_open(aid, other)
            with patch.object(ext, 'ANEXOS', folder), patch.object(ext, 'db', intercepted):
                data, _ = self._read('thumb', aid, self._principal('first'))
            with tempfile.TemporaryDirectory(prefix='a4_expected_') as tmp:
                # Thumbnail content is JPEG and visibly tied to the original.
                from io import BytesIO
                with Image.open(BytesIO(data)) as image:
                    rgb = image.convert('RGB').getpixel((0, 0))
            self.assertGreater(rgb[1], rgb[0])

    def test_unrelated_and_missing_attachments_are_denied(self):
        with tempfile.TemporaryDirectory(prefix='a4_denied_') as directory:
            folder, aid, own, other = self._seed(directory)
            with patch.object(ext, 'ANEXOS', folder):
                for kind in ('original', 'thumb'):
                    with self.subTest(kind=kind):
                        with self.assertRaises(PermissionError):
                            self._read(kind, aid, self._principal('second'))
                        with self.assertRaises(PermissionError):
                            self._read(kind, aid + 99999, self._principal('first'))


if __name__ == '__main__':
    unittest.main()
