# P0-AUTH-FINAL — fechar a revalidação transacional e o TOCTOU

**Status:** próximo passe; o P0-AUTH parcial **não está aprovado como gate
fechado**.
**Base:** branch `feat/p0-auth-partial` (commit `3ec9dc8` + este prompt).
**Não integrar na `main`.** A MAIN segue rodando; o trabalho é DEV/branch.
**Uso:** colar no ChatGPT. Trabalha sobre a branch/ZIP, não faz commit/push.

## 1. Estado aceito da entrega parcial

O subconjunto anterior foi revisado e passou:

- suíte completa: **673 testes, 0 falhas, 1 skip**;
- foco P0-AUTH: 84 OK;
- reabertura de OS `Pendente`: não-admin recebe 403, sem mutação, flags 0/1;
- admin reabre;
- `work_item.reopen` na política;
- guardas transacionais em reabertura, atribuição, assunção, arquivamento,
  rota, cancelamento e fotos;
- testes de corrida determinísticos;
- `py_compile`, audit e diff check limpos.

**Preserve tudo isso.** O que falta é o restante do gate, documentado no
`BLOCKED.md` da entrega parcial.

## 2. Objetivo

Fechar o TOCTOU de autorização × writer para os comandos de OS que ainda fazem
múltiplas transações ou efeitos externos, sem criar um segundo caminho de
autorização e sem esconder risco residual.

Critério de saída:

- nenhuma escrita parcial quando status, responsável, participante, cliente,
  vínculo ou papel mudarem entre a autorização inicial e o writer;
- todos os efeitos de banco do comando na mesma transação, incluindo eventos e
  auditoria;
- efeitos externos (PDF, arquivo, e-mail) só depois do commit e de forma
  idempotente/recuperável;
- testes de corrida para todos os writers cobertos;
- suíte completa sem novas falhas;
- flag `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` continua **0** por padrão e não é
  ativada em produção nesta peça.

## 3. Correções obrigatórias

### 3.1 Contexto de transação único

- Refatore os writers para receber a **mesma** conexão SQLite/transação
  `BEGIN IMMEDIATE`; não abrir `ext.db`/`BEGIN` dentro do writer chamado por
  `os_commands.execute_http`.
- Eventos, auditoria, status, cliente, atendimento, rota, rateio,
  participantes e anexos devem participar da mesma unidade de trabalho.
- A revalidação deve ocorrer **antes de qualquer mutação**, com a conexão da
  transação; use `require_work_item_locked`/um helper único, não uma segunda
  matriz de permissões.
- O core não pode importar o flavor/AUTOSEG nem a política da aplicação;
  manter o padrão de callback/contrato já usado.

### 3.2 Writers multi-transação

Cobrir, no mínimo:

- **`iniciar`**: `_persist_form_client`, `atendimento_os.iniciar_assumindo`,
  `ext.assumir`, início e `prod.limpar_rota_ao_iniciar` na mesma transação.
- **`salvar`/`concluir`/`cancelar`**: `ext.salvar_rascunho_web`,
  `neg.os_salvar`, `cad9.salvar_detalhes`, fluxo de relatório/nota e eventos na
  mesma transação; PDF/e-mail depois do commit.
- **`publicar`**: separar commit de banco da publicação de arquivo; a
  publicação deve ser idempotente e recuperável. Falha de arquivo não pode
  deixar o banco “meio publicado”.
- **`em-rota`**: mover `_persist_form_client` para dentro da transação do
  writer; hoje ele pode gravar cliente antes da decisão final.
- **anexos, nota fiscal, rateio, rascunhos, importação YAML**: revisar writers
  e operações de arquivo; se algum não puder entrar nesta peça, listar no
  `BLOCKED.md` com teste e impacto.
- **reabertura com cliente provisório**: resolver a mudança de comportamento.
  Preferência: criar o provisório por um serviço que use a conexão recebida.
  Se o produto decidir exigir cliente já cadastrado, documentar e atualizar a
  UI; não manter a diferença silenciosa.

### 3.3 Papel/ativação da conta

- Se a conta/role/ativação puder mudar entre a montagem do `Principal` e a
  transação, revalidar também esse estado na mesma unidade de trabalho, ou
  documentar explicitamente o que fica fora da garantia.
- Não promover papel antigo; fail-closed.

### 3.4 Schema

- Preferir **não** alterar schema nesta peça.
- Se um outbox/tabela de idempotência for realmente indispensável, **pare** e
  devolva `BLOCKED.md` com a migração proposta; não adicione schema sem
  autorização.

## 4. Testes obrigatórios

- Corrida determinística para cada writer coberto: após a pré-autorização e
  antes do writer, altere em outra conexão status, responsável, participante,
  cliente, vínculo ou papel; a escrita deve ser negada e nenhuma tabela/arquivo
  relacionado pode mudar.
- Testar flags `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0` e `=1`.
- Testar admin × employee, responsável × participante, OS ativa × arquivada.
- Testar falha de publicação/arquivo após commit: estado recuperável,
  idempotência e nenhuma duplicação.
- Testar o cliente provisório na reabertura (positivo e negativo).
- Não enfraquecer, remover ou pular teste para passar.
- Suíte completa com diretórios temporários; o alvo é manter **673+ testes,
  0 falhas, 1 skip** e adicionar os novos casos.

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  tests.test_numero_publico tests.test_p0_auth_gate tests.test_os_commands \
  tests.test_object_policy tests.test_object_permissions \
  tests.test_client_roles tests.test_client_roles_http \
  tests.test_officina_web tests.test_rev12_correcoes \
  tests.test_admin_parity -v
```

```bash
TMP=$(mktemp -d)
AUTOSEG_DEV=1 AUTOSEG_SERVER_DATA="$TMP" AUTOSEG_USER_DATA="$TMP" \
AUTOSEG_LOCAL_DATA="$TMP" PYTHONPATH=.:tests \
python3 -m unittest discover -s tests -p 'test_*.py'
```

Qualidade:

```bash
python3 -m py_compile flavors/autoseg/modules/os_commands.py \
  officina/application/work_item_access.py \
  officina/core/prestadores_ext.py officina/core/produtividade_os.py
python3 scripts/audit_comments.py --strict
git diff --check
```

## 5. Documentação e flags

- Atualizar `docs/operations/OBJECT_POLICY_ROLLOUT.md` com o que foi fechado e
  o que resta fora da garantia.
- Atualizar `docs/HANDOFF.md`, `docs/PLATFORM_MIGRATION_LEDGER.md`,
  `docs/ROADMAP.md`, `CHANGELOG.md` e `TESTES.md`.
- Manter `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`; não ativar em produção.
- Não tocar em `AUTOSEG_WEB_SESSION_DURABLE`, GTK, portal unificado, cliente,
  financeiro, dados reais ou MAIN.

## 6. Proibido

- Recriar servidor/portal legado, shim, flag ou caminho paralelo.
- Autorizar no handler e escrever em outra transação.
- Lock em processo como substituto de transação única.
- Efeito externo antes do commit ou sem idempotência.
- Novo `if admin` fora da política/serviço.
- Alterar schema sem autorização.
- Tocar na MAIN, portas 8765/8766, dados reais, GTK ou produção.
- Commit/push.

## 7. Entrega

ZIP com:

- `changed-files/` completos;
- patch cumulativo contra a branch/commit base;
- `CHANGED_FILES.txt`;
- `TEST_RESULTS.txt` com focado, regressão e suíte completa;
- `NOTES.md` com:
  - mapa writer → transação → efeitos externos;
  - o que passou a ser atômico e o que ainda é residual;
  - decisão do cliente provisório;
  - evidência dos testes de corrida;
- `BLOCKED.md` se houver bloqueio real.

Sem `.git`, banco, anexos, PDFs de produção, logs, tokens ou credenciais.
Nenhum commit/push.

## 8. Autorização de schema — outbox de efeitos externos

**Autorizado em 2026-11-11 para DEV/branch, não para produção.**

Sim, autorizo uma migração **aditiva e idempotente** em SQLite para uma outbox
transacional dos efeitos externos da OS, limitada a esta peça.

Condições obrigatórias:

- criar apenas a tabela nova `os_effect_outbox` e índices; **não** alterar
  tabelas existentes, colunas, dados, triggers ou semântica de OS;
- migração idempotente (`CREATE TABLE IF NOT EXISTS`/versão registrada), com
  backup verificado e rollback documentado (drenar/cancelar pendentes e então
  remover a tabela, ou mantê-la dormente);
- `operation_key` determinística e única por comando/revisão/ação;
- estados explícitos `pending/processing/done/failed/unknown`, lease
  `claimed_at`, tentativas, `last_error` e resultado mínimo;
- a intenção é gravada na **mesma transação `BEGIN IMMEDIATE`** da mutação de
  OS, status, vínculo, eventos e auditoria; o efeito externo só executa depois
  do commit;
- worker/reconciliador após restart recupera `processing` vencido, respeita
  lease e não duplica efeitos;
- payload mínimo: IDs, hashes, tipo e referência da operação; **sem** corpo de
  e-mail, anexos, credenciais, tokens ou PII desnecessária. Destinatários são
  resolvidos no momento da execução a partir do banco;
- PDF/arquivo: staging + hash + versão reservada na transação; publicação
  idempotente por `operation_key`/hash; arquivo órfão detectável e reconciliável;
- nenhuma publicação/entrega confirma no banco antes de existir a intenção
  persistida.

### Política de e-mail

Não prometer exactly-once com SQLite + provedor externo. A regra é:

1. se o provedor suportar idempotency key/message id, use-o e registre o
   identificador;
2. se o resultado do envio for **incerto** (queda após enviar e antes do ACK),
   marcar `unknown` e **não reenviar automaticamente**; exigir reconciliação
   manual/consulta ao provedor e registrar auditoria;
3. reenvio manual é permitido com `operation_key` novo e aviso explícito de
   possível duplicata;
4. falha comprovada antes do envio pode ser retentada.

Esse limite deve aparecer no `NOTES.md` e na UI/operação, sem esconder que a
garantia é at-most-once para resultado incerto.

### Testes da outbox

- commit da intenção + execução; queda entre commit e efeito; reinício;
- dois workers concorrentes com o mesmo `operation_key`;
- falha de arquivo/PDF/e-mail antes/depois do efeito;
- reexecução sem duplicar versão/arquivo/entrega;
- mudança de vínculo/status entre pré-autorização e transação: nenhuma
  intenção/escrita;
- rollback/downgrade da tabela sem afetar OS existentes.

Se a implementação concluir que a outbox não é suficiente para alguma garantia,
não invente exactly-once: registre o limite no `BLOCKED.md` e mantenha a flag
desligada.
