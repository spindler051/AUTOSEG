"""A3: publication must not leave unauthorized or unrecorded PDF files."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_p0_desktop_auth as base_tests
from officina.core import cadastros_v9 as cad, fluxo_os as fluxo, prestadores_ext as ext
from officina.application.local_service import LocalService


PDF = b'%PDF-1.4\n' + b'A' * 256


class PDFPublicationBoundaryTest(unittest.TestCase):
    setUp = base_tests.DesktopObjectAuthorizationTest.setUp
    request = base_tests.DesktopObjectAuthorizationTest.request

    def _prepare(self, directory):
        root = Path(directory) / 'reports'
        source = Path(directory) / 'source.pdf'
        source.write_bytes(PDF)
        with ext.db(self.db) as connection:
            connection.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=?", (self.other,))
        return root, source

    def _documents(self):
        with ext.db(self.db) as connection:
            return connection.execute('SELECT versao,caminho,sha256 FROM os_documentos WHERE os_id=?',
                                      (self.other,)).fetchall()

    def test_revoked_during_generation_leaves_no_published_file_or_row(self):
        with tempfile.TemporaryDirectory(prefix='a3_pdf_denied_') as directory:
            root, source = self._prepare(directory)
            def generated(*args):
                cad.definir_admin(self.db, self.users['admin'], False)
                return str(source)
            with patch.object(ext, 'RELATORIOS', root), patch.object(ext, 'gerar_pdf', generated):
                code, body = self.request('admin', f'/os/{self.other}/pdf/publicar', 'POST')
            self.assertEqual(code, 404, body)
            self.assertEqual(self._documents(), [])
            self.assertEqual(list((root / 'publicados').glob('*')), [])

    def test_database_failure_after_promotion_cleans_only_new_target(self):
        with tempfile.TemporaryDirectory(prefix='a3_pdf_failure_') as directory:
            root, source = self._prepare(directory)
            with patch.object(ext, 'RELATORIOS', root), patch.object(ext, 'gerar_pdf', return_value=str(source)), \
                 patch.object(ext, 'agora', side_effect=RuntimeError('injected metadata failure')):
                with self.assertRaisesRegex(RuntimeError, 'injected metadata failure'):
                    fluxo.publicar_relatorio(self.db, self.other)
            self.assertEqual(self._documents(), [])
            self.assertEqual(list((root / 'publicados').glob('*')), [])

    def test_existing_unrecorded_target_is_never_overwritten_or_deleted(self):
        with tempfile.TemporaryDirectory(prefix='a3_pdf_collision_') as directory:
            root, source = self._prepare(directory)
            dest = root / 'publicados' / 'B-OS_relatorio_v1.pdf'
            dest.parent.mkdir(parents=True)
            dest.write_bytes(b'EXISTING UNRECORDED DATA')
            with patch.object(ext, 'RELATORIOS', root), patch.object(ext, 'gerar_pdf', return_value=str(source)):
                with self.assertRaises((FileExistsError, ValueError)):
                    fluxo.publicar_relatorio(self.db, self.other)
            self.assertEqual(dest.read_bytes(), b'EXISTING UNRECORDED DATA')
            self.assertEqual(self._documents(), [])
            self.assertEqual(list(dest.parent.iterdir()), [dest])

    def test_authorized_publication_records_exact_final_file(self):
        with tempfile.TemporaryDirectory(prefix='a3_pdf_success_') as directory:
            root, source = self._prepare(directory)
            with patch.object(ext, 'RELATORIOS', root), patch.object(ext, 'gerar_pdf', return_value=str(source)):
                code, body = self.request('admin', f'/os/{self.other}/pdf/publicar', 'POST')
            self.assertEqual(code, 200, body)
            rows = self._documents()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['versao'], 1)
            self.assertEqual(rows[0]['sha256'], hashlib.sha256(PDF).hexdigest())
            self.assertEqual(Path(rows[0]['caminho']).read_bytes(), PDF)
            self.assertEqual(list((root / 'publicados').iterdir()), [Path(rows[0]['caminho'])])


if __name__ == '__main__':
    unittest.main()
