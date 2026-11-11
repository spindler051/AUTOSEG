# Peça 6.4 — shell web unificado (prestador e cliente no mesmo site)

**Uso:** colar no ChatGPT. Trabalha sobre uma cópia do repositório, **não faz
commit**, devolve ZIP.

**Base:** `4304ef7` (main com 5.1–5.5, 6.1, 6.2 e 6.3 integradas).
**Dependências:** 6.1 (shell/login/cliente), 6.2 (papéis/permissões) e 6.3
(`SessionContext`).
**Entrega:** ZIP com arquivos completos, patch, testes e notas.

## 1. Missão

Corrigir a arquitetura de apresentação: **Officina Web é um site só**. O
prestador e o cliente usam a mesma shell, o mesmo layout, os mesmos componentes
e o mesmo código de navegação. O que muda é o **contexto da conta**, as
permissões e os módulos que aparecem.

- “Portal do prestador” é o rótulo/contexto de quem entrou como prestador.
- “Portal do cliente” é o rótulo/contexto de quem entrou como cliente.
- O produto não é “dois portais”: é uma raiz Officina Web com visões.
- O prestador vê a operação completa; o cliente vê o recorte dele.
- Funcionalidades exclusivas de cliente são **módulos** da mesma shell, não um
  site separado.
- `/cliente` passa a ser alias/redirect durante a transição, não uma árvore de
  apresentação paralela.

A 6.1 entregou uma home de cliente separada, com apresentação própria. Esta
peça corrige isso sem reescrever as regras de negócio nem o fluxo de OS.

## 2. Regras de design

- Reutilizar o CSS, classes, componentes, tipografia, cores, espaçamento,
  ícones e estados existentes. Nada de framework, SPA, CSS paralelo ou
  redesign gratuito.
- A experiência do prestador deve continuar visualmente a mesma. O cliente usa
  a mesma chrome, com navegação e conteúdo reduzidos.
- A tela de login deve usar a mesma shell/design tokens, com hierarquia e
  espaçamento melhores, marca “Officina Web” e o rótulo de contexto. Não é
  preciso inventar uma nova identidade visual.
- Responsividade, acessibilidade, foco, contraste e `prefers-reduced-motion`
  devem seguir o que já existe.
- Não esconder permissão apenas no HTML; o serviço continua sendo a autoridade.

## 3. Arquitetura obrigatória

### 3.1 Shell única

Criar/consolidar uma shell de apresentação reutilizável:

```python
@dataclass(frozen=True)
class ShellPage:
    title: str
    content: str
    context: SessionContext | PageContext
    navigation: tuple[NavItem, ...]
    active: str = ""

def render_shell(page: ShellPage) -> str
```

- A shell é a única dona de header, sidebar/topbar, navegação, rodapé,
  mensagens flash e estrutura principal.
- O conteúdo de cada tela é **fragmento**, não uma página HTML completa.
- Provider e client passam pela mesma função.
- `officina_web.page()` deixa de escolher um layout alternativo para cliente.
- `client_web.py` deixa de montar header/nav próprios; devolve apenas o
  conteúdo do módulo.
- Preservar o CSS/HTML atual do prestador: extrair a chrome existente para a
  shell e usá-la nos dois contextos, em vez de criar outra.
- Se a extração do `layout_app` for grande, faça por adaptação: uma função
  compartilhada que recebe contexto/nav/conteúdo e mantém os mesmos marcadores
  visuais do prestador.

### 3.2 Contexto e navegação

- `SessionContext` (6.3) define `role`, `permissions`, `context_label`,
  `client_org_ids` etc.
- `NavItem` ganha `permission: str | None` e, se necessário, `roles`/
  `contexts` como dados.
- A navegação é montada por uma função única:

```python
def navigation_for(context: SessionContext) -> tuple[NavItem, ...]
```

- Provider vê a navegação operacional completa.
- Cliente vê o subconjunto permitido e os módulos client-only.
- Não criar `provider_navigation()` e `client_navigation()` que duplicam
  itens. Uma única tabela de itens, filtrada por permissão/contexto.
- A navegação superior (top nav) e a lateral/sidebar devem sair da **mesma**
  tabela. Se uma precisa de um subconjunto, marque isso no próprio `NavItem`
  (por exemplo `top=True`); não mantenha uma segunda lista de menus no
  `layout`.
- A decisão de mostrar item administrativo deve vir das permissões já
  filtradas, nunca de um `usuario.get('admin')` paralelo.
- O item ativo é calculado pela rota, não por `if portal == ...`.

### 3.3 Rotas

Criar um registro único de rotas de apresentação, por exemplo:

```python
@dataclass(frozen=True)
class WebRoute:
    path: str
    permission: str | None
    contexts: tuple[str, ...]      # ("provider",), ("client",), ambos
    handler: Callable
```

Regras:

- `/` é a raiz: renderiza o dashboard do provider ou o dashboard do cliente
  conforme o contexto, sempre pela mesma shell.
- `/entrar` é o login único; `/login` antigo continua como fallback.
- Rotas compartilhadas onde fizer sentido (`/os`, `/documentos`, `/perfil`);
  o serviço filtra os dados por permissão/escopo.
- Rotas client-only (por exemplo, acompanhamento de “em rota” mais amplo)
  entram como módulos com `contexts=("client",)` e permissão explícita.
- `/cliente`, `/cliente/painel`, `/cliente/os` etc. redirecionam para as rotas
  compartilhadas equivalentes; não renderizam uma segunda chrome.
- Rotas antigas do prestador continuam funcionando; não renomear URLs
  existentes sem redirect.
- Rotas desconhecidas e contextos errados falham fechado.

### 3.4 Login

- `/entrar` usa a shell e o design existente, com:
  - marca “Officina Web”;
  - rótulo “Acesso à plataforma”;
  - formulário `identificador` + `senha`;
  - link discreto “Usar login antigo” para `/login`;
  - erro genérico e identificador preservado.
- O login não decide o destino por `if cliente`; usa o `SessionContext` ou o
  tipo de identidade retornado pelo serviço.
- Provider e client caem na mesma raiz `/`; a shell mostra o contexto correto.
- Melhorar a aparência sem novo framework e sem quebrar o layout do portal do
  prestador.

### 3.5 Módulos client-only

- Criar um módulo de exemplo real para um detalhe exclusivo de cliente, por
  exemplo um painel “Em rota” mais amplo ou uma facilidade de acompanhamento.
- O módulo é conteúdo dentro da shell; não cria header, sidebar ou CSS próprio.
- O módulo é filtrado por `contexts=("client",)` e permissão; provider não vê.
- A regra de negócio continua no `client_service`, não no módulo de
  apresentação.
- Não implementar todos os edge cases nesta peça; um exemplo bem feito basta.

### 3.6 Correção única e matriz de impacto

A shell compartilhada existe para que um problema comum tenha **uma correção
só**. Toda correção de bug/feedback deve ser classificada antes de codar:

- **Comum aos dois contextos:** o componente, rota ou comportamento é
  compartilhado. Corrigir uma vez no código compartilhado e provar com teste
  nos dois contextos (provider e client). Não criar duas correções.
- **Específico de um contexto:** o problema só existe no módulo/rota daquele
  contexto. Corrigir no módulo certo e adicionar teste apenas para ele. Não
  copiar a correção para o outro lado.
- **Diferença de permissão/dados:** a tela é a mesma, mas o conteúdo muda por
  escopo. A correção é na política/serviço ou no dado, não em dois templates.

Regras práticas:

- não usar `if client`/`if provider` para forkar HTML de um componente
  compartilhado; usar contexto, permissão ou módulo;
- um bug no header, navegação, tabela, formulário, login ou rodapé é comum por
  definição e deve ser corrigido uma vez;
- um bug no painel “Em rota” do cliente, se for exclusivo dele, fica no módulo
  client-only;
- se o mesmo feedback aparece para os dois papéis, o teste de regressão deve
  cobrir os dois; se aparece em um só, o teste cobre o contexto afetado;
- o revisor deve poder olhar o diff e dizer “isto é shared” ou “isto é
  client-only” sem encontrar a mesma lógica duplicada.

## 4. O que não fazer

- Não criar um segundo site, uma segunda shell ou um “layout de cliente”.
- Não duplicar CSS, header, sidebar, navegação ou componentes.
- Não reescrever as regras de OS, financeiro, PDFs, permissões ou banco.
- Não ligar `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` nem
  `AUTOSEG_WEB_SESSION_DURABLE`; a 6.4 é apresentação, não ativação.
- Não resolver o TOCTOU nesta peça.
- Não criar modo cliente no GTK.
- Não usar framework, SPA, React, Tailwind, npm ou dependência nova.
- Não colocar SQL/regra de negócio no handler ou template.
- Não remover o `/login` antigo nem o portal antigo do cliente na 8765.
- Não “consertar” teste reduzindo cobertura.

## 5. Testes obrigatórios

Criar/expandir `tests/test_shared_shell.py` e ajustar os testes existentes.
Cobrir, no mínimo:

1. provider e client usam a mesma função de shell e os mesmos marcadores de
   chrome (header/sidebar/footer/classes);
2. provider mantém os marcadores visuais atuais;
3. client vê a mesma chrome, com navegação reduzida e sem itens de provider;
4. provider não vê módulos client-only;
5. client vê o módulo client-only permitido;
6. item de navegação sem permissão não aparece;
7. `/cliente` e rotas antigas redirecionam para as rotas compartilhadas;
8. `/entrar` funciona para os dois papéis e cai na mesma raiz;
9. `/login` antigo continua funcionando;
10. flag de login unificado desligada mantém o fluxo antigo;
11. contextos errados são negados;
12. nenhuma tela cliente renderiza uma segunda chrome;
13. login usa o design existente, sem novo framework;
14. um bug comum de chrome/componente tem uma única correção e regressão nos
    dois contextos;
15. top nav e sidebar do provider saem da mesma tabela de navegação; mudar um
    item/flag nela reflete nos dois;
16. top nav e sidebar do cliente saem da mesma tabela, com o mesmo filtro de
    permissões;
17. um módulo client-only não aparece para provider e sua correção não altera
    o provider;
18. o diff não contém duas versões da mesma lógica de apresentação;
19. suítes 6.1/6.2/6.3 e regressão do portal continuam passando.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_shared_shell tests.test_officina_web tests.test_client_web \
  tests.test_client_roles tests.test_login_web tests.test_session_context \
  tests.test_web_session tests.test_web_cookie tests.test_auth \
  tests.test_accounts -v
```

Regressão:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_rev12_correcoes tests.test_admin_parity tests.test_portal_v4 -v
```

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  tests.test_autoseg_http_novo tests.test_fluxo_cliente_v94 \
  tests.test_pf_pj_http tests.test_v953_http -v
```

Se não houver `.venv`, registrar o erro exato; não declarar aprovação.

## 6. ZIP

```text
officina-shared-shell/
├── changed-files/
│   ├── officina/web/...
│   ├── flavors/autoseg/modules/officina_web.py
│   ├── flavors/autoseg/modules/client_web.py
│   ├── flavors/autoseg/modules/login_web.py
│   ├── flavors/autoseg/modules/portal_prestador.py
│   └── tests/...
├── officina-shared-shell.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, PDFs, logs, tokens ou PII.

## 7. Critérios de aceite

- Uma shell, uma chrome, um login e uma raiz para provider e client.
- Nenhuma segunda árvore de apresentação de cliente.
- Provider com a mesma experiência visual e rotas.
- Client com o mesmo site, navegação reduzida e módulo client-only real.
- `/cliente` como alias/redirect, não site paralelo.
- Um bug/feedback comum tem uma única correção e testes nos dois contextos; um
  bug exclusivo fica no módulo do contexto afetado.
- Top nav e sidebar não mantêm listas de menu duplicadas.
- Nenhuma regra de negócio nova no handler.
- Flags 6.2/6.3 intocadas e desligadas.
- Testes e regressões passando, ou erro exato registrado.
- Diff limitado aos arquivos permitidos.
