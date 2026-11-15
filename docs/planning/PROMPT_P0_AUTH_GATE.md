# P0-AUTH — Fechar o gate de autorização por objeto

**Status:** próximo passe; não implementado.
**Base:** branch `feat/portal-unification-p0` / ZIP `autoseg-p0-auth-<commit>.zip`.
**Não integrar na `main`**: a MAIN segue rodando; este trabalho é DEV/branch.
**Uso:** colar no ChatGPT. Trabalha sobre o ZIP, não faz commit/push e devolve
ZIP.

## 1. Objetivo

Fechar o gate P0 de autorização por objeto, começando pela falha real já
existente e pelo TOCTOU entre a autorização e o writer.

Critério de saída:

1. `test_non_admin_cannot_reopen_pending_os` passa **sem ser enfraquecido**.
2. Um não-admin não reabre OS `Pendente`; admin reabre.
3. A decisão vale com `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0` e `=1`.
4. Autorização e escrita não podem divergir por mudança de vínculo/estado
   entre a leitura e a transação.
5. Nenhuma mutação ocorre quando a decisão é negativa.
6. A suíte completa não ganha novas falhas/erros.

## 2. Estado atual e evidência

- A suíte completa atual tem 667 testes: 665 OK, 1 skip e 1 falha
  **pré-existente**:
  `tests.test_numero_publico.NumeroPublicoTest.test_non_admin_cannot_reopen_pending_os`.
- O teste espera `403` em `POST /os/<id>/abrir` para não-admin; hoje a
  requisição não levanta `HTTPError` e a OS pode mudar para `Aberta`.
- A UI esconde `Aberta`/`Pendente` no popup para não-admin, mas o servidor não
  aplica a mesma negativa.
- `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` está desligada por padrão. Com a flag
  desligada, `os_commands._authorize()` retorna sem checar; é por isso que a
  negativa não acontece.
- O TOCTOU está documentado em `docs/operations/OBJECT_POLICY_ROLLOUT.md`:
  a autorização lê `os_responsaveis`/`os_prestadores` antes de o writer abrir
  sua própria transação SQLite. O lock em processo não cobre outro processo.

## 3. Correção 1 — reabrir OS pendente

Requisitos:

- `POST /os/<id>/abrir` por não-admin em OS `Pendente` deve retornar `403`,
  sem alterar status, atendimento, deslocamento, cliente ou eventos.
- Admin pode reabrir; a regra e a UI devem concordar.
- A negativa deve valer com a flag de object policy **0 e 1**. Não basta
  habilitar a flag no teste.
- Não criar `if admin` solto no handler. Modele a permissão:
  - adicionar `work_item.reopen` (ou equivalente) à matriz `policy.yaml`,
    concedida ao admin e não ao employee comum; **e**
  - garantir que o caminho legado (flag 0) também aplique essa negativa, via
    serviço/regra de domínio, sem duplicar a decisão em dois lugares.
- Se a arquitetura atual não permitir a regra única, pare e explique; não
  invente uma segunda autorização.
- Não alterar o teste para esperar `200`/`409`; o contrato é `403` e nenhuma
  mutação.
- Cobrir:
  - não-admin + `Pendente` → 403, status inalterado;
  - admin + `Pendente` → 200/redirect e status `Aberta`;
  - não-admin + `Aberta` (ou status que já permite) não sofre regressão;
  - flags 0 e 1, com banco temporário.

## 4. Correção 2 — TOCTOU autorização × writer

O problema: `execute_http()` autoriza com um snapshot e chama o writer, que
abre outra transação. Entre os dois, outro processo pode remover o vínculo,
mudar o responsável, arquivar a OS ou alterar o status.

Requisitos:

- Revalidar, **dentro da mesma transação `BEGIN IMMEDIATE` do writer**, antes
  de qualquer mutação:
  - status/arquivamento atual da OS;
  - relação atual do principal com a OS (responsável/participante) para a ação;
  - vínculo/tenant quando a ação depender dele.
- Se a relação mudou ou o estado não permite mais a ação: abortar com
  `403`/`409`, sem escrita parcial.
- Aplicar aos writers de maior risco:
  - `abrir`, `iniciar`, `cancelar`, `salvar` (incluindo concluir/cancelar),
    `publicar`, `atribuir`, `arquivar`, `rota`/`em-rota`, `assumir`;
  - anexos/nota fiscal/rateio quando houver decisão de objeto.
- Não basta manter o lock em processo; ele não cobre outro processo.
- Não criar uma segunda cópia da regra `work_item_access`. Extraia um helper
  único de revalidação transacional e use-o nos writers.
- Teste de corrida: após a autorização e antes do writer, altere o vínculo/
  responsável/status em outra conexão; a escrita deve ser negada e o banco
  deve permanecer consistente. Use um hook/mock determinístico, sem depender
  de timing.
- Documentar o que continua fora de garantia, se algo continuar; mas o alvo é
  remover a janela para as ações cobertas.

Se a correção integral não couber sem refatorar o writer de forma insegura,
entregue o subconjunto seguro e devolva `BLOCKED.md` com o restante; não declare
o TOCTOU fechado.

## 5. Flags e produção

- `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` continua **desligada por padrão**.
- Não ativar em produção nesta peça.
- O objetivo é deixar o código e os testes prontos para a decisão de ativação.
- Não tocar em `AUTOSEG_WEB_SESSION_DURABLE`, GTK, portal unificado, cliente,
  financeiro, schema ou dados.

## 6. Testes obrigatórios

Rodar com banco e portas temporárias; nunca MAIN/8765/8766.

Focado:

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  tests.test_numero_publico \
  tests.test_os_commands \
  tests.test_object_policy \
  tests.test_object_permissions \
  tests.test_client_roles \
  tests.test_client_roles_http \
  tests.test_officina_web \
  tests.test_rev12_correcoes \
  tests.test_admin_parity -v
```

Suíte completa:

```bash
TMP=$(mktemp -d)
AUTOSEG_DEV=1 AUTOSEG_SERVER_DATA="$TMP" AUTOSEG_USER_DATA="$TMP" \
AUTOSEG_LOCAL_DATA="$TMP" PYTHONPATH=.:tests \
python3 -m unittest discover -s tests -p 'test_*.py'
```

Qualidade:

```bash
python3 -m py_compile flavors/autoseg/modules/os_commands.py
python3 scripts/audit_comments.py --strict
git diff --check
```

Critérios:

- `test_non_admin_cannot_reopen_pending_os` verde;
- nenhuma falha/erro novo na suíte completa;
- testes de corrida determinísticos;
- nenhum teste enfraquecido, skip novo ou asserção removida para passar.

## 7. Documentação

Atualizar:

- `docs/operations/OBJECT_POLICY_ROLLOUT.md` — decisão de reabertura, estado
  do TOCTOU e o que ainda é risco residual;
- `docs/PLATFORM_MIGRATION_LEDGER.md` e `docs/HANDOFF.md` — estado do gate;
- `CHANGELOG.md` — mudança de comportamento;
- `TESTES.md` — novos testes e estado da suíte;
- `docs/ROADMAP.md` — somente o status do gate, se mudar.

Não reescrever `docs/archive/`.

## 8. Proibido

- Enfraquecer `test_non_admin_cannot_reopen_pending_os` ou removê-lo.
- Criar flag/shim para manter a reabertura indevida.
- Novo `if admin` fora da política/serviço.
- Autorizar no handler e escrever sem revalidar no writer.
- Tocar na MAIN, portas 8765/8766, dados reais, GTK, portal unificado,
  cliente GTK, financeiro ou schema.
- Ativar a flag em produção.
- Commit/push.

## 9. Entrega

ZIP com:

- `changed-files/` completos;
- patch cumulativo contra o ZIP base;
- `CHANGED_FILES.txt`;
- `TEST_RESULTS.txt` com focado, regressão e suíte completa;
- `NOTES.md` com:
  - desenho da regra de reabertura (onde vive, flags 0/1);
  - quais writers revalidam dentro da transação e o que resta fora;
  - evidência do teste de corrida;
- `BLOCKED.md`, se houver bloqueio.

Sem `.git`, banco, anexos, PDFs de produção, logs, tokens ou credenciais.
Nenhum commit/push.
