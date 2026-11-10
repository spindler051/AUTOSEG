# Prompt — peça 2: contrato de identidade read-only (AUTOSEG)

**Uso:** colar este arquivo no ChatGPT. Ele trabalha sobre uma cópia do
repositório, **não faz commit**, e devolve um ZIP com os arquivos alterados.

**Repositório:** `spindler051/AUTOSEG`
**Base obrigatória:** commit `c8899c9` (peça 1 já integrada).
**Branch sugerida na cópia:** `feat/identity-contract` (não precisa existir no
GitHub; é só organização local).
**Entrega:** ZIP com os arquivos completos + patch + resultados de teste +
notas. **Não fazer `git commit`, `git push` ou abrir PR.**

---

## 1. Missão

Criar a primeira camada de identidade unificada em modo **read-only**:

- resolve um login por e-mail ou CPF para uma ou mais identidades;
- carrega uma identidade por tipo/id;
- lista os vínculos (memberships) dessa identidade;
- converte a identidade em `Principal` para a política por objeto.

Nesta peça **não existe** tabela `accounts`, não muda login, não muda sessão,
não muda UI, não cria tenant, não migra dados e não bloqueia nada.

O objetivo é ter um contrato único para que a peça 3 (`accounts/account_links`)
e a peça 4 (login único) não dupliquem a leitura de `prestadores` e
`v9_usuarios`.

## 2. Leia antes de codar

1. `AGENTS.md` — change gates e regras duras.
2. `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` §2, §3 e §4.
3. `officina/application/object_policy.py` (`Principal`)
4. `flavors/autoseg/modules/policy_shadow.py`
5. `officina/core/prestadores_ext.py` (tabela `prestadores`, `autenticar`)
6. `officina/core/cadastros_v9.py` (`v9_usuarios`, `v9_admin_prestadores`)
7. `tests/test_object_policy.py`, `tests/test_policy_shadow.py`

## 3. Restrições

- **Não criar tabela, coluna, migração ou `provider_org_id`.**
- **Não alterar login, sessão, cookies, portais ou GTK.**
- **Não verificar senha** nesta peça. Isto é resolução de identidade, não
  autenticação.
- **Não criar UI.**
- **Não adicionar dependências.**
- **Não logar PII.**
- **Não alterar `AGENTS.md`.**
- **Não modificar** `portal_prestador.py`, `portal_cliente_v94.py`,
  `servidor_web.py`, `api_desktop.py`.
- Manter o diff pequeno. Se precisar de schema ou decisão de produto, parar e
  registrar em `NOTES.md`; não inventar.

## 4. Arquivos permitidos

Criar:

- `flavors/autoseg/modules/identity.py`
- `tests/test_identity.py`

Modificar somente:

- `flavors/autoseg/modules/policy_shadow.py` — apenas para delegar
  `principal_provider` e `principal_client` ao novo `identity.py`, mantendo as
  assinaturas e o comportamento.
- `tests/test_policy_shadow.py` — somente se precisar ajustar um teste de
  integração; não enfraquecer os testes existentes.

Qualquer outro arquivo é proibido nesta peça.

## 5. Interfaces exatas

### 5.1 `identity.py`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Identity:
    kind: str                  # "provider" | "client"
    id: int                    # prestadores.id or v9_usuarios.id
    display_name: str
    email: str = ""
    cpf: str = ""              # digits only
    active: bool = True
    provider_id: int | None = None
    client_id: int | None = None


@dataclass(frozen=True)
class Membership:
    identity_kind: str
    identity_id: int
    role: str                  # "admin" | "employee" | "customer"
    provider_org_id: str | None = None
    provider_id: int | None = None
    client_id: int | None = None
    active: bool = True


def resolve_identifier(banco, identifier: str) -> tuple[Identity, ...]:
    """Return every identity matching an e-mail or CPF/document.

    E-mail is matched case-insensitively for providers and clients.
    CPF is normalized to digits and matched for clients; provider documents
    are also considered. Return an empty tuple when nothing matches. Never
    raise for a malformed identifier.
    """


def load_identity(banco, kind: str, identity_id: int) -> Identity | None:
    """Load one provider or client identity by its legacy id."""


def memberships(banco, identity: Identity) -> tuple[Membership, ...]:
    """Return the current legacy memberships for one identity.

    Provider: one membership with role admin/employee and provider_id.
    Client: one membership with role customer and client_id.
    provider_org_id stays None until the tenant/account schema exists.
    """


def to_principal(identity: Identity) -> Principal:
    """Map an Identity to the existing ObjectPolicy Principal.

    provider -> account_id=id, provider_id=id, role admin/employee
    client   -> account_id=id, client_id=client_id, role customer
    organization_id stays None (tenant_unknown will be flagged by the policy).
    """
```

### 5.2 Regras de resolução

- `identifier` vazio ou inválido → `()`, sem exceção.
- Se contém `@`: buscar `prestadores.email` e `v9_usuarios.email`,
  case-insensitive; ignorar registros `excluido=1`/`ativo=0`? **Incluir** os
  inativos na resolução, com `active=False`, para o login poder negar com
  mensagem correta.
- Se é só dígitos: normalizar para dígitos; buscar `v9_usuarios.cpf` e
  `prestadores.documento` (quando o documento, sem máscara, for igual).
- Retornar **todas** as correspondências, em ordem determinística:
  providers primeiro, depois clients; por id.
- Nunca usar `LIKE` com entrada do usuário; use igualdade parametrizada.
- Não retornar senha/hash em `Identity`.

### 5.3 `policy_shadow.py`

Substituir o corpo de:

```python
def principal_provider(banco, provider_id): ...
def principal_client(banco, user_id): ...
```

por delegação:

```python
def principal_provider(banco, provider_id):
    ident = identity.load_identity(banco, "provider", provider_id)
    return identity.to_principal(ident) if ident else Principal(...)

def principal_client(banco, user_id):
    ident = identity.load_identity(banco, "client", user_id)
    return identity.to_principal(ident) if ident else Principal(...)
```

Manter exatamente o comportamento atual para id inexistente/inativo:
`Principal(..., active=False)`. Não alterar `resource_work_item`, `evaluate`
ou a instrumentação.

## 6. Testes

Criar `tests/test_identity.py` com banco temporário e dados fictícios:

1. provider admin: `resolve_identifier` por e-mail, `load_identity`,
   `memberships` role `admin`, `to_principal` com `provider_id`.
2. provider comum: role `employee`.
3. client: `resolve_identifier` por CPF e e-mail, `memberships` role
   `customer`, `to_principal` com `client_id`.
4. inativo: aparece com `active=False`.
5. e-mail case-insensitive e com espaços.
6. CPF com máscara normaliza para dígitos.
7. identificador inexistente retorna `()`.
8. mesmo e-mail em provider e client retorna as duas identidades.
9. `provider_org_id is None` em todas as memberships.
10. nenhum campo de senha/hash em `Identity`.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_identity tests.test_policy_shadow tests.test_object_policy -v
```

Se o ambiente não tiver dependências, registrar o erro exato em
`TEST_RESULTS.txt`; não afirmar que passou.

## 7. Formato do ZIP de entrega

Não incluir o repositório inteiro, `.git`, banco, anexos, PDFs, logs ou
segredos. Estrutura:

```text
identity-contract/
├── changed-files/
│   ├── flavors/autoseg/modules/identity.py
│   ├── flavors/autoseg/modules/policy_shadow.py
│   ├── tests/test_identity.py
│   └── tests/test_policy_shadow.py          (somente se alterado)
├── identity-contract.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

- `changed-files/` contém os arquivos completos, no mesmo caminho relativo do
  repositório.
- `identity-contract.patch` é o `git diff` da cópia local (pode ser gerado com
  `git diff --no-index` se os arquivos não estiverem commitados).
- `CHANGED_FILES.txt` lista os caminhos alterados.
- `TEST_RESULTS.txt` contém comandos e saída, ou o erro de ambiente.
- `NOTES.md` registra decisões, limitações e o que ficou para a peça 3.

## 8. Critérios de aceite

- `identity.py` não importa portal, GTK, UI ou `policy_shadow`.
- `policy_shadow` continua passando nos testes existentes.
- Nenhum schema, login, sessão, rota ou UI alterada.
- Nenhuma senha/hash em `Identity`.
- Nenhuma PII em log.
- Resolução determinística e parametrizada.
- Diff limitado aos arquivos permitidos.
- Se algo exigir decisão de produto, parar e anotar; não inventar.

## 9. O que o revisor vai checar

1. O ZIP contém apenas os arquivos permitidos?
2. `resolve_identifier` retorna todas as correspondências, sem `LIKE` inseguro?
3. `Identity` não carrega senha/hash?
4. `policy_shadow` mantém o comportamento e os testes?
5. Inativo aparece com `active=False`?
6. `provider_org_id` ficou `None`?
7. O diff não tocou portal/login/schema?
8. Os testes foram realmente executados?
