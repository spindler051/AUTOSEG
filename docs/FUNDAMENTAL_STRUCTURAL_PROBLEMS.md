# Problemas estruturais fundamentais do AUTOSEG

**Status:** auditoria estrutural e plano de correção incremental.  
**Data:** 2026-11-06  
**Método:** leitura de `README.md`, `AGENTS.md`, `docs/PRODUCT_VISION.md`,
`docs/PLANO_EVOLUCAO_ARQUITETURA.md`, `docs/PLATFORM_MIGRATION_PLAYBOOK.md`,
`docs/PLATFORM_MIGRATION_LEDGER.md`, `KNOWN_ISSUES.md`, `ROADMAP.md` e
`docs/GTK4_LINUX_MACOS.md`, combinada com inspeção do código atual.

Este documento ranqueia os problemas **estruturais** — não bugs pontuais nem
itens de roadmap funcional. O critério é:

```text
risco de regressão × acoplamento × frequência de mudança × custo de corrigir
```

O objetivo é preservar **comportamento, usabilidade e interface** enquanto a
engenharia melhora por fatias pequenas, reversíveis e testadas.

---

## 1. Ranking

| # | Problema fundamental | Evidência | Impacto | Esforço | Estado |
|---|---|---|---|---|---|
| 1 | **Regras de negócio e SQL dentro da UI/HTTP** | `gtk_app.py` 2.345 linhas e ~50 chamadas SQL; `gtk_dialogos.py` 2.254 e ~43; `portal_prestador.py` 3.482 e ~52. O plano 3.1/3.2/3.6 já registra o problema. | Uma mudança de regra exige tocar GTK, portal e testes; UI difícil de testar; risco de divergência. | Alto | **Parcial — leituras de clientes e resumos de OS extraídos; detalhe de OS/financeiro/estoque/GTK resta** |
| 2 | **Schema e migrações espalhados, sem versão única** | 12 `CREATE TABLE` em `prestadores_ext.py`, 11 em `cadastros_v9.py`, além de `banco.py`, `fluxo_os.py`, `produtividade_os.py`, `estoque_materiais.py`; 26 referências a `ALTER TABLE`/`CREATE TABLE` no código. | Banco antigo e novo podem divergir; rollback e migração de produção ficam frágeis. | Alto | Pendente |
| 3 | **Arquivos monolíticos sem fronteiras de domínio** | `gtk_app.py` 2.345; `gtk_dialogos.py` 2.254; `portal_prestador.py` 3.482; `prestadores_ext.py` 983; `cadastros_v9.py` 893. | Revisão difícil, conflitos frequentes, baixa coesão e acoplamento entre cadastro, OS, PDF, e-mail e portal. | Alto | Pendente |
| 4 | **Sessão, cookie, CSRF, formulário e HTML duplicados nos portais** | `portal_prestador.py`, `servidor_web.py`, `portal_cliente_v94.py`, `portal_v9.py` repetem handlers, cookies, validação de origem e templates. | Correção de segurança precisa ser replicada em vários lugares; comportamento diverge. | Alto | Pendente |
| 5 | **Configuração, caminhos e portas espalhados** | 77 referências a `AUTOSEG_BASE`, `GESTAO_BANCO`, `PRESTADOR_PORT`, `CLIENTE_PORT`, `PRESTADOR_HTTPS`; 58 leituras de `os.environ` no código do app. Defaults diferentes: 8765/8766 no MAIN e 8865/8866 no DEV. | Porta/path errado em produção, container ou teste; difícil empacotar e diagnosticar. | Médio | **Corrigido nesta fatia** |
| 6 | **Trabalho em background sem fila durável** | PDFs, e-mails, túneis e eventos usam `threading.Thread`/`after`; não há job persistente, retry ou idempotência central. | Fechar o app pode perder tarefa; duas execuções podem gerar PDF/e-mail duplicado. | Médio-alto | Pendente |
| 7 | **Workaholic ainda não é o motor real** | Integração apenas na fatia `clientes`; o restante continua em tabelas/legado. Ver `docs/WORKAHOLIC_INTEGRACAO.md` e ledger. | Estratégia de plataforma fica incompleta; risco de manter duas arquiteturas. | Alto | Pendente |
| 8 | **Testes monolíticos e sem runner/pirâmide padronizada** | 45 arquivos `test_*.py`, ~8.207 linhas, muitos cenários em scripts; sem pytest/fixtures/CI matrix consolidada. | Feedback lento, regressões em fluxos grandes, difícil isolar falha. | Médio | Pendente |
| 9 | **Armazenamento local acoplado a caminhos do app** | PDFs, anexos, comprovantes e rascunhos vivem sob `AUTOSEG_BASE`; não há interface `Storage`. | Backup, container, múltiplas máquinas e restauração ficam manuais e frágeis. | Médio | Pendente |
| 10 | **Nomes legados em português + ausência de contrato público estável** | Plano de migração para inglês; docs `NAMING_AND_CLI`; módulos e colunas legadas. | Onboarding e criação de novos clientes (CLI/GTK/Qt/mobile) ficam mais caros. | Médio-alto | Pendente |

### Estratégia desta rodada

Os itens 1–4 são os mais graves, mas também os mais arriscados. O item 5 foi
corrigido por ser fundamental, de baixo risco e habilitador. O item 1 foi
iniciado pela **fatia de leitura de clientes**, escolhida por ter caracterização
simples e não alterar HTML, CSS ou regras de apresentação.

A regra do playbook é uma fatia por vez. O restante do #1 (SQL de OS,
financeiro, estoque, anexos e dashboard GTK) continua documentado para as
próximas rodadas.

---

## 2. O que foi corrigido nesta rodada

### 2.1 Problema #1 — leitura de clientes fora do HTTP/UI

O SQL de leitura de clientes saiu do handler e da janela e passou para
`integracao/clientes.py`, junto do adaptador Workaholic já existente.

Funções novas:

- `contar_ativos`;
- `listar_paginado` — busca, filtro por CPF/CNPJ formatado e paginação da tela
  `/clientes`;
- `listar_para_selecao` — select de clientes do orçamento;
- `listar_para_os` — select do formulário completo de OS;
- `obter_linha` — formulário de edição com todas as colunas legadas;
- `obter_para_orcamento` — validação do cliente no orçamento;
- `obter_resumo_ativo` e `buscar_rapida` — abertura rápida de OS.

Consumidores migrados:

- `portal_prestador.py`: `/`, `/clientes`, `/clientes/{id}`, `/orcamento`,
  seletor de cliente da OS, busca rápida da OS e validação do orçamento;
- `gtk_app.py`: contagem de clientes ativos do painel inicial.

**Comportamento preservado:** mesmos filtros, ordem, limites, colunas e
mensagens. Nenhum HTML, CSS, texto ou rota foi alterado. A única mudança de
estrutura é a localização do SQL.

**Testes:** `test_integracao_clientes` com 10 OK, cobrindo busca por nome,
cidade, e-mail, documento formatado, paginação, listas ativas, formulário
legado e busca rápida.

**O que ainda falta do #1:** detalhe de OS, financeiro, estoque, anexos,
eventos, dashboard GTK e outros fluxos. Cada um deve ser migrado como uma fatia
própria, com teste de caracterização antes.

### 2.1.1 Resumos e listas de OS

Também saíram do handler/GTK as leituras de resumo e histórico de OS, agora em
`repositorios/ordens.py`:

- `resumo` — contagens de OS abertas/iniciadas/pendentes/concluídas;
- `financeiro_resumo` — recebido, pendente e alias `a_receber`;
- `recentes` — últimas OS da visão geral;
- `listar_historico` — OS encerradas + versão publicada do PDF;
- `listar_relatorios` — OS para relatórios/e-mails/notas;
- `listar_origem_portal` — solicitações criadas pelo Portal do Cliente.

Consumidores migrados: `portal_prestador.inicio`, `os_lista(concluidas=True)`,
`relatorios`, `portal_cliente` e `gtk_app._atualizar_inicio`.

**Comportamento preservado:** mesmas consultas, filtros de arquivamento, ordem,
limites e colunas. Nenhuma alteração de HTML, CSS, rota ou texto.

**Testes:** `test_repositorios_ordens` com 5 OK, além dos testes HTTP de portal.

### 2.2 Configuração de runtime centralizada

Foi criado `runtime_config.py`, sem dependências de UI, banco ou portal. Ele é
a fonte única para:

- `AUTOSEG_BASE` e `GESTAO_BANCO`;
- host, porta e HTTPS do Portal do Prestador;
- host e porta do Portal do Cliente;
- defaults de desenvolvimento (`AUTOSEG_DEV=1` → 8865/8866);
- leitura pontual de `CLIENTE_PORT` para links entre portais.

Entry points migrados:

| Arquivo | Antes | Depois |
|---|---|---|
| `servidor_backend.py` | `os.environ.get("CLIENTE_PORT", ...)` e `PRESTADOR_PORT` duplicados | `client_server()` / `provider_server()` |
| `gtk_app.py` | portas e binds lidos no meio da inicialização | `client_server()` / `provider_server()` |
| `portal_prestador.py` | host, porta e `PRESTADOR_HTTPS` no construtor/`iniciar`; `CLIENTE_PORT` no link | `provider_server()`, `provider_https()` e `client_port()` |
| `banco.py` | `PASTA_APP`/`BANCO` lidos do ambiente | `base_dir()` / `database_path()` |
| `prestadores_ext.py` | `BASE` lido do ambiente | `base_dir()` |
| `links_publicos.py` | `BASE` lido do ambiente | `base_dir()` |

Leituras restantes de ambiente em `composicao.py`, `versao_app.py`,
`gtk_comum.py` e `meu_auto_financeiro.py` ficam para a próxima fatia de
configuração; nenhuma delas foi alterada agora.

**Comportamento preservado:**

- as mesmas variáveis de ambiente continuam valendo;
- os mesmos defaults são usados (8765/8766 no MAIN; 8865/8866 no DEV);
- host explícito passado ao construtor continua tendo precedência sobre
  `PRESTADOR_BIND`, como antes;
- `PRESTADOR_PORT` continua tendo precedência sobre a porta passada ao
  construtor, como antes;
- nenhuma tela, rota, HTML, CSS, banco ou regra foi alterado.

**Exceção intencional e limitada ao DEV:** o link “Abrir Portal do Cliente” no
portal do prestador passa a usar `CLIENTE_PORT` (8865 no DEV). Antes ele
apontava fixamente para 8765 mesmo no DEV. No MAIN, sem `CLIENTE_PORT`, o link
continua 8765 e o texto permanece o mesmo.

### Testes

- `test_runtime_config.py`: defaults, modo DEV, overrides de ambiente e
  `PRESTADOR_HTTPS`.
- Suítes de regressão executadas após a mudança (ver seção 4).

---

## 3. Próximas fatias recomendadas

1. **Configuração de dados** — as bases `BASE`/`BANCO` já usam
   `runtime_config.py`; faltam as leituras restantes em `composicao.py`,
   `versao_app.py`, `gtk_comum.py` e `meu_auto_financeiro.py`. Baixo risco.
2. **Continuar o #1** — clientes e resumos/listas de OS já estão fora da UI;
   faltam detalhe de OS, financeiro, estoque, anexos/eventos e outros fluxos
   GTK. Uma fatia por vez, com caracterização antes.
3. **Runner de migrações versionado** — tabela `schema_version`, migrações
   numeradas e idempotentes; só depois pensar em Postgres.
4. **Plumbing web compartilhado** — sessão, cookie, CSRF, `form()` e templates
   em um módulo comum; migrar um portal por vez.
5. **Fila SQLite de jobs** — publicar PDF, enviar e-mail e importar com
   idempotência e retry.

---

## 4. Testes executados nesta fatia

```bash
python3 -m unittest test_runtime_config
python3 -m unittest test_rev12_correcoes
python3 -m unittest test_feedback_portal test_api_financeiro test_rev12_melhorias
python3 -m unittest test_meu_auto_financeiro
```

Resultados desta fatia:

- `test_runtime_config`: **5 OK**.
- `test_integracao_clientes`: **10 OK**.
- `test_repositorios_ordens`: **5 OK**.
- Suíte combinada `test_runtime_config + test_integracao_clientes +
  test_repositorios_ordens + test_rev12_correcoes + test_feedback_portal +
  test_api_financeiro + test_rev12_melhorias + test_meu_auto_financeiro`:
  **117 OK, 1 skipped**.
- `py_compile` de `runtime_config.py`, `portal_prestador.py`, `gtk_app.py`,
  `servidor_backend.py` e `integracao/clientes.py`: **OK**.
- `test_autoseg_http_novo` falha também no `HEAD` anterior a esta mudança
  (teste legado de formulário, não relacionado a esta fatia). Registrado como
  dívida de teste, não como regressão.
- A mudança é de leitura/estrutura; nenhum HTML, CSS ou texto de interface foi
  alterado.

---

## 5. Como reverter

1. Reverter o commit desta fatia.
2. Os arquivos antigos continuam funcionando porque as variáveis de ambiente e
   defaults foram preservados.
3. Não há migração de banco, alteração de dados ou mudança de contrato de
   arquivos.

---

## 6. Documentos relacionados

- `README.md`
- `AGENTS.md`
- `docs/PLANO_EVOLUCAO_ARQUITETURA.md` — seções 3.1–3.10
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md`
- `docs/PLATFORM_MIGRATION_LEDGER.md`
- `docs/WORKAHOLIC_INTEGRACAO.md`
- `KNOWN_ISSUES.md`
- `ROADMAP.md`
- `docs/GTK4_LINUX_MACOS.md`
- `docs/NAMING_AND_CLI.md`
