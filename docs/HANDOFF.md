# Handoff — estado atual do projeto

**Última atualização:** 2026-11-06
**Versão:** `9.6.0-dev.39`
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

### Comportamento preservado

- O padrão continua com os portais ligados.
- `--no-web`/`AUTOSEG_WEB_ACCESS=0` continua abrindo o modo local-only.
- Telas, rótulos, filtros, cálculos e HTML dos portais não mudaram.
- Escritas de cliente continuam last-write-wins no caminho legado.

---

## 2. Onde o código está

| Área | Estado | Observação |
|---|---|---|
| GTK → `AppService` | **parcial** | Clientes, painel e Portal do Cliente usam `LocalService`. |
| Portais HTTP | **fora do GTK** | `WebAccessManager` inicia/para; HTML e rotas não mudaram. |
| Modo remoto | **só health** | `HttpService` não lista/salva clientes ainda. |
| OS / PJ / financeiro / estoque | **legado** | SQL direto no GTK e regras nos módulos atuais. |
| Portal do Prestador | **legado** | Ainda chama `integracao/clientes.py` diretamente. |
| Condomínios | **visão documentada** | Sem identidade, permissões, auditoria ou LGPD implementados. |
| MAIN | **não sincronizada** | Código novo está em `develop`; MAIN segue no estado anterior. |
| Túneis/servidor MAIN | **parados** | Links antigos não funcionam. |

---

## 3. Commits desta sessão

```text
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
