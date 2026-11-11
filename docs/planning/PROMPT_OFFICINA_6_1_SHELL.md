# Peça 6.1 — Officina Web: shell único, login de cliente/prestador e home do cliente

**Uso:** colar no ChatGPT. Trabalha sobre uma cópia do repositório, **não faz
commit**, devolve ZIP.

**Base:** `c5a836b` (main após as peças 5.1–5.5).
**Dependências:** 5.1–5.5 integradas.
**Entrega:** ZIP com arquivos completos, patch, testes e notas.

## 1. Missão

Transformar o portal do prestador no primeiro **Officina Web**: um site, uma
origem, um login, um cookie/sessão e um shell. Prestador e cliente entram por
`/entrar`; o sistema identifica o vínculo e mostra a home correta. O prestador
continua com a mesma experiência visual e as mesmas rotas. O cliente ganha a
primeira home no mesmo site: **suas OS, seus documentos e uma solicitação de
serviço**.

Esta peça é deliberadamente grande, mas tem limites claros: não cria papéis de
cliente, não implementa OS anônima, não troca a sessão por armazenamento
durável e não mexe no GTK. Esses itens ficam para 6.2/6.3.

## 2. Decisões de produto

- O produto visível passa a se chamar **Officina Web**.
- O topo continua mostrando o contexto: **“Portal do prestador”** ou
  **“Portal do cliente”**, conforme a conta logada.
- A marca/identidade AUTOSEG continua no flavor; não renomeie tabelas, banco,
  módulos legados ou URLs existentes nesta peça.
- **Um único servidor/origem**: use o servidor do portal do prestador como site
  unificado. O portal antigo do cliente (porta 8765) continua existindo como
  fallback durante a transição.
- **Um único login** em `/entrar`: `auth.authenticate` aceita prestador e
  cliente. O mesmo cookie `autosseg_unified` e a mesma sessão valem para os
  dois.
- O prestador mantém a mesma UI, navegação, CSS, telas e fluxo. Só o nome do
  produto e o shell/contexto mudam.
- O cliente vê uma home enxuta: lista das próprias OS, documentos/PDF e um
  pedido de serviço. Não vê financeiro, clientes, estoque, administração,
  prestadores ou qualquer rota de prestador.
- Com a flag `AUTOSEG_UNIFIED_LOGIN` desligada, `/entrar` redireciona para
  `/login` e o site continua no fluxo antigo. O portal antigo do cliente
  continua funcionando na 8765.

## 3. Arquitetura obrigatória

### 3.1 Pacote genérico `officina/web/`

Criar um pacote pequeno, sem importar AUTOSEG:

```text
officina/web/
├── __init__.py
├── brand.py
├── context.py
└── shell.py
```

`brand.py`:

```python
@dataclass(frozen=True)
class Brand:
    product_name: str
    provider_label: str
    client_label: str
    logo_url: str = "/logo.png"
    accent: str = "ambar"
```

`context.py`:

```python
@dataclass(frozen=True)
class NavItem:
    id: str
    label: str
    href: str
    permission: str | None = None

@dataclass(frozen=True)
class PageContext:
    brand: Brand
    kind: str                 # "provider" | "client" | "anonymous"
    display_name: str
    context_label: str
    navigation: tuple[NavItem, ...] = ()
    csrf: str = ""
```

`shell.py`:

```python
def render_page(*, title: str, body: str, context: PageContext) -> str
def render_login(*, brand: Brand, error: str = "", identifier: str = "") -> str
```

Regras:

- `render_page` **devolve HTML**; quem envia é o handler. Não chame
  `handler.pagina`/`responder` dentro do shell.
- O shell não contém regra de negócio, SQL, permissão real ou HTML de tela
  específica.
- Reutilize o CSS/classes existentes do portal; não crie framework, template
  engine ou redesign.
- O shell deve permitir que o prestador continue com a página atual. Se for
  necessário, ele envelopa o `layout_app` existente em vez de reescrevê-lo.
- A navegação é uma lista de `NavItem`; o shell só renderiza o que recebe.
  Esconder um item não autoriza nada: o serviço continua validando.

### 3.2 Adaptador AUTOSEG `officina_web.py`

Criar `flavors/autoseg/modules/officina_web.py` com:

```python
BRAND = Brand(
    product_name="Officina Web",
    provider_label="Portal do prestador",
    client_label="Portal do cliente",
)

def context_for(session, csrf: str = "") -> PageContext
def provider_navigation(admin: bool) -> tuple[NavItem, ...]
def client_navigation() -> tuple[NavItem, ...]
def page(handler, title: str, body: str, session=None, status: int = 200) -> None
def login_page(handler, error: str = "", identifier: str = "") -> None
```

- `page` chama `handler.responder(shell.render_page(...))`.
- `login_page` chama `handler.responder(shell.render_login(...))`.
- `context_for` rotula `provider`/`client` e monta a navegação.
- Não coloque SQL nem regra de OS aqui.

### 3.3 Login e sessão

Evoluir `flavors/autoseg/modules/login_web.py` sem quebrar o contrato atual:

```python
def authenticate_and_create(banco, identifier: str, password: str,
                            allowed_kinds: tuple[str, ...] = ("provider", "client")
                            ) -> tuple[str, web_session.SessionData]
def unified_session(handler, banco) -> web_session.SessionData | None
def provider_session(handler, banco) -> dict | None
def client_session(handler, banco) -> web_session.SessionData | None
```

Regras:

- `authenticate_and_create` aceita prestador **e** cliente; rejeita qualquer
  outro tipo como `auth.LoginError("invalid")`.
- Todas as falhas públicas continuam com a mesma mensagem genérica.
- `unified_session` lê o cookie, resolve e devolve a sessão, sem filtrar papel.
- `provider_session` devolve o dicionário antigo do portal do prestador
  (`pid`, `nome`, `admin`, `csrf`, `telemetry_session`, `exp`, `unified`);
  **não inclua `cred`/hash**.
- `client_session` devolve `SessionData` somente se `identity.kind == "client"`.
- A flag desligada continua ignorando o cookie unificado.

### 3.4 Serviço do cliente

Criar `flavors/autoseg/modules/client_service.py` com dados e casos de uso,
sem SQL/HTML no handler:

```python
@dataclass(frozen=True)
class ClientWorkItem:
    id: int
    number: str
    status: str
    description: str
    organization: str
    updated_at: str
    has_documents: bool

@dataclass(frozen=True)
class ClientDocument:
    id: int
    name: str
    kind: str          # "report" | "invoice"
    work_id: int

def list_work_items(banco, session) -> tuple[ClientWorkItem, ...]
def get_work_item(banco, session, work_id: int) -> ClientWorkItem | None
def list_documents(banco, session, work_id: int) -> tuple[ClientDocument, ...]
def open_document(banco, session, work_id: int, document_id: int) -> tuple[bytes, str, str]
def create_request(banco, session, description: str, urgency: str) -> ClientWorkItem
```

Regras:

- Nesta peça o cliente só vê **as próprias OS/solicitações**; o vínculo é o
  `identity.id` do cliente (`v9_usuarios.id`). Não use apenas e-mail/CPF.
- Reutilize `fluxo_pf.listar_os_pf`, `fluxo_pf.obter_os_pf`,
  `fluxo_pf.registrar_os_pf`, `ext.listar_notas_fiscais` e
  `fluxo.validar_pdf_publicado` quando possível.
- Se precisar consultar `v9_chamados`/`ordens_servico`, faça no serviço,
  com o `usuario_id`/vínculo correto e teste negativo de acesso cruzado.
- `create_request` cria uma solicitação particular pelo fluxo existente e
  devolve o item criado. Não invente status, preço ou regra de OS.
- Acesso cruzado devolve `None`/`PermissionError`, nunca 404 com dados.
- Não logar nome, CPF, descrição, anexo ou token.

### 3.5 Rotas do cliente no site unificado

Criar `flavors/autoseg/modules/client_web.py`:

```python
def home(handler, banco, session) -> None
def list_items(handler, banco, session) -> None
def item_detail(handler, banco, session, work_id: int) -> None
def documents(handler, banco, session) -> None
def request_form(handler, banco, session, error: str = "",
                 description: str = "", urgency: str = "") -> None
def request_submit(handler, banco, session, data) -> None
def download(handler, banco, session, work_id: int, document_id: int) -> None
```

Rotas GET:

- `/cliente` e `/cliente/painel` → home.
- `/cliente/os` → lista.
- `/cliente/os/<id>` → detalhe.
- `/cliente/documentos` → documentos.
- `/cliente/solicitar` → formulário.
- `/cliente/os/<id>/documento/<doc_id>` → PDF autorizado.
- Compatibilidade: `/cliente/nota/<id>` pode redirecionar ou baixar o PDF
  autorizado; `/cliente/nova` pode redirecionar para `/cliente/solicitar`.

Rotas POST:

- `/cliente/solicitar` → cria solicitação.
- `/cliente/sair` → revoga a sessão unificada e volta para `/entrar` ou
  `/login` conforme a flag.

Regras:

- Toda página usa `officina_web.page`/`shell`.
- Todo POST valida `session.csrf` com `web_cookie.csrf_valid` ou
  `secrets.compare_digest`.
- Não use o cookie/sessão antiga `autosseg_pj` nas rotas novas.
- O cliente nunca recebe link/ação de prestador.
- Se um prestador abrir `/cliente...`, redirecione para `/`; se um cliente
  abrir rota de prestador, negue.

### 3.6 Integração no portal do prestador

Modificar `flavors/autoseg/modules/portal_prestador.py` apenas no necessário:

1. Importar `officina_web`, `client_web`, `login_web` e `web_session`.
2. `pagina()` passa a usar o shell/branding, preservando o layout atual do
   prestador. O prestador deve continuar vendo os mesmos marcadores visuais
   (`Visão geral`, `Ordens de serviço ativas`, `Clientes`, `Financeiro`, etc.).
3. `do_GET`, antes do gate de sessão do prestador:
   - `/entrar` → formulário único.
   - `/cliente...` → resolve `client_session`; se não houver, mostra login
     unificado ou redireciona para `/entrar`; se houver, despacha para
     `client_web`.
   - `/` → se houver sessão de cliente, renderiza a home do cliente; se for
     prestador, segue o dashboard atual.
4. `do_POST`, antes do bloco de `/login`:
   - `/entrar` → login único (prestador ou cliente).
   - `/cliente...` → valida CSRF e despacha para `client_web`.
5. `/sair` deve aceitar sessão unificada de prestador **e** de cliente,
   revogar o token, limpar os dois cookies e redirecionar para `/login`.
   Mantenha o fluxo antigo quando só existir `autosseg_session`.
6. Não alterar as rotas internas do prestador, o layout das telas, o
   financeiro, o PDF, o fluxo de OS ou o portal antigo do cliente.

### 3.7 Compatibilidade e rollback

- `/login` antigo continua funcionando com a flag ligada.
- O portal antigo do cliente na 8765 continua funcionando; não o remova.
- Com a flag desligada, `/entrar` volta a `/login`, o cookie unificado é
  ignorado e as rotas novas do cliente não autenticam.
- Nenhuma migração de banco nesta peça. O cliente é identificado pelas tabelas
  existentes (`v9_usuarios`, `v9_chamados`, `ordens_servico`).

## 4. O que não fazer

- Não criar papéis síndico/zelador/porteiro; nesta peça todo cliente é
  `customer`.
- Não implementar OS anônima, limites por IP/fingerprint ou captcha.
- Não trocar a sessão em memória por SQLite/Redis.
- Não mexer no GTK.
- Não criar financeiro, estoque, clientes ou administração para o cliente.
- Não reescrever o portal do prestador de uma vez nem mover as 5 mil linhas
  para outro arquivo.
- Não duplicar regra de negócio no handler; use `client_service`.
- Não usar framework, template engine, SPA, React, npm ou dependência nova.
- Não logar PII, senha, hash, token, CSRF ou conteúdo de anexo.
- Não alterar `AGENTS.md`, dinheiro, status de OS, PDFs ou e-mails.

## 5. Testes obrigatórios

Criar `tests/test_officina_web.py`, `tests/test_client_web.py` e ajustar
`tests/test_login_web.py` se necessário. Cobrir, no mínimo:

1. provedor entra por `/entrar` e vê o dashboard atual com os mesmos
   marcadores;
2. cliente entra por `/entrar` e vê a home do cliente, não o dashboard de
   prestador;
3. as duas contas usam a mesma origem/porta e o mesmo cookie
   `autosseg_unified`;
4. cliente vê somente as próprias OS/solicitações;
5. cliente não abre OS/documento de outro cliente (404/403, sem vazar dados);
6. cliente baixa somente documento/PDF autorizado;
7. cliente cria uma solicitação e ela aparece na lista;
8. prestador não abre `/cliente...`; cliente não abre rotas de prestador;
9. `/login` antigo continua autenticando o prestador com a flag ligada;
10. portal antigo do cliente continua funcionando (suíte existente);
11. flag desligada: `/entrar` redireciona para `/login`; cookie unificado é
    ignorado; cliente não autentica nas rotas novas;
12. CSRF inválido no POST do cliente é rejeitado;
13. nenhuma resposta de erro contém senha, hash, CPF, nome ou token;
14. o HTML do prestador mantém os marcadores e a navegação essenciais;
15. o HTML do cliente não contém links de financeiro, clientes, estoque,
    prestadores ou administração.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_officina_web tests.test_client_web tests.test_login_web \
  tests.test_web_session tests.test_web_cookie tests.test_auth \
  tests.test_accounts tests.test_login_flags -v
```

E, como regressão do portal:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_rev12_correcoes tests.test_admin_parity tests.test_portal_v4 -v
```

Se não houver `.venv`, registrar o erro exato; não declarar aprovação.

## 6. ZIP

```text
officina-web-shell/
├── changed-files/
│   ├── officina/web/...
│   ├── flavors/autoseg/modules/officina_web.py
│   ├── flavors/autoseg/modules/client_service.py
│   ├── flavors/autoseg/modules/client_web.py
│   ├── flavors/autoseg/modules/login_web.py
│   ├── flavors/autoseg/modules/portal_prestador.py
│   └── tests/...
├── officina-web-shell.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, PDFs, logs, tokens ou PII.

## 7. Critérios de aceite

- Um site/origem, um login e um cookie para prestador e cliente.
- Prestador com a mesma experiência e rotas; nenhuma regressão visível.
- Cliente com home de OS, documentos e solicitação, somente dos próprios dados.
- Shell genérico em `officina/web`, sem importar AUTOSEG.
- Nenhuma regra de negócio/SQL nova no handler.
- `/login` antigo e portal antigo do cliente continuam funcionando.
- Flag desligada restaura o fluxo antigo.
- Testes e suítes acima passando, ou erro exato registrado.
- Diff limitado aos arquivos permitidos.
