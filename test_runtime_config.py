"""Characterization tests for runtime_config defaults and env precedence."""
import os
import unittest
from pathlib import Path
from unittest import mock

import runtime_config


KEYS = (
    'AUTOSEG_BASE', 'GESTAO_BANCO', 'AUTOSEG_DEV',
    'PRESTADOR_PORT', 'PRESTADOR_BIND', 'PRESTADOR_HTTPS',
    'CLIENTE_PORT', 'CLIENTE_BIND',
)


class RuntimeConfigTest(unittest.TestCase):
    def setUp(self):
        self.patch = mock.patch.dict(os.environ, {}, clear=False)
        self.patch.start()
        for key in KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        self.patch.stop()

    def test_defaults_preserve_main_ports_and_paths(self):
        provider = runtime_config.provider_server()
        client = runtime_config.client_server()
        self.assertEqual((provider.host, provider.port, provider.https),
                         ('127.0.0.1', 8766, False))
        self.assertEqual((client.host, client.port), ('127.0.0.1', 8765))
        self.assertEqual(runtime_config.client_port(), 8765)
        self.assertEqual(runtime_config.base_dir(), Path(runtime_config.__file__).resolve().parent)
        self.assertEqual(runtime_config.database_path(),
                         Path(runtime_config.__file__).resolve().parent / 'dados.db')

    def test_dev_defaults_use_alt_ports(self):
        os.environ['AUTOSEG_DEV'] = '1'
        self.assertEqual(runtime_config.provider_server().port, 8866)
        self.assertEqual(runtime_config.client_server().port, 8865)

    def test_environment_overrides_match_legacy_precedence(self):
        os.environ.update({
            'PRESTADOR_PORT': '9999',
            'PRESTADOR_BIND': '0.0.0.0',
            'PRESTADOR_HTTPS': '1',
            'CLIENTE_PORT': '9998',
            'CLIENTE_BIND': '0.0.0.0',
        })
        provider = runtime_config.provider_server(port=1234, host='10.0.0.1')
        client = runtime_config.client_server(port=1234, host='10.0.0.1')
        # Explicit host wins; env port wins, exactly like the previous code.
        self.assertEqual((provider.host, provider.port, provider.https),
                         ('10.0.0.1', 9999, True))
        self.assertEqual((client.host, client.port), ('10.0.0.1', 9998))
        self.assertEqual(runtime_config.client_port(), 9998)
        self.assertTrue(runtime_config.provider_https())

    def test_explicit_ephemeral_ports_are_preserved_without_env(self):
        provider = runtime_config.provider_server(port=0)
        client = runtime_config.client_server(port=0)
        self.assertEqual(provider.port, 0)
        self.assertEqual(client.port, 0)

    def test_data_paths_follow_base_and_database_env(self):
        os.environ['AUTOSEG_BASE'] = '/tmp/autoseg-base'
        os.environ['GESTAO_BANCO'] = '/tmp/autoseg-base/custom.db'
        self.assertEqual(runtime_config.base_dir(), Path('/tmp/autoseg-base'))
        self.assertEqual(runtime_config.database_path(),
                         Path('/tmp/autoseg-base/custom.db'))
        os.environ.pop('GESTAO_BANCO')
        self.assertEqual(runtime_config.database_path(),
                         Path('/tmp/autoseg-base/dados.db'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
