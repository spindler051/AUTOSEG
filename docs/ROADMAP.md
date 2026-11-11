# Roadmap vigente

**Atualizado:** 2026-11-11
**Versão:** `9.6.0-dev.73`
**Branch:** `main`
**Foco:** produção do AUTOSEG. Arquitetura genérica e outros toolkits ficam
para depois.

> **Direção registrada em 2026-11-10:** o AUTOSEG terá **um site, um link e um
> login**, com conta/vínculo/contexto e política por objeto. O AUTOSEG é a
> primeira prestadora de serviço do ecossistema Officina; Officina Web/GTK são
> extrações posteriores. Ver
> [`planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md`](planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md)
> e [`planning/OFFICINA_WEB_AND_GTK.md`](planning/OFFICINA_WEB_AND_GTK.md).

> **Decisão registrada em 2026-11-11 — unificação real, sem fallback:** o
> portal antigo do cliente na 8765 **não** será mantido como fallback. Não
> haverá flag, shim, adaptador permanente ou caminho paralelo para preservar
> `servidor_web.py` ou código legado. Rotas antigas que ainda forem contrato
> público recebem redirect explícito com prazo de remoção; as obsoletas são
> removidas. O rollback é por deploy/git, não por fallback em runtime.

## P0-AUTH — gate de autorização ainda aberto

Reabertura pendente restrita a admin nas duas modalidades de flag e revalidada
em transação; alguns writers já recebem guardas transacionais. Permanecem
operações de OS com múltiplas transações e efeitos externos, portanto a
ativação de `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` não foi autorizada.

## Concluído

### Identidade, login e sessões (5.1–5.5)

- **5.1 — accounts:** schema opt-in `accounts`, `account_identifiers`,
  `account_links` e `login_policy`; migração legada idempotente com `dry_run`.
- **5.2 — auth:** autenticação por e-mail, CPF, telefone ou nametag, com
  fallback legado e mensagens sem enumeração.
- **5.3 — sessão:** `web_session` em memória com TTL, token/CSRF, revalidação e
  revogação; depois, SQLite durável atrás de `AUTOSEG_WEB_SESSION_DURABLE`.
- **5.4 — rota:** primeira rota unificada, ainda provider-only; o cliente
  entrou na 6.1 e a rota final foi consolidada em `/login`.
- **5.5 — compatibilidade:** logout, reset de senha, desativação, arquivamento e
  mudança de papel revogam as sessões; rollback por flag.
- **Rota final:** `/login` é a única tela de entrada; `/entrar` foi removida e
  responde `404`. Com a flag desligada, `/login` serve o formulário antigo do
  prestador como rollback.
- **Tela:** o login unificado reutiliza o split-screen do AUTOSEG, com campo
  único “E-mail, CPF ou telefone”, e não o card genérico.
- **GTK:** o botão/menu **Sair** agora revoga o token no servidor, limpa a
  sessão salva e volta ao login.

### Officina Web (6.1–6.4)

- **6.1 — shell e cliente:** uma shell web, home do cliente e login para os dois
  papéis.
- **6.2 — papéis e permissões:** papéis de cliente, `work_item_access`,
  `/contas`, extração de `os_commands` e a flag independente
  `AUTOSEG_OBJECT_POLICY_ENFORCEMENT`, desligada por padrão.
- **6.3 — sessão e contexto:** `SessionContext`, `/api/v1/desktop/me` com
  permissões, navegação do GTK por permissão e sessão durável opt-in.
- **6.4 — shell única:** a mesma chrome, a mesma raiz e uma única tabela de
  navegação para topo e sidebar; `/cliente` virou alias e “Em rota” é um módulo
  client-only.
- **Banco DEV:** 9 contas, 9 vínculos, `ready=True`; backup anterior à migração
  preservado.

### Ainda não é produção

As flags continuam desligadas por padrão. A ativação em produção depende das
decisões abaixo, não apenas do código integrado:

- `AUTOSEG_UNIFIED_LOGIN`;
- `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` — bloqueada pelo TOCTOU entre autorização
  e writer;
- `AUTOSEG_WEB_SESSION_DURABLE` — decisão de produção pendente.

## Agora — P0

1. **Unificação real dos portais, sem fallback**
   - prompt: [`planning/PROMPT_PORTAL_UNIFICATION.md`](planning/PROMPT_PORTAL_UNIFICATION.md);
   - inventariar rotas e responsabilidades de `servidor_web.py`/8765;
   - migrar para a origem única o que ainda for contrato público atual;
   - remover o que for obsoleto e atualizar links, launchers e docs;
   - desligar o processo 8765 e retirar `servidor_web.py` do caminho de
     execução; depois da migração, apagar o arquivo e seus testes/launchers
     antigos;
   - não criar flag, shim, adaptador permanente ou caminho paralelo para manter
     o portal antigo;
   - critério: uma origem, um login, uma shell e um caminho de código; testes e
     smoke cobrindo as rotas que sobreviverem.
2. **Fechar a numeração de OS na MAIN**
   - ensaiar a migração em cópia da MAIN;
   - backup, janela de manutenção e smoke;
   - manter aliases para links, PDFs e e-mails antigos;
   - não reescrever documentos já publicados.
3. **Fechar o gate de autorização por objeto**
   - corrigir ou aceitar formalmente o TOCTOU entre autorização e writer;
   - rodar testes negativos de isolamento entre prestadoras e entre clientes;
   - decidir a ativação de `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` em produção.
4. **Decidir a sessão durável em produção**
   - retenção, revogação entre processos, backup do SQLite de sessões;
   - manter `AUTOSEG_WEB_SESSION_DURABLE` desligada até a decisão.
5. **Consolidar a API/contrato do desktop**
   - manter a paridade do prestador entre GTK, site e API;
   - preparar os endpoints client-safe que a peça 6.5 vai consumir.

## Próximo — 6.5 Cliente no GTK (remote-only)

**Objetivo:** permitir que uma conta cliente entre no app GTK e veja apenas os
próprios dados, reutilizando autenticação, sessão e política do site, sem
duplicar regra de negócio no widget.

**Depende de:** unificação real dos portais e fechamento do gate P0 de
autorização por objeto. É a prova de modularidade do GTK, não um segundo
portal.

**O que falta:**

1. **Login desktop de cliente** — `/api/v1/desktop/login` hoje usa
   `prestador_auth` e devolve `prestador`. Precisa aceitar cliente via
   `auth.authenticate` e devolver o contexto.
2. **Sessão desktop genérica** — `desktop_sessoes` só guarda `prestador_id`, e
   `Sessao` é provider-centric. Precisa de conta/identidade, tipo, cliente/org,
   papel e permissões.
3. **API desktop client-safe** — `/api/v1/desktop/me` força provider e as rotas
   são de prestador. No MVP, faltam home e próprias OS com autorização no
   serviço; documentos/PDF e solicitações ficam para a 6.6.
4. **UI GTK de cliente** — o login diz “E-mail do prestador” e a `Janela` monta
   as páginas do prestador. Falta uma projeção cliente com navegação reduzida e
   sem financeiro/administração.
5. **Modo local** — o modo local do GTK também é provider-only. No MVP, o
   cliente fica **remote-only**; modo local é uma decisão posterior.
6. **Permissões e testes negativos** — cliente só vê as próprias OS/documentos;
   rotas de prestador devem responder `403`; testar troca de papel,
   desativação, revogação e logout.
7. **Rollout** — flag própria, smoke manual e rollback; nada de cliente no GTK
   em produção antes da revisão humana.

**MVP aceitável:** login remoto de cliente, `/me` com contexto cliente, home
somente leitura com as próprias OS, logout e bloqueio total das rotas de
prestador.

**Fora do MVP:** pedido de serviço, documentos/PDF, “Em rota”, financeiro,
modo local e paridade visual completa. Esses itens ficam para a 6.6.

A análise detalhada, decisões e critérios de aceite estão em
[`planning/GTK_CLIENT_MODE.md`](planning/GTK_CLIENT_MODE.md).

## Depois

- **6.6 — paridade cliente no GTK:** solicitações, documentos/PDF, “Em rota”,
  modo local (se aprovado) e paridade com o site;
- sincronização híbrida com servidor como autoridade de numeração, financeiro e
  estoque;
- backup/restauração verificados;
- revisão externa dos módulos de dinheiro, autenticação, permissões, schema e
  migração;
- primeiros ciclos de revisão com IA externa registrados em `docs/reviews/`;
- protocolo de trabalho genérico: vocabulário, fluxo configurável e requisitos
  de conclusão por flavor; planejamento em
  [`planning/WORK_PROTOCOL_TERMINOLOGY_AND_WORKFLOW.md`](planning/WORK_PROTOCOL_TERMINOLOGY_AND_WORKFLOW.md);
- Workaholic como motor real, uma fatia por vez;
- app GTK genérico e flavor AUTOSEG;
- CLI;
- clientes móveis/PWA;
- Qt, WinUI, Jetpack Compose e SwiftUI **somente** se o núcleo e o contrato de
  aplicação estiverem estáveis;
- sync LAN e P2P/WAN apenas depois de servidor central estável.

## Fora de escopo por enquanto

- reescrever tudo de uma vez;
- 20 GUIs em 20 toolkits;
- sincronizar `dados.db` como arquivo;
- trocar SQLite por Postgres sem dor real;
- publicar na MAIN sem revisão humana externa para mudanças N3/N4;
- criar um segundo portal de cliente dentro do GTK;
- manter o portal antigo do cliente na 8765 como fallback, ou criar
  flag/shim/caminho paralelo para preservar código legado.

## Critério para avançar

Uma fase só termina com teste automatizado, smoke manual descrito, backup e
rollback quando houver dados, e documentação atualizada. O estado detalhado
está em [`HANDOFF.md`](HANDOFF.md).
