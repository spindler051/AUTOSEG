# Pipeline — login unificado em 5 peças

> **Status 2026-11-11:** 5.1–5.5 integradas. A rota final é `/login`;
> `/entrar` foi removida e responde `404`. Ver [`ROADMAP.md`](../ROADMAP.md) e
> [`operations/UNIFIED_LOGIN_ROLLOUT.md`](../operations/UNIFIED_LOGIN_ROLLOUT.md).

**Base de código:** `205bd64`.
**Formato:** cada peça é um prompt independente; o ChatGPT trabalha numa cópia
do GitHub, **não faz commit** e devolve ZIP.

## Ordem técnica

A ordem abaixo não é a ordem da sua lista; é a ordem sem dependência circular:

| Ordem | Peça | Depende de | Entrega |
|---|---|---|---|
| 1 | [5.1 Flag e ativação](PROMPT_LOGIN_5_1_FLAG.md) | — | `login_flags.py` + testes |
| 2 | [5.2 Sessão única](PROMPT_LOGIN_5_2_SESSION.md) | 5.1 | `web_session.py` + testes |
| 3 | [5.3 Cookie/CSRF](PROMPT_LOGIN_5_3_COOKIE.md) | 5.2 | `web_cookie.py` + testes |
| 4 | [5.4 Rota `/entrar`](PROMPT_LOGIN_5_4_ROUTE.md) | 5.1–5.3 | `login_web.py` + rota mínima |
| 5 | [5.5 Compatibilidade/rollback](PROMPT_LOGIN_5_5_COMPAT.md) | 5.4 | logout/reset/rollback |

A rota não pode vir antes da sessão/cookie; a flag vem primeiro porque é
pequena e destrava a rota. O shell único e o cliente no mesmo site ficam para
depois dessas cinco.

## Como conduzir

1. Envie a peça 5.1 ao ChatGPT.
2. Quando o ZIP chegar, me envie; eu aplico, rodo a suíte e reviso.
3. Enquanto eu reviso, você já pode enviar a 5.2; ela assume a interface da
   5.1 e pode ser gerada sem esperar o merge.
4. Repita para 5.3, 5.4 e 5.5.
5. Se uma peça depender de código ainda não integrado, o ChatGPT deve assumir a
   interface congelada e registrar em `NOTES.md` que os testes de integração
   serão rodados por mim.

## Regras para todas as peças

- sem `git commit`, `git push` ou PR;
- ZIP com `changed-files/`, patch, `CHANGED_FILES.txt`, `TEST_RESULTS.txt`,
  `NOTES.md`;
- sem `.git`, banco, anexos, PDFs, logs, tokens ou PII;
- não alterar `AGENTS.md`;
- se faltar uma decisão de produto, parar e anotar.

## O que fica para depois

- shell único e cliente no mesmo site;
- contexto cliente/prestador;
- editor de permissões;
- sessão durável/compartilhada;
- cutover definitivo dos cookies antigos.
