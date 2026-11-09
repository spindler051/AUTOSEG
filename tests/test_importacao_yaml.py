"""Testes dos modelos YAML de cliente, OS e materiais (sem gravar no banco)."""
from flavors.autoseg.modules import importacao_yaml as imp
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
  cliente_documento: 12.345.678/0001-95
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


def test_cliente_yaml_nao_depende_do_nome_do_arquivo():
    conteudo = """versao: 1
cliente:
  nome: Cliente Sem Extensão
  tipo_pessoa: Física
  status: Prospect
""".encode()
    for nome in ('cadastro', 'cadastro.txt', 'CADASTRO.YAML'):
        dados = imp.cliente(nome, conteudo)
        assert dados["nome"] == "Cliente Sem Extensão"


def test_modelos_vazios():
    for modelo in (
        imp.MODELO_CLIENTE_VAZIO,
        imp.MODELO_OS_VAZIO,
        imp.MODELO_MATERIAIS_VAZIO,
        imp.MODELO_MATERIAIS_OS_VAZIO,
    ):
        assert "versao: 1" in modelo


# ---------------------------------------------------------------------------
# Correções críticas: materiais do relatório (seção `os`) sem lançamento
# financeiro forçado, `null`/ausente tratados como vazio e mensagens específicas.
# ---------------------------------------------------------------------------

def _relatorio(yaml_texto):
    return imp.relatorio("os.yaml", yaml_texto.encode())


def test_relatorio_materiais_vazio():
    d = _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais: []
""")
    assert d["material_yaml"] == []


def test_relatorio_materiais_ausente():
    d = _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
""")
    # Sem a chave `materiais`, não deve pré-preencher/limpar materiais.
    assert "material_yaml" not in d


def test_relatorio_materiais_null():
    d = _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais: null
""")
    assert d["material_yaml"] == []


def test_relatorio_materiais_nao_lista():
    try:
        _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais: "cabo e câmera"
""")
    except ValueError as erro:
        assert 'O campo "materiais" deve ser uma lista.' in str(erro)
    else:
        raise AssertionError("aceitou materiais como texto")


def test_relatorio_materiais_estruturados_validos():
    d = _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais:
    - item: Câmera IP
      quantidade: 2
      valor_unitario: 250,00
    - item: Cabo de rede
      quantidade: 10
      valor_unitario: 3,50
""")
    assert len(d["material_yaml"]) == 2
    assert d["material_yaml"][0]["item"] == "Câmera IP"
    assert d["material_yaml"][0]["quantidade"] == 2.0
    assert d["material_yaml"][0]["valor_unitario"] == 250.0


def test_relatorio_material_item_faltando():
    try:
        _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais:
    - quantidade: 2
      valor_unitario: 10
""")
    except ValueError as erro:
        assert 'Material 1: campo "item" não informado.' in str(erro)
    else:
        raise AssertionError("aceitou material sem item")


def test_relatorio_material_quantidade_faltando():
    try:
        _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais:
    - item: Cabo
      valor_unitario: 10
""")
    except ValueError as erro:
        assert 'Material 1: campo "quantidade" não informado.' in str(erro)
    else:
        raise AssertionError("aceitou material sem quantidade")


def test_relatorio_material_quantidade_invalida():
    try:
        _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais:
    - item: Cabo
      quantidade: abc
      valor_unitario: 10
""")
    except ValueError as erro:
        assert 'Material 1: campo "quantidade" inválido.' in str(erro)
    else:
        raise AssertionError("aceitou quantidade inválida")


def test_relatorio_material_valor_faltando_nao_vira_zero():
    # Regra: campo ausente NÃO recebe zero automático.
    try:
        _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais:
    - item: Cabo
      quantidade: 2
""")
    except ValueError as erro:
        assert 'Material 1: campo "valor_unitario" não informado.' in str(erro)
    else:
        raise AssertionError("atribuiu zero automaticamente a material incompleto")


def test_relatorio_material_texto_nao_vira_financeiro():
    # Itens de texto (descrição técnica) não devem virar lançamento financeiro.
    try:
        _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais:
    - Câmera externa
    - Conectores e cabeamento
""")
    except ValueError as erro:
        assert 'Material 1' in str(erro)
    else:
        raise AssertionError("converteu texto descritivo em material financeiro")


def test_relatorio_erro_numera_material_correto():
    try:
        _relatorio("""versao: 1
os:
  diagnostico: D
  execucao: E
  resultado: R
  relatorio_tecnico: RT
  materiais:
    - item: Cabo
      quantidade: 2
      valor_unitario: 10
    - item: Fonte
      quantidade: abc
      valor_unitario: 40
""")
    except ValueError as erro:
        assert 'Material 2: campo "quantidade" inválido.' in str(erro)
    else:
        raise AssertionError("não apontou o número correto do material")


def test_relatorio_composicao_declarativa():
    dados = imp.relatorio("os.yaml", """versao: 1
os:
  diagnostico: "d"
  execucao: "e"
  resultado: "r"
  relatorio_tecnico: "x"
  materiais: []
  composicao:
    - id: visita
      valor: 250.00
      filhos:
        - id: deslocamento
          valor: 50.00
        - id: administrativo
          percentual: 10
        - id: operacional
          percentual: 10
        - id: risco
          percentual: 5
        - id: outros
          residual: true
""".encode())
    comp = dados["composicao_yaml"]
    assert len(comp) == 1
    assert comp[0]["id"] == "visita"
    assert float(comp[0]["valor"]) == 250.0
    assert len(comp[0]["filhos"]) == 5
    assert comp[0]["filhos"][-1]["residual"] is True


if __name__ == "__main__":
    test_cliente_yaml()
    test_ordem_servico_yaml()
    test_materiais_yaml()
    test_modelos_vazios()
    test_relatorio_materiais_vazio()
    test_relatorio_materiais_ausente()
    test_relatorio_materiais_null()
    test_relatorio_materiais_nao_lista()
    test_relatorio_materiais_estruturados_validos()
    test_relatorio_material_item_faltando()
    test_relatorio_material_quantidade_faltando()
    test_relatorio_material_quantidade_invalida()
    test_relatorio_material_valor_faltando_nao_vira_zero()
    test_relatorio_material_texto_nao_vira_financeiro()
    test_relatorio_erro_numera_material_correto()
    test_relatorio_composicao_declarativa()
    print("TESTES_YAML_OK")
