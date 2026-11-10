# Peça 5.3 — cookie e CSRF únicos

**Uso:** colar no ChatGPT. Trabalha sobre uma cópia do repositório, **não faz
commit**, devolve ZIP.

**Base:** `205bd64` + peças 5.1 (`login_flags`) e 5.2 (`web_session`).
**Dependências:** sessão única (`SessionData`) já integrada.
**Entrega:** ZIP com arquivos completos + patch + testes + notas.

## 1. Missão

Criar os helpers de cookie e CSRF da sessão única. **Sem rota, sem login, sem
UI, sem alterar portais.**

## 2. Arquivos permitidos

Criar:

- `flavors/autoseg/modules/web_cookie.py`
- `tests/test_web_cookie.py`

Nenhum outro arquivo.

## 3. Interfaces

```python
COOKIE_NAME = web_session.COOKIE_NAME   # "autosseg_unified"

def set_cookie(token: str, secure: bool = False,
               max_age: int = web_session.SESSION_TTL) -> str
def clear_cookie(secure: bool = False) -> str
def token_from_headers(headers) -> str | None
def secure_request(headers) -> bool
def csrf_input(session: SessionData) -> str
def csrf_valid(session: SessionData | None, supplied: str) -> bool
```

Regras:

- `set_cookie` devolve um `Set-Cookie` completo:
  `autosseg_unified=<token>; Path=/; HttpOnly; SameSite=Strict; Max-Age=...`;
  adicionar `Secure` quando `secure=True`.
- `clear_cookie` devolve o mesmo cookie com `Max-Age=0`.
- `token_from_headers` lê `Cookie` com `http.cookies.SimpleCookie`; token
  ausente/inválido → `None`.
- `secure_request` é **paridade com o portal atual**: verdadeiro com
  `CF-Ray` ou `X-Forwarded-Proto: https`. Documentar que headers de proxy só
  são confiáveis quando o origin é loopback/Cloudflare.
- `csrf_input` devolve
  `<input type="hidden" name="csrf" value="...">` com escape.
- `csrf_valid` compara em tempo constante (`secrets.compare_digest`); sessão
  nula ou token vazio → `False`.
- Não logar token/CSRF.

## 4. Restrições

- Sem rota, login, sessão, UI, portal, GTK ou schema.
- Não alterar `web_session.py`, `auth.py`, `accounts.py`, `identity.py` ou
  `portal_prestador.py`.
- Não adicionar dependências.
- Diff limitado aos dois arquivos.

## 5. Testes

`tests/test_web_cookie.py`:

1. `set_cookie` contém `HttpOnly`, `SameSite=Strict`, `Path=/`, `Max-Age`;
2. `secure=True` adiciona `Secure`; `false` não adiciona;
3. `clear_cookie` tem `Max-Age=0`;
4. `token_from_headers` lê cookie no meio de outros cookies;
5. cookie ausente/malformado → `None`;
6. `secure_request` com `CF-Ray`/`X-Forwarded-Proto` → `True`; sem headers →
   `False`;
7. `csrf_input` escapa valor;
8. `csrf_valid` aceita igual e rejeita diferente/vazio/sessão nula;
9. cookie/CSRF não aparecem em `repr`/logs.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_web_cookie tests.test_web_session -v
```

## 6. ZIP

```text
cookie-csrf/
├── changed-files/
│   ├── flavors/autoseg/modules/web_cookie.py
│   └── tests/test_web_cookie.py
├── cookie-csrf.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, logs ou segredos.

## 7. Critérios de aceite

- Cookie único, `HttpOnly`, `SameSite=Strict`, `Secure` condicional.
- CSRF constante no tempo e sem vazamento.
- Nenhuma rota/portal alterado.
- Diff limitado aos dois arquivos.
