"""Lifecycle tests for the optional local web access manager."""
import unittest
from pathlib import Path

from flavors.autoseg.modules.web_access import WebAccessManager


class FakeProvider:
    def __init__(self, banco, host, porta):
        self.banco = banco
        self.host = host
        self.porta = porta
        self.started = False
        self.stopped = False

    def iniciar(self):
        self.started = True
        return 'http://127.0.0.1:9999'

    def parar(self):
        self.stopped = True


class FakeClient:
    def __init__(self, banco, pasta_app, host, porta):
        self.banco = banco
        self.pasta_app = pasta_app
        self.host = host
        self.porta = porta
        self.ativo = False
        self.stopped = False

    def iniciar(self):
        self.ativo = True
        return self.info()

    def parar(self):
        self.ativo = False
        self.stopped = True

    def info(self):
        return {
            'ativo': self.ativo,
            'porta': self.porta,
            'url_local': f'http://127.0.0.1:{self.porta}' if self.ativo else '',
            'url_rede': '',
            'iniciado_em': '06/11/2026 18:00' if self.ativo else '',
            'erro': '',
        }

    def consumir_eventos(self):
        return [{'tipo': 'nova_os', 'numero': 'OS-1'}]


class WebAccessManagerTest(unittest.TestCase):
    def test_local_only_does_not_create_servers(self):
        manager = WebAccessManager('/tmp/nao-usado.db', enabled=False)
        estado = manager.start()
        self.assertFalse(estado['enabled'])
        self.assertFalse(estado['provider']['ativo'])
        self.assertIn('Modo local', manager.provider_error)
        self.assertFalse(manager.client_info()['ativo'])
        self.assertEqual(manager.consume_events(), [])
        manager.stop()

    def test_start_and_stop_are_delegated_to_servers(self):
        providers = []
        clients = []

        def provider_factory(banco, host, porta):
            item = FakeProvider(banco, host, porta)
            providers.append(item)
            return item

        def client_factory(banco, pasta_app, host, porta):
            item = FakeClient(banco, pasta_app, host, porta)
            clients.append(item)
            return item

        manager = WebAccessManager(
            '/tmp/nao-usado.db', Path('/tmp'),
            provider_factory=provider_factory, client_factory=client_factory)
        estado = manager.start()
        self.assertEqual(len(providers), 1)
        self.assertEqual(len(clients), 1)
        self.assertTrue(providers[0].started)
        self.assertTrue(clients[0].ativo)
        self.assertEqual(estado['provider']['url'], 'http://127.0.0.1:9999')
        self.assertTrue(manager.client_info()['ativo'])
        self.assertEqual(manager.consume_events()[0]['numero'], 'OS-1')

        manager.stop()
        self.assertTrue(providers[0].stopped)
        self.assertTrue(clients[0].stopped)
        self.assertFalse(manager.provider_active)

    def test_provider_failure_does_not_block_client(self):
        clients = []

        def provider_factory(banco, host, porta):
            raise RuntimeError('porta ocupada')

        def client_factory(banco, pasta_app, host, porta):
            item = FakeClient(banco, pasta_app, host, porta)
            clients.append(item)
            return item

        manager = WebAccessManager(
            '/tmp/nao-usado.db', Path('/tmp'),
            provider_factory=provider_factory, client_factory=client_factory)
        estado = manager.start()
        self.assertFalse(estado['provider']['ativo'])
        self.assertEqual(manager.provider_error, 'porta ocupada')
        self.assertTrue(manager.client_info()['ativo'])
        self.assertEqual(len(clients), 1)
        manager.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
