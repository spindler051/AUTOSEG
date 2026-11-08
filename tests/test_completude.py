"""Testa o mínimo configurável de cliente/OS em completude.yaml."""
import os
import tempfile
from pathlib import Path

from officina.core import completude
def test_padrao():
    assert completude.cliente_faltantes({"nome": ""}) == ["nome"]
    assert completude.cliente_faltantes({"nome": "Cliente"}) == []
    assert completude.os_faltantes({"cliente_id": 1, "descricao": ""}) == ["descricao"]
    assert completude.os_faltantes({"cliente_id": 1, "descricao": "Serviço"}) == []


def test_config_runtime():
    anterior = os.environ.get("AUTOSEG_BASE")
    with tempfile.TemporaryDirectory() as pasta:
        os.environ["AUTOSEG_BASE"] = pasta
        arquivo = Path(pasta) / "completude.yaml"
        arquivo.write_text("""versao: 1
cliente:
  - nome
  - documento
ordem_servico:
  - cliente_id
  - descricao
  - tecnico
""", encoding="utf-8")
        assert completude.cliente_faltantes({"nome": "X"}) == ["documento"]
        assert completude.os_faltantes({"cliente_id": 1, "descricao": "X"}) == ["tecnico"]

        # Alteração em runtime, sem reiniciar.
        arquivo.write_text("""versao: 1
cliente: []
ordem_servico:
  - descricao
""", encoding="utf-8")
        assert completude.cliente_faltantes({}) == []
        assert completude.os_faltantes({"descricao": "X"}) == []
    if anterior is None:
        os.environ.pop("AUTOSEG_BASE", None)
    else:
        os.environ["AUTOSEG_BASE"] = anterior


def test_config_invalida_cai_no_padrao():
    anterior = os.environ.get("AUTOSEG_BASE")
    with tempfile.TemporaryDirectory() as pasta:
        os.environ["AUTOSEG_BASE"] = pasta
        (Path(pasta) / "completude.yaml").write_text("invalido: true", encoding="utf-8")
        assert completude.cliente_faltantes({"nome": ""}) == ["nome"]
    if anterior is None:
        os.environ.pop("AUTOSEG_BASE", None)
    else:
        os.environ["AUTOSEG_BASE"] = anterior


if __name__ == "__main__":
    test_padrao()
    test_config_runtime()
    test_config_invalida_cai_no_padrao()
    print("TESTES_COMPLETUDE_OK")
