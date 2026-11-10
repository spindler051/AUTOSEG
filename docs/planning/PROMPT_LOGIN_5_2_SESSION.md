# Peça 5.2 — núcleo da sessão única

**Uso:** colar no ChatGPT. Trabalha sobre uma cópia do repositório, **não faz
commit**, devolve ZIP.

**Base:** `205bd64` + interface da peça 5.1 (`login_flags.py`).
**Dependências:** peça 5.1 (flag) e peças 2/3/4 (`identity`, `accounts`,
`auth`) já integradas.
**Entrega:** ZIP com arquivos completos + patch + testes + notas.

## 1. Missão

Criar o núcleo da sessão única: em memória, TTL de 8 h, CSRF, revalidação de
credencial e revogação por conta/identidade. **Sem cookie, sem rota, sem UI.**

## 2. Arquivos permitidos

Criar:

- `flavors/autoseg/modules/web_session.py`
- `tests/test_web_session.py`

Nenhum outro arquivo.

## 3. Interfaces

```python
COOKIE_NAME = "autosseg_unified"
SESSION_TTL = 28800

@dataclass(frozen=True)
class SessionData:
    account_id: int | None
    identity: Identity
    membership: Membership
    principal: Principal
    credential: str = field(repr=False)
    source: str                  # "account" | "legacy"
    csrf: str
    telemetry_session: str
    created_at: float
    expires_at: float

def create(banco, account_id, identity, membership, principal,
           credential, source, ttl=SESSION_TTL) -> tuple[str, SessionData]
def resolve(banco, token: str | None) -> SessionData | None
def revoke(token: str | None) -> None
def revoke_account(account_id: int) -> None
def revoke_identity(kind: str, identity_id: int) -> None
def current_credential(banco, source: str, account_id: int | None,
                       identity: Identity) -> str | None
def prune() -> None
def clear() -> None
```

Regras:

- `create` gera token `secrets.token_urlsafe(36)`, CSRF
  `secrets.token_urlsafe(32)` e `telemetry_session` aleatório; guarda a sessão
  em memória por token; devolve `(token, SessionData)`.
- `resolve`:
  - token inexistente/expirado → remove e retorna `None`;
  - recalcula `current_credential`; se mudou ou sumiu → revoga e retorna
    `None`;
  - identidade/conta inativa → revoga e retorna `None`;
  - não reconstruir papel automaticamente; mudança de papel deve chamar
    `revoke_account`/`revoke_identity`.
- `current_credential`:
  - `source="account"`: `accounts.load_account(account_id).password_hash`;
  - `source="legacy"`: hash em `prestadores`/`v9_usuarios` conforme
    `identity.kind`;
  - ausência/erro → `None`.
- `revoke_identity` remove todas as sessões daquela identidade (provider/client).
- `prune` remove expiradas; chamar em `create` quando o mapa passar de 2000.
- `clear` só para testes.
- Mapa global protegido por `threading.Lock`; sem SQLite, sem disco.
- Não logar token, CSRF, credencial ou PII.

## 4. Restrições

- Sem cookie, rota, UI, portal, GTK ou schema.
- Não alterar `auth.py`, `accounts.py`, `identity.py`, `login_flags.py`.
- Não adicionar dependências.
- Não usar `float` para dinheiro (não há dinheiro).
- Diff limitado aos dois arquivos.

## 5. Testes

`tests/test_web_session.py`, banco temporário com `criar_banco` +
`ext.instalar` + `cad.instalar` + `accounts.install`:

1. `create`/`resolve` devolve a mesma identidade/principal.
2. token inválido/`None` → `None`.
3. TTL expirado → `None` e sessão removida.
4. mudança de hash (senha) → `resolve` None e sessão revogada.
5. conta/identidade inativa → `None`.
6. `revoke(token)` invalida só aquela sessão.
7. `revoke_account` invalida todas as sessões da conta.
8. `revoke_identity("provider", id)` invalida todas do provider.
9. `prune` remove expiradas e mantém válidas.
10. `SessionData` não expõe token nem credencial no `repr`.
11. `source="legacy"` revalida o hash legado.
12. nenhuma PII em `repr`/logs (o teste pode inspecionar `repr`).

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_web_session tests.test_auth tests.test_accounts -v
```

Se não houver `.venv`, registrar o erro exato; não declarar aprovação.

## 6. ZIP

```text
session-core/
├── changed-files/
│   ├── flavors/autoseg/modules/web_session.py
│   └── tests/test_web_session.py
├── session-core.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, logs ou segredos.

## 7. Critérios de aceite

- Núcleo sem cookie/rota/UI.
- Credencial revalidada em `resolve`.
- Revogação por token/conta/identidade.
- TTL e poda funcionando.
- Nenhum token/credencial em `repr`/logs.
- Diff limitado aos dois arquivos.
