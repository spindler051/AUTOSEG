# Prompt — peça 3: accounts/account_links + migração legada

**Uso:** colar no ChatGPT. Ele trabalha sobre uma cópia do repositório, **não
faz commit**, e devolve um ZIP com os arquivos alterados.

**Repositório:** `spindler051/AUTOSEG`
**Base:** `e983ae1` (peça 2 de identidade já integrada).
**Entrega:** ZIP com arquivos completos + patch + resultados + notas.
**Não fazer** `git commit`, `git push` ou PR.

---

## 1. Missão

Criar o schema de contas unificadas e a migração read-only dos cadastros
legados, **sem mudar login, sessão, UI ou portais**.

Decisões de produto já tomadas:

- **Uma conta = um papel nesta fase.** Conta de prestador e conta de cliente
  são separadas; não existe seletor “entrar como cliente/prestador”.
- O login será configurável por **e-mail, CPF, telefone ou nametag**. “Somente
  senha” não é um identificador válido e não entra no schema.
- O **tenant** é a empresa dona dos dados. Nesta fase existe um único tenant:
  `provider_org_id='autoseg'`. `provider_id` é a pessoa/prestador, não a empresa.
- Senhas legadas são migradas como hash; nenhuma senha em texto.
- O login antigo continua funcionando até a peça 4/5 ligar o novo login.

## 2. Leia antes

1. `AGENTS.md`
2. `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` §3 e §6
3. `docs/planning/PROMPT_IDENTITY_CONTRACT.md`
4. `flavors/autoseg/modules/identity.py`
5. `officina/core/prestadores_ext.py`
6. `officina/core/cadastros_v9.py`
7. `tests/test_identity.py`, `tests/test_policy_shadow.py`

## 3. Restrições

- Não alterar login, sessão, cookies, rotas, portais, GTK ou templates.
- Não criar UI de cadastro/permissões.
- Não alterar `identity.py` nesta peça.
- Não apagar as tabelas legadas.
- Não migrar dados reais; testes só com dados fictícios.
- Não usar `float`/`REAL` para dinheiro (não há dinheiro nesta peça).
- Não logar PII, senha ou hash.
- Não adicionar dependências.
- Não alterar `AGENTS.md`.

## 4. Arquivos permitidos

Criar:

- `flavors/autoseg/modules/accounts.py`
- `tests/test_accounts.py`

Opcional (somente se necessário para documentar o schema):

- `docs/planning/ACCOUNTS_MODEL.md`

Qualquer outro arquivo é proibido.

## 5. Schema

`accounts.install(banco)` deve criar de forma idempotente:

```sql
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  display_name TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  password_changed_at TEXT
);

CREATE TABLE IF NOT EXISTS account_identifiers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK(type IN ('email','cpf','phone','nametag')),
  value TEXT NOT NULL,
  normalized TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  is_primary INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE(type, normalized)
);
CREATE INDEX IF NOT EXISTS idx_account_identifiers_account
  ON account_identifiers(account_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_account_identifiers_primary
  ON account_identifiers(account_id) WHERE is_primary=1;

CREATE TABLE IF NOT EXISTS account_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL UNIQUE REFERENCES accounts(id) ON DELETE CASCADE,
  provider_org_id TEXT NOT NULL DEFAULT 'autoseg',
  link_type TEXT NOT NULL CHECK(link_type IN ('provider','client')),
  role TEXT NOT NULL CHECK(role IN ('admin','employee','customer')),
  provider_id INTEGER,
  client_user_id INTEGER,
  client_id INTEGER,
  legacy_provider_id INTEGER UNIQUE,
  legacy_client_user_id INTEGER UNIQUE,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  CHECK (
    (link_type='provider' AND role IN ('admin','employee')
     AND provider_id IS NOT NULL AND client_user_id IS NULL AND client_id IS NULL)
    OR
    (link_type='client' AND role='customer'
     AND provider_id IS NULL AND client_user_id IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS login_policy (
  id INTEGER PRIMARY KEY CHECK(id=1),
  allowed_identifier_types TEXT NOT NULL,
  password_min_length INTEGER NOT NULL DEFAULT 12,
  require_letter_number INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT NOT NULL
);
```

Notas:

- `account_links.account_id UNIQUE` implementa “uma conta = um papel” nesta
  fase. Não criar múltiplos vínculos por conta.
- `client_user_id` é `v9_usuarios.id`; `client_id` é `clientes.id`
  (`cliente_pf_id`), podendo ser `NULL`.
- `provider_id` é `prestadores.id`.
- `provider_org_id='autoseg'` é o tenant único desta fase.
- `allowed_identifier_types` é JSON, por exemplo `["email","cpf"]`.
  “password” nunca é um tipo válido.
- Default da política: `["email","cpf"]`, `password_min_length=12`,
  `require_letter_number=1`.

## 6. Interfaces

```python
IDENTIFIER_TYPES = ("email", "cpf", "phone", "nametag")

@dataclass(frozen=True)
class Account:
    id: int
    display_name: str
    password_hash: str
    active: bool
    created_at: str
    updated_at: str
    password_changed_at: str | None = None

@dataclass(frozen=True)
class AccountIdentifier:
    id: int
    account_id: int
    type: str
    value: str
    normalized: str
    verified: bool
    is_primary: bool

@dataclass(frozen=True)
class AccountLink:
    id: int
    account_id: int
    provider_org_id: str
    link_type: str
    role: str
    provider_id: int | None
    client_user_id: int | None
    client_id: int | None
    legacy_provider_id: int | None
    legacy_client_user_id: int | None
    active: bool

@dataclass(frozen=True)
class LoginPolicy:
    allowed_identifier_types: tuple[str, ...]
    password_min_length: int
    require_letter_number: bool

@dataclass(frozen=True)
class MigrationReport:
    dry_run: bool
    providers: int
    clients: int
    accounts_created: int
    accounts_updated: int
    identifiers_created: int
    identifiers_skipped: int
    conflicts: tuple[dict, ...]

def install(banco) -> None
def normalize_identifier(kind: str, value: str) -> str
def login_policy(banco) -> LoginPolicy
def save_login_policy(banco, allowed_identifier_types, password_min_length=12,
                      require_letter_number=True) -> LoginPolicy
def migrate_legacy(banco, dry_run: bool = True) -> MigrationReport
def load_account(banco, account_id: int) -> Account | None
def find_account_by_identifier(banco, kind: str, value: str) -> Account | None
def identifiers(banco, account_id: int) -> tuple[AccountIdentifier, ...]
def account_link(banco, account_id: int) -> AccountLink | None
def identity_for_account(banco, account_id: int) -> Identity | None
def membership_for_account(banco, account_id: int) -> Membership | None
```

`identity_for_account`/`membership_for_account` devem usar
`identity.py` e o vínculo legado (`provider_id` ou `client_user_id`) para
devolver `Identity`/`Membership` compatíveis com `identity.to_principal`.
Não duplicar a lógica de `identity.py`.

## 7. Normalização

- `email`: `strip().casefold()`.
- `cpf`: somente dígitos; exigir 11 dígitos.
- `phone`: somente dígitos; aceitar 10–13 dígitos; não inventar `+55`.
- `nametag`: `strip().casefold()`, 3–30 caracteres, `[a-z0-9._-]`.
- valor inválido → `ValueError` em `normalize_identifier`; a migração registra
  conflito e segue.

## 8. Migração

`migrate_legacy(banco, dry_run=True)`:

- chama `install` de forma idempotente;
- lê `prestadores` e `v9_usuarios` (incluindo inativos; `excluido=1` do
  prestador vira `active=0`);
- para cada provider:
  - cria/atualiza `accounts` com `display_name`, `senha_hash`, `active`;
  - cria `account_links` provider, `legacy_provider_id`, `provider_id`,
    `provider_org_id='autoseg'`, `role=admin` se `v9_admin_prestadores`, senão
    `employee`;
  - identificadores: e-mail é primário; CPF/documento de 11 dígitos e telefone
    entram como secundários **se não conflitarem**; nametag não é inventado;
- para cada client:
  - cria/atualiza `accounts` com `display_name`, `senha_hash`, `ativo`;
  - cria `account_links` client, `legacy_client_user_id`, `client_user_id`,
    `client_id=cliente_pf_id`, `provider_org_id='autoseg'`,
    `role='customer'`;
  - identificadores: CPF é primário; e-mail e telefone entram como secundários
    **se não conflitarem**; nametag não é inventado;
- conflito de identificador (`UNIQUE(type, normalized)`): manter o primeiro
  (provider e-mail e client CPF são prioritários), pular o secundário e
  registrar no relatório **sem o valor**, apenas tipo + ids legados;
- idempotência: rerun atualiza a conta pelo `legacy_*_id`, não duplica; se a
  senha legada mudou, atualiza o hash; não cria link duplicado;
- `dry_run=True` não escreve nada e retorna o relatório;
- `dry_run=False` usa uma transação; falha em uma linha não pode deixar meio
  schema/meia migração.

## 9. Testes

Criar `tests/test_accounts.py` com banco temporário e dados fictícios:

1. `install` é idempotente.
2. migração dry-run não escreve.
3. provider admin vira conta + link admin.
4. provider comum vira employee.
5. client vira customer, com `client_user_id` e `client_id`.
6. inativo/excluído vira `active=0`.
7. senha hash é copiada; plaintext não aparece.
8. e-mail conflitante entre provider e client: provider mantém o identificador,
   client mantém o perfil e o conflito é reportado.
9. CPF conflitante: client mantém, provider usa e-mail; conflito reportado.
10. rerun é idempotente e atualiza hash/ativo.
11. `find_account_by_identifier` normaliza email/CPF/phone/nametag.
12. `account_links.account_id` rejeita segundo vínculo.
13. `login_policy` default e `save_login_policy` rejeitam “password”.
14. `identity_for_account`/`membership_for_account` devolvem dados compatíveis
    com `identity.to_principal`.
15. nenhuma PII em `MigrationReport.conflicts`.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_accounts tests.test_identity tests.test_policy_shadow -v
```

Se o ambiente não tiver o repositório/dependências, registrar o erro exato em
`TEST_RESULTS.txt`; não declarar aprovação.

## 10. ZIP

```text
accounts-schema/
├── changed-files/
│   ├── flavors/autoseg/modules/accounts.py
│   ├── tests/test_accounts.py
│   └── docs/planning/ACCOUNTS_MODEL.md   (opcional)
├── accounts-schema.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, PDFs, logs ou segredos.

## 11. Critérios de aceite

- Schema idempotente; uma conta = um vínculo.
- Nenhum login/sessão/UI/portal alterado.
- Hashes copiados; nenhum plaintext.
- Migração idempotente e dry-run sem escrita.
- Conflitos reportados sem PII.
- `provider_org_id='autoseg'`; `provider_id` é a pessoa, não o tenant.
- `allowed_identifier_types` nunca inclui “password”.
- Testes oficiais executados ou erro de ambiente registrado.
- Diff limitado aos arquivos permitidos.

## 12. O revisor vai checar

1. O ZIP contém apenas os arquivos permitidos?
2. O schema força uma conta = um vínculo?
3. A migração é idempotente e dry-run não escreve?
4. Conflitos não vazam PII?
5. Hashes não viram plaintext?
6. `identity_for_account` reutiliza `identity.py`?
7. `login_policy` rejeita “password”?
8. Nenhum portal/login/UI foi tocado?
