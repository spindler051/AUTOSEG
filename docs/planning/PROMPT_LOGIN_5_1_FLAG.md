# Peça 5.1 — flag de ativação e relatório de ativação

**Uso:** colar no ChatGPT. Trabalha sobre uma cópia do repositório, **não faz
commit**, devolve ZIP.

**Base:** `205bd64` (última peça integrada).
**Dependências:** nenhuma.
**Entrega:** ZIP com arquivos completos + patch + testes + notas.

## 1. Missão

Criar a flag central do login unificado e um relatório read-only que diga se a
ativação está segura. Nada de rota, cookie, sessão ou UI nesta peça.

## 2. Arquivos permitidos

Criar:

- `flavors/autoseg/modules/login_flags.py`
- `tests/test_login_flags.py`

Nenhum outro arquivo.

## 3. Interfaces

```python
COOKIE_NAME = "autosseg_unified"

def unified_login_enabled(banco=None) -> bool:
    """Read AUTOSEG_UNIFIED_LOGIN; default False.

    Accepted true values: 1, true, on, yes (case-insensitive).
    Any other value, including empty, is False.
    """

def activation_report(banco) -> dict:
    """Read-only readiness report; never migrates, writes or logs PII.

    Keys:
      flag: bool
      cookie_name: str
      accounts_installed: bool
      accounts: int
      providers: int
      clients: int
      policy_types: tuple[str, ...]
      conflicts: int | None
      ready: bool
      blockers: tuple[str, ...]
    """
```

`ready` só é True quando:

- `accounts_installed` e `accounts > 0`;
- existem providers/clientes migrados;
- `policy_types` não está vazio e não contém `"password"`;
- não há blocker de schema.

`activation_report` não roda `migrate_legacy`; apenas lê tabelas existentes.
Se `accounts` não existir, retorna `accounts_installed=False`, contadores 0 e
o blocker `"accounts_not_installed"`.

## 4. Restrições

- Sem schema, sem migração, sem login, sem cookie, sem rota, sem UI.
- Não logar PII, senha ou hash.
- Não alterar `AGENTS.md`, `portal_prestador.py`, `servidor_web.py`,
  `auth.py`, `accounts.py` ou `identity.py`.
- Não adicionar dependências.
- Não ler `AUTOSEG_UNIFIED_LOGIN` em outro lugar nesta peça.

## 5. Testes

`tests/test_login_flags.py` com `unittest.mock.patch.dict(os.environ, ...)`:

1. sem env → `False`;
2. `"1"`, `"true"`, `"on"`, `"yes"` → `True`;
3. `"0"`, `"false"`, `"off"`, `""`, `"banana"` → `False`;
4. `activation_report` sem `accounts` → `accounts_installed=False`,
   `ready=False`, blocker;
5. `activation_report` com schema mínimo e contas → contadores e
   `ready=True`;
6. política inválida/`password` → `ready=False` com blocker;
7. relatório não escreve no banco (comparar bytes/contadores).

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_login_flags -v
```

Se não houver `.venv`, registrar o erro exato; não declarar aprovação.

## 6. ZIP

```text
login-flag/
├── changed-files/
│   ├── flavors/autoseg/modules/login_flags.py
│   └── tests/test_login_flags.py
├── login-flag.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, PDFs, logs ou segredos.

## 7. Critérios de aceite

- Flag default False.
- Nenhuma rota/sessão/cookie/UI.
- Relatório read-only e sem PII.
- `ready` conservador: na dúvida, False com blocker.
- Diff limitado aos dois arquivos.
