# Peça 5.5 — compatibilidade, logout, reset e rollback

**Uso:** colar no ChatGPT. Trabalha sobre uma cópia do repositório, **não faz
commit**, devolve ZIP.

**Base:** `205bd64` + peças 5.1–5.4.
**Dependências:** `/entrar`, sessão única, cookie/CSRF e flag já integrados.
**Entrega:** ZIP com arquivos completos + patch + testes + notas.

## 1. Missão

Fechar a transição sem quebrar o login antigo:

- logout encerra sessão unificada **e** antiga, limpando os dois cookies;
- reset/desativação de prestador revoga sessões unificadas;
- flag desligada ignora o cookie unificado e mantém o login antigo;
- documentar ativação e rollback.

Nada de shell único, portal do cliente novo ou UI de permissões.

## 2. Arquivos permitidos

Modificar minimamente:

- `flavors/autoseg/modules/portal_prestador.py`
- `flavors/autoseg/modules/web_cookie.py` (somente se precisar de helper de
  limpeza/múltiplos cookies)

Criar:

- `tests/test_login_compat.py`
- `docs/operations/UNIFIED_LOGIN_ROLLOUT.md`

Nenhum outro arquivo.

## 3. Comportamento

### 3.1 Logout

`POST /sair` deve:

1. ler o cookie `autosseg_unified` e chamar `web_session.revoke(token)`;
2. manter a revogação da sessão antiga (`autosseg_session`) já existente;
3. responder com **dois** `Set-Cookie` de limpeza:
   - `autosseg_unified=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict`;
   - `autosseg_session=; Max-Age=0` (formato atual do portal).
4. redirecionar para `/login`.

Para isso, `PortalPrestador.redir` pode aceitar `cookie` como string **ou**
lista/tupla de strings e emitir um `Set-Cookie` por item. Preserve o
comportamento atual para string.

### 3.2 Reset de senha / desativação

Nos pontos em que o admin redefine a senha do prestador (rota
`/prestadores/<id>/senha`) e quando um prestador é desativado/arquivado:

- chamar `web_session.revoke_identity("provider", provider_id)`;
- isso invalida todas as sessões unificadas daquele provider;
- o fluxo antigo de invalidação por hash continua.

Não alterar o hash, a senha ou a auditoria existentes.

### 3.3 Flag e rollback

Com `AUTOSEG_UNIFIED_LOGIN` desligada:

- `/entrar` redireciona para `/login` (peça 5.4);
- `sessao()` não tenta `autosseg_unified`;
- login/sessão antigos funcionam normalmente;
- o cookie unificado, se existir, é ignorado.

Com a flag ligada:

- `/entrar` e `/login` coexistem;
- `/login` antigo continua funcionando;
- o portal do cliente continua no fluxo antigo;
- logout/reset revogam os dois mundos.

### 3.4 Documento de rollout

`docs/operations/UNIFIED_LOGIN_ROLLOUT.md` deve conter:

- pré-requisitos: backup, `accounts.install`, `migrate_legacy(dry_run=True)`,
  revisão dos conflitos;
- ativação: `AUTOSEG_UNIFIED_LOGIN=1`, restart, smoke com provider;
- verificação: login novo, login antigo, logout, reset de senha, OS/financeiro;
- rollback: `AUTOSEG_UNIFIED_LOGIN=0`, restart, login antigo; nenhum dado é
  apagado;
- aviso: sessões em memória somem no restart; migração não é executada
  automaticamente.

## 4. Testes

`tests/test_login_compat.py`:

1. logout com sessão unificada remove o cookie e invalida o token;
2. logout com sessão antiga continua funcionando;
3. logout com os dois cookies emite duas limpezas;
4. reset de senha de provider invalida a sessão unificada existente;
5. provider desativado/arquivado invalida a sessão unificada;
6. flag off: `/entrar` → `/login`; cookie unificado não autentica;
7. flag on: `/login` antigo ainda autentica;
8. flag on: `/entrar` autentica e o portal abre;
9. cliente continua no portal antigo (sem regressão);
10. nenhuma senha/hash/PII em resposta/log.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_login_compat tests.test_login_web tests.test_web_session tests.test_web_cookie -v
```

## 5. ZIP

```text
login-compat/
├── changed-files/
│   ├── flavors/autoseg/modules/portal_prestador.py
│   ├── flavors/autoseg/modules/web_cookie.py        (se alterado)
│   ├── tests/test_login_compat.py
│   └── docs/operations/UNIFIED_LOGIN_ROLLOUT.md
├── login-compat.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, logs ou segredos.

## 6. Critérios de aceite

- Logout limpa/revoga os dois mundos.
- Reset/desativação revoga sessão unificada.
- Flag off restaura o fluxo antigo por completo.
- Flag on mantém `/login` antigo funcional.
- Portal do cliente intacto.
- Documento de rollout/rollback sem PII.
- Diff limitado aos arquivos permitidos.
