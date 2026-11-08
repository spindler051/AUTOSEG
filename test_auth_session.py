"""Authentication, revocable tokens and client session-file tests."""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from banco import criar_banco
import cadastros_v9 as cad9
import prestador_auth
import prestadores_ext as ext
from application.connection import ConnectionMode
from application.session import (
    Sessao,
    carregar_sessao,
    limpar_sessao,
    salvar_sessao,
)


class ProviderAuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='auth_')
        self.db = str(Path(self.tmp.name) / 'auth.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad9.instalar(self.db)
        prestador_auth.instalar(self.db)
        self.pid = ext.cadastrar(
            self.db, 'Admin Auth', 'admin-auth@example.invalid',
            'senha-auth-12345')
        cad9.definir_admin(self.db, self.pid, True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_login_validate_and_revoke_token(self):
        resultado = prestador_auth.login(
            self.db, 'admin-auth@example.invalid', 'senha-auth-12345')
        self.assertIsNotNone(resultado)
        self.assertTrue(resultado['prestador']['admin'])
        header = 'Bearer ' + resultado['token']
        info = prestador_auth.validar_sessao(self.db, header)
        self.assertEqual(info['id'], self.pid)
        self.assertTrue(info['admin'])
        self.assertTrue(prestador_auth.revogar_sessao(self.db, header))
        self.assertIsNone(prestador_auth.validar_sessao(self.db, header))

    def test_wrong_password_is_rejected(self):
        self.assertIsNone(prestador_auth.login(
            self.db, 'admin-auth@example.invalid', 'senha-errada'))

    def test_first_admin_can_be_created_only_once(self):
        with tempfile.TemporaryDirectory(prefix='auth_first_') as tmp:
            db = str(Path(tmp) / 'new.db')
            criar_banco(db)
            ext.instalar(db)
            cad9.instalar(db)
            prestador_auth.instalar(db)
            info = prestador_auth.criar_primeiro_admin(
                db, 'Primeiro Admin', 'primeiro@example.invalid',
                'senha-primeiro-123')
            self.assertTrue(info['admin'])
            with self.assertRaises(ValueError):
                prestador_auth.criar_primeiro_admin(
                    db, 'Outro', 'outro@example.invalid', 'senha-outro-123')


class SessionFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='session_')
        self.path = Path(self.tmp.name) / 'session.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_remote_session_is_saved_with_private_permissions(self):
        sessao = Sessao(
            mode=ConnectionMode.REMOTE.value, prestador_id=7,
            nome='Admin', email='admin@example.invalid', admin=True,
            server_url='http://127.0.0.1:8766', token='token-secreto',
            expira_em='2026-12-07 00:00:00')
        salvar_sessao(sessao, self.path)
        self.assertEqual(
            stat.S_IMODE(self.path.stat().st_mode), 0o600)
        carregada = carregar_sessao(self.path)
        self.assertEqual(carregada.prestador_id, 7)
        self.assertTrue(carregada.admin)
        self.assertEqual(carregada.token, 'token-secreto')

    def test_local_session_is_never_persisted(self):
        sessao = Sessao(
            mode=ConnectionMode.LOCAL.value, prestador_id=1,
            nome='Local', email='local@example.invalid', admin=True)
        salvar_sessao(sessao, self.path)
        self.assertFalse(self.path.exists())

    def test_clear_removes_session(self):
        self.path.write_text('{}', encoding='utf-8')
        limpar_sessao(self.path)
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
