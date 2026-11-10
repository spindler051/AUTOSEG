# Peça 5.4 — rota `/entrar` e adaptador de sessão do prestador

**Uso:** colar no ChatGPT. Trabalha sobre uma cópia do repositório, **não faz
commit**, devolve ZIP.

**Base:** `205bd64` + peças 5.1 (`login_flags`), 5.2 (`web_session`) e 5.3
(`web_cookie`).
**Dependências:** auth/accounts/identity já integrados.
**Entrega:** ZIP com arquivos completos + patch + testes + notas.

## 1. Missão

Adicionar a rota pública `/entrar` no portal do prestador, usando
`auth.authenticate`, a sessão única e o cookie/CSRF novos. Nesta fase **só
provider entra**; cliente continua no portal antigo. A flag decide se `/entrar`
existe; desligada, redireciona para `/login`.

## 2. Arquivos permitidos

Criar:

- `flavors/autoseg/modules/login_web.py`
- `tests/test_login_web.py`

Modificar **minimamente**:

- `flavors/autoseg/modules/portal_prestador.py` — imports, dispatch de
  `/entrar` em `do_GET`/`do_POST`, e o topo de `sessao()`.

Nenhum outro arquivo.

## 3. Interface de `login_web.py`

```python
def render_login(handler, error: str = '', identifier: str = '') -> str
def authenticate_and_create(banco, identifier: str, password: str) -> tuple[str, SessionData]
def provider_session(handler, banco) -> dict | None
```

### `render_login`

- monta HTML com `handler.pagina('Entrar', corpo, None)`;
- formulário `POST /entrar` com:
  - `identificador` (texto, autocomplete username);
  - `senha` (password, autocomplete current-password);
  - botão “Entrar”;
- mostra `error` genérico e preserva `identifier`;
- link discreto “Usar login antigo” para `/login`;
- não inclui token CSRF de sessão (pré-auth); a proteção é a mesma do login
  atual: `origem_permitida` + `SameSite=Strict`. Documente isso em `NOTES.md`.

### `authenticate_and_create`

1. chama `auth.authenticate(banco, identifier, password)`;
2. se `result.identity.kind != "provider"` → `auth.LoginError("unsupported")`;
3. `credential = web_session.current_credential(...)`; se `None` →
   `auth.LoginError("invalid")`;
4. `token, session = web_session.create(...)` com `source`, `account_id`,
   `identity`, `membership`, `principal`, `credential`;
5. devolve `(token, session)`.

### `provider_session`

- se a flag estiver desligada → `None`;
- lê `autosseg_unified` via `web_cookie.token_from_headers`;
- resolve via `web_session.resolve`;
- se `identity.kind != "provider"` → `None` (não deixa cliente acessar o portal
  do prestador nesta fase);
- devolve o dicionário que o portal já espera:
  ```python
  {
    "pid": identity.id,
    "nome": identity.display_name,
    "admin": principal.role == "admin",
    "csrf": session.csrf,
    "cred": session.credential,
    "telemetry_session": session.telemetry_session,
    "exp": session.expires_at,
    "unified": True,
  }
  ```

## 4. Integração no portal

Em `portal_prestador.py`:

- importar `auth`, `login_flags`, `web_cookie`, `web_session`, `login_web`;
- `do_GET`, antes do gate de sessão:
  ```python
  if path == '/entrar':
      if not login_flags.unified_login_enabled(banco):
          return self.redir('/login')
      return self.responder(login_web.render_login(self))
  ```
- `do_POST`, antes do bloco de `/login`:
  ```python
  if path == '/entrar':
      if not login_flags.unified_login_enabled(banco):
          return self.redir('/login')
      if not self.origem_permitida():
          return self.erro('Origem da requisição inválida.', 403)
      d = self.form(PREAUTH_MAX)
      try:
          token, _sessao = login_web.authenticate_and_create(
              banco, str(d.get('identificador','')), str(d.get('senha','')))
      except auth.LoginError as exc:
          return self.responder(login_web.render_login(
              self, str(exc), str(d.get('identificador',''))))
      return self.redir('/', web_cookie.set_cookie(
          token, secure=web_cookie.secure_request(self.headers)))
  ```
- `sessao()`, no topo, **sem remover** o fluxo antigo:
  ```python
  unified = login_web.provider_session(self, banco)
  if unified:
      return unified
  ```
- Não alterar `/login`, `/sair`, `/entrar-pf`, portal do cliente, layout ou
  templates existentes.

## 5. Testes

`tests/test_login_web.py` com `PortalPrestador` e banco temporário:

1. flag off: `GET /entrar` → 303 `/login`; `POST /entrar` → 303 `/login`.
2. flag on: `GET /entrar` → 200 com campo `identificador` e `senha`.
3. provider ativo + senha correta → 303 `/`, `Set-Cookie` com
   `autosseg_unified`, `HttpOnly`, `SameSite=Strict`.
4. com o cookie, `GET /` → 200 e a sessão do prestador funciona.
5. senha errada → 200 com mensagem genérica e sem cookie.
6. cliente ativo + senha correta → 200/403 com erro genérico e sem cookie.
7. inativo → erro genérico, sem cookie.
8. `/login` antigo continua 200 com a flag ligada.
9. cookie de cliente forjado/real não abre o portal do prestador.
10. flag off não cria/valida `autosseg_unified`.
11. nenhuma senha/hash/PII na resposta de erro.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_login_web tests.test_web_session tests.test_web_cookie tests.test_auth -v
```

Se não houver `.venv`, registrar o erro exato; não declarar aprovação.

## 6. ZIP

```text
login-route/
├── changed-files/
│   ├── flavors/autoseg/modules/login_web.py
│   ├── flavors/autoseg/modules/portal_prestador.py
│   └── tests/test_login_web.py
├── login-route.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, logs ou segredos.

## 7. Critérios de aceite

- `/entrar` existe só com a flag ligada.
- Só provider entra nesta fase; cliente é rejeitado.
- Cookie único, `HttpOnly`, `SameSite=Strict`, `Secure` condicional.
- Sessão antiga e `/login` continuam funcionando.
- Nenhuma mudança no portal do cliente, shell ou layout.
- Diff mínimo no `portal_prestador.py`.
