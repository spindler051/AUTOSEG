"""Headless API-only server: JSON only, no HTML portals."""
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import api_server
import banco
import prestadores_ext as ext


class ApiServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='api_server_')
        self.db = str(Path(self.tmp.name) / 'teste.db')
        banco.criar_banco(self.db)
        ext.instalar(self.db)
        self.server = api_server.start(self.db, '127.0.0.1', 0)
        host, porta = self.server.server_address[:2]
        self.base = f'http://{host}:{porta}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_health_is_json_and_html_is_not_served(self):
        with urllib.request.urlopen(self.base + '/api/v1/health', timeout=5) as r:
            self.assertEqual(r.status, 200)
            self.assertIn('application/json', r.headers.get('Content-Type', ''))
            dados = json.loads(r.read().decode())
        self.assertEqual(dados['data']['status'], 'ok')

        with self.assertRaises(urllib.error.HTTPError) as contexto:
            urllib.request.urlopen(self.base + '/', timeout=5)
        self.assertEqual(contexto.exception.code, 404)
        self.assertIn('application/json',
                      contexto.exception.headers.get('Content-Type', ''))
        corpo = contexto.exception.read().decode()
        self.assertNotIn('<html', corpo.lower())

    def test_write_methods_are_not_part_of_read_api(self):
        pedido = urllib.request.Request(self.base + '/api/v1/health',
                                        data=b'x', method='POST')
        with self.assertRaises(urllib.error.HTTPError) as contexto:
            urllib.request.urlopen(pedido, timeout=5)
        self.assertEqual(contexto.exception.code, 405)


if __name__ == '__main__':
    unittest.main(verbosity=2)
