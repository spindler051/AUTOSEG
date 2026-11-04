"""Tests for the disabled-by-default telemetry skeleton."""

import unittest

from telemetry import MemorySink, TelemetryClient, TelemetryConfig, TelemetryEvent
from telemetry.privacy import hash_ip, page_path, truncate_ip


def evento(**kwargs):
    dados = {
        "name": "page_view",
        "occurred_at": "2026-11-04T12:00:00Z",
        "session_id": "sessao-ficticia",
        "page": "/clientes/1?cpf=12345678900#dados",
        "authenticated": True,
        "actor_type": "user",
    }
    dados.update(kwargs)
    return TelemetryEvent(**dados)


class TelemetriaSkeletonTest(unittest.TestCase):
    def test_desligada_por_padrao_nao_coleta(self):
        sink = MemorySink()
        cliente = TelemetryClient(TelemetryConfig(), sink)
        self.assertFalse(cliente.active)
        self.assertFalse(cliente.emit(evento()))
        self.assertEqual(sink.events, [])

    def test_ligada_explicitamente_emite(self):
        sink = MemorySink()
        cliente = TelemetryClient(
            TelemetryConfig(enabled=True, mode="local", notice_version="v1"), sink)
        self.assertTrue(cliente.active)
        self.assertTrue(cliente.emit(evento(attributes={"status_code": 200})))
        self.assertEqual(len(sink.events), 1)
        self.assertEqual(sink.events[0]["page"], "/clientes/1")
        self.assertEqual(sink.events[0]["attributes"]["status_code"], 200)
        self.assertNotIn("cpf", sink.events[0])

    def test_evento_fora_da_allowlist_rejeitado(self):
        with self.assertRaises(ValueError):
            evento(name="track_everything")

    def test_atributo_sensivel_rejeitado(self):
        with self.assertRaises(ValueError):
            evento(attributes={"email": "pessoa@example.org"})
        with self.assertRaises(ValueError):
            evento(attributes={"token": "segredo"})

    def test_atributo_desconhecido_rejeitado(self):
        with self.assertRaises(ValueError):
            evento(attributes={"livre": "qualquer coisa"})

    def test_url_sem_query_ou_fragmento(self):
        self.assertEqual(page_path("/os/16?email=x#topo"), "/os/16")
        self.assertEqual(page_path("https://exemplo.test/clientes?cpf=1"), "/clientes")
        self.assertEqual(page_path(""), "/")

    def test_ip_truncado(self):
        self.assertEqual(truncate_ip("203.0.113.45"), "203.0.113.0")
        self.assertEqual(truncate_ip("2001:db8:abcd::1"), "2001:db8:abcd::")

    def test_hash_de_ip_exige_chave(self):
        with self.assertRaises(ValueError):
            hash_ip("203.0.113.45", "")
        a = hash_ip("203.0.113.45", "chave-local")
        b = hash_ip("203.0.113.45", "chave-local")
        self.assertEqual(a, b)
        self.assertNotEqual(a, hash_ip("203.0.113.46", "chave-local"))
        self.assertEqual(len(a), 32)

    def test_otlp_exige_endpoint_e_hash_exige_chave(self):
        with self.assertRaises(ValueError):
            TelemetryConfig(enabled=True, mode="otlp")
        with self.assertRaises(ValueError):
            TelemetryConfig(collect_ip=True, ip_mode="hash")
        config = TelemetryConfig(
            enabled=True, mode="otlp", otlp_endpoint="https://collector.example/v1",
            collect_ip=True, ip_mode="hash", ip_hash_key="chave")
        self.assertTrue(config.active)


if __name__ == "__main__":
    unittest.main()
