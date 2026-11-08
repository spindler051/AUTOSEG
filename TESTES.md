# Testes

## Suíte não visual

```bash
find . -maxdepth 1 -name 'test_*.py' ! -name 'test_visual_*' \
  -exec basename {} .py \; | sort | xargs ./.venv/bin/python -m unittest
```

Estado em 2026-11-07: **313 testes, 0 falhas, 1 skip**.

## Scripts de aceitação

```bash
./.venv/bin/python -m unittest -q test_auth_session.py test_application_service.py
./.venv/bin/python test_portal_v4.py
./.venv/bin/python test_fluxo_v5.py
./.venv/bin/python test_fluxo_v6.py
./.venv/bin/python test_fluxo_v7.py
./.venv/bin/python test_fluxo_cliente_v94.py
./.venv/bin/python test_rev09_fluxo_os.py
./.venv/bin/python test_importacao_yaml.py
```

Todos usam banco, arquivos e portas temporárias; não gravam em `dados.db`.

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
