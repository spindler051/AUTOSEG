"""Define o mínimo para um cliente/OS ser considerado completo.

O arquivo `completude.yaml` pode ser editado em tempo de execução. A cada
chamada ele é relido; não exige reiniciar o app.

Ordem de procura:
1. $AUTOSEG_BASE/completude.yaml
2. completude.yaml ao lado do código
3. padrão interno
"""
import os
from decimal import Decimal
from pathlib import Path

PASTA_APP = Path(__file__).resolve().parent

PADRAO = {
    "cliente": ["nome"],
    "ordem_servico": ["cliente_id", "descricao"],
}

CAMPOS_CLIENTE = {
    "tipo_pessoa", "documento", "nome", "nome_fantasia", "endereco", "numero",
    "complemento", "bairro", "cep", "cidade", "uf", "telefone", "email",
    "sindico_nome", "sindico_telefone", "sindico_email", "administradora",
    "administradora_email", "administradora_telefone", "observacoes", "status",
}

CAMPOS_OS = {
    "cliente_id", "descricao", "tecnico", "forma_pagamento", "valor_total",
    "urgencia", "observacoes",
}


def _arquivo():
    base = os.environ.get("AUTOSEG_BASE")
    if base:
        candidato = Path(base).expanduser() / "completude.yaml"
        if candidato.is_file():
            return candidato
    candidato = PASTA_APP / "flavors" / "autoseg" / "config" / "completude.yaml"
    return candidato if candidato.is_file() else None


def _lista(secao, permitidos, padrao):
    if not isinstance(secao, list):
        return list(padrao)
    campos = []
    for campo in secao:
        campo = str(campo).strip()
        if campo in permitidos and campo not in campos:
            campos.append(campo)
    return campos


def carregar():
    """Retorna as listas de campos mínimos; YAML inválido cai no padrão."""
    caminho = _arquivo()
    if caminho is None:
        return {chave: list(valor) for chave, valor in PADRAO.items()}
    try:
        import yaml
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
        if not isinstance(dados, dict) or dados.get("versao") != 1:
            raise ValueError("versao: 1 obrigatória")
        return {
            "cliente": _lista(dados.get("cliente"), CAMPOS_CLIENTE, PADRAO["cliente"]),
            "ordem_servico": _lista(dados.get("ordem_servico"), CAMPOS_OS,
                                    PADRAO["ordem_servico"]),
        }
    except Exception as erro:
        print(f"completude.yaml inválido ({caminho}): {erro}; usando padrão.")
        return {chave: list(valor) for chave, valor in PADRAO.items()}


def _vazio(valor):
    """Zero é um valor válido (ex.: mão de obra gratuita em garantia)."""
    if valor is None:
        return True
    if isinstance(valor, bool):
        return not valor
    if isinstance(valor, (int, float, Decimal)):
        return False
    if isinstance(valor, str):
        return not valor.strip()
    return not bool(valor)


def _faltantes(dados, secao):
    return [campo for campo in carregar()[secao]
            if _vazio(dados.get(campo))]


def cliente_faltantes(dados):
    return _faltantes(dados, "cliente")


def os_faltantes(dados):
    return _faltantes(dados, "ordem_servico")


def cliente_completo(dados):
    return not cliente_faltantes(dados)


def os_completo(dados):
    return not os_faltantes(dados)
