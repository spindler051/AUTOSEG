# Peça 6.3 — Sessão durável e contexto compartilhado com o GTK

**Uso:** colar no ChatGPT. Trabalha sobre uma cópia do repositório, **não faz
commit**, devolve ZIP.

**Base:** `c76fbe4` (main com as peças 6.1 e 6.2 integradas).
**Dependências:** 6.1 (shell/login/cliente) e 6.2 (papéis/permissões).
**Entrega:** ZIP com arquivos completos, patch, testes e notas.

A 6.2 entrou com `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`. Esta peça não deve
ligar essa flag, alterar a matriz de papéis nem mexer na fronteira de comandos
de OS; ela só troca a sessão por SQLite e expõe o contexto compartilhado.

## 1. Missão

Fechar a base de sessão e contexto:

1. trocar a sessão web em memória por uma **sessão durável em SQLite**,
   compartilhável entre processos locais e sobrevivente a restart;
2. expor um **contexto de sessão/permissões** comum para web e GTK;
3. fazer o GTK consumir esse contexto em uma tela/ação real, sem duplicar
   regra de permissão.

Se o GTK exigir uma segunda implementação da regra ou uma reescrita grande,
**pare** e registre o bloqueio; a sessão durável e o contrato de contexto ainda
devem ser entregues. Não invente um modo cliente no GTK nesta peça.

## 2. Sessão durável

### 2.1 Tabela

Criar `web_sessions` de forma idempotente em `web_session.install(banco)`:

```sql
CREATE TABLE IF NOT EXISTS web_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_hash TEXT NOT NULL UNIQUE,
  account_id INTEGER,
  source TEXT NOT NULL CHECK(source IN ('account','legacy')),
  identity_kind TEXT NOT NULL CHECK(identity_kind IN ('provider','client')),
  identity_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  provider_org_id TEXT,
  provider_id INTEGER,
  client_id INTEGER,
  client_org_ids TEXT NOT NULL DEFAULT '[]',
  csrf TEXT NOT NULL,
  telemetry_session TEXT NOT NULL,
  credential_fingerprint TEXT NOT NULL,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_web_sessions_account ON web_sessions(account_id);
CREATE INDEX IF NOT EXISTS idx_web_sessions_identity
  ON web_sessions(identity_kind, identity_id);
CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry ON web_sessions(expires_at);
```

Regras:

- O token opaco **nunca** é gravado; grave `sha256(token)` em `token_hash`.
- A senha/hash **nunca** é gravada; grave
  `sha256(credential)` em `credential_fingerprint`.
- Não grave nome, e-mail, CPF, descrição, documento ou PII na tabela.
- `csrf` e `telemetry_session` são aleatórios e privados; não aparecem em
  `repr`/logs.
- `client_org_ids` é JSON de lista de inteiros; valide ao ler.
- A tabela é opt-in atrás da flag; flag desligada ignora as linhas.

### 2.2 Interface pública

Trocar a implementação, mantendo o contrato conceitual e atualizando chamadas:

```python
def install(banco) -> None

def create(banco, account_id, identity_record, membership, principal,
           credential, source, ttl=SESSION_TTL) -> tuple[str, SessionData]

def resolve(banco, token: str | None) -> SessionData | None

def revoke(banco, token: str | None) -> None
def revoke_account(banco, account_id: int) -> None
def revoke_identity(banco, kind: str, identity_id: int) -> None
def prune(banco) -> None
def clear(banco) -> None   # somente testes
```

- `SessionData` mantém `identity`, `membership`, `principal`, `source`,
  `csrf`, `telemetry_session`, `created_at`, `expires_at` e
  `account_id`.
- `credential` deixa de carregar o hash; use
  `credential_fingerprint` (ou mantenha o nome `credential` documentado como
  fingerprint, mas nunca o hash).
- `create` valida tudo que a 5.2 valida: principal/identidade/vínculo,
  credencial atual, `account_id` inteiro, `source` coerente, TTL.
- `resolve`:
  - lê por `token_hash`, checa expiração;
  - recarrega identidade, membership e principal atuais;
  - compara `role`, `provider_org_id`, `provider_id`, `client_id`,
    `client_org_ids` e `credential_fingerprint`;
  - se algo mudou/sumiu, apaga a linha e devolve `None`;
  - devolve `SessionData` com os dados atuais, não com PII da linha.
- `revoke*`, `prune` e `clear` operam no banco, com transação.
- `create` pode chamar `prune` quando a tabela passar de 2000 linhas; não é
  obrigatório manter esse limite exato.
- `install` deve ser chamado no start do portal unificado e nos testes. Se a
  tabela não existir, `resolve` devolve `None`; não crie tabela silenciosamente
  dentro de `resolve`.
- Atualizar `login_web`, `portal_prestador` (5.5), `web_cookie` se necessário e
  todos os testes.

### 2.3 Concorrência e restart

- Cada operação abre sua conexão via `ext.db(banco)`; não use um dicionário
  global.
- Duas conexões/processos no mesmo arquivo devem enxergar a mesma sessão.
- Reiniciar o processo não pode apagar sessões válidas.
- Um `revoke` em uma conexão deve invalidar a sessão na outra.
- Use transações/`sqlite3` corretamente; não segure lock global durante I/O.
- Não ative WAL globalmente sem testar o impacto no banco atual; se usar,
  documente e teste.

## 3. Contexto compartilhado web/GTK

### 3.1 DTO

Adicionar em `officina/application/contracts.py` (ou módulo equivalente):

```python
@dataclass(frozen=True)
class SessionContext:
    account_id: int | None
    identity_kind: str          # "provider" | "client"
    identity_id: int
    display_name: str
    role: str
    provider_org_id: str | None
    provider_id: int | None
    client_id: int | None
    client_org_ids: frozenset[int]
    permissions: frozenset[str]
    context_label: str          # "Portal do prestador" | "Portal do cliente"
```

- `permissions` vem da política (`policy.allows`), não de `if admin` na UI.
- O DTO não contém hash, token, CSRF, cookie, `sqlite3.Row` ou HTML.
- Web e GTK usam o mesmo DTO; cada um renderiza nativamente.

### 3.2 API desktop

- Estender `GET /api/v1/desktop/me` para devolver o `SessionContext` (campos
  atuais + role/permissions/contexto), mantendo compatibilidade com o que o
  GTK já lê (`id`, `nome`, `email`, `admin`).
- O contexto do desktop continua usando o token `autosseg_desk_` existente;
  **não** migre a tabela `desktop_sessoes` nesta peça.
- Um employee não recebe permissões de admin; um cliente, se um dia usar esse
  endpoint, recebe o papel/escopo corretos.
- A API continua negando no serviço; `permissions` é só para a UI esconder
  ações.

### 3.3 GTK

- `Sessao`/`HttpService.me()` passam a carregar `role`, `context_label` e
  `permissions` (com defaults para sessões antigas).
- Usar o contexto em **uma** tela/ação real do GTK, preferencialmente a
  navegação lateral ou a lista de OS: item admin-only não aparece para
  employee.
- Não criar modo cliente no GTK.
- Não duplicar a matriz de permissões no GTK; se a tela precisar de regra que
  não existe no contrato, pare e documente.
- Testes de contrato devem rodar sem GTK/gi quando possível; se o ambiente não
  tiver `gi`, registrar o erro exato e não declarar o teste visual aprovado.

## 4. O que não fazer

- Não ligar `AUTOSEG_OBJECT_POLICY_ENFORCEMENT`; a 6.2 permanece atrás da flag
  desligada até a decisão sobre o TOCTOU.
- Não migrar `desktop_sessoes`, `api_tokens` ou `cliente_acessos` para a nova
  tabela nesta peça.
- Não criar modo cliente no GTK.
- Não implementar OS anônima, fingerprint ou captcha.
- Não alterar a matriz de papéis da 6.2 além do necessário para o contexto.
- Não colocar permissão só na UI; o serviço continua sendo a autoridade.
- Não guardar token/hash/senha/PII em claro na tabela ou em logs.
- Não usar Redis, dependência nova ou serviço externo.
- Não reescrever o portal do prestador; só atualizar as chamadas de sessão.
- Não “consertar” teste reduzindo cobertura; se a sessão durável não passar,
  registrar o erro exato.

## 5. Testes obrigatórios

Criar/expandir `tests/test_web_session_durable.py` (ou equivalente) e
`tests/test_session_context.py`. Cobrir, no mínimo:

1. create/resolve na mesma conexão;
2. create em uma conexão e resolve em outra conexão do mesmo arquivo;
3. resolve após fechar e reabrir o banco (restart);
4. token não aparece em claro na tabela; só o hash;
5. hash da senha não aparece na tabela; só o fingerprint;
6. expiração remove a sessão;
7. `revoke(token)` em uma conexão invalida na outra;
8. `revoke_account` invalida todas as sessões da conta;
9. `revoke_identity` invalida provider e client corretamente;
10. reset de senha/role change/desativação invalidam via resolve;
11. `prune` remove só expiradas;
12. `SessionData`/contexto não expõem token, CSRF, hash ou PII no `repr`;
13. flag desligada ignora cookie/sessão;
14. `GET /api/v1/desktop/me` devolve role/permissions/contexto para admin e
    employee;
15. employee não recebe permissão de admin;
16. GTK/contrato esconde a ação admin-only para employee;
17. chamada direta ao serviço continua negando mesmo se a UI for alterada;
18. suítes de 6.1/6.2 e do portal continuam passando.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_web_session_durable tests.test_session_context \
  tests.test_web_session tests.test_login_compat tests.test_login_web \
  tests.test_client_roles tests.test_object_permissions \
  tests.test_officina_web tests.test_auth tests.test_accounts -v
```

Regressão:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_rev12_correcoes tests.test_admin_parity tests.test_portal_v4 -v
```

Se não houver `.venv`, registrar o erro exato; não declarar aprovação.

## 6. ZIP

```text
officina-durable-session/
├── changed-files/
│   ├── flavors/autoseg/modules/web_session.py
│   ├── flavors/autoseg/modules/login_web.py
│   ├── flavors/autoseg/modules/portal_prestador.py
│   ├── flavors/autoseg/modules/api_desktop.py
│   ├── officina/application/contracts.py
│   ├── officina/application/http_service.py
│   ├── officina/application/session.py
│   ├── flavors/autoseg/modules/gtk_app.py
│   ├── flavors/autoseg/modules/gtk_login.py
│   └── tests/...
├── officina-durable-session.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, PDFs, logs, tokens ou PII.

## 7. Critérios de aceite

- Sessão web em SQLite, sem token/hash de senha em claro, com TTL e revogação.
- Duas conexões/processos enxergam a mesma sessão; restart preserva; revoke
  propaga.
- `SessionContext` único para web/GTK, com role/permissions/contexto.
- GTK usa o contrato em pelo menos uma tela/ação, sem duplicar permissão.
- Nenhuma mudança de cliente GTK, OS anônima ou financeiro.
- Testes negativos provam que a UI não é a autoridade.
- Se o GTK não fechar sem duplicação, o bloqueio está documentado e a peça
  **não** foi declarada concluída.
- Diff limitado aos arquivos permitidos.
