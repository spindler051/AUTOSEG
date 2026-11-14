"""In-process application service backed by the existing SQLite modules.

This is the first migration slice: clients, dashboard and portal summary
reads. The adapter keeps current queries, validation and last-write-wins
behavior untouched while giving the GTK shell a transport-neutral contract.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from officina.core import atendimento_os as aten
from officina.core import cadastros_v9 as cad9
from officina.core import catalogo_servicos as catalogo
from officina.core import completude
from officina.core import composicao
from officina.core import empresa_financeiro as empresa
from officina.core import estoque_materiais as estoque
from officina.core import fluxo_os as fluxo
from officina.core import portal_negocios as neg
from officina.core import prestadores_ext as ext
from officina.core.banco import BANCO
from officina.integration import clientes as clientes_core
from officina.repositories import ordens as ordens_repo
from officina.core.versao_app import versao_local
from workaholic.domain.errors import ConflictError as WorkaholicConflictError
from workaholic.domain.errors import NotFoundError as WorkaholicNotFoundError

from officina.application.contracts import (
    ChamadoPJ,
    Cliente,
    ClienteOpcao,
    ClienteResumo,
    ConflitoError,
    Health,
    HistoricoOS,
    LancamentoFinanceiro,
    NaoEncontradoError,
    OrganizacaoPJ,
    OSInput,
    OSOpcao,
    OSResultado,
    OSResumo,
    PrestadorResumo,
    RelatorioOS,
    ResumoFinanceiro,
    ResumoHistorico,
    ResumoInicio,
    ResumoPortal,
    SindicoContato,
    SolicitacaoPortal,
    ValidacaoError,
    VinculoPJ,
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

    _SQL_OS_RESUMO = """SELECT os.id,os.numero_os,os.cliente_id,c.nome cliente,
                  os.data_abertura,os.valor_total,os.descricao,os.observacoes,
                  os.forma_pagamento,os.urgencia,os.origem,
                  (SELECT GROUP_CONCAT(p.nome, ', ') FROM os_prestadores op
                     JOIN prestadores p ON p.id=op.prestador_id
                     WHERE op.os_id=os.id AND op.ativo=1) prestadores,
                  resp.nome responsavel_atual,os.tecnico tecnico_legado,os.status,
                  os.dados_incompletos
           FROM ordens_servico os
           JOIN clientes c ON c.id=os.cliente_id
           LEFT JOIN os_responsaveis r ON r.os_id=os.id
           LEFT JOIN prestadores resp ON resp.id=r.prestador_id"""

    def _mapear_os(self, registros, termo: str = '') -> list[OSResumo]:
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

    def listar_os_ativas(self, termo: str = '') -> list[OSResumo]:
        with ext.db(self.banco) as conexao:
            registros = conexao.execute(
                self._SQL_OS_RESUMO
                + " WHERE os.status IN ('Aberta','Iniciada','Pendente')"
                  " ORDER BY os.id DESC").fetchall()
        return self._mapear_os(registros, termo)

    def listar_os_recentes(self, limite: int = 6) -> list[OSResumo]:
        with ext.db(self.banco) as conexao:
            registros = conexao.execute(
                self._SQL_OS_RESUMO + " ORDER BY os.id DESC LIMIT ?",
                (int(limite),)).fetchall()
        return self._mapear_os(registros)

    def listar_os_para_escolha(self, limite: int = 250) -> list[OSOpcao]:
        with ext.db(self.banco) as conexao:
            linhas = conexao.execute(
                "SELECT id,numero_os,status FROM ordens_servico ORDER BY id DESC LIMIT ?",
                (int(limite),)).fetchall()
        return [OSOpcao(
            id=int(linha['id']),
            numero_os=str(linha['numero_os'] or ''),
            status=str(linha['status'] or ''),
        ) for linha in linhas]

    def listar_os_para_atribuicao(self) -> list[OSOpcao]:
        with ext.db(self.banco) as conexao:
            linhas = conexao.execute(
                """SELECT o.id,o.numero_os,c.nome cliente,o.status FROM ordens_servico o
                   JOIN clientes c ON c.id=o.cliente_id
                   WHERE o.status IN ('Aberta','Iniciada','Pendente') ORDER BY o.id DESC""").fetchall()
        return [OSOpcao(
            id=int(linha['id']),
            numero_os=str(linha['numero_os'] or ''),
            cliente=str(linha['cliente'] or ''),
            status=str(linha['status'] or ''),
        ) for linha in linhas]

    def contar_os_cliente(self, cliente_id: int) -> int:
        with ext.db(self.banco) as conexao:
            return int(conexao.execute(
                'SELECT COUNT(*) FROM ordens_servico WHERE cliente_id=?',
                (int(cliente_id),)).fetchone()[0])

    def contar_clientes_ativos(self) -> int:
        return int(clientes_core.contar_ativos(self.banco))

    def listar_prestadores(self) -> list[PrestadorResumo]:
        with ext.db(self.banco) as conexao:
            linhas = conexao.execute(
                "SELECT id,nome,documento,email,especialidade,ativo FROM prestadores "
                "WHERE excluido=0 ORDER BY nome").fetchall()
        return [PrestadorResumo(
            id=int(linha['id']),
            nome=str(linha['nome'] or ''),
            documento=str(linha['documento'] or ''),
            email=str(linha['email'] or ''),
            especialidade=str(linha['especialidade'] or ''),
            ativo=bool(linha['ativo']),
        ) for linha in linhas]

    def alternar_prestador(self, prestador_id: int) -> None:
        with ext.db(self.banco) as conexao:
            conexao.execute(
                'UPDATE prestadores SET ativo=1-ativo WHERE id=?',
                (int(prestador_id),))

    def arquivar_prestador(self, prestador_id: int) -> None:
        with ext.db(self.banco) as conexao:
            conexao.execute(
                'UPDATE prestadores SET ativo=0,excluido=1 WHERE id=?',
                (int(prestador_id),))

    def obter_contato_sindico(self, organizacao_id: int) -> SindicoContato:
        with ext.db(self.banco) as conexao:
            linha = conexao.execute(
                'SELECT sindico_nome,sindico_telefone FROM v9_organizacoes WHERE id=?',
                (int(organizacao_id),)).fetchone()
        if not linha:
            raise NaoEncontradoError(
                'Organização não encontrada.', 'Síndico')
        return SindicoContato(
            nome=str(linha['sindico_nome'] or ''),
            telefone=str(linha['sindico_telefone'] or ''),
        )

    def listar_relatorios(self, termo: str = '') -> list[RelatorioOS]:
        busca = str(termo or '').casefold().strip()
        resultado = []
        for linha in ordens_repo.listar_relatorios(self.banco):
            texto = ' '.join(str(linha[chave] or '') for chave in (
                'numero_os', 'cliente', 'status')).casefold()
            if busca and busca not in texto:
                continue
            resultado.append(RelatorioOS(
                id=int(linha['id']),
                numero_os=str(linha['numero_os'] or ''),
                cliente=str(linha['cliente'] or ''),
                status=str(linha['status'] or ''),
                valor_total=float(linha['valor_total'] or 0),
            ))
        return resultado

    def listar_historico(self, termo: str = '') -> list[HistoricoOS]:
        busca = str(termo or '').strip()
        with ext.db(self.banco) as conexao:
            if busca:
                registros = conexao.execute(
                    """SELECT os.id,os.numero_os,c.nome cliente,os.data_conclusao,
                              os.valor_total,os.forma_pagamento,os.status,
                              (SELECT COUNT(*) FROM os_documentos d
                                 WHERE d.os_id=os.id AND d.tipo='relatorio_pdf') pdfs
                       FROM ordens_servico os JOIN clientes c ON c.id=os.cliente_id
                       WHERE os.status IN ('Concluída','Cancelada','Não realizada')
                         AND (os.numero_os LIKE ? OR c.nome LIKE ? OR os.descricao LIKE ?)
                       ORDER BY os.id DESC""",
                    (f'%{busca}%', f'%{busca}%', f'%{busca}%')).fetchall()
            else:
                registros = conexao.execute(
                    """SELECT os.id,os.numero_os,c.nome cliente,os.data_conclusao,
                              os.valor_total,os.forma_pagamento,os.status,
                              (SELECT COUNT(*) FROM os_documentos d
                                 WHERE d.os_id=os.id AND d.tipo='relatorio_pdf') pdfs
                       FROM ordens_servico os JOIN clientes c ON c.id=os.cliente_id
                       WHERE os.status IN ('Concluída','Cancelada','Não realizada')
                       ORDER BY os.id DESC""").fetchall()
        return [HistoricoOS(
            id=int(linha['id']),
            numero_os=str(linha['numero_os'] or ''),
            cliente=str(linha['cliente'] or ''),
            data_conclusao=str(linha['data_conclusao'] or ''),
            valor_total=float(linha['valor_total'] or 0),
            forma_pagamento=str(linha['forma_pagamento'] or ''),
            status=str(linha['status'] or ''),
            pdf_disponivel=bool(linha['pdfs']),
        ) for linha in registros]

    def resumo_historico(self) -> ResumoHistorico:
        with ext.db(self.banco) as conexao:
            linha = conexao.execute(
                """SELECT COUNT(*) total,
                          COALESCE(SUM(status='Aberta'),0) abertas,
                          COALESCE(SUM(status='Iniciada'),0) iniciadas,
                          COALESCE(SUM(status='Pendente'),0) pendentes,
                          COALESCE(SUM(status='Concluída'),0) concluidas,
                          COALESCE(SUM(CASE WHEN status='Concluída' THEN valor_total ELSE 0 END),0) valor_concluido,
                          COALESCE(SUM(CASE WHEN status IN ('Aberta','Iniciada','Pendente') THEN valor_total ELSE 0 END),0) valor_aberto
                   FROM ordens_servico""").fetchone()
        return ResumoHistorico(
            total=int(linha['total'] or 0),
            abertas=int(linha['abertas'] or 0),
            iniciadas=int(linha['iniciadas'] or 0),
            pendentes=int(linha['pendentes'] or 0),
            concluidas=int(linha['concluidas'] or 0),
            valor_concluido=float(linha['valor_concluido'] or 0),
            valor_aberto=float(linha['valor_aberto'] or 0),
        )

    def painel_pj(self) -> tuple[list[ChamadoPJ], list[OrganizacaoPJ],
                                 list[VinculoPJ]]:
        with ext.db(self.banco) as conexao:
            chamados = conexao.execute(
                """SELECT h.id,h.os_id,o.nome organizacao,u.nome solicitante,h.status,h.descricao
                   FROM v9_chamados h JOIN v9_organizacoes o ON o.id=h.organizacao_id
                   JOIN v9_usuarios u ON u.id=h.usuario_id ORDER BY h.id DESC LIMIT 300""").fetchall()
            organizacoes = conexao.execute(
                "SELECT id,nome,tipo,situacao,cliente_id FROM v9_organizacoes "
                "WHERE mesclado_em IS NULL ORDER BY nome").fetchall()
            vinculos = conexao.execute(
                """SELECT v.id,o.nome organizacao,u.nome pessoa,v.papel
                   FROM v9_vinculos v JOIN v9_organizacoes o ON o.id=v.organizacao_id
                   JOIN v9_usuarios u ON u.id=v.usuario_id
                   WHERE v.situacao='Pendente' ORDER BY v.id DESC""").fetchall()
        return (
            [ChamadoPJ(
                id=int(linha['id']),
                os_id=int(linha['os_id']) if linha['os_id'] else None,
                organizacao=str(linha['organizacao'] or ''),
                solicitante=str(linha['solicitante'] or ''),
                status=str(linha['status'] or ''),
                descricao=str(linha['descricao'] or ''),
            ) for linha in chamados],
            [OrganizacaoPJ(
                id=int(linha['id']),
                nome=str(linha['nome'] or ''),
                tipo=str(linha['tipo'] or ''),
                situacao=str(linha['situacao'] or ''),
                cliente_id=int(linha['cliente_id']) if linha['cliente_id'] else None,
            ) for linha in organizacoes],
            [VinculoPJ(
                id=int(linha['id']),
                organizacao=str(linha['organizacao'] or ''),
                pessoa=str(linha['pessoa'] or ''),
                papel=str(linha['papel'] or ''),
            ) for linha in vinculos],
        )

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

    def obter_cliente_ativo(self, cliente_id: int) -> ClienteOpcao | None:
        registro = clientes_core.obter(cliente_id, banco=self.banco)
        if registro is None:
            return None
        campos = dict(registro.get('fields') or {})
        if str(campos.get('status') or '') == 'Inativo':
            return None
        return ClienteOpcao(
            id=int(registro.get('id') or 0),
            nome=str(campos.get('nome') or ''),
        )

    def obter_cliente_ativo_por_documento(
        self, documento: str
    ) -> ClienteOpcao | None:
        digitos = cad9.digitos(documento)
        with ext.db(self.banco) as conexao:
            linha = conexao.execute(
                """SELECT id,nome FROM clientes
                   WHERE status!='Inativo' AND replace(
                       replace(replace(replace(documento,'.',''),'/',''),'-',''),' ','')=?
                   LIMIT 1""", (digitos,)).fetchone()
        if not linha:
            return None
        return ClienteOpcao(id=int(linha['id']), nome=str(linha['nome'] or ''))

    def url_whatsapp_chamado(self, chamado_id: int,
                             link_publico: str = '') -> dict:
        url, destino = cad9.url_whatsapp(
            self.banco, int(chamado_id), str(link_publico or ''))
        return {'url': url, 'destino': destino}

    def analisar_chamado(self, chamado_id: int, decisao: str,
                         observacao: str = '') -> None:
        cad9.analisar(self.banco, int(chamado_id), 'Desktop AUTOSEG',
                      str(decisao), str(observacao or ''))

    def confirmar_chamado(self, chamado_id: int, confirmacao: str) -> None:
        cad9.confirmar(self.banco, int(chamado_id),
                       'Desktop AUTOSEG — ' + str(confirmacao).strip(), True)

    def gerar_os_chamado(self, chamado_id: int) -> int:
        return int(cad9.gerar_os(self.banco, int(chamado_id),
                                 'Desktop AUTOSEG'))

    def validar_organizacao(self, organizacao_id: int,
                            cliente_id: int) -> None:
        cad9.validar_organizacao(
            self.banco, int(organizacao_id), int(cliente_id),
            'Desktop AUTOSEG')

    def atualizar_sindico(self, organizacao_id: int, nome: str,
                          telefone: str) -> None:
        cad9.atualizar_sindico(
            self.banco, int(organizacao_id), str(nome or ''),
            str(telefone or ''), 'Desktop AUTOSEG')

    def mesclar_organizacoes(self, origem: int, destino: int) -> None:
        cad9.mesclar_organizacoes(
            self.banco, int(origem), int(destino), 'Desktop AUTOSEG')

    def alterar_vinculo(self, vinculo_id: int, aprovar: bool) -> None:
        cad9.alterar_vinculo(
            self.banco, int(vinculo_id), bool(aprovar), 'Desktop AUTOSEG')

    def salvar_os(self, dados: OSInput, *, authorize=None) -> OSResultado:
        from officina.application.os_write import salvar_os
        try:
            return salvar_os(self.banco, dados, authorize=authorize)
        except ValidacaoError:
            raise
        except ValueError as erro:
            raise ValidacaoError(str(erro)) from erro

    def contexto_os(self, os_id: int | None = None) -> dict:
        from officina.application.desktop_context import contexto_os
        return contexto_os(self.banco, os_id)

    def contar_anexos_os(self, os_id: int) -> int:
        from officina.application.desktop_context import contar_anexos_os
        return contar_anexos_os(self.banco, os_id)

    def contexto_atribuicao(self, os_id: int) -> dict:
        from officina.application.desktop_context import contexto_atribuicao
        return contexto_atribuicao(self.banco, os_id)

    def documento_prestador(self, prestador_id: int) -> str:
        from officina.application.desktop_context import documento_prestador
        return documento_prestador(self.banco, prestador_id)

    def contexto_responsavel(self) -> dict:
        from officina.application.desktop_context import contexto_responsavel
        return contexto_responsavel(self.banco)

    def contexto_os_rapida(self) -> dict:
        from officina.application.desktop_context import contexto_os_rapida
        return contexto_os_rapida(self.banco)

    def contexto_movimento_empresa(self) -> dict:
        from officina.application.desktop_context import contexto_movimento_empresa
        return contexto_movimento_empresa(self.banco)

    def listar_clientes(self, termo: str = '') -> list[ClienteResumo]:
        return [self._resumo(registro)
                for registro in clientes_core.listar(termo, banco=self.banco)]

    def obter_cliente(self, cliente_id: int) -> Cliente | None:
        registro = clientes_core.obter(cliente_id, banco=self.banco)
        if registro is None:
            return None
        return self._cliente(registro)

    def desativar_cliente(self, cliente_id: int, motivo: str = '') -> None:
        cad9.desativar_cliente(self.banco, int(cliente_id),
                               motivo or 'Desktop AUTOSEG')

    def excluir_cliente(self, cliente_id: int) -> None:
        neg.cliente_excluir(self.banco, int(cliente_id), 0)

    def definir_senha_cliente(self, cliente_id: int, senha: str | None = None) -> str:
        return fluxo.definir_senha_cliente(self.banco, int(cliente_id), senha)

    def atribuir_os(self, os_id: int, prestador_id: int, *, authorize=None) -> bool:
        return bool(ext.atribuir(self.banco, int(os_id), int(prestador_id),
                                 ator='Desktop AUTOSEG', authorize=authorize))

    def desatribuir_os(self, os_id: int, *, authorize=None) -> bool:
        return bool(ext.desatribuir(self.banco, int(os_id),
                                    ator='Desktop AUTOSEG', authorize=authorize))

    def iniciar_os(self, os_id: int, *, authorize=None) -> None:
        if authorize is None:
            return aten.iniciar(self.banco, int(os_id))
        with ext.db(self.banco) as connection:
            connection.execute('BEGIN IMMEDIATE')
            authorize(connection)
            return aten.iniciar(self.banco, int(os_id), connection=connection)

    def atribuir_responsavel(self, organizacao_id: int, usuario_id: int) -> str:
        return cad9.atribuir_responsavel(
            self.banco, int(organizacao_id), int(usuario_id),
            'Desktop AUTOSEG')

    def remover_responsavel(self, organizacao_id: int) -> None:
        cad9.remover_responsavel(self.banco, int(organizacao_id),
                                 'Desktop AUTOSEG')

    def criar_prestador(self, dados: Mapping[str, Any]) -> int:
        return int(ext.cadastrar(
            self.banco,
            nome=str(dados.get('nome') or ''),
            email=str(dados.get('email') or ''),
            senha=str(dados.get('senha') or ''),
            telefone=str(dados.get('telefone') or ''),
            documento=str(dados.get('documento') or ''),
            especialidade=str(dados.get('especialidade') or '')))

    def redefinir_senha_prestador(self, prestador_id: int, senha: str) -> None:
        ext.redefinir_senha_prestador_desktop(
            self.banco, int(prestador_id), str(senha))

    def obter_config_prestador(self, prestador_id: int) -> dict:
        return dict(ext.obter_config_prestador(self.banco, int(prestador_id)))

    def salvar_config_prestador(self, prestador_id: int,
                                dados: Mapping[str, Any]) -> None:
        ext.salvar_config_prestador(self.banco, int(prestador_id), dict(dados))

    def definir_documento_prestador(self, prestador_id: int,
                                    documento: str) -> str:
        return ext.definir_documento_prestador(
            self.banco, int(prestador_id), str(documento))

    def publicar_pdf(self, os_id: int, *, authorize=None) -> str:
        return str(fluxo.publicar_relatorio(self.banco, int(os_id),
                                           authorize=authorize))

    def preparar_email(self, os_id: int, *, authorize=None) -> str:
        def prepare():
            publicado = fluxo.ultimo_documento(self.banco, int(os_id))
            if not publicado:
                raise ValueError('Esta OS não possui PDF publicado.')
            pdf = fluxo.validar_pdf_publicado(publicado)
            return str(ext.criar_email_rascunho(self.banco, int(os_id), pdf))
        if authorize is None:
            return prepare()
        with ext.db(self.banco) as connection:
            connection.execute('BEGIN IMMEDIATE')
            authorize(connection)
            return prepare()

    def preparar_nota(self, os_id: int, *, authorize=None) -> str:
        if authorize is None:
            return str(ext.criar_rascunho_fiscal(self.banco, int(os_id)))
        with ext.db(self.banco) as connection:
            connection.execute('BEGIN IMMEDIATE')
            authorize(connection)
            return str(ext.criar_rascunho_fiscal(self.banco, int(os_id)))

    def pdf_publicado(self, os_id: int) -> str:
        publicado = fluxo.ultimo_documento(self.banco, int(os_id))
        if not publicado:
            fluxo.recuperar_relatorios_antigos(self.banco, os_id=int(os_id))
            publicado = fluxo.ultimo_documento(self.banco, int(os_id))
        if not publicado:
            raise ValueError('PDF ainda não encontrado. Use Republicar PDF.')
        return str(fluxo.validar_pdf_publicado(publicado))

    def listar_materiais_estoque(self, ativos: bool = False) -> list[dict]:
        return [dict(item) for item in estoque.listar(
            self.banco, ativos=bool(ativos))]

    def catalogo_listar(self, ativos: bool = False) -> list[dict]:
        return [dict(item) for item in catalogo.listar(
            self.banco, ativos=bool(ativos))]

    def catalogo_obter(self, servico_id: int) -> dict | None:
        return catalogo.obter(self.banco, int(servico_id))

    def catalogo_salvar(self, dados: Mapping[str, Any],
                        servico_id: int | None = None) -> int:
        return int(catalogo.salvar(
            self.banco, dict(dados),
            None if servico_id is None else int(servico_id)))

    def catalogo_excluir(self, servico_id: int) -> None:
        catalogo.excluir(self.banco, int(servico_id))

    def catalogo_definir_ativo(self, servico_id: int, ativo: bool) -> None:
        acao = catalogo.reativar if ativo else catalogo.arquivar
        acao(self.banco, int(servico_id))

    def estoque_cadastrar(self, dados: Mapping[str, Any],
                          produto_id: int | None = None) -> int:
        return int(estoque.cadastrar(
            self.banco,
            nome=str(dados.get('nome') or ''),
            sku=str(dados.get('sku') or ''),
            unidade=str(dados.get('unidade') or 'un'),
            custo=dados.get('custo', '0'),
            venda=dados.get('venda', '0'),
            minimo=dados.get('minimo', '0'),
            identificador=None if produto_id is None else int(produto_id)))

    def estoque_obter(self, produto_id: int) -> dict | None:
        alvo = int(produto_id)
        return next((dict(item) for item in estoque.listar(self.banco)
                     if int(item['id']) == alvo), None)

    def estoque_ajuste(self, produto_id: int, delta, motivo: str) -> None:
        estoque.ajuste(self.banco, int(produto_id), delta, str(motivo or ''),
                       ator='Desktop')

    def estoque_movimentos(self, produto_id: int,
                           limite: int = 300) -> list[dict]:
        return [dict(item) for item in estoque.movimentos(
            self.banco, int(produto_id), int(limite))]

    def estoque_excluir(self, produto_id: int) -> str:
        return estoque.excluir(self.banco, int(produto_id))

    def estoque_importar_lote(self, materiais: list[Mapping[str, Any]]) -> dict:
        ids = estoque.importar_lote(self.banco, list(materiais))
        return {'ids': list(ids or []), 'total': len(ids or [])}

    def empresa_resumo(self) -> dict:
        return dict(empresa.resumo(self.banco))

    def empresa_listar(self) -> list[dict]:
        return [dict(item) for item in empresa.listar(self.banco)]

    def empresa_registrar(self, dados: Mapping[str, Any]) -> int:
        return int(empresa.registrar(
            self.banco,
            tipo=dados.get('tipo', ''),
            descricao=dados.get('descricao', ''),
            valor=dados.get('valor', '0'),
            data=dados.get('data', ''),
            prestador_id=dados.get('prestador_id'),
            os_id=dados.get('os_id'),
            categoria=dados.get('categoria', ''),
            finalidade=dados.get('finalidade', ''),
            observacao=dados.get('observacao', ''),
            criado_por='Desktop AUTOSEG'))

    def empresa_arquivar(self, movimento_id: int) -> None:
        empresa.arquivar(self.banco, int(movimento_id), ator='Desktop AUTOSEG')

    def composicao_config(self) -> dict:
        composicao.instalar()
        return dict(composicao.carregar())

    def composicao_salvar(self, config: Mapping[str, Any]) -> None:
        composicao.salvar(dict(config))

    def composicao_recalcular(self) -> dict:
        return dict(composicao.recalcular_tudo(self.banco))

    def prestador_admin(self, prestador_id: int) -> bool:
        return bool(cad9.prestador_admin(self.banco, int(prestador_id)))

    def definir_admin(self, prestador_id: int, ativo: bool) -> None:
        cad9.definir_admin(self.banco, int(prestador_id), bool(ativo))

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
        return ('health', 'resumo_inicio', 'os.listar_ativas', 'os.salvar',
                'os.escolha', 'os.atribuicao', 'clientes.contar',
                'prestadores.listar', 'prestadores.alternar',
                'prestadores.arquivar', 'sindico.contato',
                'clientes.ativo', 'clientes.ativo_documento',
                'desktop.contexto_os', 'desktop.contexto_atribuicao',
                'desktop.contexto_responsavel', 'desktop.contexto_os_rapida',
                'desktop.contexto_movimento',
                'historico.listar', 'historico.resumo', 'pj.painel',
                'resumo_financeiro', 'financeiro.listar', 'financeiro.receber',
                'resumo_portal', 'solicitacoes_portal',
                'clientes.listar', 'clientes.obter', 'clientes.salvar',
                'clientes.desativar', 'clientes.excluir', 'clientes.senha',
                'os.atribuir', 'os.desatribuir', 'os.iniciar',
                'responsavel.atribuir', 'responsavel.remover',
                'prestadores.criar', 'prestadores.senha',
                'prestadores.config', 'prestadores.documento',
                'os.pdf.publicar', 'os.pdf.abrir', 'os.email.preparar', 'os.nota.preparar',
                'relatorios.listar',
                'estoque.materiais', 'prestadores.admin',
                'pj.whatsapp', 'pj.analisar', 'pj.confirmar', 'pj.gerar_os',
                'pj.validar', 'pj.sindico', 'pj.mesclar', 'pj.vinculo',
                'catalogo.listar', 'catalogo.obter', 'catalogo.salvar',
                'catalogo.excluir', 'catalogo.ativo',
                'estoque.cadastrar', 'estoque.obter', 'estoque.ajuste',
                'estoque.movimentos', 'estoque.excluir', 'estoque.importar',
                'empresa.resumo', 'empresa.listar', 'empresa.registrar',
                'empresa.arquivar',
                'composicao.config', 'composicao.salvar',
                'composicao.recalcular')

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
            incompleto=bool(campos.get('dados_incompletos'))
            or completude.cliente_faltantes(campos),
        )

    @staticmethod
    def _cliente(registro) -> Cliente:
        campos = dict(registro.get('fields') or {})
        return Cliente(
            id=int(registro.get('id') or 0),
            versao=int(registro.get('version') or 1),
            campos=campos,
            incompleto=bool(campos.get('dados_incompletos'))
            or completude.cliente_faltantes(campos),
        )
