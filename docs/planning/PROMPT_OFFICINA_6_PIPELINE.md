# Pipeline — Officina Web 6.1–6.5

**Base de código:** `main` após `15ddcd0`; 5.1–5.5 e 6.1–6.4 integradas,
com a rota final de login em `/login`. A 6.5 ainda não foi iniciada.
**Formato:** cada peça é um prompt independente; o ChatGPT trabalha numa cópia
do repositório, **não faz commit** e devolve ZIP. O revisor aplica, testa e
integra.

## Ordem

**Próxima peça, antes da 6.5:** [P0 — Unificação real dos portais](PROMPT_PORTAL_UNIFICATION.md).
Ela remove `servidor_web.py`/8765, deixa uma origem só e não é uma peça 6.x.

| Ordem | Peça | Depende de | Entrega | Status |
|---|---|---|---|---|
| 1 | [6.1 Shell, login e cliente](PROMPT_OFFICINA_6_1_SHELL.md) | 5.1–5.5 | `officina/web`, login para os dois papéis, home do cliente | Integrada |
| 2 | [6.2 Papéis e permissões](PROMPT_OFFICINA_6_2_ROLES.md) | 6.1 | papéis de cliente, matriz, `ObjectPolicy` no serviço | Integrada atrás de flag |
| 3 | [6.3 Sessão durável e GTK](PROMPT_OFFICINA_6_3_SESSION_GTK.md) | 6.1–6.2 | SQLite de sessões, contexto compartilhado, GTK | Integrada atrás de flag |
| 4 | [6.4 Shell web unificado](PROMPT_OFFICINA_6_4_SHARED_SHELL.md) | 6.1–6.3 | a mesma shell para provider e client; `/cliente` como alias, módulo client-only | Integrada; login consolidado em `/login` |
| 5 | [6.5 Cliente no GTK](GTK_CLIENT_MODE.md) | 6.1–6.4 + gate P0 | login cliente remote-only, `/me`, home com as próprias OS, logout, bloqueio de rotas | Planejada |

A 6.1 pode ser gerada sem a 6.2; a 6.2 assume a 6.1 aplicada; a 6.3 assume as
duas; a 6.4 corrige a apresentação e assume 6.1–6.3. A 6.5 só começa depois de
fechar ou aceitar formalmente o TOCTOU da autorização por objeto.

## Decisões já tomadas

- **Um site, uma origem, um login**: prestador e cliente entram por `/login`,
  com o mesmo cookie/sessão. O sistema decide a home pelo vínculo. `/entrar`
  foi removida e responde `404`.
- **Provider UI preservada**: a experiência do prestador continua a mesma; muda
  o nome do produto para Officina Web e o rótulo de contexto. A tela de login
  mantém o split-screen do AUTOSEG.
- **Cliente no primeiro corte web**: próprias OS, documentos/PDF e pedido de
  serviço. Sem financeiro, sem OS anônima, sem papéis nesta primeira peça.
- **Shell única:** provider e client usam a mesma chrome, o mesmo login e a
  mesma raiz; “Portal do prestador”/“Portal do cliente” são rótulos de
  contexto. A 6.4 corrige a home separada da 6.1 e transforma `/cliente` em
  alias, não em site paralelo.
- **Papéis**: customer, porteiro, zelador e síndico; um papel por conta nesta
  fase; escopo organizacional via `v9_responsaveis`/`v9_vinculos`.
- **Matriz provisória**: fica em `policy.yaml`/`PADRAO` e será ajustada com uso
  real; não hardcode no handler.
- **GTK**: continua provider-only na 6.4; a 6.5 planeja o cliente remote-only,
  reutilizando `auth`, `SessionContext`, `client_service` e `ObjectPolicy`, sem
  duplicar regra no widget.
- **Fora deste bloco**: OS anônima/anti-abuso, financeiro do cliente, editor
  granular de permissões, migração completa de escrita para `accounts`,
  multi-prestadora, reescrita big-bang do portal, modo local cliente.

## Como conduzir

1. 6.1–6.4 estão integradas e revisadas; o login final é `/login`.
2. Antes da 6.5, fechar ou aceitar o TOCTOU e decidir a ativação de
   `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` em produção.
3. Enviar a 6.5 em escopo remote-only: login, `/me`, home com as próprias OS,
   logout e bloqueio de rotas de prestador. Documento de análise em
   [`GTK_CLIENT_MODE.md`](GTK_CLIENT_MODE.md).
4. Só depois de 6.5 integrada se discute 6.6 (documentos/PDF, “Em rota”, modo
   local, paridade completa) e ativação em produção.
5. OS anônima, financeiro do cliente e migração de escrita para `accounts`
   continuam em blocos posteriores.

## Critérios de rejeição

O ZIP será devolvido, não integrado, se apresentar qualquer item abaixo:

- SQL, regra de negócio ou decisão de permissão dentro de handler/template;
- permissão escondida só na UI, sem negativa no serviço;
- teste enfraquecido, removido ou “ajustado” para passar;
- novo `if admin` fora da política;
- duplicação da regra de OS/permissão em web e GTK;
- refatoração ampla não pedida, renomeação de tabela/rota ou reescrita do
  portal;
- token, senha, hash, CSRF, cookie ou PII em log, resposta, ZIP ou tabela de
  sessão em claro;
- dependência nova, framework, SPA, npm, Redis ou serviço externo sem pedido;
- teste HTTP que não usa servidor real quando o contrato pede integração;
- “concluído” com bloqueio escondido ou suíte oficial não executada.

## Regras para todas as peças

- sem `git commit`, `git push` ou PR;
- ZIP com `changed-files/`, patch, `CHANGED_FILES.txt`, `TEST_RESULTS.txt`,
  `NOTES.md`;
- sem `.git`, banco, anexos, PDFs, logs, tokens ou PII;
- não alterar `AGENTS.md`;
- se faltar uma decisão de produto, parar e anotar;
- se a peça não fechar sem gambiarra, entregar o que fecha e declarar o
  bloqueio; não declarar aprovação.
