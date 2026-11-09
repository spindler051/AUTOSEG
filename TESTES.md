# Testes

## Suíte não visual

```bash
./autoseg test
./autoseg check   # suíte + compilação + portal.js
```

Estado em 2026-11-08: **343 testes, 0 falhas, 1 skip**.

O comando cria uma pasta temporária e aponta `AUTOSEG_BASE`,
`GESTAO_BANCO`, `AUTOSEG_USER_DATA`, `AUTOSEG_SERVER_DATA` e
`AUTOSEG_LOCAL_DATA` para ela. Assim, um teste não abre o banco local nem o
banco de produção.

## Scripts de aceitação

```bash
./autoseg test
PYTHONPATH=. ./.venv/bin/python tests/test_portal_v4.py
PYTHONPATH=. ./.venv/bin/python tests/test_fluxo_v5.py
PYTHONPATH=. ./.venv/bin/python tests/test_fluxo_v6.py
PYTHONPATH=. ./.venv/bin/python tests/test_fluxo_v7.py
PYTHONPATH=. ./.venv/bin/python tests/test_fluxo_cliente_v94.py
PYTHONPATH=. ./.venv/bin/python tests/test_rev09_fluxo_os.py
PYTHONPATH=. ./.venv/bin/python tests/test_importacao_yaml.py
```

Todos usam banco, arquivos e portas temporárias; não gravam nos bancos reais.

## Testes históricos

`test_v9.py`, `test_v91.py`, `test_v92.py` e `test_v94_correcoes.py` descrevem
a arquitetura anterior à separação dos portais e não devem ser usados como
sinal de regressão. Eles ficam preservados como referência.

## Auditores

```bash
./.venv/bin/python scripts/audit_comments.py --strict
./.venv/bin/python scripts/audit_code_rot.py
```

## Antes de produção

- backup do banco e dos anexos;
- smoke manual no macOS;
- portais do cliente e do prestador;
- PDF e e-mail de uma OS de teste;
- rollback descrito quando houver mudança de schema ou dados.
