# Prompt — peça 4: serviço de login unificado (sem rotas/cookies)

**Uso:** colar no ChatGPT. Ele trabalha sobre uma cópia do repositório, **não
faz commit**, e devolve um ZIP com os arquivos alterados.

**Repositório:** `spindler051/AUTOSEG`
**Base:** `e983ae1` + interfaces da peça 3 (accounts/account_links).
**Entrega:** ZIP com arquivos completos + patch + resultados + notas.
**Não fazer** `git commit`, `git push` ou PR.

---

## 1. Missão

Implementar o **serviço de autenticação unificado** em nível de biblioteca:

- recebe identificador + senha;
- respeita a política configurável de identificadores;
- tenta a conta nova (`accounts`) e, se ela ainda não existir, o legado
  (`prestadores`/`v9_usuarios`);
- devolve `LoginResult` com identidade, vínculo e `Principal`;
- não altera rotas, cookies, sessões, portais, GTK ou templates.

A peça 5 vai ligar esse serviço ao site único. Esta peça é só o cérebro do
login, testável isoladamente.

## 2. Decisões de produto

- Identificadores configuráveis: **email, cpf, phone, nametag**.
- **“Somente senha” não é um identificador válido.** Não implementar login sem
  identificador. Passwordless/passkeys são uma feature separada.
- **Uma conta = um papel nesta fase.** Prestador e cliente são contas
  separadas; não há seletor “entrar como cliente/prestador”.
- Se o identificador casar com mais de uma conta/identidade, o login é
  **ambíguo** e deve falhar com mensagem genérica, sem revelar quais contas
  existem.
- O tenant é a empresa (`provider_org_id='autoseg'`); `provider_id` é a pessoa.
- Senha forte: mínimo configurável, com letra e número por padrão.
- O login antigo continua como fallback até a migração/cutover.

## 3. Leia antes

1. `AGENTS.md`
2. `docs/planning/PROMPT_ACCOUNTS_SCHEMA.md`
3. `docs/planning/PROMPT_IDENTITY_CONTRACT.md`
4. `flavors/autoseg/modules/identity.py`
5. `flavors/autoseg/modules/accounts.py` (interface da peça 3)
6. `flavors/autoseg/modules/policy_shadow.py`
7. `officina/core/prestadores_ext.py` (`autenticar`, `verificar_senha`)
8. `officina/core/cadastros_v9.py` (`autenticar`)
9. `tests/test_identity.py`, `tests/test_accounts.py`

## 4. Restrições

- Não alterar `portal_prestador.py`, `portal_cliente_v94.py`,
  `servidor_web.py`, `api_desktop.py`, `prestador_auth.py`.
- Não criar cookie, sessão, CSRF, rota ou template.
- Não criar tabela nem migração; isso é peça 3.
- Não alterar `identity.py` nem `accounts.py` (apenas consumir as interfaces).
- Não logar senha, hash, identificador completo ou PII.
- Não adicionar dependências.
- Não alterar `AGENTS.md`.

## 5. Arquivos permitidos

Criar:

- `flavors/autoseg/modules/auth.py`
- `tests/test_auth.py`

Opcional:

- `docs/planning/LOGIN_SERVICE.md` (contrato curto)

Qualquer outro arquivo é proibido.

## 6. Interface com a peça 3

Assumir que `accounts.py` expõe:

```python
IDENTIFIER_TYPES = ("email", "cpf", "phone", "nametag")

@dataclass(frozen=True)
class Account: ...
@dataclass(frozen=True)
class AccountIdentifier: ...
@dataclass(frozen=True)
class AccountLink: ...
@dataclass(frozen=True)
class LoginPolicy: ...

def normalize_identifier(kind, value) -> str
def login_policy(banco) -> LoginPolicy
def save_login_policy(banco, allowed_identifier_types, password_min_length=12,
                      require_letter_number=True) -> LoginPolicy
def find_account_by_identifier(banco, kind, value) -> Account | None
def identifiers(banco, account_id) -> tuple[AccountIdentifier, ...]
def account_link(banco, account_id) -> AccountLink | None
def identity_for_account(banco, account_id) -> Identity | None
def membership_for_account(banco, account_id) -> Membership | None
```

Se `accounts.py` ainda não estiver presente no checkout, o código de produção
deve detectar a ausência e usar apenas o fallback legado. **Não criar
`accounts.py` nesta peça.** Testes que dependem do schema novo podem usar um
stub local em `tests/test_auth.py` ou `skipUnless`; registrar isso em
`NOTES.md`.

## 7. Interfaces de `auth.py`

```python
@dataclass(frozen=True)
class LoginResult:
    account_id: int | None
    identity: Identity
    membership: Membership
    principal: Principal
    source: str          # "account" | "legacy"

class LoginError(Exception):
    code: str            # "invalid" | "ambiguous" | "inactive" | "unsupported"
    # mensagem pública genérica; nunca incluir senha/hash/PII

def normalize_identifier(kind: str, value: str) -> str
def allowed_identifier_types(banco) -> tuple[str, ...]
def validate_password_strength(password: str,
                               policy: LoginPolicy | None = None) -> tuple[bool, str]
def authenticate(banco, identifier: str, password: str) -> LoginResult
```

### 7.1 `authenticate`

1. Validar `identifier` e `password` não vazios.
2. Ler a política (`accounts.login_policy` se existir; senão default
   `("email","cpf")`, `password_min_length=12`, `require_letter_number=True`).
3. Detectar os tipos candidatos entre os permitidos:
   - contém `@` → `email`;
   - somente dígitos 11 → `cpf` e/ou `phone` (tentar ambos, se permitidos);
   - 10–13 dígitos → `phone`;
   - padrão de nametag `[a-z0-9._-]{3,30}` → `nametag`.
4. Se `accounts` existir:
   - buscar contas por cada tipo candidato permitido;
   - se mais de uma conta distinta corresponder → `LoginError("ambiguous")`;
   - se uma conta: verificar `password_hash`; se inválida → `LoginError("invalid")`;
   - se inativa → `LoginError("inactive")`;
   - montar `Identity`/`Membership` via `identity_for_account`/
     `membership_for_account`, e `Principal` via
     `identity.to_principal(identity, membership)`;
   - `source="account"`.
5. Fallback legado (quando não há conta ou `accounts` não existe):
   - `email`: `ext.autenticar(banco, email, password)` (provider);
   - `cpf`: `cad9.autenticar(banco, cpf, password)` (client);
   - `phone`/`nametag`: não existem no legado; `LoginError("unsupported")`;
   - se provider e client casarem com o mesmo identificador → `ambiguous`;
   - montar `Identity`/`Membership` via `identity.py` e `Principal` via
     `identity.to_principal`;
   - `source="legacy"`.
6. Nunca diferenciar “usuário não existe” de “senha errada” na mensagem
   pública; ambos são `invalid`.
7. Não criar sessão, cookie ou CSRF. Devolver `LoginResult`.

### 7.2 `validate_password_strength`

- mínimo `policy.password_min_length` (default 12);
- se `require_letter_number`: pelo menos uma letra e um dígito;
- rejeitar senha igual ao identificador ou ao display name? O caller pode
  passar; nesta peça, comparar apenas se receber `identifier` opcional.
- retornar `(True, "")` ou `(False, "mensagem pública curta")`.
- não logar a senha.

### 7.3 Política configurável

- `allowed_identifier_types` vem de `accounts.login_policy` quando existir;
- fallback `("email","cpf")`;
- “password” nunca é aceito;
- não permitir lista vazia; se a política estiver inválida, usar o fallback e
  registrar em `NOTES.md`.

## 8. Testes

Criar `tests/test_auth.py` com banco temporário e dados fictícios:

1. provider legado entra por e-mail e devolve `source="legacy"`.
2. client legado entra por CPF e devolve `source="legacy"`.
3. senha errada → `LoginError("invalid")`, sem revelar existência.
4. inativo → `LoginError("inactive")`.
5. mesmo e-mail em provider e client → `LoginError("ambiguous")`.
6. política default permite email/CPF; telefone/nametag → `unsupported` sem
   accounts.
7. `save_login_policy` com `["email"]` faz CPF cair em `unsupported` (ou
   `invalid`, documentar a escolha; preferir `unsupported`).
8. senha curta/sem número → `validate_password_strength` falha.
9. senha forte → passa.
10. conta nova via stub de `accounts` → `source="account"` e `Principal`
    correto.
11. identificador de conta ambíguo → `ambiguous`.
12. nenhuma senha/hash/PII em mensagens de erro ou logs.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_auth tests.test_identity tests.test_accounts -v
```

Se `accounts.py` ainda não existir, rodar apenas os testes que não dependem
dele e registrar em `NOTES.md`/`TEST_RESULTS.txt`; não declarar aprovação da
suíte completa.

## 9. ZIP

```text
unified-login/
├── changed-files/
│   ├── flavors/autoseg/modules/auth.py
│   ├── tests/test_auth.py
│   └── docs/planning/LOGIN_SERVICE.md   (opcional)
├── unified-login.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, PDFs, logs ou segredos.

## 10. Critérios de aceite

- Nenhuma rota/cookie/sessão/UI alterada.
- `authenticate` não vaza se a conta existe.
- Identificadores configuráveis; “password” rejeitado.
- Uma conta = um papel; ambiguidade falha.
- Fallback legado funciona sem `accounts.py`.
- `source` distingue `account`/`legacy`.
- `Principal` vem de `identity.to_principal`.
- Senha forte validada.
- Nenhuma PII/senha/hash em erro/log.
- Diff limitado aos arquivos permitidos.

## 11. O revisor vai checar

1. O ZIP contém apenas os arquivos permitidos?
2. `authenticate` usa a política configurável?
3. “Password only” foi rejeitado?
4. Ambiguidade falha sem enumerar contas?
5. Fallback legado funciona?
6. `LoginResult` carrega `Identity`, `Membership` e `Principal` corretos?
7. Nenhuma sessão/cookie/rota foi criada?
8. Senha/hash/PII ficaram fora de erros e logs?
