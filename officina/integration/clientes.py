"""Clientes do AUTOSEG sobre o núcleo genérico Workaholic.

O Workaholic cuida de validação, CRUD e versionamento. Este adaptador mapeia
o registro genérico para a tabela legada ``clientes`` e mantém as regras
específicas do AUTOSEG: CPF/CNPJ, completude e sincronização PJ.

Legacy writers (portal, desktop, importers) still bypass this adapter and do
not increment ``versao``. UI writes therefore remain last-write-wins; direct
adapter callers use optimistic locking. Those writers must be migrated before
the legacy path can be removed.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from workaholic.application.service import RecordService
from workaholic.domain.errors import ConflictError, NotFoundError
from workaholic.domain.schema import AppSchema
from workaholic.infrastructure.repositories import Repository

from officina.core import cadastros_v9 as cad9
from officina.core import completude
from officina.core import prestadores_ext as ext
from officina.core.banco import BANCO

SCHEMA = Path(__file__).resolve().parent / "schema_autoseg.yaml"


@lru_cache(maxsize=1)
def _schema():
    with SCHEMA.open(encoding="utf-8") as arquivo:
        return AppSchema.from_dict(yaml.safe_load(arquivo))


CAMPOS = tuple(_schema().entities["cliente"].fields)


class ErroCliente(ValueError):
    """Erro de cadastro com o título que a interface já exibe."""

    def __init__(self, titulo, mensagem):
        super().__init__(mensagem)
        self.titulo = titulo


class RepositorioClientes(Repository):
    """Mapeia o registro genérico para a tabela ``clientes`` existente."""

    def __init__(self, banco=None):
        self.banco = str(banco or BANCO)

    def get(self, entity, id):
        self._validar(entity)
        try:
            identificador = int(id)
        except (TypeError, ValueError):
            return None
        with ext.db(self.banco) as conexao:
            linha = conexao.execute(
                "SELECT * FROM clientes WHERE id=?", (identificador,)).fetchone()
        return self._registro(linha) if linha else None

    def list(self, entity):
        self._validar(entity)
        with ext.db(self.banco) as conexao:
            linhas = conexao.execute(
                "SELECT * FROM clientes ORDER BY nome").fetchall()
        return [self._registro(linha) for linha in linhas]

    def put(self, entity, record, expected_version):
        self._validar(entity)
        if record.get("archived"):
            record["fields"]["status"] = "Inativo"
        valores = [
            int(bool(record["fields"].get(campo))) if campo == "dados_incompletos"
            else record["fields"].get(campo, "")
            for campo in CAMPOS
        ]
        agora = ext.agora()
        with ext.db(self.banco) as conexao:
            if expected_version is None:
                cursor = conexao.execute(
                    f"INSERT INTO clientes ({','.join(CAMPOS)}, criado_em, atualizado_em, versao) "
                    f"VALUES ({','.join('?' for _ in CAMPOS)}, ?, ?, 1)",
                    valores + [agora, agora])
                record["id"] = str(cursor.lastrowid)
                record["version"] = 1
                record["created_at"] = agora
                record["updated_at"] = agora
                self._sincronizar_pj(conexao, cursor.lastrowid, record)
                return
            cursor = conexao.execute(
                f"UPDATE clientes SET {','.join(f'{campo}=?' for campo in CAMPOS)}, "
                "versao=versao+1, atualizado_em=? WHERE id=? AND versao=?",
                valores + [agora, int(record["id"]), int(expected_version)])
            if cursor.rowcount != 1:
                raise ConflictError(
                    "Cliente alterado por outra sessão; recarregue e tente novamente.")
            record["version"] = int(expected_version) + 1
            record["updated_at"] = agora
            self._sincronizar_pj(conexao, int(record["id"]), record)

    def delete(self, entity, id, expected_version):
        self._validar(entity)
        raise ValueError("Exclusão física não permitida; arquive o cliente.")

    @staticmethod
    def _validar(entity):
        if entity != "cliente":
            raise ValueError(f"Entidade ainda não migrada: {entity}")

    @staticmethod
    def _sincronizar_pj(conexao, cliente_id, record):
        campos = record["fields"]
        if (not record.get("archived")
                and campos.get("tipo_pessoa") == "Jurídica"
                and campos.get("status") != "Inativo"
                and str(campos.get("nome") or "").strip()):
            cad9.sincronizar_cliente_pj(conexao, cliente_id)

    @staticmethod
    def _registro(linha):
        campos = {
            campo: bool(linha[campo]) if campo == "dados_incompletos"
            else (linha[campo] if linha[campo] is not None else "")
            for campo in CAMPOS
        }
        criado = linha["criado_em"] or ""
        return {
            "id": str(linha["id"]),
            "entity": "cliente",
            "version": int(linha["versao"] or 1),
            "state": None,
            "fields": campos,
            "archived": linha["status"] == "Inativo",
            "created_at": criado,
            "updated_at": linha["atualizado_em"] or criado,
        }


def _servico(banco=None):
    return RecordService(_schema(), RepositorioClientes(banco))


def listar(termo="", banco=None):
    registros = _servico(banco).list("cliente", include_archived=True)
    termo = str(termo or "").casefold().strip()
    if termo:
        registros = [
            registro for registro in registros
            if termo in " ".join(
                str(registro["fields"].get(campo) or "")
                for campo in ("nome", "documento", "cidade")).casefold()
        ]
    return sorted(registros,
                  key=lambda registro: (registro["fields"].get("nome") or "").casefold())


def obter(cliente_id, banco=None):
    try:
        return _servico(banco).get("cliente", str(cliente_id))
    except NotFoundError:
        return None


# ---------------------------------------------------------------------------
# Leituras legadas usadas pelos portais/GTK.
#
# O SQL fica nesta camada de integração, não no handler HTTP nem na janela.
# As consultas preservam exatamente os filtros, ordem, limites e colunas do
# código anterior; a apresentação continua na interface.
# ---------------------------------------------------------------------------

def contar_ativos(banco=None):
    """Quantidade de clientes com status diferente de Inativo."""
    with ext.db(banco or BANCO) as conexao:
        return int(conexao.execute(
            "SELECT COUNT(*) FROM clientes WHERE status NOT IN ('Inativo','A definir')").fetchone()[0])


def listar_paginado(termo="", limite=40, offset=0, banco=None):
    """Lista paginada da tela /clientes do Portal do Prestador.

    Retorna ``(total, linhas)``. O filtro por documento também aceita
    CPF/CNPJ formatado, comparando somente os dígitos.
    """
    busca = str(termo or "").strip()[:110]
    filtro = " WHERE status!='A definir'"
    params = []
    if busca:
        filtro += (" AND (nome LIKE ? ESCAPE '!' OR documento LIKE ? ESCAPE '!' "
                   "OR cidade LIKE ? ESCAPE '!' OR email LIKE ? ESCAPE '!' "
                   "OR replace(replace(replace(documento,'.',''),'/',''),'-','') "
                   "LIKE ? ESCAPE '!') ")
        termo_like = '%' + busca.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        documentos = cad9.digitos(busca)
        params = [termo_like] * 4 + [
            '%' + documentos + '%' if documentos else 'documento_nunca_corresponde']
    with ext.db(banco or BANCO) as conexao:
        total = int(conexao.execute(
            'SELECT COUNT(*) FROM clientes' + filtro, params).fetchone()[0])
        linhas = conexao.execute(
            'SELECT id,nome,documento,cidade,telefone,email,status,dados_incompletos '
            'FROM clientes' + filtro + ' ORDER BY nome LIMIT ? OFFSET ?',
            params + [int(limite), int(offset)]).fetchall()
    return total, [dict(linha) for linha in linhas]


def listar_para_selecao(banco=None, limite=500):
    """Clientes ativos para selects de orçamento/OS."""
    with ext.db(banco or BANCO) as conexao:
        linhas = conexao.execute(
            "SELECT id,nome,documento,dados_incompletos FROM clientes "
            "WHERE status NOT IN ('Inativo','A definir') "
            "ORDER BY nome LIMIT ?", (int(limite),)).fetchall()
    return [dict(linha) for linha in linhas]


def listar_para_os(banco=None):
    """Clientes ativos para o seletor do formulário completo de OS."""
    with ext.db(banco or BANCO) as conexao:
        linhas = conexao.execute(
            "SELECT id,nome,cidade,bairro,endereco,numero,dados_incompletos FROM clientes "
            "WHERE status NOT IN ('Inativo','A definir') ORDER BY nome").fetchall()
    return [dict(linha) for linha in linhas]


def obter_linha(cliente_id, banco=None):
    """Linha completa para o formulário de edição legado.

    Diferente de ``obter``, preserva todas as colunas da tabela, incluindo
    observações e campos que não fazem parte do schema genérico do Workaholic.
    """
    with ext.db(banco or BANCO) as conexao:
        linha = conexao.execute(
            'SELECT * FROM clientes WHERE id=?', (int(cliente_id),)).fetchone()
    return dict(linha) if linha else None


def obter_para_orcamento(cliente_id, banco=None):
    """Cliente ativo e resumido para validar um orçamento."""
    with ext.db(banco or BANCO) as conexao:
        linha = conexao.execute(
            "SELECT id,nome,documento FROM clientes WHERE id=? AND status!='Inativo'",
            (int(cliente_id),)).fetchone()
    return dict(linha) if linha else None


def obter_resumo_ativo(cliente_id, banco=None):
    """Cliente ativo para o cartão de abertura rápida de OS."""
    with ext.db(banco or BANCO) as conexao:
        linha = conexao.execute(
            "SELECT id,nome,tipo_pessoa,cidade,bairro,email FROM clientes "
            "WHERE id=? AND status!='Inativo'", (int(cliente_id),)).fetchone()
    return dict(linha) if linha else None


def buscar_rapida(termo="", banco=None, limite=100):
    """Busca da abertura rápida de OS: nome, documento, cidade ou e-mail."""
    termo = str(termo or "").strip()[:120]
    with ext.db(banco or BANCO) as conexao:
        if termo:
            esc_like = termo.replace('!', '!!').replace('%', '!%').replace('_', '!_')
            documentos = cad9.digitos(termo)
            filtro = ("WHERE status NOT IN ('Inativo','A definir') AND (nome LIKE ? ESCAPE '!' "
                      "OR documento LIKE ? ESCAPE '!' OR cidade LIKE ? ESCAPE '!' "
                      "OR email LIKE ? ESCAPE '!'")
            params = ['%' + esc_like + '%'] * 4
            if documentos:
                filtro += " OR documento LIKE ? ESCAPE '!'"
                params.append('%' + documentos + '%')
            filtro += ")"
            linhas = conexao.execute(
                "SELECT id,nome,tipo_pessoa,cidade,bairro,email,documento,dados_incompletos "
                "FROM clientes " + filtro + " ORDER BY nome LIMIT ?",
                params + [int(limite)]).fetchall()
        else:
            linhas = conexao.execute(
                "SELECT id,nome,tipo_pessoa,cidade,bairro,email,documento,dados_incompletos "
                "FROM clientes WHERE status NOT IN ('Inativo','A definir') ORDER BY nome LIMIT ?",
                (int(limite),)).fetchall()
    return [dict(linha) for linha in linhas]


def buscar_por_nome_exato(nome, banco=None):
    """Return the first active client with exactly this display name."""
    nome = str(nome or "").strip()
    if not nome:
        return None
    with ext.db(banco or BANCO) as conexao:
        linha = conexao.execute(
            "SELECT id,nome FROM clientes WHERE status NOT IN ('Inativo','A definir') "
            "AND lower(nome)=lower(?) ORDER BY id LIMIT 1", (nome,)).fetchone()
    return dict(linha) if linha else None


def criar_provisorio(nome, banco=None):
    """Create a minimal client, explicitly marked as incomplete.

    Used when a provider types a new client name directly in the OS form.
    The record can be completed later; does not create an organization.
    """
    nome = str(nome or "").strip()[:250]
    if len(nome) < 2:
        raise ErroCliente("Cliente não criado", "Informe ao menos 2 caracteres no nome.")
    existente = buscar_por_nome_exato(nome, banco=banco)
    if existente:
        return int(existente["id"])
    registro = salvar(None, {
        "nome": nome,
        "status": "Ativo",
        "provisorio": True,
    }, banco=banco)
    return int(registro["id"])


def salvar(cliente_id, dados, banco=None):
    servico = _servico(banco)
    existente = None
    if cliente_id is not None:
        existente = obter(cliente_id, banco)
        if existente is None:
            raise ErroCliente("Cadastro não salvo", "Cliente não encontrado.")
    tipo = str(dados.get("tipo_pessoa") or "Jurídica")
    documento = cad9.digitos(dados.get("documento"))
    tipo_anterior = existente["fields"].get("tipo_pessoa") if existente else None
    documento_anterior = (
        cad9.digitos(existente["fields"].get("documento")) if existente else "")
    if existente is None or tipo != tipo_anterior or documento != documento_anterior:
        try:
            documento = cad9.validar_documento(tipo, documento)
        except ValueError as erro:
            raise ErroCliente("Documento inválido", str(erro)) from erro
        if documento:
            with ext.db(banco or BANCO) as conexao:
                duplicado = cad9.buscar_documento_duplicado(
                    conexao, documento, cliente_id)
            if duplicado:
                raise ErroCliente(
                    "Documento duplicado",
                    f"CPF/CNPJ já cadastrado para {duplicado['nome']}.")
    campos = {}
    for campo in CAMPOS:
        if campo == "documento":
            campos[campo] = documento
        elif campo == "tipo_pessoa":
            campos[campo] = tipo
        elif campo == "status":
            campos[campo] = str(dados.get("status") or "Ativo")
        elif campo == "dados_incompletos":
            continue
        else:
            valor = dados.get(campo, "")
            campos[campo] = "" if valor is None else str(valor)
    campos["dados_incompletos"] = bool(
        dados.get("provisorio") or dados.get("dados_incompletos_provisorio")
        or completude.cliente_faltantes(campos))
    if existente is None:
        return servico.create("cliente", campos)
    return servico.update("cliente", str(cliente_id), campos,
                          expected_version=existente["version"])
