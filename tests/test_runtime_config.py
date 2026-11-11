"""Characterization tests for runtime_config defaults and env precedence."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from officina.core import runtime_config
KEYS = (
    'AUTOSEG_BASE', 'GESTAO_BANCO', 'AUTOSEG_DEV',
    'AUTOSEG_USER_DATA', 'AUTOSEG_SERVER_DATA', 'AUTOSEG_LOCAL_DATA',
    'PRESTADOR_PORT', 'PRESTADOR_BIND', 'PRESTADOR_HTTPS',
    'AUTOSEG_WEB_ACCESS',
)


class RuntimeConfigTest(unittest.TestCase):
    def setUp(self):
        self.patch = mock.patch.dict(os.environ, {}, clear=False)
        self.patch.start()
        for key in KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        self.patch.stop()

    def test_single_site_main_port_and_paths(self):
        provider = runtime_config.provider_server()
        self.assertEqual((provider.host, provider.port, provider.https),
                         ('127.0.0.1', 8766, False))
        self.assertFalse(hasattr(runtime_config, 'client_server'))
        self.assertFalse(hasattr(runtime_config, 'client_port'))
        repo = Path(runtime_config.__file__).resolve().parents[2]
        self.assertEqual(runtime_config.base_dir(), runtime_config.local_data_dir())
        self.assertEqual(runtime_config.database_path(),
                         runtime_config.local_data_dir() / 'dados.db')
        self.assertNotEqual(runtime_config.base_dir(), repo)
        self.assertNotEqual(runtime_config.database_path().parent, repo)

    def test_dev_site_uses_alt_port(self):
        os.environ['AUTOSEG_DEV'] = '1'
        self.assertEqual(runtime_config.provider_server().port, 8866)

    def test_provider_environment_override_precedence(self):
        os.environ.update({
            'PRESTADOR_PORT': '9999',
            'PRESTADOR_BIND': '0.0.0.0',
            'PRESTADOR_HTTPS': '1',
        })
        provider = runtime_config.provider_server(port=1234, host='192.0.2.1')
        # Explicit host wins; env port wins, exactly like the previous code.
        self.assertEqual((provider.host, provider.port, provider.https),
                         ('192.0.2.1', 9999, True))
        self.assertTrue(runtime_config.provider_https())

    def test_explicit_ephemeral_ports_are_preserved_without_env(self):
        provider = runtime_config.provider_server(port=0)
        self.assertEqual(provider.port, 0)

    def test_web_access_is_on_by_default_and_can_be_disabled(self):
        self.assertTrue(runtime_config.web_access_enabled())
        os.environ['AUTOSEG_WEB_ACCESS'] = '0'
        self.assertFalse(runtime_config.web_access_enabled())
        os.environ['AUTOSEG_WEB_ACCESS'] = '1'
        self.assertTrue(runtime_config.web_access_enabled())

    def test_data_paths_follow_base_and_database_env(self):
        os.environ['AUTOSEG_BASE'] = '/tmp/autoseg-base'
        os.environ['GESTAO_BANCO'] = '/tmp/autoseg-base/custom.db'
        self.assertEqual(runtime_config.base_dir(), Path('/tmp/autoseg-base'))
        self.assertEqual(runtime_config.database_path(),
                         Path('/tmp/autoseg-base/custom.db'))
        os.environ.pop('GESTAO_BANCO')
        self.assertEqual(runtime_config.database_path(),
                         Path('/tmp/autoseg-base/dados.db'))

    def test_user_data_override_drives_local_and_dev_server_dirs(self):
        os.environ['AUTOSEG_USER_DATA'] = '/tmp/autoseg-user'
        os.environ['AUTOSEG_DEV'] = '1'
        self.assertEqual(runtime_config.user_data_dir(), Path('/tmp/autoseg-user'))
        self.assertEqual(runtime_config.local_data_dir(),
                         Path('/tmp/autoseg-user/local'))
        self.assertEqual(runtime_config.server_data_dir(),
                         Path('/tmp/autoseg-user/server-dev'))

    def test_configure_local_creates_and_exports_private_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ['AUTOSEG_LOCAL_DATA'] = str(Path(tmp) / 'local')
            base = runtime_config.configure_local()
            self.assertEqual(base, Path(tmp) / 'local')
            self.assertTrue(base.is_dir())
            self.assertEqual(os.environ['AUTOSEG_BASE'], str(base))
            self.assertEqual(os.environ['GESTAO_BANCO'],
                             str(base / 'dados.db'))

    def test_configure_server_dev_uses_dados_teste_and_exports_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ['AUTOSEG_DEV'] = '1'
            os.environ['AUTOSEG_SERVER_DATA'] = str(Path(tmp) / 'server')
            base = runtime_config.configure_server()
            self.assertEqual(base, Path(tmp) / 'server')
            self.assertTrue(base.is_dir())
            self.assertEqual(os.environ['AUTOSEG_BASE'], str(base))
            self.assertEqual(
                os.environ['GESTAO_BANCO'],
                str(base / 'dados_teste' / 'autoseg_teste.db'))
            self.assertTrue((base / 'dados_teste').is_dir())


if __name__ == '__main__':
    unittest.main(verbosity=2)
