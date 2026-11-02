"""Testes dos modelos YAML de cliente, OS e materiais (sem gravar no banco)."""
import importacao_yaml as imp


def test_cliente_yaml():
    dados = imp.cliente("cliente.yaml", """versao: 1
cliente:
  tipo_pessoa: Física
  nome: Cliente YAML Teste
  documento: 529.982.247-25
  cidade: Porto Alegre
  status: Prospect
""".encode())
    assert dados["nome"] == "Cliente YAML Teste"
    assert dados["documento"] == "529.982.247-25"

    try:
        imp.cliente("x.yaml", b"versao: 1\ncliente:\n  nome: Cliente X\n  documento: '111.111.111-11'\n")
    except ValueError as erro:
        assert "CPF/CNPJ" in str(erro)
    else:
        raise AssertionError("aceitou CPF inválido")


def test_ordem_servico_yaml():
    dados = imp.ordem_servico("os.yaml", """versao: 1
ordem_servico:
  cliente_documento: 52.204.907/0001-76
  tecnico: Fulano
  descricao: OS importada de YAML
  forma_pagamento: PIX
  mao_obra: 100,50
  urgencia: Alta
  materiais:
    - item: Cabo
      quantidade: 2
      valor_unitario: 12,50
""".encode())
    assert dados["descricao"] == "OS importada de YAML"
    assert dados["mao_obra"] == 100.5
    assert dados["urgencia"] == "Alta"
    assert dados["materiais"][0]["valor_total"] == 25.0

    try:
        imp.ordem_servico("x.yaml", b"versao: 1\nordem_servico:\n  descricao: sem cliente\n")
    except ValueError as erro:
        assert "cliente_id" in str(erro)
    else:
        raise AssertionError("aceitou OS sem cliente")


def test_materiais_yaml():
    dados = imp.materiais("materiais.yaml", """versao: 1
materiais:
  - nome: Cabo YAML
    sku: CAB-Y
    unidade: metro
    custo: '2,50'
    venda: '5,00'
    minimo: 2
""".encode())
    assert dados[0]["nome"] == "Cabo YAML"
    assert dados[0]["venda"] == "5,00"

    dados = imp.materiais_os("materiais_os.yaml", """versao: 1
materiais:
  - item: Cabo
    quantidade: 2
    valor_unitario: 12,50
""".encode())
    assert dados[0]["quantidade"] == 2.0
    assert dados[0]["valor_total"] == 25.0


def test_modelos_vazios():
    for modelo in (
        imp.MODELO_CLIENTE_VAZIO,
        imp.MODELO_OS_VAZIO,
        imp.MODELO_MATERIAIS_VAZIO,
        imp.MODELO_MATERIAIS_OS_VAZIO,
    ):
        assert "versao: 1" in modelo


if __name__ == "__main__":
    test_cliente_yaml()
    test_ordem_servico_yaml()
    test_materiais_yaml()
    test_modelos_vazios()
    print("TESTES_YAML_OK")
