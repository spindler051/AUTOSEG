# Pipeline — Officina Web 6.1–6.4

**Base de código:** `4304ef7` (main após login unificado 5.1–5.5, Officina Web 6.1, papéis/permissões 6.2 e sessão durável 6.3).
**Formato:** cada peça é um prompt independente; o ChatGPT trabalha numa cópia
do repositório, **não faz commit** e devolve ZIP. O revisor aplica, testa e
integra.

## Ordem

| Ordem | Peça | Depende de | Entrega |
|---|---|---|---|
| 1 | [6.1 Shell, login e cliente](PROMPT_OFFICINA_6_1_SHELL.md) | 5.1–5.5 | `officina/web`, `/entrar` para os dois papéis, home do cliente |
| 2 | [6.2 Papéis e permissões](PROMPT_OFFICINA_6_2_ROLES.md) | 6.1 | papéis de cliente, matriz, `ObjectPolicy` no serviço |
| 3 | [6.3 Sessão durável e GTK](PROMPT_OFFICINA_6_3_SESSION_GTK.md) | 6.1–6.2 | SQLite de sessões, contexto compartilhado, GTK |
| 4 | [6.4 Shell web unificado](PROMPT_OFFICINA_6_4_SHARED_SHELL.md) | 6.1–6.3 | a mesma shell para provider e client; `/cliente` como alias, módulo client-only |

A 6.1 pode ser gerada sem a 6.2; a 6.2 assume a 6.1 aplicada; a 6.3 assume as
duas; a 6.4 corrige a apresentação e assume 6.1–6.3. Se o ChatGPT não tiver a
peça anterior no checkout, deve assumir a interface congelada e registrar em
`NOTES.md` que a integração será validada pelo revisor.

## Decisões já tomadas

- **Um site, uma origem, um login**: prestador e cliente entram por `/entrar`,
  com o mesmo cookie/sessão. O sistema decide a home pelo vínculo.
- **Provider UI preservada**: a experiência do prestador continua a mesma; muda
  o nome do produto para Officina Web e o rótulo de contexto.
- **Cliente no primeiro corte**: próprias OS, documentos/PDF e pedido de
  serviço. Sem financeiro, sem OS anônima, sem papéis nesta primeira peça.
- **Shell única:** provider e client usam a mesma chrome, o mesmo login e a
  mesma raiz; “Portal do prestador”/“Portal do cliente” são rótulos de
  contexto. A 6.4 corrige a home separada da 6.1 e transforma `/cliente` em
  alias, não em site paralelo.
- **Papéis**: customer, porteiro, zelador e síndico; um papel por conta nesta
  fase; escopo organizacional via `v9_responsaveis`/`v9_vinculos`.
- **Matriz provisória**: fica em `policy.yaml`/`PADRAO` e será ajustada com uso
  real; não hardcode no handler.
- **GTK**: contrato e sessão compartilhados; não criar modo cliente no GTK
  agora. Se o GTK exigir duplicar regra, parar e documentar.
- **Fora deste bloco**: OS anônima/anti-abuso, financeiro do cliente, editor
  granular de permissões, migração completa de escrita para `accounts`,
  multi-prestadora, reescrita big-bang do portal.

## Como conduzir

1. Envie a 6.1. Quando o ZIP chegar, o revisor aplica, roda a suíte, revisa
   segurança/arquitetura e devolve o que estiver errado.
2. Enquanto a 6.1 é revisada, a 6.2 pode ser gerada; ela assume a interface da
   6.1.
3. Repita para a 6.3.
4. A 6.4 corrige a apresentação: uma shell para os dois contextos, `/cliente`
   como alias e um módulo client-only real.
5. Só depois de 6.1–6.4 integradas e revisadas se discute ativação em produção
   e os blocos seguintes (OS anônima, financeiro do cliente, migração de
   escrita para accounts, shell GTK completo).

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
