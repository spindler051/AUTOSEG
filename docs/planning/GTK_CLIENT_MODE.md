# Cliente no GTK — análise e MVP da peça 6.5

**Status:** planejado; não implementado.
**Dependência:** fechar o gate P0 de autorização por objeto.
**Objetivo:** permitir que uma conta cliente entre no app GTK e veja apenas os
próprios dados, reutilizando autenticação, sessão e política do site, sem
duplicar regra de negócio no widget.

## 1. Estado atual

O GTK é provider-only de ponta a ponta:

- `gtk_login.py` oferece conta local ou servidor, mas o campo do servidor é
  “E-mail do prestador”;
- `HttpService.login` chama `/api/v1/desktop/login`, que usa
  `prestador_auth.login` e devolve `prestador`;
- `desktop_sessoes` guarda `prestador_id`; não existe vínculo de cliente;
- `Sessao` guarda `prestador_id`, `admin`, `role` e permissões, sem
  `identity_kind` nem `client_id`;
- `/api/v1/desktop/me` força `identity.load_identity(..., 'provider', ...)`;
- as rotas `/api/v1/desktop/*` são operações de prestador (clientes, OS,
  financeiro, catálogo, estoque, composição etc.);
- a `Janela` do GTK monta a navegação e as páginas do prestador;
- o modo local do GTK também é provider-only;
- a API desktop ainda não aplica todas as regras de objeto/papel nas rotas de
  OS.

O que já existe e deve ser reutilizado:

- `auth.authenticate` aceita cliente;
- `SessionContext` já tem `identity_kind`, `client_id`, `client_org_ids` e
  permissões;
- `client_service`/`client_web` já implementam a leitura client-safe usada pelo
  site;
- `ObjectPolicy`/`work_item_access` já modelam o acesso por objeto;
- o site já tem login único em `/login` e home do cliente.

## 2. Lacunas por camada

### 2.1 Autenticação desktop

- Criar um login desktop que aceite cliente e prestador.
- Não criar uma segunda regra de senha: reutilizar `auth.authenticate` e a
  política de identificadores.
- Erros continuam genéricos, sem enumerar existência, papel ou inatividade.
- Rate limit compartilhado com o login web.

### 2.2 Sessão desktop

- Definir se `desktop_sessoes` passa a guardar `account_id`/`identity_kind` ou se
  haverá uma tabela de sessão de desktop genérica.
- O token continua revogável e com hash no banco.
- `Sessao` do cliente precisa carregar `identity_kind`, `client_id`,
  `client_org_ids`, papel, permissões e `context_label`.
- Restaurar sessão (`/me`) e logout devem funcionar igual ao prestador.

### 2.3 API desktop

- `/api/v1/desktop/login` e `/me` precisam devolver o contexto cliente.
- Rotas de prestador precisam negar cliente com `403` antes de qualquer leitura
  ou escrita.
- Endpoints client-safe do MVP:
  - resumo/home do cliente;
  - lista das próprias OS;
  - detalhe de uma OS própria;
  - logout.
- Reutilizar `client_service`/`work_item_access`; não colocar SQL no handler.
- Testes negativos: cliente A não lê OS de cliente B, não lê OS de outra
  prestadora, não acessa financeiro/prestadores/estoque.

### 2.4 UI GTK

- Ajustar o texto do login para “E-mail, CPF ou telefone” e explicar que a mesma
  entrada aceita prestador e cliente.
- Criar uma projeção cliente da `Janela`: navegação reduzida, sem financeiro,
  prestadores, estoque, caixa ou configuração administrativa.
- Home cliente com as próprias OS; “Em rota” e documentos ficam para a 6.6.
- Não criar uma segunda árvore de apresentação; usar o mesmo shell e o mesmo
  contrato de navegação, filtrando por contexto/permissão.

### 2.5 Modo local

- O modo local do GTK é provider-only.
- No MVP, cliente entra **remote-only**; o seletor local não aparece para
  cliente ou explica que o modo local ainda não tem cliente.
- Modo local cliente exige um serviço local client-safe e uma decisão de
  sincronização; não entra na 6.5.

### 2.6 Permissões e rollout

- A 6.5 depende da autorização por objeto no serviço, não só da UI.
- Flag própria para o login cliente no GTK (proposta:
  `AUTOSEG_GTK_CLIENT_LOGIN`), desligada por padrão.
- Testar desativação da conta, troca de papel, revogação de token, logout e
  restart.
- Smoke manual: cliente entra, vê só as próprias OS, não vê menus de prestador,
  sai e o token antigo é rejeitado.

## 3. MVP da 6.5

**Entra:**

- login remoto de cliente;
- `/me` com contexto cliente;
- home somente leitura com as próprias OS;
- detalhe de OS própria, se o contrato de leitura já existir;
- logout real;
- bloqueio das rotas de prestador;
- testes negativos e smoke.

**Não entra:**

- pedido de serviço pelo GTK;
- documentos/PDF;
- “Em rota”;
- financeiro do cliente;
- modo local;
- paridade visual completa;
- administração de contas/papéis pelo GTK.

## 4. Critérios de aceite

1. Cliente válido entra e recebe sessão com `identity_kind=client` e
   `client_id` correto.
2. Cliente vê somente as próprias OS; outro cliente recebe `403`/`404` sem
   vazar existência.
3. Cliente não acessa `/api/v1/desktop/clientes`, `/financeiro`, `/prestadores`,
   `/estoque`, `/caixa` nem `/composicao`.
4. Prestador continua com o comportamento atual; nenhuma rota/negócio muda.
5. Logout revoga o token e limpa a sessão local; token antigo retorna `401`.
6. Conta inativa, senha errada e papel inválido usam a mesma mensagem genérica.
7. Suíte focada, regressão, smoke GTK e auditoria de comentários passam.
8. Rollback: desligar a flag restaura o GTK provider-only sem migração de
   dados.

## 5. Decisões pendentes

- **Sessão:** reutilizar `desktop_sessoes` com colunas genéricas ou criar uma
  tabela/namespace de sessão desktop? A primeira opção é menor, mas exige
  migração idempotente e revisão de autenticação (N3).
- **Token:** o cliente usa o mesmo formato `autoseg_desktop_...` ou um prefixo
  separado? O formato e a revogação devem ser únicos.
- **Escopo do MVP:** home + lista de OS é suficiente, ou o detalhe da OS entra
  já na 6.5? Recomendação: lista + detalhe somente leitura, se o contrato já
  estiver authorizado.
- **Modo local:** manter remote-only na 6.5 e decidir o local na 6.6.

## 6. Arquivos prováveis

- `flavors/autoseg/modules/gtk_login.py` — campos e fluxo de login;
- `flavors/autoseg/modules/gtk_app.py` — projeção cliente da janela/navegação;
- `flavors/autoseg/modules/api_desktop.py` — login, `/me` e rotas client-safe;
- `flavors/autoseg/modules/prestador_auth.py` — sessão desktop genérica ou
  adaptador;
- `officina/application/session.py` — `Sessao` genérica;
- `officina/application/http_service.py` — contrato remoto do cliente;
- `officina/application/contracts.py` — DTOs/contexto;
- `flavors/autoseg/modules/client_service.py` / `client_web.py` — reutilização
  da leitura client-safe;
- testes novos de API desktop, sessão e smoke GTK.

## 7. Relação com outras peças

- 5.1–5.5: identidade, login e sessão web;
- 6.1–6.4: shell web, papéis, `SessionContext`, navegação e cliente web;
- 6.5: este MVP remote-only;
- 6.6: paridade cliente no GTK, documentos/PDF, “Em rota” e modo local;
- `docs/operations/OBJECT_POLICY_ROLLOUT.md`: bloqueio de produção e TOCTOU;
- `docs/planning/WEB_GTK_SHARED_CONTRACT.md`: contrato de telas/ações;
- `docs/ROADMAP.md`: ordem prática e gate P0.

## 8. Não objetivos

- criar um segundo portal dentro do GTK;
- duplicar regra de OS ou de permissão no widget;
- liberar cliente em produção antes da autorização por objeto;
- usar `if admin`/`if cliente` fora da política;
- prometer paridade total antes de o contrato compartilhado existir.
