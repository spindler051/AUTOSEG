"""Composição configurável do valor de serviços e ordens de serviço.

Nenhuma taxa ou categoria é fixa no código. O arquivo ``composicao.yaml``
(padrão ao lado deste módulo, ou ``$AUTOSEG_BASE/composicao.yaml``) define os
componentes, os modos de cálculo e os parâmetros. A leitura é feita a cada
cálculo, então alterações valem em runtime, sem reiniciar o app.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import sqlite3
import unicodedata
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import yaml

PADRAO = (Path(__file__).resolve().parent / "flavors" / "autoseg" / "config" / "composicao_padrao.yaml")
MODOS = {
    "materiais": "Materiais (custo real)",
    "fixo": "Valor fixo",
    "hora": "Hora técnica",
    "percentual": "Percentual do total",
    "formula": "Fórmula",
    "residual": "Residual (fecha o total)",
}
MODOS_CHAVES = list(MODOS)
MODOS_LABELS = list(MODOS.values())


def _slug(texto):
    normalizado = unicodedata.normalize("NFKD", str(texto or ""))
    normalizado = "".join(c for c in normalizado if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", normalizado.casefold()).strip("_") or "componente"


def novo_id(nome, existentes):
    base = _slug(nome)
    candidato = base
    numero = 2
    while candidato in existentes:
        candidato = f"{base}_{numero}"
        numero += 1
    return candidato


def _arquivo():
    base = os.environ.get("AUTOSEG_BASE")
    if not base:
        return PADRAO
    pasta = Path(base).expanduser()
    destino = pasta / "composicao.yaml"
    if not destino.exists() and PADRAO.exists() and destino.resolve() != PADRAO.resolve():
        pasta.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PADRAO, destino)
    return destino


def instalar():
    """Garante a configuração no AUTOSEG_BASE e devolve o caminho."""
    return _arquivo()


def centavos_de_reais(valor):
    texto = str(valor if valor is not None else "").strip().replace("R$", "").replace(" ", "")
    if not texto:
        return 0
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Valor inválido.") from exc
    if not numero.is_finite() or numero < 0:
        raise ValueError("Valor inválido.")
    return int(numero * 100)


def reais_de_centavos(centavos):
    return float(Decimal(int(centavos or 0)) / 100)


def _numero(valor, rotulo):
    try:
        numero = Decimal(str(valor if valor is not None else 0))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{rotulo} inválido.") from exc
    if not numero.is_finite() or numero < 0:
        raise ValueError(f"{rotulo} inválido.")
    return numero


def _formula_nomes(expr):
    try:
        arvore = ast.parse(str(expr or ""), mode="eval")
    except SyntaxError as exc:
        raise ValueError("Fórmula inválida.") from exc
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, (ast.Attribute, ast.Call, ast.Subscript, ast.Lambda)):
            raise ValueError("A fórmula aceita apenas números, nomes de componentes e + - * / ( ).")
    return nomes


def _avaliar_formula(expr, valores):
    arvore = ast.parse(str(expr or ""), mode="eval")

    def avaliar(no):
        if isinstance(no, ast.Expression):
            return avaliar(no.body)
        if isinstance(no, ast.Constant) and isinstance(no.value, (int, float)) and not isinstance(no.value, bool):
            return Decimal(str(no.value))
        if isinstance(no, ast.Name):
            if no.id not in valores:
                raise ValueError(f"Fórmula referencia componente inexistente ou posterior: {no.id}")
            return Decimal(int(valores[no.id]))
        if isinstance(no, ast.BinOp):
            esquerda, direita = avaliar(no.left), avaliar(no.right)
            if isinstance(no.op, ast.Add):
                return esquerda + direita
            if isinstance(no.op, ast.Sub):
                return esquerda - direita
            if isinstance(no.op, ast.Mult):
                return esquerda * direita
            if isinstance(no.op, ast.Div):
                if direita == 0:
                    raise ValueError("Divisão por zero na fórmula.")
                return esquerda / direita
        if isinstance(no, ast.UnaryOp):
            valor = avaliar(no.operand)
            if isinstance(no.op, ast.USub):
                return -valor
            if isinstance(no.op, ast.UAdd):
                return valor
        raise ValueError("Fórmula inválida.")

    return max(0, _round(avaliar(arvore)))


def _round(valor):
    return int(Decimal(valor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _normalizar_componente(bruto, indice, ids):
    if not isinstance(bruto, dict):
        raise ValueError("Componente inválido.")
    nome = str(bruto.get("nome") or "").strip()
    if not nome:
        raise ValueError("Informe o nome do componente.")
    modo = str(bruto.get("modo") or "").strip()
    if modo not in MODOS:
        raise ValueError(f"Modo de cálculo inválido: {modo}")
    componente_id = str(bruto.get("id") or "").strip() or _slug(nome)
    base_id = componente_id
    numero = 2
    while componente_id in ids:
        componente_id = f"{base_id}_{numero}"
        numero += 1
    ids.add(componente_id)
    valor_bruto = bruto.get("valor", 0)
    if modo == "percentual":
        valor = float(_numero(valor_bruto, "Percentual"))
        if valor > 100:
            raise ValueError("Percentual deve estar entre 0 e 100.")
    elif modo in ("fixo", "hora"):
        valor = int(_round(_numero(valor_bruto, "Valor")))
    else:
        valor = 0
    aplicavel = bruto.get("aplicavel_a") or []
    if isinstance(aplicavel, str):
        aplicavel = [x.strip() for x in aplicavel.split(",") if x.strip()]
    if not isinstance(aplicavel, list):
        raise ValueError("Aplicável a deve ser uma lista de nomes.")
    formula = str(bruto.get("formula") or "").strip()
    if modo == "formula" and not formula:
        raise ValueError("Informe a fórmula do componente.")
    return {
        "id": componente_id,
        "nome": nome,
        "descricao": str(bruto.get("descricao") or "").strip(),
        "modo": modo,
        "valor": valor,
        "formula": formula,
        "horas_padrao": float(_numero(bruto.get("horas_padrao", 0), "Horas padrão")),
        "minimo_centavos": (int(_round(_numero(bruto.get("minimo_centavos", 0), "Mínimo")))
                            if modo == "hora" else 0),
        "aplicavel_a": [str(x).strip() for x in aplicavel if str(x).strip()],
        "ativo": bool(bruto.get("ativo", True)),
        "obrigatorio": bool(bruto.get("obrigatorio", False)),
        "ordem": int(bruto.get("ordem", indice + 1) or indice + 1),
    }


def validar(config):
    if not isinstance(config, dict) or int(config.get("versao", 0) or 0) != 1:
        raise ValueError("composicao.yaml deve começar com versao: 1.")
    componentes = config.get("componentes")
    if not isinstance(componentes, list) or not componentes:
        raise ValueError("A composição precisa de pelo menos um componente.")
    ids = set()
    normalizados = [_normalizar_componente(c, i, ids) for i, c in enumerate(componentes)]
    normalizados.sort(key=lambda c: (c["ordem"], c["id"]))
    ativos = [c for c in normalizados if c["ativo"]]
    if not ativos:
        raise ValueError("A composição precisa de pelo menos um componente ativo.")
    residuais = [c for c in ativos if c["modo"] == "residual"]
    if len(residuais) > 1:
        raise ValueError("Só pode haver um componente residual ativo.")
    posicoes = {c["id"]: i for i, c in enumerate(normalizados)}
    for componente in normalizados:
        if componente["modo"] != "formula":
            continue
        for nome in _formula_nomes(componente["formula"]):
            if nome not in posicoes:
                raise ValueError(f"Fórmula referencia componente inexistente: {nome}")
            if posicoes[nome] >= posicoes[componente["id"]]:
                raise ValueError(
                    f"Fórmula de {componente['id']} só pode usar componentes anteriores.")
    bases_brutas = config.get("bases_percentuais")
    if not isinstance(bases_brutas, dict) or not bases_brutas:
        bases_brutas = {"total": {"nome": "Total da OS", "cobertura": "separado"}}
    bases = {}
    for chave, bruto in bases_brutas.items():
        chave = str(chave or "").strip()
        if not chave:
            raise ValueError("Base de percentuais sem identificador.")
        if not isinstance(bruto, dict):
            raise ValueError(f"Base de percentuais inválida: {chave}")
        cobertura = str(bruto.get("cobertura") or "separado")
        if cobertura not in ("separado", "incluido"):
            raise ValueError(f"Cobertura inválida na base {chave}: {cobertura}")
        componente = str(bruto.get("componente") or "").strip()
        campo = str(bruto.get("campo") or "").strip()
        if componente and campo:
            raise ValueError(f"Base {chave} não pode ter componente e campo ao mesmo tempo.")
        if chave != "total" and not componente and not campo:
            raise ValueError(f"Base {chave} precisa de componente ou campo.")
        bases[chave] = {
            "nome": str(bruto.get("nome") or chave),
            "cobertura": cobertura,
            "componente": componente,
            "campo": campo,
        }
    if "total" not in bases:
        bases["total"] = {"nome": "Total da OS", "cobertura": "separado",
                          "componente": "", "campo": ""}
    padrao = str(config.get("base_percentuais_padrao") or "total")
    if padrao not in bases:
        padrao = "total"
    return {
        "versao": 1,
        "moeda": str(config.get("moeda") or "BRL"),
        "horas_padrao": float(_numero(config.get("horas_padrao", 1.0), "Horas padrão")),
        "componentes": normalizados,
        "bases_percentuais": bases,
        "base_percentuais_padrao": padrao,
    }


def carregar():
    arquivo = _arquivo()
    if not arquivo.is_file():
        raise ValueError("composicao.yaml não encontrado.")
    with arquivo.open(encoding="utf-8") as handle:
        return validar(yaml.safe_load(handle))


def salvar(config):
    config = validar(config)
    destino = _arquivo()
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".yaml.tmp")
    with temporario.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, allow_unicode=True, sort_keys=False)
    os.replace(temporario, destino)
    return destino


def _aplicavel(componente, tipo_servico):
    regras = componente.get("aplicavel_a") or []
    if not regras or not str(tipo_servico or "").strip():
        return True
    alvo = str(tipo_servico).casefold().strip()
    return any(str(regra).casefold().strip() == alvo for regra in regras)


def _escalar(valores, total):
    if total <= 0:
        return {chave: 0 for chave in valores}
    soma = sum(valores.values())
    if soma <= 0:
        chaves = list(valores)
        base, resto = divmod(total, len(chaves))
        return {chave: base + (1 if i < resto else 0) for i, chave in enumerate(chaves)}
    ajustado = {
        chave: _round(Decimal(valor) * Decimal(total) / Decimal(soma))
        for chave, valor in valores.items()
    }
    diferenca = total - sum(ajustado.values())
    if diferenca:
        chave = max(ajustado, key=ajustado.get)
        ajustado[chave] += diferenca
    return ajustado


def calcular(total_centavos=None, materiais_centavos=0, horas=None,
             tipo_servico="", config=None, mao_obra_centavos=None):
    """Calcula a composição; o total sempre confere com a soma dos componentes.

    Quando ``mao_obra_centavos`` é informado, a composição é explícita: o valor
    real de mão de obra e o de materiais são usados e nenhuma taxa fixa,
    percentual ou fórmula padrão é aplicada por cima. O que sobrar (se houver)
    fica no componente residual.
    """
    config = validar(config or carregar())
    componentes = [
        c for c in config["componentes"]
        if c["ativo"] and _aplicavel(c, tipo_servico)
    ]
    if not componentes:
        raise ValueError("Nenhum componente ativo para este tipo de serviço.")
    total = None if total_centavos is None else int(total_centavos)
    if total is not None and total < 0:
        raise ValueError("O valor total não pode ser negativo.")
    materiais = int(materiais_centavos or 0)
    if materiais < 0:
        raise ValueError("O valor de materiais não pode ser negativo.")
    mao_obra = None if mao_obra_centavos is None else int(mao_obra_centavos)
    if mao_obra is not None and mao_obra < 0:
        raise ValueError("O valor de mão de obra não pode ser negativo.")
    if horas in (None, ""):
        horas = None
    else:
        texto_horas = str(horas).strip().replace(" ", "")
        if "," in texto_horas:
            texto_horas = texto_horas.replace(".", "").replace(",", ".")
        try:
            horas = float(texto_horas)
        except (TypeError, ValueError) as exc:
            raise ValueError("Horas inválidas. Use, por exemplo, 1,5.") from exc
    if horas is not None and horas < 0:
        raise ValueError("As horas não podem ser negativas.")

    aviso = ""
    if mao_obra is not None:
        # Composição explícita: materiais e mão de obra reais. Os demais
        # componentes ficam zerados e o residual fecha o valor total.
        valores = {}
        hora_atribuida = False
        for componente in componentes:
            modo = componente["modo"]
            if modo == "materiais":
                valores[componente["id"]] = materiais
            elif modo == "hora" and not hora_atribuida:
                valores[componente["id"]] = mao_obra
                hora_atribuida = True
            else:
                valores[componente["id"]] = 0
        if total is None:
            total = materiais + mao_obra
        residual = next((c for c in componentes if c["modo"] == "residual"), None)
        if residual is not None:
            valores[residual["id"]] = max(
                0, total - sum(v for cid, v in valores.items() if cid != residual["id"]))
        # Fecha o total com exatidão em centavos.
        diferenca = total - sum(valores.values())
        if diferenca:
            alvo = residual["id"] if residual is not None else next(
                (c["id"] for c in componentes if c["modo"] == "hora"), None)
            if alvo is None:
                alvo = next((c["id"] for c in componentes if c["modo"] == "materiais"), None)
            if alvo is not None:
                valores[alvo] = max(0, valores[alvo] + diferenca)
        if sum(valores.values()) != total:
            raise ValueError("Não foi possível fechar a composição no valor total.")
    else:
        valores = {}
        for componente in componentes:
            modo = componente["modo"]
            if modo == "materiais":
                valor = materiais
            elif modo == "fixo":
                valor = int(componente["valor"])
            elif modo == "hora":
                quantidade = horas if horas is not None and horas > 0 else (
                    componente.get("horas_padrao") or config.get("horas_padrao") or 0)
                valor = _round(Decimal(str(quantidade)) * Decimal(int(componente["valor"])))
            elif modo == "formula":
                valor = _avaliar_formula(componente["formula"], valores)
            else:
                valor = 0
            valores[componente["id"]] = max(0, int(valor))

        percentuais = [c for c in componentes if c["modo"] == "percentual"]
        soma_percentual = sum(Decimal(str(c["valor"])) / Decimal(100) for c in percentuais)
        if total is None:
            base = sum(valores[c["id"]] for c in componentes
                       if c["modo"] not in ("percentual", "residual"))
            if soma_percentual >= 1:
                total = base + sum(
                    _round(Decimal(base) * Decimal(str(c["valor"])) / 100)
                    for c in percentuais)
            else:
                total = _round(Decimal(base) / (Decimal(1) - soma_percentual))
            total = max(0, int(total))
        for componente in percentuais:
            valores[componente["id"]] = _round(
                Decimal(total) * Decimal(str(componente["valor"])) / 100)

        residual = next((c for c in componentes if c["modo"] == "residual"), None)
        if residual is not None:
            valores[residual["id"]] = 0
            sem_residual = {c["id"]: valores[c["id"]] for c in componentes if c is not residual}
            resto = total - sum(sem_residual.values())
            if resto >= 0:
                valores[residual["id"]] = resto
            else:
                valores.update(_escalar(sem_residual, total))
                valores[residual["id"]] = 0
                aviso = ("O total informado é menor que a soma dos componentes fixos; "
                         "os valores foram proporcionalizados sem alterar o total.")
        else:
            valores = _escalar(valores, total)
            aviso = ("O total informado foi distribuído proporcionalmente entre os "
                     "componentes configurados, sem alterar o total.")

        diferenca = total - sum(valores.values())
        if diferenca:
            candidato = residual["id"] if residual is not None else max(
                componentes, key=lambda c: valores[c["id"]])["id"]
            valores[candidato] = max(0, valores[candidato] + diferenca)
        diferenca = total - sum(valores.values())
        if diferenca:
            for componente in sorted(componentes, key=lambda c: valores[c["id"]], reverse=True):
                novo = valores[componente["id"]] + diferenca
                if novo >= 0:
                    valores[componente["id"]] = novo
                    break
        if sum(valores.values()) != total:
            raise ValueError("Não foi possível fechar a composição no valor total.")

    saida = []
    for componente in componentes:
        valor = valores[componente["id"]]
        saida.append({
            "id": componente["id"],
            "nome": componente["nome"],
            "descricao": componente["descricao"],
            "modo": componente["modo"],
            "valor_centavos": valor,
            "percentual": round((valor / total * 100), 2) if total else 0.0,
            "obrigatorio": componente["obrigatorio"],
            "ordem": componente["ordem"],
        })
    return {
        "versao": 1,
        "total_centavos": total,
        "componentes": saida,
        "aviso": aviso,
    }


def calcular_os(total_centavos=None, materiais_centavos=0, mao_obra_centavos=0,
                horas=None, tipo_servico="", config=None,
                hora_minima_centavos=10000, base_percentuais=None, campos=None):
    """Composição da OS com bases de percentuais configuráveis.

    A base de cada modo vem de ``bases_percentuais`` no composicao.yaml:
    ``total`` ou uma referência a componente/campo. ``cobertura`` define se os
    percentuais ficam dentro da base (``incluido``) ou em linhas próprias
    (``separado``). O total negociado é autoritativo e nunca recebe desconto
    automático; se não comportar a hora mínima, a operação é recusada com uma
    mensagem clara.
    """
    config = validar(config or carregar())
    componentes = [c for c in config["componentes"]
                   if c["ativo"] and c["modo"] != "residual"
                   and _aplicavel(c, tipo_servico)]
    if not componentes:
        raise ValueError("Nenhum componente ativo para este tipo de serviço.")
    materiais = int(materiais_centavos or 0)
    labor = int(mao_obra_centavos or 0)
    if materiais < 0 or labor < 0:
        raise ValueError("Materiais e mão de obra não podem ser negativos.")
    if labor <= 0:
        return calcular(total_centavos=total_centavos,
                        materiais_centavos=materiais, horas=horas,
                        tipo_servico=tipo_servico, config=config,
                        mao_obra_centavos=labor)
    hora = next((c for c in componentes if c["modo"] == "hora"), None)
    if hora is None or any(c["modo"] == "formula" for c in componentes):
        return calcular(total_centavos=total_centavos,
                        materiais_centavos=materiais, horas=horas,
                        tipo_servico=tipo_servico, config=config,
                        mao_obra_centavos=labor)
    minimo = int(hora.get("minimo_centavos") or hora_minima_centavos or 0)
    labor = max(labor, minimo)
    fixos = [c for c in componentes if c["modo"] == "fixo"]
    percentuais = [c for c in componentes if c["modo"] == "percentual"]
    soma_fixa = sum(int(c["valor"]) for c in fixos)
    soma_percentual = sum(Decimal(str(c["valor"])) / Decimal(100) for c in percentuais)
    if soma_percentual >= 1:
        raise ValueError("Os componentes percentuais somam 100% ou mais.")
    bases = config["bases_percentuais"]
    base_nome = str(base_percentuais or config.get("base_percentuais_padrao") or "total")
    base_cfg = bases.get(base_nome)
    if not base_cfg:
        raise ValueError(f"Base de percentuais desconhecida: {base_nome}")
    cobertura = str(base_cfg.get("cobertura") or "separado")
    base_componente = None
    base_valor = None
    if base_cfg.get("componente"):
        base_componente = next(
            (c for c in componentes if c["id"] == base_cfg["componente"]), None)
        if base_componente is None:
            raise ValueError(f"Componente da base não encontrado: {base_cfg['componente']}")
        modo_base = base_componente["modo"]
        if modo_base == "materiais":
            base_valor = materiais
        elif modo_base == "fixo":
            base_valor = int(base_componente["valor"])
        elif modo_base == "hora":
            base_valor = labor
        else:
            raise ValueError("A base deve ser materiais, um componente fixo ou a hora técnica.")
    elif base_cfg.get("campo"):
        nome_campo = base_cfg["campo"]
        if not isinstance(campos, dict) or nome_campo not in campos:
            raise ValueError(f"Campo da base não informado: {nome_campo}")
        try:
            base_valor = int(Decimal(str(campos[nome_campo])))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"Valor inválido para a base {base_nome}.") from exc
        if base_valor < 0:
            raise ValueError(f"Valor negativo para a base {base_nome}.")
    if cobertura == "incluido" and base_valor is None:
        raise ValueError("Cobertura incluída exige um componente ou campo como base.")

    def percentuais_da_base(valor_base):
        return {c["id"]: _round(Decimal(valor_base) * Decimal(str(c["valor"])) /
                                Decimal(100)) for c in percentuais}

    hora_valor = labor
    if base_valor is None:
        # Base = total: percentuais em linhas próprias.
        if total_centavos is None:
            total = _round((Decimal(materiais + soma_fixa + labor) /
                            (Decimal(1) - soma_percentual)))
            total = ((total + 99) // 100) * 100
            for _ in range(100):
                valores_pct = percentuais_da_base(total)
                hora_valor = total - materiais - soma_fixa - sum(valores_pct.values())
                if hora_valor >= minimo:
                    break
                total += 100
            else:
                raise ValueError("Não foi possível fechar a composição em reais inteiros.")
        else:
            total = max(0, int(total_centavos))
            valores_pct = percentuais_da_base(total)
            hora_valor = total - materiais - soma_fixa - sum(valores_pct.values())
            if hora_valor < minimo:
                raise ValueError(
                    "O total não cobre a hora técnica mínima. Aumente o total, "
                    "reduza materiais/visita ou use a base de visita mínima.")
        top_percentuais = valores_pct
        base_extra = 0
    else:
        valores_pct = percentuais_da_base(base_valor)
        soma_pct = sum(valores_pct.values())
        incluido = cobertura == "incluido"
        # Base já incluída em soma_fixa quando é um componente fixo; quando é
        # campo, precisa entrar explicitamente no total.
        base_extra = (base_valor if incluido and base_componente is None else 0)
        if incluido:
            if total_centavos is None:
                total = materiais + soma_fixa + base_extra + labor
                total = ((total + 99) // 100) * 100
                hora_valor = total - materiais - soma_fixa - base_extra
                if hora_valor < minimo:
                    raise ValueError("A hora técnica ficou abaixo do mínimo.")
            else:
                total = max(0, int(total_centavos))
                hora_valor = total - materiais - soma_fixa - base_extra
                if hora_valor < minimo:
                    raise ValueError(
                        "O total não cobre a hora técnica mínima com esta base. "
                        "Aumente o total, reduza materiais/visita ou troque a base.")
            top_percentuais = {}
        else:
            if total_centavos is None:
                total = materiais + soma_fixa + labor + soma_pct
                total = ((total + 99) // 100) * 100
                hora_valor = total - materiais - soma_fixa - soma_pct
                if hora_valor < minimo:
                    raise ValueError("A hora técnica ficou abaixo do mínimo.")
            else:
                total = max(0, int(total_centavos))
                hora_valor = total - materiais - soma_fixa - soma_pct
                if hora_valor < minimo:
                    raise ValueError(
                        "O total não cobre a hora técnica mínima com esta base. "
                        "Aumente o total, reduza materiais/visita ou troque a base.")
            top_percentuais = valores_pct

    valores = {}
    for componente in componentes:
        modo = componente["modo"]
        if modo == "materiais":
            valores[componente["id"]] = materiais
        elif modo == "fixo":
            valores[componente["id"]] = int(componente["valor"])
        elif modo == "hora":
            valores[componente["id"]] = hora_valor
        elif modo == "percentual":
            if cobertura == "incluido" and base_componente is not None:
                continue
            valores[componente["id"]] = top_percentuais.get(componente["id"], 0)
        else:
            valores[componente["id"]] = 0
    if base_extra:
        valores["__base__"] = base_extra
    diferenca = total - sum(valores.values())
    if diferenca:
        valores[hora["id"]] = max(0, valores[hora["id"]] + diferenca)
    if sum(valores.values()) != total:
        raise ValueError("Não foi possível fechar a composição no valor total.")
    if valores[hora["id"]] < minimo:
        raise ValueError("A hora técnica ficou abaixo do mínimo configurado.")

    saida = []
    for componente in componentes:
        if (componente["modo"] == "percentual"
                and cobertura == "incluido" and base_componente is not None):
            continue
        item = {
            "id": componente["id"],
            "nome": componente["nome"],
            "descricao": componente["descricao"],
            "modo": componente["modo"],
            "valor_centavos": valores[componente["id"]],
            "percentual": round((valores[componente["id"]] / total * 100), 2) if total else 0.0,
            "obrigatorio": componente["obrigatorio"],
            "ordem": componente["ordem"],
        }
        if (base_componente is not None and componente is base_componente
                and cobertura == "incluido"):
            item["filhos"] = [
                {"id": c["id"], "nome": c["nome"], "descricao": c["descricao"],
                 "modo": "percentual", "valor_centavos": valores_pct[c["id"]],
                 "percentual": float(c["valor"]), "obrigatorio": c["obrigatorio"],
                 "ordem": c["ordem"], "base": base_nome}
                for c in percentuais
            ]
        saida.append(item)
    if base_extra:
        saida.append({
            "id": base_nome,
            "nome": base_cfg.get("nome") or base_nome,
            "descricao": "Base configurável de cálculo dos percentuais.",
            "modo": "base",
            "valor_centavos": base_extra,
            "percentual": round((base_extra / total * 100), 2) if total else 0.0,
            "obrigatorio": False,
            "ordem": max((c["ordem"] for c in componentes), default=0) + 1,
            "filhos": [
                {"id": c["id"], "nome": c["nome"], "descricao": c["descricao"],
                 "modo": "percentual", "valor_centavos": valores_pct[c["id"]],
                 "percentual": float(c["valor"]), "obrigatorio": c["obrigatorio"],
                 "ordem": c["ordem"], "base": base_nome}
                for c in percentuais
            ],
        })
    if total:
        soma_pct_saida = round(sum(x["percentual"] for x in saida), 2)
        if soma_pct_saida != 100.0:
            alvo = next((x for x in saida if x["id"] == hora["id"]), None)
            if alvo:
                alvo["percentual"] = round(
                    alvo["percentual"] + (100.0 - soma_pct_saida), 2)
    if cobertura == "incluido":
        aviso = (f"Percentuais calculados sobre {base_cfg.get('nome') or base_nome} e "
                 f"incluídos nela.")
    else:
        aviso = f"Percentuais calculados sobre {base_cfg.get('nome') or base_nome}."
    return {
        "versao": 1,
        "total_centavos": total,
        "componentes": saida,
        "base_percentuais": base_nome,
        "aviso": aviso,
    }


def declarativa(total_centavos, blocos, config=None):
    """Composição declarativa (pai + filhos) definida no YAML da OS.

    Cada bloco traz ``id`` e ``valor`` (R$) ou ``percentual``; opcionalmente
    ``filhos``. O pai pode ser percentual do total; os filhos podem ser valor,
    percentual do pai ou ``residual: true`` para fechar o pai. Só os
    componentes declarados entram na composição.
    """
    config = validar(config or carregar())
    catalogo = {c["id"]: c for c in config["componentes"]}
    total = int(total_centavos or 0)
    if total < 0:
        raise ValueError("O valor total não pode ser negativo.")
    if not isinstance(blocos, list) or not blocos:
        raise ValueError("Informe ao menos um componente na composição.")

    def _normalizar(entrada, base_centavos, rotulo):
        if not isinstance(entrada, dict):
            raise ValueError(f"{rotulo}: componente inválido.")
        cid = str(entrada.get("id") or "").strip()
        if cid not in catalogo:
            raise ValueError(f"{rotulo}: componente desconhecido: {cid or '(vazio)'}")
        cfg = catalogo[cid]
        if entrada.get("valor") not in (None, ""):
            valor = centavos_de_reais(entrada["valor"])
        elif entrada.get("percentual") not in (None, ""):
            try:
                pct = Decimal(str(entrada["percentual"]))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"{rotulo}: percentual inválido.") from exc
            if not pct.is_finite() or pct < 0 or pct > 100:
                raise ValueError(f"{rotulo}: percentual fora de 0–100.")
            valor = _round(Decimal(base_centavos) * pct / 100)
        elif entrada.get("residual"):
            valor = None
        else:
            raise ValueError(f"{rotulo}: informe valor, percentual ou residual.")
        return cid, cfg, valor, entrada

    saida = []
    soma_pais = 0
    for indice_pai, entrada_pai in enumerate(blocos, start=1):
        cid_pai, cfg_pai, valor_pai, entrada_norm = _normalizar(
            entrada_pai, total, f"Componente {indice_pai}")
        if valor_pai is None:
            raise ValueError(f"Componente {indice_pai}: o pai não pode ser residual.")
        valor_pai = max(0, int(valor_pai))
        soma_pais += valor_pai

        valores_filhos = []
        if entrada_norm.get("filhos"):
            lista_filhos = entrada_norm["filhos"]
            if not isinstance(lista_filhos, list) or len(lista_filhos) > 100:
                raise ValueError(f"Componente {indice_pai}: filhos inválidos.")
            ocupado = 0
            residuais = []
            for indice_filho, entrada_filho in enumerate(lista_filhos, start=1):
                cid_f, cfg_f, valor_f, _ = _normalizar(
                    entrada_filho, valor_pai,
                    f"Filho {indice_filho} de {cid_pai}")
                if valor_f is None:
                    residuais.append((cid_f, cfg_f))
                    continue
                valor_f = max(0, int(valor_f))
                ocupado += valor_f
                valores_filhos.append((cid_f, cfg_f, valor_f))
            disponivel = valor_pai - ocupado
            if disponivel < 0:
                raise ValueError(
                    f"Componente {cid_pai}: os filhos excedem o valor do pai.")
            for posicao, (cid_f, cfg_f) in enumerate(residuais):
                valores_filhos.append((cid_f, cfg_f, disponivel if posicao == 0 else 0))
            if not residuais and disponivel > 0:
                if not valores_filhos:
                    raise ValueError(f"Componente {cid_pai}: informe os filhos.")
                cid_f, cfg_f, valor_f = valores_filhos[-1]
                valores_filhos[-1] = (cid_f, cfg_f, valor_f + disponivel)
            if sum(valor for _, _, valor in valores_filhos) != valor_pai:
                raise ValueError(
                    f"Componente {cid_pai}: a soma dos filhos não fecha o valor do pai.")

        filhos = []
        for cid_f, cfg_f, valor_f in valores_filhos:
            filhos.append({
                "id": cid_f,
                "nome": cfg_f["nome"],
                "descricao": cfg_f["descricao"],
                "modo": cfg_f["modo"],
                "valor_centavos": int(valor_f),
                "percentual": round((valor_f / valor_pai * 100), 2) if valor_pai else 0.0,
                "obrigatorio": cfg_f["obrigatorio"],
                "ordem": len(filhos) + 1,
            })

        saida.append({
            "id": cid_pai,
            "nome": cfg_pai["nome"],
            "descricao": cfg_pai["descricao"],
            "modo": cfg_pai["modo"],
            "valor_centavos": valor_pai,
            "percentual": round((valor_pai / total * 100), 2) if total else 0.0,
            "obrigatorio": cfg_pai["obrigatorio"],
            "ordem": indice_pai,
            "filhos": filhos,
        })

    if soma_pais != total:
        raise ValueError(
            f"A soma dos componentes ({soma_pais / 100:.2f}) não fecha com o total ({total / 100:.2f}).")
    return {
        "versao": 1,
        "total_centavos": total,
        "declarativa": True,
        "componentes": saida,
        "aviso": "",
    }


def para_json(composicao):
    return json.dumps(composicao, ensure_ascii=False, sort_keys=True)


def de_json(texto):
    if not texto:
        return None
    try:
        dados = json.loads(texto)
    except (TypeError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def multiplicar(composicao, fator):
    fator = int(fator or 1)
    if fator <= 1:
        return deepcopy(composicao)
    saida = deepcopy(composicao)
    saida["total_centavos"] = int(saida.get("total_centavos") or 0) * fator
    for componente in saida.get("componentes", []):
        componente["valor_centavos"] = int(componente.get("valor_centavos") or 0) * fator
    return saida


def _banco_padrao():
    if os.environ.get("GESTAO_BANCO"):
        return os.environ["GESTAO_BANCO"]
    base = os.environ.get("AUTOSEG_BASE") or str(Path(__file__).resolve().parent)
    return str(Path(base) / "dados.db")


def instalar_banco(banco=None):
    """Adiciona colunas de composição sem tocar em dados existentes."""
    caminho = str(banco or _banco_padrao())
    if not Path(caminho).is_file():
        return
    with sqlite3.connect(caminho, timeout=20) as conexao:
        for tabela, coluna, definicao in (
            ("catalogo_servicos", "tempo_horas", "REAL DEFAULT 0"),
            ("catalogo_servicos", "composicao_json", "TEXT"),
            ("ordens_servico", "tempo_horas", "REAL DEFAULT 0"),
            ("ordens_servico", "composicao_json", "TEXT"),
            ("ordens_servico", "base_percentuais", "TEXT NOT NULL DEFAULT 'total'"),
        ):
            colunas = [linha[1] for linha in conexao.execute(f"PRAGMA table_info({tabela})")]
            if colunas and coluna not in colunas:
                conexao.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")


def recalcular_tudo(banco=None):
    """Recalcula serviços e OS abertas, preservando composições autoritativas.

    OSs com base modular são recalculadas na mesma base. Composições
    declarativas e OSs que não fecham com a nova configuração são mantidas e
    contadas em ``preservadas``.
    """
    caminho = str(banco or _banco_padrao())
    if not Path(caminho).is_file():
        return {"servicos": 0, "os": 0, "preservadas": 0}
    instalar_banco(caminho)
    config = carregar()
    servicos = ordens = preservadas = 0
    with sqlite3.connect(caminho, timeout=20) as conexao:
        for linha in conexao.execute(
                """SELECT id,nome,preco_servico_centavos,materiais_json,tempo_horas
                   FROM catalogo_servicos"""):
            identificador, nome, preco, materiais_json, tempo = linha
            try:
                materiais = json.loads(materiais_json or "[]")
                total_materiais = sum(
                    int(Decimal(str(m.get("quantidade", 0))) * int(m.get("preco_centavos", 0)))
                    for m in materiais)
            except (ValueError, TypeError, InvalidOperation):
                total_materiais = 0
            total = int(preco or 0) + total_materiais
            composicao = calcular(
                total_centavos=total, materiais_centavos=total_materiais,
                horas=tempo, tipo_servico=nome or "", config=config,
                mao_obra_centavos=int(preco or 0))
            conexao.execute(
                "UPDATE catalogo_servicos SET composicao_json=? WHERE id=?",
                (para_json(composicao), identificador))
            servicos += 1
        for linha in conexao.execute(
                """SELECT id,valor_mao_obra,valor_total,valor_materiais,tempo_horas,
                          base_percentuais,composicao_json
                   FROM ordens_servico WHERE status IN ('Aberta','Iniciada','Pendente')"""):
            (identificador, mao_reais, total_reais, materiais_reais, tempo,
             base, comp_json) = linha
            existente = de_json(comp_json)
            if isinstance(existente, dict) and existente.get("declarativa"):
                # Composição declarativa não é recalculável pela configuração
                # global; preservar os componentes definidos no YAML.
                preservadas += 1
                continue
            try:
                if (str(base or "").strip()
                        and isinstance(existente, dict)
                        and existente.get("base_percentuais")):
                    composicao = calcular_os(
                        total_centavos=centavos_de_reais(total_reais),
                        materiais_centavos=centavos_de_reais(materiais_reais),
                        mao_obra_centavos=centavos_de_reais(mao_reais),
                        horas=tempo, base_percentuais=str(base),
                        config=config)
                else:
                    composicao = calcular(
                        total_centavos=centavos_de_reais(total_reais),
                        materiais_centavos=centavos_de_reais(materiais_reais),
                        horas=tempo, config=config,
                        mao_obra_centavos=centavos_de_reais(mao_reais))
            except ValueError:
                # A nova configuração não fecha esta OS; manter a composição
                # anterior em vez de gravar um valor inconsistente.
                preservadas += 1
                continue
            conexao.execute(
                "UPDATE ordens_servico SET composicao_json=? WHERE id=?",
                (para_json(composicao), identificador))
            ordens += 1
    return {"servicos": servicos, "os": ordens, "preservadas": preservadas}
