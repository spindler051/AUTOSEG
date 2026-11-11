# P0 — Correções da revisão da unificação dos portais

**Status:** correção solicitada; a P0 **não está aprovada** para a MAIN.
**Uso:** colar no ChatGPT. Trabalha sobre o ZIP `autoseg-p0-review-<commit>.zip`,
**não faz commit/push** e devolve ZIP.
**Base:** o ZIP anexado, que já contém a implementação P0 sobre `e2cfec1` mais
as correções desta revisão. **Não aplique o patch antigo sobre `e2cfec1` sem
incluir estas correções.**

## 1. Contexto

A implementação P0 passou na revisão funcional:

- patch aplicado sobre `e2cfec1`;
- P0: 15 testes OK;
- suíte focada: 139 testes OK;
- regressão: 65 OK, 1 skip;
- `py_compile` do GTK/web_access e `audit_comments --strict` OK;
- DEV 8866: login de cliente/prestador, shell única, rotas migradas, aliases
  `308`, fluxos retirados `410`, sem listener 8865;
- MAIN 8766 intocada.

A revisão já corrigiu no ZIP:

- isolamento de `AUTOSEG_SERVER_DATA` em `tests/test_portal_unification.py`;
- `tests/test_rev05_seguro.py` atualizado para `(8866,)`;
- `/cliente/...` desconhecido agora responde `404`, não `403`;
- textos GTK antigos (“dois portais”, “Portal do Cliente” e “Login antigo: ID”);
- import inútil de `portal_cliente_v94` em `tests/test_pf_pj_responsaveis.py`.

**Preserve essas correções.** O que falta está abaixo.

## 2. Regras não negociáveis

- Sem `servidor_web.py`, `portal_cliente_v94.py`, 8765/8865, fallback, shim,
  flag ou caminho paralelo.
- Não tocar na MAIN, nas portas 8765/8766, em dados reais, no GTK além do
  plumbing de porta já autorizado, nas flags da 6.2/6.3 ou no TOCTOU.
- Não criar alias implícito. A lista de URLs públicas é fechada.
- Não colocar SQL/regra de negócio em handler/template.
- Não enfraquecer, pular ou apagar teste de comportamento que ainda existe só
  para “ficar verde”.
- Se uma decisão de produto nova aparecer, parar e devolver `BLOCKED.md`.

## 3. Correções obrigatórias

### 3.1 Testes legados que ainda importam módulos removidos

A suíte completa ainda tem erros de importação e métodos antigos. Resolva cada
um com uma decisão explícita, registrada em `NOTES.md`:

- **12 módulos:** `test_autoseg_http_novo.py`, `test_cadastro_v951.py`,
  `test_fluxo_cliente_v94.py`, `test_fluxo_v5.py`, `test_fluxo_v6.py`,
  `test_fluxo_v7.py`, `test_links_cliente_952.py`, `test_pf_pj_http.py`,
  `test_rev03_http.py`, `test_rev09_fluxo_os.py`, `test_v94_correcoes.py`,
  `test_v953_http.py`.
- **4 métodos** em `test_rev12_melhorias.py`:
  `test_alteracao_de_senha_http`,
  `test_chamado_condominio_exige_nome_e_telefone`,
  `test_logo_e_icone_nos_dois_portais`,
  `test_pj_publico_sem_login_aceitar_e_recusar`.

Regras:

- Se o teste cobre **feature removida** (cadastro, login legado, PJ público
  anônimo, portal antigo), remova-o do `tests/` (ou arquive fora do discovery)
  e remova a referência do `TESTES.md`. Deixe a justificativa no `NOTES.md`.
- Se o teste cobre **feature que continua** (perfil, senha, organizações,
  chamados, PDFs, orçamento, fluxo PF/PJ), migre-o para o novo caminho:
  `PortalPrestador`, `/login`, `client_web`/`client_features` e banco
  temporário. Preserve as asserções de comportamento.
- `test_logo_e_icone_nos_dois_portais` deve virar um teste da **origem única**
  (logo/ícone em 8766/8866), não de dois servidores.
- `test_pj_publico_sem_login_aceitar_e_recusar` deve sair; o novo teste P0 já
  cobre `410` para `/pj-rapido*`.
- `test_pf_pj_responsaveis.py` deve continuar passando (8 testes).
- `test_rev05_seguro.py` deve manter `(8866,)`.
- Atualizar `TESTES.md` e `README.md` com a realidade nova (sem contagens
  antigas de “legacy client portal: 3 OK”).
- **Proibido:** recriar `servidor_web.py` ou um helper que o importe; pular
  módulos com `SkipTest` sem decisão; esconder erro de importação.

### 3.2 PDF de organização × cliente responsável

Há uma inconsistência:

- a lista `/cliente/sindico` usa `cad.listar_os_organizacao` e
  `v9_responsaveis`;
- o PDF em `client_features.report_for_organization` usa
  `session.principal.client_org_ids`/`ObjectPolicy`.

Um cliente nomeado responsável com `client_role='customer'` pode ver a lista e
receber `404` no PDF. Resolva de forma explícita, preferindo o contrato de
papéis da 6.2:

- `sindico`/`zelador` têm acesso organizacional; `customer` não;
- o link “Consultar todas as OS” só aparece se o papel/permissão permitir;
- a lista e o PDF usam a mesma autoridade;
- não contorne `ObjectPolicy` silenciosamente; se usar
  `cad.autorizar_pdf_os_organizacao`, documente a decisão e mantenha o
  fail-closed.

Adicionar testes:

1. responsável com papel `sindico` vê a lista e baixa o PDF da própria org;
2. o mesmo responsável não baixa OS/PDF de outra org;
3. cliente `customer` sem papel organizacional não vê o link nem baixa PDF;
4. um responsável `customer` (se o produto decidir permitir) tem o papel
   ajustado/documentado, não um bypass.

### 3.3 Cobertura positiva de documentos

Adicionar pelo menos um teste positivo para:

- relatório PDF de OS própria (`/cliente/os/<id>/pdf` ou rota canônica);
- nota fiscal de OS própria (`/cliente/nota/<id>` ou rota canônica);
- PDF de chamado;
- manter os negativos de outro cliente (404/403 sem vazar existência).

### 3.4 Documentação e contagens

Atualizar somente docs vigentes (não `docs/archive/`):

- `docs/security/SECURITY_ARCHITECTURE.md` — remover `ServidorPortal`/8765
  como arquitetura atual;
- `docs/GTK_SERVER_DECOUPLING.md`, `docs/GTK4_LINUX_MACOS.md`,
  `docs/operations/TUNEL_FIXO.md`, `docs/PLATFORM_MIGRATION_LEDGER.md` —
  remover referências ao portal antigo e à segunda porta;
- `TESTES.md` — remover scripts antigos e atualizar o estado;
- `README.md` — atualizar contagens e remover “legacy client portal: 3 OK”;
- rodar `grep -RIn "servidor_web\\|Portal do Cliente\\|8765\\|8865\\|dois portais"`
  nos docs vigentes e explicar o que restar.

### 3.5 Suíte completa

Rodar a suíte completa em ambiente temporário:

```bash
TMP=$(mktemp -d)
AUTOSEG_DEV=1 AUTOSEG_SERVER_DATA="$TMP" AUTOSEG_USER_DATA="$TMP" \
AUTOSEG_LOCAL_DATA="$TMP" PYTHONPATH=. \
python3 -m unittest discover -s tests -p 'test_*.py'
```

- Não usar banco/porta da MAIN.
- `test_numero_publico.test_non_admin_cannot_reopen_pending_os` falha também na
  base `e2cfec1`; confirme isso e documente como **falha pré-existente**. Não a
  esconda nem mude autorização para “passar”.
- O critério da P0 é: **nenhum erro/falha novo** em relação à base, e todos os
  testes legados resolvidos por migração ou remoção justificada.
- Se a suíte completa exceder o tempo, rode por módulos e informe exatamente o
  que foi executado; não declare “verde” sem o discovery completo.

## 4. Testes de aceite após a correção

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_portal_unification tests.test_officina_web tests.test_client_web \
  tests.test_client_roles_http tests.test_login_web tests.test_login_compat \
  tests.test_shared_shell tests.test_web_access tests.test_runtime_config \
  tests.test_pf_pj_responsaveis tests.test_rev05_seguro -v
```

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_rev12_correcoes tests.test_admin_parity tests.test_portal_v4 -v
```

Qualidade:

```bash
python3 -m py_compile flavors/autoseg/modules/gtk_app.py \
  flavors/autoseg/modules/web_access.py
python3 scripts/audit_comments.py --strict
git diff --check
```

## 5. Condições de parada

Pare e devolva `BLOCKED.md` se:

- uma feature ainda existente não puder ser migrada sem decisão de produto;
- a correção do PDF organizacional exigir mudar o modelo de papéis;
- a suíte completa revelar uma falha nova de autorização/dados que não possa
  ser corrigida dentro do escopo;
- for necessário tocar na MAIN/8765/8766 ou em dados reais.

## 6. Entrega

ZIP com:

- `changed-files/` completos;
- patch cumulativo contra o ZIP base desta revisão;
- `CHANGED_FILES.txt`;
- `TEST_RESULTS.txt` com a suíte completa (ou módulos, se o tempo exceder) e a
  falha pré-existente separada;
- `NOTES.md` com a tabela de decisão de cada teste legado e a decisão de
  autorização do PDF organizacional;
- `ROUTE_MAP.md` atualizado;
- `BLOCKED.md`, se houver bloqueio.

Sem `.git`, banco, anexos, PDFs de produção, logs, tokens ou credenciais.
Nenhum commit ou push.
