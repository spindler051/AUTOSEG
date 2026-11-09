"""HTTP implementation of the application contract.

The desktop talks to the headless server through these methods. Read calls
degrade to empty values when the server is unavailable; writes raise a stable
``ServicoIndisponivelError`` so the UI never silently touches a local database.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from typing import Any, Mapping

from officina.application.contracts import (
    AppError,
    AppService,
    AutenticacaoError,
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
    ServicoIndisponivelError,
    SindicoContato,
    SolicitacaoPortal,
    ValidacaoError,
    VinculoPJ,
)
from officina.core.versao_app import versao_local


class HttpService(AppService):
    """Thin JSON client for the headless AUTOSEG server."""

    mode = 'remote'

    def __init__(self, base_url: str, token: str = '', timeout: float = 2.5):
        self.base_url = str(base_url or '').rstrip('/')
        self.token = str(token or '')
        self.desktop_token = os.environ.get('AUTOSEG_DESKTOP_TOKEN', '')
        self.timeout = float(timeout)
        self.write_timeout = max(20.0, self.timeout)
        self.last_error = ''
        self._offline_until = 0.0

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _url(self, caminho: str, params: Mapping[str, Any] | None = None) -> str:
        url = self.base_url + caminho
        if params:
            limpos = {chave: valor for chave, valor in params.items()
                      if valor is not None and str(valor) != ''}
            if limpos:
                url += '?' + urllib.parse.urlencode(limpos)
        return url

    def _request(self, metodo: str, caminho: str,
                 payload: Mapping[str, Any] | None = None,
                 params: Mapping[str, Any] | None = None,
                 force: bool = False) -> Any:
        if not self.base_url:
            raise ServicoIndisponivelError(
                'URL do servidor não configurada.', 'Servidor não configurado')
        if not force and time.monotonic() < self._offline_until:
            raise ServicoIndisponivelError(
                self.last_error or 'Servidor indisponível.', 'Servidor indisponível')
        corpo = None
        cabecalhos = {'Accept': 'application/json'}
        if payload is not None:
            corpo = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            cabecalhos['Content-Type'] = 'application/json; charset=utf-8'
        pedido = urllib.request.Request(
            self._url(caminho, params), data=corpo, method=metodo,
            headers=cabecalhos)
        if self.token:
            pedido.add_header('Authorization', 'Bearer ' + self.token)
        if self.desktop_token:
            pedido.add_header('X-AUTOSEG-Desktop-Token', self.desktop_token)
        timeout = self.write_timeout if metodo != 'GET' else self.timeout
        try:
            with urllib.request.urlopen(pedido, timeout=timeout) as resposta:
                bruto = resposta.read().decode('utf-8')
        except urllib.error.HTTPError as erro:
            self._erro_http(erro)
        except (urllib.error.URLError, OSError) as erro:
            self._marcar_offline(f'Servidor indisponível: {erro}')
            raise ServicoIndisponivelError(
                self.last_error, 'Servidor indisponível') from erro
        try:
            dados = json.loads(bruto)
        except ValueError as erro:
            self._marcar_offline('Servidor respondeu um JSON inválido.')
            raise ServicoIndisponivelError(
                self.last_error, 'Resposta inválida') from erro
        if not isinstance(dados, dict):
            self._marcar_offline('Resposta do servidor inválida.')
            raise ServicoIndisponivelError(
                self.last_error, 'Resposta inválida')
        self._offline_until = 0.0
        self.last_error = ''
        return dados.get('data', dados)

    def _marcar_offline(self, mensagem: str):
        self.last_error = str(mensagem)
        self._offline_until = time.monotonic() + 2.5

    def reset_offline(self) -> None:
        """Allow the next refresh to try the server again."""
        self._offline_until = 0.0

    def _erro_http(self, erro: urllib.error.HTTPError):
        mensagem = f'Servidor respondeu HTTP {erro.code}.'
        codigo = ''
        try:
            bruto = erro.read().decode('utf-8')
            dados = json.loads(bruto)
            detalhe = dados.get('error') if isinstance(dados, dict) else None
            if isinstance(detalhe, dict):
                codigo = str(detalhe.get('code') or '')
                mensagem = str(detalhe.get('message') or mensagem)
        except (OSError, ValueError, AttributeError):
            pass
        if erro.code == 401 or codigo == 'unauthorized':
            raise AutenticacaoError(mensagem, 'Sessão expirada')
        if erro.code == 404 or codigo == 'not_found':
            raise NaoEncontradoError(mensagem)
        if erro.code == 409 or codigo == 'conflict':
            raise ConflitoError(mensagem)
        if erro.code == 400 or codigo == 'validation':
            raise ValidacaoError(mensagem)
        if erro.code == 503 or codigo == 'unavailable':
            self._marcar_offline(mensagem)
            raise ServicoIndisponivelError(mensagem, 'Servidor indisponível')
        raise AppError(mensagem)

    def _get(self, caminho: str, params: Mapping[str, Any] | None = None,
             force: bool = False) -> Any:
        return self._request('GET', caminho, params=params, force=force)

    def _post(self, caminho: str, payload: Mapping[str, Any] | None = None) -> Any:
        return self._request('POST', caminho, payload=payload)

    def _ler(self, caminho: str, padrao, params=None):
        try:
            return self._get(caminho, params=params)
        except ServicoIndisponivelError:
            return padrao

    # ------------------------------------------------------------------
    # Contract
    # ------------------------------------------------------------------

    def login(self, email: str, senha: str, lembrar: bool = False) -> dict:
        resposta = self._post('/api/v1/desktop/login', {
            'email': email,
            'senha': senha,
            'lembrar': bool(lembrar),
        })
        self.token = str(resposta.get('token') or '')
        self.reset_offline()
        return resposta

    def me(self) -> dict:
        return self._get('/api/v1/desktop/me')

    def logout(self) -> None:
        try:
            self._post('/api/v1/desktop/logout')
        finally:
            self.token = ''

    def health(self) -> Health:
        try:
            dados = self._get('/api/v1/desktop/health', force=True)
        except (ServicoIndisponivelError, AppError) as erro:
            return Health(
                status='unavailable',
                version=versao_local(),
                mode=self.mode,
                database='',
                capabilities=self._capabilities(),
                detail=str(erro),
            )
        return Health(
            status=str(dados.get('status') or 'ok'),
            version=str(dados.get('version') or versao_local()),
            mode=self.mode,
            database='',
            capabilities=self._capabilities(),
            detail=str(dados.get('detail') or ''),
        )

    def resumo_inicio(self) -> ResumoInicio:
        dados = self._ler('/api/v1/desktop/resumo', {})
        return ResumoInicio(
            clientes_ativos=int(dados.get('clientes_ativos') or 0),
            os_abertas=int(dados.get('os_abertas') or 0),
            os_iniciadas=int(dados.get('os_iniciadas') or 0),
            os_pendentes=int(dados.get('os_pendentes') or 0),
            financeiro_recebido=float(dados.get('financeiro_recebido') or 0),
            financeiro_a_receber=float(dados.get('financeiro_a_receber') or 0),
        )

    def resumo_portal(self) -> ResumoPortal:
        dados = self._ler('/api/v1/desktop/portal/resumo', {})
        return ResumoPortal(
            total=int(dados.get('total') or 0),
            andamento=int(dados.get('andamento') or 0),
            concluidas=int(dados.get('concluidas') or 0),
        )

    def listar_solicitacoes_portal(
        self, limite: int = 50
    ) -> list[SolicitacaoPortal]:
        dados = self._ler('/api/v1/desktop/portal/solicitacoes', [],
                          params={'limite': limite})
        return [SolicitacaoPortal(**item) for item in dados]

    def listar_os_ativas(self, termo: str = '') -> list[OSResumo]:
        dados = self._ler('/api/v1/desktop/os/ativas', [],
                          params={'termo': termo})
        return [OSResumo(**item) for item in dados]

    def listar_os_recentes(self, limite: int = 6) -> list[OSResumo]:
        dados = self._ler('/api/v1/desktop/os/recentes', [],
                          params={'limite': limite})
        return [OSResumo(**item) for item in dados]

    def listar_os_para_escolha(self, limite: int = 250) -> list[OSOpcao]:
        dados = self._ler('/api/v1/desktop/os/escolha', [],
                          params={'limite': limite})
        return [OSOpcao(**item) for item in dados]

    def listar_os_para_atribuicao(self) -> list[OSOpcao]:
        dados = self._ler('/api/v1/desktop/os/atribuicao', [])
        return [OSOpcao(**item) for item in dados]

    def contar_os_cliente(self, cliente_id: int) -> int:
        dados = self._ler(
            f'/api/v1/desktop/clientes/{int(cliente_id)}/os/contar', {})
        return int(dados.get('total') or 0)

    def contar_clientes_ativos(self) -> int:
        dados = self._ler('/api/v1/desktop/clientes/ativos/contar', {})
        return int(dados.get('total') or 0)

    def listar_prestadores(self) -> list[PrestadorResumo]:
        dados = self._ler('/api/v1/desktop/prestadores', [])
        return [PrestadorResumo(**item) for item in dados]

    def alternar_prestador(self, prestador_id: int) -> None:
        self._post(f'/api/v1/desktop/prestadores/{int(prestador_id)}/alternar')

    def arquivar_prestador(self, prestador_id: int) -> None:
        self._post(f'/api/v1/desktop/prestadores/{int(prestador_id)}/arquivar')

    def obter_contato_sindico(self, organizacao_id: int) -> SindicoContato:
        dados = self._ler(
            f'/api/v1/desktop/organizacoes/{int(organizacao_id)}/sindico', {})
        return SindicoContato(
            nome=str(dados.get('nome') or ''),
            telefone=str(dados.get('telefone') or ''),
        )

    def listar_relatorios(self, termo: str = '') -> list[RelatorioOS]:
        dados = self._ler('/api/v1/desktop/relatorios', [],
                          params={'termo': termo})
        return [RelatorioOS(**item) for item in dados]

    def listar_historico(self, termo: str = '') -> list[HistoricoOS]:
        dados = self._ler('/api/v1/desktop/historico', [],
                          params={'termo': termo})
        return [HistoricoOS(**item) for item in dados]

    def resumo_historico(self) -> ResumoHistorico:
        dados = self._ler('/api/v1/desktop/historico/resumo', {})
        return ResumoHistorico(
            total=int(dados.get('total') or 0),
            abertas=int(dados.get('abertas') or 0),
            iniciadas=int(dados.get('iniciadas') or 0),
            pendentes=int(dados.get('pendentes') or 0),
            concluidas=int(dados.get('concluidas') or 0),
            valor_concluido=float(dados.get('valor_concluido') or 0),
            valor_aberto=float(dados.get('valor_aberto') or 0),
        )

    def painel_pj(self) -> tuple[list[ChamadoPJ], list[OrganizacaoPJ],
                                 list[VinculoPJ]]:
        dados = self._ler('/api/v1/desktop/pj/painel', {})
        return (
            [ChamadoPJ(**item) for item in dados.get('chamados', [])],
            [OrganizacaoPJ(**item) for item in dados.get('organizacoes', [])],
            [VinculoPJ(**item) for item in dados.get('vinculos', [])],
        )

    def resumo_financeiro(self) -> ResumoFinanceiro:
        dados = self._ler('/api/v1/desktop/financeiro/resumo', {})
        return ResumoFinanceiro(
            a_receber=float(dados.get('a_receber') or 0),
            recebido=float(dados.get('recebido') or 0),
        )

    def listar_financeiro(self, termo: str = '') -> list[LancamentoFinanceiro]:
        dados = self._ler('/api/v1/desktop/financeiro', [],
                          params={'termo': termo})
        return [LancamentoFinanceiro(**item) for item in dados]

    def marcar_recebido(self, lancamento_id: int) -> None:
        self._post(f'/api/v1/desktop/financeiro/{int(lancamento_id)}/receber')

    def obter_cliente_ativo(self, cliente_id: int) -> ClienteOpcao | None:
        try:
            dados = self._get(f'/api/v1/desktop/clientes/{int(cliente_id)}/ativo')
        except NaoEncontradoError:
            return None
        except ServicoIndisponivelError:
            return None
        return ClienteOpcao(**dados) if dados else None

    def obter_cliente_ativo_por_documento(
        self, documento: str
    ) -> ClienteOpcao | None:
        dados = self._ler('/api/v1/desktop/clientes/ativo', None,
                          params={'documento': documento})
        return ClienteOpcao(**dados) if dados else None

    def listar_clientes(self, termo: str = '') -> list[ClienteResumo]:
        dados = self._ler('/api/v1/desktop/clientes', [],
                          params={'termo': termo})
        return [ClienteResumo(**item) for item in dados]

    def obter_cliente(self, cliente_id: int) -> Cliente | None:
        try:
            dados = self._get(f'/api/v1/desktop/clientes/{int(cliente_id)}')
        except NaoEncontradoError:
            return None
        except ServicoIndisponivelError:
            return None
        return Cliente(**dados) if dados else None

    def salvar_cliente(
        self, cliente_id: int | None, dados: Mapping[str, Any]
    ) -> Cliente:
        if cliente_id is None:
            resposta = self._post('/api/v1/desktop/clientes', {'dados': dict(dados)})
        else:
            resposta = self._request(
                'PUT', f'/api/v1/desktop/clientes/{int(cliente_id)}',
                payload={'dados': dict(dados)})
        return Cliente(**resposta)

    def url_whatsapp_chamado(self, chamado_id: int,
                             link_publico: str = '') -> dict:
        return self._ler(
            f'/api/v1/desktop/pj/chamados/{int(chamado_id)}/whatsapp',
            {'url': '', 'destino': ''},
            params={'link': link_publico})

    def analisar_chamado(self, chamado_id: int, decisao: str,
                         observacao: str = '') -> None:
        self._post(f'/api/v1/desktop/pj/chamados/{int(chamado_id)}/analisar',
                   {'decisao': decisao, 'observacao': observacao})

    def confirmar_chamado(self, chamado_id: int, confirmacao: str) -> None:
        self._post(f'/api/v1/desktop/pj/chamados/{int(chamado_id)}/confirmar',
                   {'confirmacao': confirmacao})

    def gerar_os_chamado(self, chamado_id: int) -> int:
        resposta = self._post(
            f'/api/v1/desktop/pj/chamados/{int(chamado_id)}/gerar-os')
        return int(resposta.get('os_id') or 0)

    def validar_organizacao(self, organizacao_id: int,
                            cliente_id: int) -> None:
        self._post(
            f'/api/v1/desktop/pj/organizacoes/{int(organizacao_id)}/validar',
            {'cliente_id': int(cliente_id)})

    def atualizar_sindico(self, organizacao_id: int, nome: str,
                          telefone: str) -> None:
        self._post(
            f'/api/v1/desktop/pj/organizacoes/{int(organizacao_id)}/sindico',
            {'nome': nome, 'telefone': telefone})

    def mesclar_organizacoes(self, origem: int, destino: int) -> None:
        self._post('/api/v1/desktop/pj/organizacoes/mesclar',
                   {'origem': int(origem), 'destino': int(destino)})

    def alterar_vinculo(self, vinculo_id: int, aprovar: bool) -> None:
        self._post(f'/api/v1/desktop/pj/vinculos/{int(vinculo_id)}/alterar',
                   {'aprovar': bool(aprovar)})

    def salvar_os(self, dados: OSInput) -> OSResultado:
        payload = asdict(dados)
        payload['imagens'] = [
            {'nome': nome,
             'conteudo': base64.b64encode(conteudo).decode('ascii')}
            for nome, conteudo in dados.imagens
        ]
        resposta = self._post('/api/v1/desktop/os', payload)
        return OSResultado(**resposta)

    def contexto_os(self, os_id: int | None = None) -> dict:
        padrao = {
            'clientes': [], 'dados': None, 'materiais': [],
            'original_portal': None, 'andamento': None,
            'encerramento': None,
        }
        return self._ler('/api/v1/desktop/os/contexto', padrao,
                         params={'os_id': os_id})

    def contar_anexos_os(self, os_id: int) -> int:
        dados = self._ler(
            f'/api/v1/desktop/os/{int(os_id)}/anexos/contar', {})
        return int(dados.get('total') or 0)

    def contexto_atribuicao(self, os_id: int) -> dict:
        padrao = {'ordem': None, 'prestadores': [], 'atual_id': None}
        return self._ler(
            f'/api/v1/desktop/os/{int(os_id)}/contexto-atribuicao', padrao)

    def documento_prestador(self, prestador_id: int) -> str:
        dados = self._ler(
            f'/api/v1/desktop/prestadores/{int(prestador_id)}/documento', {})
        return str(dados.get('documento') or '')

    def contexto_responsavel(self) -> dict:
        return self._ler('/api/v1/desktop/contexto/responsavel',
                         {'organizacoes': [], 'pessoas': []})

    def contexto_os_rapida(self) -> dict:
        return self._ler('/api/v1/desktop/contexto/os-rapida',
                         {'clientes': [], 'prestadores': []})

    def contexto_movimento_empresa(self) -> dict:
        return self._ler('/api/v1/desktop/contexto/movimento',
                         {'prestadores': [], 'oses': []})

    def desativar_cliente(self, cliente_id: int, motivo: str = '') -> None:
        self._post(f'/api/v1/desktop/clientes/{int(cliente_id)}/desativar',
                   {'motivo': motivo})

    def excluir_cliente(self, cliente_id: int) -> None:
        self._post(f'/api/v1/desktop/clientes/{int(cliente_id)}/excluir')

    def definir_senha_cliente(self, cliente_id: int,
                              senha: str | None = None) -> str:
        resposta = self._post(
            f'/api/v1/desktop/clientes/{int(cliente_id)}/senha',
            {'senha': senha})
        return str(resposta.get('senha') or senha or '')

    def atribuir_os(self, os_id: int, prestador_id: int) -> bool:
        resposta = self._post(
            f'/api/v1/desktop/os/{int(os_id)}/atribuir',
            {'prestador_id': int(prestador_id)})
        return bool(resposta.get('mudou'))

    def desatribuir_os(self, os_id: int) -> bool:
        resposta = self._post(
            f'/api/v1/desktop/os/{int(os_id)}/desatribuir')
        return bool(resposta.get('mudou'))

    def iniciar_os(self, os_id: int) -> None:
        self._post(f'/api/v1/desktop/os/{int(os_id)}/iniciar')

    def atribuir_responsavel(self, organizacao_id: int, usuario_id: int) -> str:
        resposta = self._post(
            f'/api/v1/desktop/organizacoes/{int(organizacao_id)}/responsavel',
            {'usuario_id': int(usuario_id)})
        return str(resposta.get('papel') or '')

    def remover_responsavel(self, organizacao_id: int) -> None:
        self._request(
            'DELETE',
            f'/api/v1/desktop/organizacoes/{int(organizacao_id)}/responsavel')

    def criar_prestador(self, dados: Mapping[str, Any]) -> int:
        resposta = self._post('/api/v1/desktop/prestadores', dict(dados))
        return int(resposta.get('id') or 0)

    def redefinir_senha_prestador(self, prestador_id: int, senha: str) -> None:
        self._post(f'/api/v1/desktop/prestadores/{int(prestador_id)}/senha',
                   {'senha': senha})

    def obter_config_prestador(self, prestador_id: int) -> dict:
        return self._ler(
            f'/api/v1/desktop/prestadores/{int(prestador_id)}/config', {})

    def salvar_config_prestador(self, prestador_id: int,
                                dados: Mapping[str, Any]) -> None:
        self._request(
            'PUT',
            f'/api/v1/desktop/prestadores/{int(prestador_id)}/config',
            payload=dict(dados))

    def definir_documento_prestador(self, prestador_id: int,
                                    documento: str) -> str:
        resposta = self._request(
            'PUT',
            f'/api/v1/desktop/prestadores/{int(prestador_id)}/documento',
            payload={'documento': documento})
        return str(resposta.get('documento') or '')

    def publicar_pdf(self, os_id: int) -> str:
        resposta = self._post(f'/api/v1/desktop/os/{int(os_id)}/pdf/publicar')
        return str(resposta.get('arquivo') or '')

    def preparar_email(self, os_id: int) -> str:
        resposta = self._post(f'/api/v1/desktop/os/{int(os_id)}/email/preparar')
        return str(resposta.get('arquivo') or '')

    def preparar_nota(self, os_id: int) -> str:
        resposta = self._post(f'/api/v1/desktop/os/{int(os_id)}/nota/preparar')
        return str(resposta.get('arquivo') or '')

    def pdf_publicado(self, os_id: int) -> str:
        resposta = self._get(f'/api/v1/desktop/os/{int(os_id)}/pdf/arquivo')
        return str(resposta.get('arquivo') or '')

    def listar_materiais_estoque(self, ativos: bool = False) -> list[dict]:
        dados = self._ler('/api/v1/desktop/estoque/materiais', [],
                          params={'ativos': '1' if ativos else '0'})
        return [dict(item) for item in dados]

    def prestador_admin(self, prestador_id: int) -> bool:
        dados = self._ler(
            f'/api/v1/desktop/prestadores/{int(prestador_id)}/admin', {})
        return bool(dados.get('admin'))

    def definir_admin(self, prestador_id: int, ativo: bool) -> None:
        self._post(f'/api/v1/desktop/prestadores/{int(prestador_id)}/admin',
                   {'ativo': bool(ativo)})

    def catalogo_listar(self, ativos: bool = False) -> list[dict]:
        return [dict(item) for item in self._ler(
            '/api/v1/desktop/catalogo/servicos', [],
            params={'ativos': '1' if ativos else '0'})]

    def catalogo_obter(self, servico_id: int) -> dict | None:
        try:
            dados = self._get(
                f'/api/v1/desktop/catalogo/servicos/{int(servico_id)}')
        except (NaoEncontradoError, ServicoIndisponivelError):
            return None
        return dict(dados) if dados else None

    def catalogo_salvar(self, dados: Mapping[str, Any],
                        servico_id: int | None = None) -> int:
        if servico_id is None:
            resposta = self._post('/api/v1/desktop/catalogo/servicos',
                                  {'dados': dict(dados)})
        else:
            resposta = self._request(
                'PUT', f'/api/v1/desktop/catalogo/servicos/{int(servico_id)}',
                payload={'dados': dict(dados)})
        return int(resposta.get('id') or 0)

    def catalogo_excluir(self, servico_id: int) -> None:
        self._post(
            f'/api/v1/desktop/catalogo/servicos/{int(servico_id)}/excluir')

    def catalogo_definir_ativo(self, servico_id: int, ativo: bool) -> None:
        acao = 'reativar' if ativo else 'arquivar'
        self._post(
            f'/api/v1/desktop/catalogo/servicos/{int(servico_id)}/{acao}')

    def estoque_cadastrar(self, dados: Mapping[str, Any],
                          produto_id: int | None = None) -> int:
        if produto_id is None:
            resposta = self._post('/api/v1/desktop/estoque/produtos',
                                  {'dados': dict(dados)})
        else:
            resposta = self._request(
                'PUT', f'/api/v1/desktop/estoque/produtos/{int(produto_id)}',
                payload={'dados': dict(dados)})
        return int(resposta.get('id') or 0)

    def estoque_obter(self, produto_id: int) -> dict | None:
        try:
            dados = self._get(
                f'/api/v1/desktop/estoque/produtos/{int(produto_id)}')
        except (NaoEncontradoError, ServicoIndisponivelError):
            return None
        return dict(dados) if dados else None

    def estoque_ajuste(self, produto_id: int, delta, motivo: str) -> None:
        self._post(
            f'/api/v1/desktop/estoque/produtos/{int(produto_id)}/ajuste',
            {'delta': delta, 'motivo': motivo})

    def estoque_movimentos(self, produto_id: int,
                           limite: int = 300) -> list[dict]:
        return [dict(item) for item in self._ler(
            f'/api/v1/desktop/estoque/produtos/{int(produto_id)}/movimentos',
            [], params={'limite': limite})]

    def estoque_excluir(self, produto_id: int) -> str:
        resposta = self._post(
            f'/api/v1/desktop/estoque/produtos/{int(produto_id)}/excluir')
        return str(resposta.get('resultado') or '')

    def estoque_importar_lote(self, materiais: list[Mapping[str, Any]]) -> dict:
        return dict(self._post('/api/v1/desktop/estoque/importar',
                               {'materiais': [dict(x) for x in materiais]}) or {})

    def empresa_resumo(self) -> dict:
        dados = self._ler('/api/v1/desktop/empresa/resumo', {})
        padrao = {
            'aportes_centavos': 0, 'material_centavos': 0,
            'api_centavos': 0, 'outras_despesas_centavos': 0,
            'despesas_centavos': 0, 'saldo_centavos': 0,
            'por_investidor': [], 'por_categoria': [],
        }
        padrao.update({chave: valor for chave, valor in dados.items()
                       if chave in padrao})
        return padrao

    def empresa_listar(self) -> list[dict]:
        return [dict(item) for item in self._ler(
            '/api/v1/desktop/empresa/movimentos', [])]

    def empresa_registrar(self, dados: Mapping[str, Any]) -> int:
        resposta = self._post('/api/v1/desktop/empresa/movimentos',
                              dict(dados))
        return int(resposta.get('id') or 0)

    def empresa_arquivar(self, movimento_id: int) -> None:
        self._post(
            f'/api/v1/desktop/empresa/movimentos/{int(movimento_id)}/arquivar')

    def composicao_config(self) -> dict:
        return dict(self._ler('/api/v1/desktop/composicao/config', {
            'versao': 1, 'componentes': []}))

    def composicao_salvar(self, config: Mapping[str, Any]) -> None:
        self._request('PUT', '/api/v1/desktop/composicao/config',
                      payload=dict(config))

    def composicao_recalcular(self) -> dict:
        return dict(self._post('/api/v1/desktop/composicao/recalcular'))

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
