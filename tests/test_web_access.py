"""A single Officina Web server is owned by the GTK web manager."""
import unittest
from unittest.mock import patch
from flavors.autoseg.modules.web_access import WebAccessManager


class FakeSite:
    def __init__(self, banco, host, porta):
        self.host, self.porta = host, porta
        self.started = self.stopped = False

    def iniciar(self):
        self.started = True
        return f'http://127.0.0.1:{self.porta}'

    def parar(self):
        self.stopped = True


class WebAccessManagerTest(unittest.TestCase):
    def test_local_mode_does_not_create_site(self):
        manager = WebAccessManager('unused.db', enabled=False,
                                   provider_factory=lambda *args: self.fail('factory called'))
        status = manager.start()
        self.assertFalse(status['enabled'])
        self.assertFalse(status['site']['ativo'])
        self.assertFalse(manager.provider_active)
        manager.stop()

    def test_one_server_serves_client_and_provider(self):
        servers = []
        def create(*args):
            item = FakeSite(*args)
            servers.append(item)
            return item
        manager = WebAccessManager('unused.db', provider_factory=create)
        with patch('flavors.autoseg.modules.web_access.runtime_config.provider_server') as config:
            config.return_value.host, config.return_value.port = '127.0.0.1', 8866
            self.assertTrue(manager.start()['site']['ativo'])
            self.assertEqual(manager.start()['site']['url_local'], 'http://127.0.0.1:8866')
        self.assertEqual(len(servers), 1)
        self.assertEqual(manager.site_info()['porta'], 8866)
        self.assertEqual(manager.consume_events(), [])
        manager.stop()
        self.assertTrue(servers[0].stopped)
        self.assertFalse(manager.site_info()['ativo'])

    def test_failure_starts_no_second_listener(self):
        def fail(*args):
            raise OSError('port busy')
        manager = WebAccessManager('unused.db', provider_factory=fail)
        status = manager.start()
        self.assertFalse(status['site']['ativo'])
        self.assertIn('port busy', manager.provider_error)

    def test_legacy_second_server_contract_does_not_exist(self):
        for name in ('client_info','client_on_network','start_client',
                     'stop_client','client_error','_criar_cliente'):
            self.assertFalse(hasattr(WebAccessManager, name), name)


if __name__ == '__main__':
    unittest.main()
