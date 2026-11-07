# Handoff — estado atual do projeto

**Última atualização:** 2026-11-07
**Versão:** `9.6.0-dev.44`
**Branch de trabalho:** `develop`
**Regra do dia:** a MAIN não foi aberta nem sincronizada; servidor e túneis
continuam parados.

Este documento é o ponto de retomada. Ele resume o que foi feito, o que está
funcionando, o que ainda é legado e qual é o próximo passo pequeno. Não é um
plano de big-bang.

---

## 1. O que foi feito nesta sessão

### Documentação de visão e processo

- `docs/CONDO_SHARING_AND_TENANCY.md` — visão de compartilhamento de OS com
  condomínios, papéis, consentimento, LGPD, modelos de implantação e open
  source. **Não é compromisso nem implementação.**
- `docs/REVIEW_WITHOUT_DEVELOPER.md` — política de risco N0–N4 sem dev humano.
- `docs/EXTERNAL_AI_REVIEW_ROUTINE.md` — rotina mensal de revisão com ChatGPT
  e Gemini, um arquivo por ciclo, com fontes e triagem.
- `docs/CODE_ROT_CLEANUP_PLAN.md` — plano de limpeza e baseline de podridão.
- `scripts/audit_code_rot.py` — auditor de exceções amplas/silenciosas,
  funções/classes longas, TODO sem issue e SQL em UI/HTTP.

### Separação GTK × servidor (primeira fatia)

- `application/contracts.py` — contrato `AppService`, DTOs e erros estáveis.
- `application/local_service.py` — saúde, resumo do início, clientes e
  cartões/lista do Portal do Cliente.
- `application/http_service.py` — cliente remoto; hoje só `health`, sem
  fallback silencioso para o banco local.
- `application/connection.py` — modo local/remoto, URL e arquivo de conexão.
- `web_access.py` — `WebAccessManager` concentra o ciclo de vida dos portais.
- `gtk_app.py` — não importa mais os portais no topo; usa `AppService` para a
  fatia migrada.
- `gtk_dialogos.py` — diálogo de cliente usa o serviço.
- `repositorios/ordens.py` — resumo e lista de solicitações do portal.

### Separação GTK: shell completo sem SQL

- `gtk_app.py` e `gtk_dialogos.py` não executam mais SQL direto.
- A escrita transacional da OS foi para `application/os_write.py`; as leituras
  dos diálogos foram para `application/desktop_context.py`.
- SQL direto em UI/HTTP caiu para 43 linhas, todas no site.
- O shell GTK está em zero SQL.

### Separação GTK: janela principal sem SQL

- `gtk_app.py` não executa mais SQL direto.
- Histórico, PJ/chamados, prestadores, seletores de OS e lookup de cliente YAML
  usam `AppService`/`LocalService`.
- SQL direto em UI/HTTP caiu de 117 para 86 linhas.
- O SQL restante do GTK está em `gtk_dialogos.py` (diálogo de OS, materiais,
  anexos e escrita transacional).

### Separação GTK: financeiro e OS ativas

- Cartões, lista e marcação de recebimento do financeiro usam
  `LocalService`/`AppService`.
- A lista de OS ativas usa `LocalService`, com o mesmo filtro, ordem,
  responsável e aviso de dados incompletos.
- SQL direto em UI/HTTP caiu de 126 para 117 linhas.

### Tela de conexão no GTK

- Nova página **Conexão** em libadwaita: modo local, URL do servidor, teste de
  `/api/v1/health` e salvamento em `connection.json`.
- Ainda não troca para o modo remoto nem pede login; isso é a próxima fase
  N3/N4.

### Servidor headless e GTK local-only

- `servidor_backend.py --api` sobe só `/api/v1`, sem HTML, sem GTK e sem
  Cloudflare. `--web` sobe Officina Web + API.
- O GTK agora abre local-only por padrão; `AUTOSEG_WEB_ACCESS=1` ou
  `INICIAR_AUTOSEG_COM_WEB.command` restauram o comportamento antigo.
- `INICIAR_SERVIDOR_API.command` e `INICIAR_SERVIDOR_WEB.command` são os
  atalhos de terminal.
- Ainda falta o login/conexão remota no GTK; o modo remoto continua em
  preparação.

### Permissões configuráveis e aprovações

- `docs/PERMISSIONS_AND_APPROVALS.md` define grupos, papéis, flags, escopos e
  change requests no estilo Git.
- Admin do tenant é root; employee vê só o próprio/involvido e não vê
  financeiro completo nem lista de funcionários; customer vê só o próprio.
- Employee vê CPF/CNPJ/e-mail somente de clientes envolvidos em uma OS dele;
  não lista a base inteira, não busca por documento e não exporta clientes.
- Implementação fica em fases: política pura, enforcement, change requests,
  UI, login e revisão.
- `policy.yaml` + `application/policy.py` já permitem mudar escopo de campo
  (por exemplo, telefone `involved` → `none`) com `PolicyStore.reload()`, sem
  alterar código. Ainda não está ligado à autenticação/UI.

### Matriz de permissões P0

- `docs/PERMISSIONS_P0.md` define atores, ações, regra de OS, isolamento por
  tenant e 15 testes de autorização (AUT-001 a AUT-015).
- Próximo passo: implementar a política pura, depois o serviço, depois o login.
- Nada foi implementado; auth/permissões continuam N3/N4.

### Modos, papéis e descoberta de servidores

- `docs/APP_MODES_ROLES_AND_SERVERS.md` decompõe o produto em problemas
  menores: prestador × cliente, admin × não-admin, paridade web/GTK/Qt/nativo,
  descoberta de servidores, solicitação sem login e fases P0–P4.
- Nada foi implementado; auth/permissões continuam N3/N4.

### Login local e conexão com servidor

- A UX de primeira conta admin, usuários locais e “lembrar este dispositivo”
  foi documentada em `docs/AUTH_AND_CONNECTION_UX.md`.
- Nada foi implementado; autenticação é N3/N4 e exige revisão humana.
- O documento cobre localhost, LAN e Cloudflare Tunnel, e separa conta local
  de conta do servidor.

### Campo genérico de texto na OS

- `ordens_servico.texto_adicional` é um texto livre, sem semântica fixa no
  código.
- `texto_os.yaml` define rótulo, título do PDF, texto padrão e ajuda.
- O campo aparece no GTK e no portal; o PDF imprime a seção somente se houver
  texto.
- O texto padrão está vazio para ser decidido pelo dono.

### Feedback novo corrigido

- `/financeiro` ganhou prazo opcional de recebimento e destaque **Atrasado** em
  vermelho para lançamentos vencidos e ainda não recebidos.
- A alteração usa `financeiro.vencimento`, é restrita ao finalizador/admin e
  gera auditoria.
- Feedback registrado como FB-0001 em `docs/feedback/PENDENCIAS_DEV.md`.

### Comportamento preservado

- O padrão continua com os portais ligados.
- `--no-web`/`AUTOSEG_WEB_ACCESS=0` continua abrindo o modo local-only.
- Telas, rótulos, filtros, cálculos e HTML dos portais não mudaram.
- Escritas de cliente continuam last-write-wins no caminho legado.

---

## 2. Onde o código está

| Área | Estado | Observação |
|---|---|---|
| GTK → `AppService` | **shell concluído** | `gtk_app.py` e `gtk_dialogos.py` em zero SQL; escrita da OS em `application/os_write.py`. |
| Portais HTTP | **fora do GTK** | `WebAccessManager` inicia/para; HTML e rotas não mudaram. |
| Modo remoto | **só health** | `HttpService` não lista/salva clientes ainda. |
| Escrita de OS / materiais / anexos | **no serviço** | `application/os_write.py`, com teste de caracterização. |
| Portal do Prestador | **legado** | Ainda chama `integracao/clientes.py` diretamente. |
| Condomínios | **visão documentada** | Sem identidade, permissões, auditoria ou LGPD implementados. |
| MAIN | **em `8b134a9`** | Recebeu texto adicional, financeiro e janela GTK sem SQL; o refactor de escrita da OS está só em `develop`. |
| Túneis/servidor MAIN | **parados** | Links antigos não funcionam. |

---

## 3. Commits desta sessão

```text
b35ad58 refactor: dialogo de OS sem SQL direto
e9b8728 refactor: historico, PJ e prestadores via AppService
cd79f19 refactor: financeiro e OS ativas via AppService
d6b1e50 feat: campo de texto adicional configuravel na OS
efc7e3c feat: prazo de recebimento e destaque de atraso
197a2c8 docs: atualiza baseline apos fatia AppService
b1cdab7 feat: separa GTK dos portais e inicia AppService
5ca6b2c docs: modelos de implantacao e open source em condominios
4cd52bd docs: visao de compartilhamento de OS em condominios
e2a0292 docs: rotina de revisao externa com outras IAs
68973f1 docs: politica de revisao sem desenvolvedor humano
dc18fa1 docs: plano de limpeza de podridao e auditor de codigo
```

---

## 4. Testes e verificações

### Passaram

- `test_application_service.py`
- `test_web_access.py`
- `test_integracao_clientes.py`
- `test_repositorios_ordens.py`
- `test_runtime_config.py`
- `test_versionador.py`

Resultado: **41 OK**.

- `test_financeiro_vencimento.py`: **4 OK**.
- `test_texto_os.py`: **4 OK**.
- `test_pdf_relatorio.py`: **7 OK**.
- `test_application_service.py`: **14 OK** (inclui financeiro, OS ativas, histórico e PJ).
- `test_os_write.py`: **3 OK** (criação, edição, status, contexto).
- Suíte completa não-visual: **278 testes, 3 falhas pré-existentes, 1 skip**.
- Testes relacionados de portal/financeiro: **61 OK, 1 falha pré-existente**
  (`test_autoseg_http_novo`).

- Smoke GTK local-only (`--no-web`): **exit 0**.
- Smoke GTK com portas efêmeras: **exit 0**.
- Manager real: portais subiram em portas efêmeras, portal do cliente
  respondeu **HTTP 200** e `/api/v1/health` respondeu **ok**.
- Auditoria de comentários: **0 alto, 0 baixo**.
- Baseline de podridão: **149** exceções amplas, **32** silenciosas,
  **126** linhas de SQL em UI/HTTP.

### Falhas pré-existentes da suíte completa

A suíte não-visual rodou **259 testes** com **3 erros** confirmados também no
commit anterior `5ca6b2c`:

1. `test_autoseg_http_novo.HttpTest.test_cliente_para_pendencias_prestador_e_formularios` — HTTP 400.
2. `test_rev03_http.Rev03HttpTest.test_cadastro_direto_e_orcamento_pdf` — HTTP 400.
3. `test_rev04_operacoes.Operacoes.test_yml_relatorio_reutilizavel_em_qualquer_os` — `KeyError: v9_diagnostico`.

Os testes visuais Playwright precisam dos portais rodando em 8865/8866 e não
entram nessa contagem.

---

## 5. O que falta fazer

### Prioridade 0 — validar a escrita da OS na DEV

- O refactor de `gtk_dialogos.py`/`application/os_write.py` é **N3** (escrita de
  OS). Ele está em `develop` e **não foi promovido para a MAIN** sem revisão
  humana externa, conforme `docs/REVIEW_WITHOUT_DEVELOPER.md`.
- Testar criação, edição, materiais, pendência e encerramento na DEV.
- Registrar o resultado e decidir a promoção depois.

### Promover o fix do feedback

- Testar o prazo de recebimento no `/financeiro` da DEV.
- Se estiver correto, sincronizar `main` e a pasta MAIN.
- O feedback FB-0001 continua como “Corrigido na DEV” até a promoção.

### Prioridade 1 — validar a fatia atual com uso real

- Abrir a DEV com dados de teste.
- Conferir lista de clientes, edição de cliente, cartões do início e página do
  Portal do Cliente.
- Confirmar que `--no-web` continua abrindo sem portas.

### Prioridade 2 — completar o modo remoto

- Expor `GET /api/v1/clientes` e `GET /api/v1/clientes/{id}`.
- Expor escrita de cliente com idempotência/versão.
- Ligar `HttpService` ao mesmo contrato.
- Criar a tela de conexão local/remota no GTK.
- Testar Mac → celular na LAN e via túnel.

### Prioridade 3 — tirar o resto do SQL da UI

- OS: lista ativa, detalhe, escolha de OS.
- PJ/chamados.
- Financeiro.
- Estoque.
- Cada fatia com teste de caracterização e sem mudar comportamento.

### Prioridade 4 — controle visual do acesso web

- Preferência “Ativar acesso web”.
- Botão para ligar/parar o Portal do Prestador.
- Mostrar URL local, rede e pública no mesmo lugar.
- Não abrir dois túneis para o mesmo banco.

### Prioridade 5 — limpeza e revisão

- Onda 3: triar as **32 exceções amplas silenciosas**, P0 primeiro
  (dinheiro, OS, PDF, estoque).
- Primeiro ciclo externo de IA em `fluxo_os.py` ou `pdf_cliente_v9.py`.
- Registrar o ciclo em `docs/reviews/AAAA-MM-DD-arquivo.md`.

### Prioridade 6 — condomínios

Não implementar antes de:

- identidade e papéis;
- permissões por recurso;
- auditoria e revogação;
- consentimento e retenção/LGPD;
- exportação confiável.

O documento de visão existe, mas nada disso está autorizado ou agendado.

---

## 6. Bloqueios e riscos

- **Sem dev humano:** N3/N4 continuam exigindo revisor humano externo ou
  ficam em DEV/flag. IA revisora é evidência, não aprovação.
- **3 testes pré-existentes falhando:** não foram causados por esta fatia, mas
  precisam de issue e correção em onda separada.
- **Workflows de CI:** `.github/workflows/develop-ci.yml` e
  `.github/workflows/estabilidade-main.yml` continuam modificados e não
  commitados; a publicação depende de token GitHub com escopo `workflow`.
- **MAIN parada:** não há links públicos ativos. Não abrir sem pedido.
- **Modo remoto incompleto:** não prometer que o GTK já roda contra o celular.
- **Sem sync local-first:** um modo usa um banco só; não tentar sincronizar
  bancos agora.

---

## 7. Como retomar amanhã

```bash
cd /Users/idkosx/GestaoServicos_DEV
git status
git log --oneline -8
```

Abrir a DEV:

```bash
./INICIAR_AUTOSEG_DEV.command
```

Abrir local-only, sem portas:

```bash
./INICIAR_AUTOSEG_SEM_WEB.command
```

Rodar a suíte dirigida:

```bash
.venv/bin/python -m unittest \
  test_application_service.py test_web_access.py \
  test_integracao_clientes.py test_repositorios_ordens.py \
  test_runtime_config.py test_versionador.py
```

Rodar auditores:

```bash
.venv/bin/python scripts/audit_comments.py --strict
.venv/bin/python scripts/audit_code_rot.py
```

---

## 8. Próximas três ações recomendadas

1. **Testar a DEV com dados reais** e registrar qualquer diferença visual.
2. **Expor clientes no `/api/v1` e ligar o `HttpService`** — primeira prova
   real de que o mesmo contrato funciona local e remoto.
3. **Escolher uma fatia P0 de limpeza** (encerramento de OS + rateio) ou
   iniciar o primeiro ciclo de revisão externa.

Não começar por reescrita, troca de linguagem, ORM ou “limpeza geral”.
