# Peça P0 — Unificação real dos portais (sem fallback)

> **Status 2026-11-11:** prompt pronto para o ChatGPT. **Não implementado.**
> A MAIN está rodando em 8765/8766 e **não pode ser tocada** por esta peça.

**Uso:** colar no ChatGPT. Ele trabalha sobre uma cópia do repositório, **não
faz commit**, não faz push e devolve ZIP.

**Base:** `main` após `a635115` (5.1–5.5 + 6.1–6.4 + login final em `/login`).
**Dependências:** 6.1–6.4 integradas, shell única, `client_web`,
`SessionContext` e `client_service`.
**Entrega:** ZIP com arquivos completos, patch, testes, mapa de rotas e notas.

## 1. Missão

Remover o portal legado do cliente e a segunda origem. O Officina Web passa a
ser servido por **um único processo e uma única porta**, com prestador e
cliente no mesmo `/login`, na mesma shell e no mesmo caminho de código.

O resultado não pode manter `servidor_web.py`, a porta 8765/8865, um segundo
login, um segundo shell, um adaptador permanente ou uma flag para preservar o
portal antigo.

Esta peça é de **migração e remoção**, não de redesign. Preserve o
comportamento/labels/validações das rotas que continuarem existindo.

## 2. Decisão de produto (não negociável)

- **Uma origem:** somente a porta do prestador (8766 em produção, 8866 em
  DEV). O cliente é servido pelo mesmo `PortalPrestador`.
- **Um login:** `/login` aceita prestador e cliente. Não criar segundo login,
  segundo cookie ou segundo portal.
- **Uma shell:** todo cliente passa por `officina/web` e pelo mesmo renderer do
  prestador. Nenhum HTML/header/sidebar próprio do cliente.
- **Sem fallback:** `servidor_web.py`, `ServidorPortal`, 8765 e 8865 saem do
  caminho de execução. Não manter um processo antigo “só por segurança”.
- **Sem gambiarra:** proibido flag, shim, adaptador permanente, `if legacy`,
  `if path.startswith('/cliente')` paralelo ou cópia de handler para preservar
  código legado.
- **Rollback:** por deploy/git, não por fallback em runtime.

### 2.1 Rotas antigas

Cada rota do portal antigo deve entrar numa destas categorias, com evidência:

1. **Contrato público atual + equivalente unificado:** alias ou redirect
   explícito (`308`) para a rota nova na origem única.
2. **Funcionalidade atual sem equivalente:** migrar para `client_web` +
   `client_service`/serviço de domínio, preservando comportamento e testes.
3. **Obsoleta/duplicada:** remover; responder `410 Gone` ou `404`, atualizar
   links, navegação e docs. Não redirecionar para uma tela que não existe.
4. **Ambígua:** **parar** e registrar em `BLOCKED.md`; não decidir sozinho.

O default é remover o legado. Redirect só para contrato público documentado,
nunca para manter uma implementação paralela.

### 2.2 Porta 8765/8865

O default é **não existir**. Se algum contrato público exigir a porta antiga,
o máximo permitido é um listener mínimo que responde apenas `308` para a
origem única, sem HTML, sessão, cookie, API, banco ou template, com prazo de
remoção documentado. Isso não pode importar `servidor_web`, `portal_cliente_v94`
nem reutilizar a árvore antiga.

### 2.3 Login do cliente

O cliente precisa entrar por `/login` na origem única. A flag existente
`AUTOSEG_UNIFIED_LOGIN` pode continuar como rollout do formulário do prestador,
mas **não pode manter o portal antigo vivo**. Não criar uma flag nova para
cliente.

Se a flag desligada impedir o login do cliente, o comportamento deve ser
explícito e documentado (mensagem/erro de indisponibilidade), nunca um
redirecionamento para `servidor_web` ou 8765.

## 3. Estado atual que será removido

- `flavors/autoseg/modules/servidor_web.py` — servidor do portal antigo do
  cliente, com login CPF, cadastro, PJ, organizações, orçamento, legado e PDFs.
- `flavors/autoseg/modules/portal_cliente_v94.py` — handlers/telas do portal
  antigo. Pode conter regra reaproveitável; não pode ser importado pelo novo
  caminho como handler/HTML.
- `flavors/autoseg/modules/servidor_backend.py` — `run_site()` inicia
  `ServidorPortal` + `PortalPrestador` em duas portas. Deve iniciar só a origem
  única.
- `scripts/autoseg/cli.py` — `ports()`/start/stop/status tratam site como
  8865+8866. Deve tratar uma porta só.
- `officina/core/runtime_config.py` — `client_server`/`CLIENTE_PORT` e
  `CLIENTE_BIND`; remover do caminho de execução ou deixar de ser usado, sem
  código morto.
- Launchers/docs que prometem 8765/8865 como portal do cliente.

O que **não** será removido nesta peça:

- `PortalPrestador` como origem única;
- `client_web.py`, `client_service.py`, `officina/web/`, `SessionContext`;
- login `/login` e sessão unificada;
- CSS/design do prestador;
- dados/banco; nenhuma migração de dados nesta peça.

## 4. Inventário obrigatório de rotas

Antes de codar, gere `ROUTE_MAP.md` com **todas** as rotas encontradas em
`servidor_web.py`, `portal_cliente_v94.py` e `cliente_fluxo_v94.py` (inclua
métodos GET/POST). Procure também por strings de rota em `portal.js` e
launchers.

Colunas obrigatórias:

| Rota | Métodos | Arquivo atual | Contrato público? | Equivalente unificado | Disposição | Teste |
|---|---|---|---|---|---|---|

Disposições permitidas: `ALIAS`, `MIGRAR`, `REMOVER`, `BLOQUEADO`.

Rotas conhecidas que precisam aparecer (adicione as que faltarem):

- Infra: `/`, `/api/versao`, `/api/health`, `/api/info`,
  `/manifest.webmanifest`, `/static/portal.js`,
  `/static/cliente_whatsapp.js`, `/icone.png`, `/favicon.ico`, `/logo.png`.
- Legado: `/legado`, `/legado/entrar`, `/legado/sair`,
  `/legado/os/<token>/pdf`.
- Conta/perfil: `/cliente`, `/cliente/painel`, `/cliente/perfil`,
  `/cliente/senha`, `/cliente/sair-pf`, `/cliente/entrar-pf`,
  `/cliente/cadastro`, `/cliente/cadastrar`, `/cliente/cadastro-pj`.
- OS/chamados: `/cliente/nova`, `/cliente/os/nova`, `/cliente/os/<id>`,
  `/cliente/chamado/novo`, `/cliente/chamado/<id>`,
  `/cliente/orcamento`, `/cliente/orcamento/pdf`.
- PJ/organizações: `/pj-rapido`, `/pj-rapido/enviar`, `/cliente/pj-rapido`,
  `/cliente/pj-rapido/enviar`, `/cliente/organizacoes`,
  `/cliente/nova-organizacao`, `/cliente/administrar-organizacao`,
  `/cliente/vinculo/novo`, `/cliente/sindico`.
- Rotas já unificadas: `/`, `/login`, `/os`, `/os/<id>`, `/documentos`,
  `/solicitar`, `/em-rota`, `/chamado/<id>`, `/sair`, `/cliente/...` aliases.

Para cada `MIGRAR`, escreva no `NOTES.md` qual serviço existente será usado
(`client_service`, `cliente_fluxo_v94`, `ordens_repo`, etc.) e qual teste
caracteriza o comportamento atual.

## 5. Implementação

### 5.1 Uma origem

- `servidor_backend.run_site()` deve iniciar somente `PortalPrestador`.
- `servidor_backend` não pode importar `servidor_web`/`ServidorPortal`.
- `cli.py` deve reportar/iniciar/parar uma única porta de site.
- `runtime_config` deve ter uma única configuração de site; remova
  `client_server`/`CLIENTE_PORT` se não houver consumidor legítimo.
- O banner do `--site` deve mostrar **um** endereço, não Cliente/Prestador.
- A API embutida continua em `/api/v1` na mesma porta.

Se for necessário um listener de redirect na porta antiga, ele deve ser um
módulo mínimo separado, sem banco/HTML/sessão, e coberto por teste. O default é
não existir.

### 5.2 Rotas e apresentação do cliente

- Rotas `MIGRAR` entram em `client_web.dispatch_get/post` (ou no registro
  `autoseg_web_navigation.client_routes`), usando `officina_web.page` e a
  shell única.
- Nenhum handler/template novo pode conter SQL ou regra de negócio.
- Reutilize `client_service` e os serviços de domínio. Se precisar mover uma
  função de `portal_cliente_v94`/`servidor_web`, mova para um serviço com
  teste; não copie HTML.
- Não criar uma segunda tabela de navegação. Itens client-only entram em
  `ITEMS`/`client_routes` com `contexts=("client",)` e permissão.
- Aliases/redirects ficam em um único registro (`ALIASES`/`canonical_client_path`
  ou equivalente), sem lista duplicada no layout.
- Preserve labels, validações, mensagens e fluxos das rotas migradas.
- Rotas `REMOVER` devem responder de forma explícita (`410`/`404`) e sair da
  navegação/docs.

### 5.3 Login/sessão

- Cliente entra por `/login`; a sessão e o cookie são os mesmos já usados por
  `PortalPrestador`/`web_session`.
- Não criar segundo cookie, segundo CSRF ou segundo logout.
- Logout do cliente continua revogando a sessão e voltando para `/login`.
- O cliente não pode acessar rotas de prestador; teste negativo obrigatório.

### 5.4 Remoção do legado

- Retire `servidor_web.py` do caminho de execução.
- Depois de migrar o que for contrato atual, **apague** `servidor_web.py` e o
  que só existir para ele.
- `portal_cliente_v94.py`: apague se não sobrar consumidor; se sobrar lógica de
  domínio, mova a lógica e apague a camada de apresentação.
- Remova launchers, portas, testes e docs que só existem para o portal antigo.
- Não manter arquivo “morto” só para rollback; o rollback é git/deploy.

### 5.5 Docs e launchers

Atualize somente o que a mudança afeta:

- `README.md`;
- `docs/operations/DATA_STORAGE.md` e docs que citam 8765 como portal do
  cliente;
- `docs/ROADMAP.md`/pipeline somente se o status mudar;
- `scripts/autoseg/INICIAR_SITE*`, `cli.py`, help e status;
- comentários de código que dizem “dois portais”.

Não reescreva documentação histórica/arquivo.

## 6. Proibido

- Criar flag/shim para manter `servidor_web.py`, `portal_cliente_v94` ou 8765.
- Manter `Cliente: http://...:8765` no banner/status/launcher.
- Duplicar login, cookie, CSRF, logout, shell, navegação ou CSS do cliente.
- Colocar SQL/regra de negócio em handler/template.
- Alterar regras de OS, financeiro, PDFs, permissões, banco ou dinheiro.
- Ligar `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` ou
  `AUTOSEG_WEB_SESSION_DURABLE`.
- Resolver o TOCTOU nesta peça.
- Mexer no GTK, no cliente GTK ou no login do GTK.
- Tocar em `~/gestaoservicos_MAIN`, nas portas 8765/8766, no processo MAIN
  rodando ou em dados reais.
- Usar o banco de produção/MAIN nos testes.
- Rodar `git commit`, `git push` ou abrir PR.
- Enfraquecer, remover ou “ajustar” teste para passar.

## 7. Testes obrigatórios

Criar `tests/test_portal_unification.py` e ajustar os testes existentes.

Cobrir no mínimo:

1. `run_site()` inicia uma única origem e não importa/instancia
   `ServidorPortal`.
2. `cli.ports('dev','site')`/status/start usam só a porta única.
3. Cliente entra por `/login` e cai na home da shell única.
4. Cliente vê somente as próprias OS/documentos; outro cliente é negado.
5. Cliente não acessa `/clientes`, `/financeiro`, `/prestadores`, `/estoque`,
   `/composicao`, `/caixa`; retorno `403`/`404` sem vazar dados.
6. Rotas `ALIAS` redirecionam `308` para a rota unificada canônica.
7. Rotas `MIGRAR` mantêm comportamento/labels/validações e têm teste de
   caracterização.
8. Rotas `REMOVER` não aparecem em navegação/docs e respondem de forma
   explícita.
9. Não existe listener 8765/8865 no fluxo `--site` (ou, se houver redirect
   aprovado, ele só responde `308` sem banco/HTML/sessão).
10. `servidor_backend`/`cli` não têm referência de runtime a
    `servidor_web`/`ServidorPortal`.
11. Logout do cliente revoga a sessão e o token antigo é rejeitado.
12. Prestador continua funcionando e nenhuma rota/label de prestador mudou.
13. Testes usam banco temporário e porta efêmera; não tocam 8765/8766 nem a
    MAIN.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_portal_unification \
  tests.test_officina_web \
  tests.test_client_web \
  tests.test_client_roles_http \
  tests.test_login_web \
  tests.test_login_compat \
  tests.test_shared_shell -v
```

Regressão:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_rev12_correcoes tests.test_admin_parity tests.test_portal_v4 -v
```

Qualidade:

```bash
.venv/bin/python scripts/audit_comments.py --strict
git diff --check
```

## 8. Condições de parada

Pare e devolva `BLOCKED.md` se:

- uma rota não puder ser classificada sem decisão de produto;
- a migração exigir regra de negócio nova ou alteração de dados;
- for necessário tocar na MAIN/8765/8766 ou em dados reais;
- o teste de caracterização não puder ser escrito;
- a remoção de `servidor_web.py` quebrar uma rota sem equivalente claro.

Não invente comportamento, não esconda bloqueio e não declare “concluído” com
teste falhando.

## 9. Entrega

ZIP com:

- `changed-files/` com os arquivos completos;
- `portal-unification.patch` (cumulativo contra a base);
- `CHANGED_FILES.txt`;
- `ROUTE_MAP.md` com a tabela preenchida;
- `TEST_RESULTS.txt` com comandos e saída;
- `NOTES.md` com decisões, serviços reutilizados e riscos;
- `BLOCKED.md`, se houver bloqueio.

Sem `.git`, banco, anexos, PDFs, logs, tokens, credenciais ou dados reais.

## 10. Checklist do revisor

- [ ] Uma única porta/origem; 8765/8865 não sobem.
- [ ] `servidor_web.py` e `ServidorPortal` fora do runtime e apagados.
- [ ] `portal_cliente_v94` apagado ou reduzido a serviço de domínio testado.
- [ ] Nenhum flag/shim/rota paralela para preservar legado.
- [ ] Logout/login do cliente na origem única.
- [ ] Rotas antigas mapeadas: ALIAS/MIGRAR/REMOVER/BLOQUEADO.
- [ ] Nenhuma regra de negócio nova no handler/template.
- [ ] Testes negativos de cliente × cliente e cliente × prestador.
- [ ] Prestador sem regressão.
- [ ] Docs/launchers sem 8765 como portal do cliente.
- [ ] Suíte focada + regressão + audit + diff check verdes.
- [ ] MAIN intocada; nenhum dado real usado.
