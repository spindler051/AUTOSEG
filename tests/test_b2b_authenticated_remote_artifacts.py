"""B2b reviewer regressions: remote draft bytes, permissions, and finance gates.

Intentional review-only module.  The author has NOT executed these tests.
"""
from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import prestador_auth
from flavors.autoseg.modules.autoseg_actions import resolved_actions
from officina.application.contracts import NaoEncontradoError, ValidacaoError
from officina.application.http_service import HttpService
from officina.application.local_service import LocalService
from officina.application.object_policy import Principal
from officina.application.remote_artifact import load_artifact, resolve_draft
from officina.core import prestadores_ext as ext, produtividade_os as prod
from test_p0_desktop_auth import DesktopObjectAuthorizationTest


class B2bRemoteArtifactTest(unittest.TestCase):
    # Reuse the existing real-SQL, HTTP and bearer-auth fixture without
    # inheriting the old test methods and duplicating the test suite.
    setUp = DesktopObjectAuthorizationTest.setUp
    request = DesktopObjectAuthorizationTest.request

    def _fetch(self, user, os_id, kind, name=''):
        path = (f'/api/v1/desktop/os/{os_id}/artefato/{kind}' +
                ('?'+urllib.parse.urlencode({'nome':name}) if name else ''))
        req = urllib.request.Request(
            self.base + path, method='GET',
            headers={'Authorization': 'Bearer ' + self.tokens[user]})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.read(), error.headers

    def test_email_draft_download_private_and_authenticated(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ext, 'RASCUNHOS', Path(tmp)):
            name = f'email_A-OS_p{self.users["first"]}_aabbccdd.eml'
            original = b'To: private@invalid.test\r\nSubject: Draft\r\n\r\nUnsent\r\n'
            (Path(tmp) / name).write_bytes(original)
            status, body, headers = self._fetch('first', self.own, 'email', name)
            self.assertEqual(status, 200, body)
            self.assertEqual(body, original)
            self.assertEqual(headers.get_content_type(), 'message/rfc822')
            self.assertEqual(headers['Cache-Control'], 'no-store, max-age=0')
            self.assertEqual(self._fetch('second', self.own, 'email', name)[0], 404)
            self.assertEqual(self._fetch('first', self.other, 'email', name)[0], 404)
            self.assertEqual(self._fetch('first', 999999, 'email', name)[0], 404)
            self.assertEqual(self._fetch('first', self.own, 'email', '../'+name)[0], 404)

    def test_revoked_session_cannot_download_even_existing_draft(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ext, 'RASCUNHOS', Path(tmp)):
            name = f'email_A-OS_p{self.users["first"]}_12345678.eml'
            (Path(tmp) / name).write_bytes(b'From: no-send\r\n\r\nDraft only\r\n')
            self.assertEqual(self._fetch('first', self.own, 'email', name)[0], 200)
            self.assertTrue(prestador_auth.revogar_sessao(
                self.db, 'Bearer '+self.tokens['first']))
            self.assertEqual(self._fetch('first', self.own, 'email', name)[0], 401)

    def test_json_draft_tied_to_exact_os_and_never_claims_emission(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ext, 'RASCUNHOS', Path(tmp)):
            name = 'nota_fiscal_rascunho_A-OS.json'
            draft = {'ordem_servico_id': self.own,
                     'status': 'RASCUNHO_NAO_EMITIDO'}
            path = Path(tmp) / name
            path.write_text(json.dumps(draft), encoding='utf-8')
            status, body, headers = self._fetch('first', self.own, 'nota', name)
            self.assertEqual(status, 200, body)
            self.assertEqual(headers.get_content_type(), 'application/json')
            self.assertEqual(json.loads(body), draft)
            draft['ordem_servico_id'] = self.other
            path.write_text(json.dumps(draft), encoding='utf-8')
            self.assertEqual(self._fetch('first', self.own, 'nota', name)[0], 404)
            draft['ordem_servico_id'] = self.own
            draft['status'] = 'EMITIDA'
            path.write_text(json.dumps(draft), encoding='utf-8')
            self.assertEqual(self._fetch('first', self.own, 'nota', name)[0], 404)

    def test_pdf_bytes_are_guarded_by_os_access_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'report.pdf'
            pdf = b'%PDF-1.4\n% mock reviewer document\n%%EOF\n'
            file.write_bytes(pdf)
            with patch.object(LocalService, 'pdf_publicado', return_value=str(file)):
                status, body, headers = self._fetch('first', self.own, 'pdf')
                self.assertEqual(status, 200, body)
                self.assertEqual(body, pdf)
                self.assertEqual(headers.get_content_type(), 'application/pdf')
                self.assertEqual(self._fetch('first', self.other, 'pdf')[0], 404)
                remote = HttpService(self.base, self.tokens['first'])
                local_path = Path(remote.baixar_artefato_os(self.own, 'pdf'))
                self.addCleanup(lambda: local_path.unlink(missing_ok=True))
                self.assertEqual(local_path.read_bytes(), pdf)
                self.assertEqual(local_path.stat().st_mode & 0o077, 0)
            file.write_bytes(b'NOT A PDF')
            with self.assertRaises(ValidacaoError):
                load_artifact(file, 'pdf')

    def test_resolver_refuses_symlink_traversal_and_wrong_os(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            with patch.object(ext, 'RASCUNHOS', Path(tmp)):
                name = 'nota_fiscal_rascunho_A-OS.json'
                target = Path(outside) / name
                target.write_text(json.dumps({
                    'ordem_servico_id': self.own,
                    'status': 'RASCUNHO_NAO_EMITIDO'}), encoding='utf-8')
                (Path(tmp)/name).symlink_to(target)
                with self.assertRaises(NaoEncontradoError):
                    resolve_draft(self.db, self.own, 'nota', name)
                with self.assertRaises(NaoEncontradoError):
                    resolve_draft(self.db, self.other, 'nota', name)
                with self.assertRaises(NaoEncontradoError):
                    resolve_draft(self.db, self.own, 'nota', 'other.json')

    def test_finance_actions_require_actual_finalizer_or_admin_for_row(self):
        prod.instalar(self.db)
        with ext.db(self.db) as c:
            c.execute('''INSERT INTO os_encerramentos
                         (os_id,situacao,ator,prestador_id,encerrado_em)
                         VALUES (?,'Concluída','first',?,'2026-11-14')''',
                      (self.own,self.users['first']))
            c.execute('''INSERT INTO os_encerramentos
                         (os_id,situacao,ator,prestador_id,encerrado_em)
                         VALUES (?,'Concluída','second',?,'2026-11-14')''',
                      (self.other,self.users['second']))
            own_fin = c.execute('''INSERT INTO financeiro
                           (os_id,cliente_id,valor,status)
                           VALUES(?,?,100,'Aguardando pagamento')''',
                           (self.own,self.own_client)).lastrowid
            other_fin = c.execute('SELECT id FROM financeiro WHERE os_id=?',
                                  (self.other,)).fetchone()[0]
        for user in ('first', 'second', 'admin'):
            role = 'admin' if user == 'admin' else 'employee'
            actor = Principal(self.users[user], role,
                              organization_id='autoseg', provider_id=self.users[user])
            for row, expected in ((own_fin, user in ('first','admin')),
                                  (other_fin, user in ('second','admin'))):
                actions = {a.id for a in resolved_actions(
                    self.db, actor, 'finance', object_id=row, surface='gtk')}
                self.assertEqual('finance.receive' in actions, expected)
                self.assertEqual('finance.due' in actions, expected)
            without_object = {a.id for a in resolved_actions(
                self.db, actor, 'finance', surface='gtk')}
            self.assertNotIn('finance.receive', without_object)
            self.assertNotIn('finance.due', without_object)
        with ext.db(self.db) as c:
            self.assertEqual(c.execute('SELECT status FROM financeiro WHERE id=?',
                                       (own_fin,)).fetchone()[0],
                             'Aguardando pagamento')
