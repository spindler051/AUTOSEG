"""In-process application service backed by the existing SQLite modules.

This is the first migration slice: clients, dashboard and portal summary
reads. The adapter keeps current queries, validation and last-write-wins
behavior untouched while giving the GTK shell a transport-neutral contract.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

import completude
import prestadores_ext as ext
from banco import BANCO
from integracao import clientes as clientes_core
from repositorios import ordens as ordens_repo
from versao_app import versao_local
from workaholic.domain.errors import ConflictError as WorkaholicConflictError
from workaholic.domain.errors import NotFoundError as WorkaholicNotFoundError

from application.contracts import (
    Cliente,
    ClienteResumo,
    ConflitoError,
    Health,
    LancamentoFinanceiro,
    NaoEncontradoError,
    OSResumo,
    ResumoFinanceiro,
    ResumoInicio,
    ResumoPortal,
    SolicitacaoPortal,
    ValidacaoError,
)


class LocalService:
    """Application service that runs in the desktop process, without HTTP."""

    mode = 'local'

    def __init__(self, banco=None):
        self.banco = str(banco or BANCO)

    def health(self) -> Health:
        try:
            with ext.db(self.banco) as conexao:
                conexao.execute('SELECT 1').fetchone()
        except Exception as erro:
            return Health(
                status='degraded',
                version=versao_local(),
                mode=self.mode,
                database=self.banco,
                capabilities=self._capabilities(),
                detail=str(erro),
            )
        return Health(
            status='ok',
            version=versao_local(),
            mode=self.mode,
            database=self.banco,
            capabilities=self._capabilities(),
        )

    def resumo_inicio(self) -> ResumoInicio:
        clientes = clientes_core.contar_ativos(self.banco)
        os_resumo = ordens_repo.resumo(self.banco)
        financeiro = ordens_repo.financeiro_resumo(self.banco)
        return ResumoInicio(
            clientes_ativos=int(clientes),
            os_abertas=os_resumo['abertas'],
            os_iniciadas=os_resumo['iniciadas'],
            os_pendentes=os_resumo['pendentes'],
            financeiro_recebido=financeiro['recebido'],
            financeiro_a_receber=financeiro['a_receber'],
        )

    def listar_os_ativas(self, termo: str = '') -> list[OSResumo]:
        with ext.db(self.banco) as conexao:
            registros = conexao.execute(
                """SELECT os.id,os.numero_os,os.cliente_id,c.nome cliente,os.data_abertura,os.valor_total,
                          os.descricao,os.observacoes,os.forma_pagamento,os.urgencia,os.origem,
                          (SELECT GROUP_CONCAT(p.nome, ', ') FROM os_prestadores op
                             JOIN prestadores p ON p.id=op.prestador_id
                             WHERE op.os_id=os.id AND op.ativo=1) prestadores,
                          resp.nome responsavel_atual,os.tecnico tecnico_legado,os.status,
                          os.dados_incompletos
                   FROM ordens_servico os
                   JOIN clientes c ON c.id=os.cliente_id
                   LEFT JOIN os_responsaveis r ON r.os_id=os.id
                   LEFT JOIN prestadores resp ON resp.id=r.prestador_id
                   WHERE os.status IN ('Aberta','Iniciada','Pendente') ORDER BY os.id DESC""").fetchall()
        busca = str(termo or '').casefold().strip()
        resultado = []
        for linha in registros:
            texto = ' '.join(str(linha[chave] or '') for chave in (
                'numero_os', 'cliente', 'prestadores', 'responsavel_atual', 'status',
                'forma_pagamento', 'tecnico_legado')).casefold()
            if busca and busca not in texto:
                continue
            responsavel = (str(linha['responsavel_atual']) + ' (atual)'
                           if linha['responsavel_atual'] else 'Não atribuído')
            if linha['prestadores']:
                responsavel += ' | Equipe: ' + str(linha['prestadores'])
            elif linha['tecnico_legado']:
                responsavel += ' | Técnico: ' + str(linha['tecnico_legado'])
            dados = dict(linha)
            dados['tecnico'] = linha['tecnico_legado']
            resultado.append(OSResumo(
                id=int(linha['id']),
                numero_os=str(linha['numero_os'] or ''),
                cliente=str(linha['cliente'] or ''),
                data_abertura=str(linha['data_abertura'] or ''),
                valor_total=float(linha['valor_total'] or 0),
                forma_pagamento=str(linha['forma_pagamento'] or ''),
                origem='Portal' if (linha['origem'] or 'App') == 'Portal' else 'App',
                responsavel=responsavel,
                status=str(linha['status'] or ''),
                incompleto=bool(completude.os_faltantes(dados)),
            ))
        return resultado

    def resumo_financeiro(self) -> ResumoFinanceiro:
        with ext.db(self.banco) as conexao:
            linha = conexao.execute(
                """SELECT COALESCE(SUM(CASE WHEN status='Aguardando pagamento' THEN valor ELSE 0 END),0) pendente,
                          COALESCE(SUM(CASE WHEN status='Recebido' THEN valor ELSE 0 END),0) recebido
                   FROM financeiro""").fetchone()
        return ResumoFinanceiro(
            a_receber=float(linha['pendente'] or 0),
            recebido=float(linha['recebido'] or 0),
        )

    def listar_financeiro(
        self, termo: str = ''
    ) -> list[LancamentoFinanceiro]:
        with ext.db(self.banco) as conexao:
            registros = conexao.execute(
                """SELECT f.id,os.numero_os,c.nome cliente,f.valor,f.forma_pagamento,
                          f.status,f.vencimento
                   FROM financeiro f JOIN ordens_servico os ON os.id=f.os_id
                   JOIN clientes c ON c.id=f.cliente_id ORDER BY f.id DESC""").fetchall()
        busca = str(termo or '').casefold().strip()
        resultado = []
        for linha in registros:
            texto = ' '.join(str(linha[chave] or '') for chave in (
                'numero_os', 'cliente', 'forma_pagamento', 'status', 'vencimento'
            )).casefold()
            if busca and busca not in texto:
                continue
            resultado.append(LancamentoFinanceiro(
                id=int(linha['id']),
                numero_os=str(linha['numero_os'] or ''),
                cliente=str(linha['cliente'] or ''),
                valor=float(linha['valor'] or 0),
                forma_pagamento=str(linha['forma_pagamento'] or ''),
                status=str(linha['status'] or ''),
                vencimento=str(linha['vencimento'] or ''),
            ))
        return resultado

    def marcar_recebido(self, lancamento_id: int) -> None:
        with ext.db(self.banco) as conexao:
            cursor = conexao.execute(
                "UPDATE financeiro SET status='Recebido',data_pagamento=? WHERE id=?",
                (datetime.now().strftime('%d/%m/%Y'), int(lancamento_id)))
            if cursor.rowcount != 1:
                raise NaoEncontradoError(
                    'Lançamento financeiro não encontrado.',
                    'Financeiro')

    def resumo_portal(self) -> ResumoPortal:
        dados = ordens_repo.resumo_portal(self.banco)
        return ResumoPortal(
            total=dados['total'],
            andamento=dados['andamento'],
            concluidas=dados['concluidas'],
        )

    def listar_solicitacoes_portal(
        self, limite: int = 50
    ) -> list[SolicitacaoPortal]:
        return [
            SolicitacaoPortal(
                id=int(linha['id']),
                numero_os=str(linha.get('numero_os') or ''),
                cliente=str(linha.get('cliente') or ''),
                data_abertura=str(linha.get('data_abertura') or ''),
                urgencia=str(linha.get('urgencia') or 'Normal'),
                status=str(linha.get('status') or ''),
            )
            for linha in ordens_repo.listar_solicitacoes_portal(
                self.banco, limite=limite)
        ]

    def listar_clientes(self, termo: str = '') -> list[ClienteResumo]:
        return [self._resumo(registro)
                for registro in clientes_core.listar(termo, banco=self.banco)]

    def obter_cliente(self, cliente_id: int) -> Cliente | None:
        registro = clientes_core.obter(cliente_id, banco=self.banco)
        if registro is None:
            return None
        return self._cliente(registro)

    def salvar_cliente(
        self, cliente_id: int | None, dados: Mapping[str, Any]
    ) -> Cliente:
        try:
            registro = clientes_core.salvar(
                cliente_id, dict(dados), banco=self.banco)
        except clientes_core.ErroCliente as erro:
            raise ValidacaoError(str(erro), erro.titulo) from erro
        except WorkaholicConflictError as erro:
            raise ConflitoError(
                str(erro), 'Cadastro alterado por outra sessão') from erro
        except WorkaholicNotFoundError as erro:
            raise NaoEncontradoError(str(erro), 'Cliente não encontrado') from erro
        except ValueError as erro:
            raise ValidacaoError(str(erro)) from erro
        return self._cliente(registro)

    @staticmethod
    def _capabilities() -> tuple[str, ...]:
        return ('health', 'resumo_inicio', 'os.listar_ativas',
                'resumo_financeiro', 'financeiro.listar', 'financeiro.receber',
                'resumo_portal', 'solicitacoes_portal',
                'clientes.listar', 'clientes.obter', 'clientes.salvar')

    @staticmethod
    def _resumo(registro) -> ClienteResumo:
        campos = dict(registro.get('fields') or {})
        return ClienteResumo(
            id=int(registro.get('id') or 0),
            nome=str(campos.get('nome') or ''),
            documento=str(campos.get('documento') or ''),
            cidade=str(campos.get('cidade') or ''),
            telefone=str(campos.get('telefone') or ''),
            status=str(campos.get('status') or ''),
            incompleto=completude.cliente_faltantes(campos),
        )

    @staticmethod
    def _cliente(registro) -> Cliente:
        campos = dict(registro.get('fields') or {})
        return Cliente(
            id=int(registro.get('id') or 0),
            versao=int(registro.get('version') or 1),
            campos=campos,
            incompleto=completude.cliente_faltantes(campos),
        )
