# P0-AUTH-CLOSE-GATE — B6, B7, integridade do PDF e dispatcher

**Status:** próximo passe; o P0-AUTH ainda **não é um gate fechado**.
**Base:** branch `feat/p0-auth-outbox`, commit `3a3cbb0`.
**Não integrar na `main`.** A MAIN continua rodando; o trabalho é DEV/branch.
**Uso:** colar no ChatGPT. Trabalha sobre a branch/ZIP, não faz commit/push.

## 1. Estado aceito

O passe anterior foi revisado e passou:

- suíte completa: **694 testes, 0 falhas, 1 skip**;
- outbox `os_effect_outbox` aditiva, com lease, claim, restart e reconciliação;
- PDF/arquivo com staging, hash e publicação idempotente no caminho migrado;
- e-mail com `unknown` e sem reenvio automático após resultado incerto;
- writers de OS cobertos na entrega anterior com `BEGIN IMMEDIATE` único;
- testes de corrida determinísticos em `tests/test_p0_auth_final_races.py`;
- `py_compile`, `audit_comments --strict` e `git diff --check` limpos.

**Preserve tudo isso.** O que falta está no `BLOCKED.md` do passe anterior:

- **B6:** `mover/remover/girar/publicar` anexo e `nota-fiscal/remover` ainda
  usam transações/filesystem fora do contrato único;
- **B7:** falta UI de reenvio manual com `confirmar_duplicata`,
  `reenviar_operacao` e preservação dos destinatários sem PII no payload;
- projeções `produtividade_email`/`os_entregas` não são atualizadas pelo
  caminho da outbox;
- `publish_pdf` pode aceitar um PDF órfão já existente no caminho
  determinístico;
- não há dispatcher/observabilidade para pendências após restart;
- a flag `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` continua **0**.

## 2. Objetivo e critério de saída

Fechar os quatro blocos abaixo **sem** ativar a flag, **sem** migrar a MAIN e
**sem** criar um segundo caminho de autorização.

Critério de saída:

- B6: as cinco operações de anexo/nota fiscal usam a mesma conexão
  `BEGIN IMMEDIATE` do dispatcher, revalidam vínculo/status/papel antes de
  qualquer mutação e não deixam arquivo órfão ou metadado divergente em
  rollback/crash;
- B7: o operador consegue reenviar e-mail com confirmação explícita de
  duplicata e chave única; a seleção de destinatários é preservada por
  IDs/referências; `produtividade_email` e `os_entregas` refletem
  `enviado`/`falhou`/`unknown`/`sem_destinatario`;
- PDF: PDF órfão ou divergente no caminho determinístico é rejeitado ou
  reconciliado por geração + comparação de hash, nunca adotado às cegas;
- dispatcher: worker/CLI recupera `processing` vencido, lista
  `pending`/`failed`/`unknown`, não reenvia `unknown` automaticamente e
  permite rollback DEV sem tocar nas OS;
- suíte completa verde, sem novos skips;
- flag continua **0** por padrão.

## 3. B6 — anexos e nota fiscal

### 3.1 Contrato único de transação

Refatore os writers abaixo para receber a **mesma** conexão SQLite já em
`BEGIN IMMEDIATE` pelo dispatcher:

- `_write_move_attachment` (`/os/<id>/anexo/<aid>/mover`);
- `_write_remove_attachment` (`/os/<id>/anexo/<aid>/remover`);
- `_write_rotate_attachment` (`/os/<id>/anexo/<aid>/girar`);
- `_write_publish_attachment` (`/os/<id>/anexo/<aid>/publico`);
- `_write_remove_invoice` (`/os/<id>/nota-fiscal/<nid>/remover`).

Em `flavors/autoseg/modules/os_commands.py` e nos serviços de
`officina/core/prestadores_ext.py`:

- `mover_anexo`, `remover_anexo`, `girar_imagem` e `remover_nota_fiscal`
  precisam aceitar `connection=` (ou um helper equivalente) e **não** abrir
  `ext.db`/`BEGIN` quando chamados pelo writer;
- a revalidação de `work_item` deve usar o mesmo helper
  `_transaction_guard(..., 'attach')` já usado no caminho de fotos/nota;
- revalidar na mesma conexão, antes de qualquer mutação: OS existe, status
  permite a operação, OS não está arquivada, anexo/nota pertence à OS,
  prestador ativo, responsável atual ou admin;
- eventos e auditoria entram na mesma transação;
- não duplicar a matriz de permissões dentro do serviço e do handler; o core
  não pode importar o flavor/AUTOSEG.

`_write_publish_attachment` hoje faz uma checagem em uma conexão e a escrita
em outra; `_write_rotate_attachment` faz pré-checagem fora e o serviço abre
outra transação; `_write_remove_invoice` idem. Isso precisa virar uma única
unidade de trabalho.

### 3.2 Operações e efeitos de arquivo

| Operação | Mutação de banco | Efeito de arquivo | Regra |
|---|---|---|---|
| mover | ordem + evento | nenhum | mesma transação; rollback não move nada |
| publicar/ocultar | `v9_anexos_visiveis` + evento | nenhum | mesma transação |
| girar | `os_anexos.sha256` + evento | novo conteúdo da imagem | staging + promoção pós-commit |
| remover anexo | `DELETE` + evento | quarentena/remoção | nada é apagado antes do commit |
| remover nota | `DELETE` + evento | quarentena/remoção | nada é apagado antes do commit |

Regras de arquivo:

- **girar:** escreva o novo conteúdo em staging privado dentro da raiz
  gerenciada (`ANEXOS/.outbox-staging/<operation_key>`), atualize o hash na
  transação e só promova depois do commit. A promoção pode substituir o
  arquivo antigo de forma atômica; se o processo cair entre commit e
  promoção, o staging + hash no banco permitem recuperar. Rollback deixa o
  arquivo antigo intacto e o staging é limpo como órfão.
- **remover:** renomeie o arquivo para quarentena determinística
  (`ANEXOS/.outbox-trash/<operation_key>` ou equivalente) **antes** do
  commit, com restauração no `except`/rollback. Depois do commit, a remoção
  definitiva é best-effort e idempotente; se cair antes do commit, a linha
  ainda existe e a quarentena é restaurável; se cair depois, a linha não
  existe e a quarentena é lixo seguro para limpeza.
- **nunca** aceitar caminho vindo do payload da outbox; derive o caminho da
  linha e confirme que ele está dentro da raiz gerenciada.
- não apagar arquivo de OS encerrada/arquivada fora das regras atuais.

Quando houver intenção de arquivo, registre-a na `os_effect_outbox` na mesma
transação, com payload mínimo (`source_id`, `source_sha256`, `reason_code`).
Para remoção, a intenção pode ser o próprio registro de quarentena
determinístico; se usar a outbox, o `publish_file` precisa de um caminho
explícito para `attachment-remove`, sem consultar uma linha já deletada.

### 3.3 Testes B6

- rollback em cada operação: nenhuma linha/evento/arquivo muda;
- crash entre commit e promoção/remoção: recuperação idempotente, sem
  duplicar arquivo nem perder o original;
- arquivo órfão em staging/quarentena: limpeza não remove arquivo de
  operação ainda pendente;
- corrida: após o preflight e antes do writer, altere status, responsável,
  vínculo, arquivada ou papel em outra conexão; a operação deve ser negada e
  nada pode mudar;
- admin × employee, OS ativa × encerrada × arquivada, anexo de outra OS;
- flags `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0` e `=1`;
- rota HTTP real (`tests/test_os_commands.py` e `tests/test_rev12_correcoes.py`),
  não só o serviço.

## 4. B7 — e-mail, interface e projeções

### 4.1 Reenvio manual

No formulário de `flavors/autoseg/modules/portal_prestador.py` (próximo de
`/reenviar-email`):

- adicionar `reenviar_operacao` como campo oculto, gerado no render com
  `secrets.token_urlsafe(...)`, 12–80 caracteres `[A-Za-z0-9_-]`;
- adicionar `confirmar_duplicata` como checkbox com texto explícito:
  “O e-mail anterior pode já ter sido entregue; reenviar pode duplicar”;
- o POST sem confirmação ou sem chave válida deve ser rejeitado antes de
  qualquer enfileiramento;
- reenviar o mesmo formulário (mesma chave) não pode disparar duas vezes;
  um novo render após `unknown` gera uma chave nova;
- exibir estado atual (`pendente`, `enviado`, `falhou`, `unknown`,
  `sem_destinatario`), tentativas, último erro e o `Message-ID` quando
  existir;
- para `unknown`, mostrar aviso de resultado incerto, instrução de conferir
  no provedor e **não** oferecer reenvio automático.

### 4.2 Destinatários sem PII no payload

- preservar a seleção por referências estáveis: `cliente`, `sindico`,
  `administradora`, `contato:<id>` ou IDs equivalentes;
- o payload da outbox não pode conter endereços de e-mail, corpo, anexos,
  tokens ou credenciais;
- destinatários adicionais digitados pelo operador devem ficar na projeção
  `produtividade_email.destinatarios_json` (tabela de domínio existente) ou
  ser rejeitados no modo outbox; nunca no `payload_json`;
- o dispatcher resolve as referências no momento da execução a partir do
  banco; se um contato foi removido, falhe antes do envio com
  `PreDispatchError`, não envie para um endereço antigo;
- a seleção precisa sobreviver ao commit e a um restart do worker.

### 4.3 Projeções `produtividade_email` e `os_entregas`

Hoje o caminho da outbox chama `deliver_email` e **não** atualiza
`produtividade_email`; `os_entregas` pode ficar em `aguardando_api`. Corrija
com uma finalização atômica:

- `done` → `produtividade_email.status='enviado'`, `message_id`, erro vazio;
  `os_entregas.email_status='enviado'`;
- `unknown` → `produtividade_email.status='unknown'`, erro com código
  estável; `os_entregas.email_status='unknown'`;
- `failed` antes do envio → `produtividade_email.status='falhou'`, erro;
  `os_entregas.email_status='falhou'`;
- `sem_destinatario` → `produtividade_email.status='sem_destinatario'`,
  `os_entregas.email_status='sem_destinatario'`; **nunca** deixar
  `aguardando_api`;
- a atualização da outbox (`done`/`unknown`/`failed`) e as duas projeções
  devem ocorrer na mesma transação `BEGIN IMMEDIATE`;
- não sobrescrever `os_entregas.destinatario` com string vazia, não criar
  segunda linha de entrega e não criar novo `os_documentos` no reenvio
  manual (reutilize o último PDF publicado).

`produtividade_email.status` é texto livre; não altere schema. Atualize a UI
e os testes para o vocabulário novo de forma retrocompatível.

### 4.4 Política de e-mail

- `PreDispatchError` só pode ser lançado **antes** da chamada ao provedor;
- depois de entrar no provedor, qualquer exceção/queda vira `unknown`, sem
  retry automático;
- `Message-ID` não é idempotency key garantida; não prometa exactly-once;
- `pending` nunca enviado pode ser despachado; `processing` com lease
  vencido vira `unknown`, não é reenviado automaticamente;
- reenvio manual exige chave nova e confirmação explícita.

### 4.5 Testes B7

- formulário renderiza os dois campos e o POST sem eles falha sem enfileirar;
- mesma chave não duplica; chave nova enfileira uma nova operação;
- seleção de destinatários sobrevive ao commit/restart e resolve por ID;
- contato removido entre commit e dispatch → `failed` antes do provedor,
  sem envio;
- `done`/`unknown`/`failed`/`sem_destinatario` atualizam as duas projeções na
  mesma transação (teste de falha injetada no meio);
- `sem_destinatario` não deixa `aguardando_api`;
- `unknown` não é reenviado pelo dispatcher;
- UI mostra `unknown` e não oferece reenvio automático.

## 5. Integridade do PDF

`publish_pdf` não pode adotar um arquivo que já esteja no caminho
determinístico sem provar que ele corresponde ao conteúdo esperado.

Implemente uma destas opções (preferência pela primeira):

1. **geração + comparação obrigatória:** sempre gere o candidato em staging
   privado e compare o hash com o `target` existente; se forem iguais,
   trate como recuperação de crash; se forem diferentes, falhe com erro
   explícito (`OrphanPDF`/`PDFConflict`), não sobrescreva e deixe para
   reconciliação manual;
2. **hash esperado na intenção:** grave `expected_sha256` no payload mínimo
   (campo permitido, sem PII) e só reuse o `target` se o hash bater.

Regras:

- se existir linha em `os_documentos` para `(os_id, tipo, versao)`, ela deve
  bater caminho **e** hash; senão é conflito;
- se não existir linha e o `target` existir, só adote após comparação com o
  candidato gerado; nunca apague/sobrescreva um PDF publicado;
- `after_publish` só roda depois de `done` no banco;
- falha de geração/validação antes do efeito marca `failed`; queda depois do
  link atômico é recuperável pelo caminho determinístico + hash;
- não crie versão nova no retry; a `version_reserved` é a mesma.

Testes:

- PDF órfão válido no caminho determinístico → rejeitado ou reconciliado por
  hash, nunca adotado às cegas;
- PDF errado/truncado no caminho → falha sem sobrescrever;
- crash após `os.link` e antes da linha em `os_documentos` → retry compara e
  conclui sem duplicar versão;
- duas execuções concorrentes da mesma operação → uma publica, a outra
  retorna `done`/lease, sem duplicar;
- status da OS muda para não publicável entre claim e publicação → `failed`,
  sem arquivo novo.

## 6. Dispatcher, observabilidade e rollback DEV

Crie `scripts/autoseg/dispatch_os_effect_outbox.py` (ou amplie o
`reconcile_os_effect_outbox.py` existente) com:

- `--status` e `--json`: contagens por estado/tipo, mais antigo pendente,
  tentativas, último erro; **sem PII**;
- `--once --limit N`: processa `pending` e `processing` com lease vencido;
  PDF/arquivo podem ser reprocessados; e-mail `pending` nunca reivindicado
  pode ser enviado; `processing` de e-mail vencido vira `unknown`;
- `--reconcile`: recupera PDF/arquivo pendente após restart;
- `--cleanup-stages` e `--cleanup-trash`: removem apenas órfãos antigos sem
  intenção pendente;
- `--dry-run`: não executa efeito nem muda estado;
- código de saída estável para automação e log estruturado com
  `operation_key`, tipo, ação, estado, tentativas e código de erro.

Não reenvie `unknown` automaticamente. Não faça o dispatcher apagar arquivo
de OS que ainda existe.

Rollback DEV em `scripts/autoseg/install_os_effect_outbox.py`:

- `--status` para inspecionar a tabela;
- `--rollback` recusa se houver `pending`/`processing`/`unknown` sem
  tratamento; exige drenar/cancelar/exportar antes;
- remove apenas `os_effect_outbox` e índices; não toca em OS, anexos, notas,
  PDFs ou outras tabelas;
- backup verificado antes de instalar/remover, como já existe;
- teste em banco temporário: instalar, criar operação, rollback recusado,
  drenar, rollback aceito, OS intacta.

## 7. Documentação

Atualizar:

- `docs/operations/OBJECT_POLICY_ROLLOUT.md` — o que foi fechado, o que
  permanece residual, política de `unknown`, garantia at-most-once;
- `docs/HANDOFF.md`, `docs/PLATFORM_MIGRATION_LEDGER.md`, `docs/ROADMAP.md`,
  `CHANGELOG.md`, `TESTES.md`;
- `BLOCKED.md` — esvaziar os itens resolvidos e manter apenas bloqueios
  reais, com teste e impacto;
- `NOTES.md` do ZIP — mapa writer → transação → efeito, decisões de
  staging/quarentena, hash do PDF, projeções de e-mail e limites.

## 8. Proibido

- Tocar na `main`, portas 8765/8766, dados reais, produção, GTK ou portal
  legado.
- Ativar `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` ou migrar fora de DEV.
- Criar tabela/coluna nova sem autorização; o schema existente da outbox
  deve bastar.
- Recriar shim, fallback, flag ou segundo caminho de autorização.
- Efeito externo antes do commit ou sem idempotência/recuperação.
- Apagar arquivo antes do commit sem quarentena restaurável.
- Colocar e-mail, corpo, anexo, token ou credencial no payload da outbox.
- Reenviar e-mail `unknown` automaticamente ou prometer exactly-once.
- Enfraquecer, remover ou pular teste para passar.
- Commit/push.

## 9. Entrega

ZIP com:

- `changed-files/` completos;
- `p0-auth-close-gate.patch` cumulativo contra `3a3cbb0`;
- `CHANGED_FILES.txt`;
- `TEST_RESULTS.txt` com focado, regressão e suíte completa;
- `NOTES.md` com o mapa de atomicidade, decisões de arquivo/PDF/e-mail e
  evidência dos testes de corrida/restart;
- `BLOCKED.md` se houver bloqueio real.

Sem `.git`, banco, anexos, PDFs de produção, logs, tokens ou credenciais.
Nenhum commit/push.

## 10. Comandos de teste

Focado:

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  tests.test_os_effect_outbox tests.test_os_effect_outbox_files \
  tests.test_p0_auth_final_races tests.test_os_commands \
  tests.test_rev12_correcoes tests.test_gmail_integracao \
  tests.test_numero_publico tests.test_p0_auth_gate \
  tests.test_object_policy tests.test_object_permissions \
  tests.test_client_roles tests.test_client_roles_http \
  tests.test_officina_web tests.test_admin_parity -v
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
python3 -m py_compile flavors/autoseg/modules/os_commands.py \
  flavors/autoseg/modules/portal_prestador.py \
  flavors/autoseg/modules/gmail_service.py \
  officina/core/prestadores_ext.py officina/core/os_effect_outbox.py \
  officina/core/produtividade_os.py officina/core/fluxo_os.py \
  scripts/autoseg/dispatch_os_effect_outbox.py
python3 scripts/audit_comments.py --strict
git diff --check
```

## 11. Checklist de aceite

- [ ] B6: cinco rotas com transação única, revalidação e eventos juntos.
- [ ] B6: girar/remover com staging/quarentena e recuperação após crash.
- [ ] B6: testes de rollback, órfão, corrida, admin × employee, flags 0/1.
- [ ] B7: UI com `confirmar_duplicata` e `reenviar_operacao` única.
- [ ] B7: destinatários por referência, sem PII no payload.
- [ ] B7: `produtividade_email`/`os_entregas` atômicos em
      `done`/`unknown`/`failed`/`sem_destinatario`.
- [ ] B7: `unknown` não reenviado automaticamente; UI explica.
- [ ] PDF: órfão/divergente rejeitado; crash após link recuperável.
- [ ] Dispatcher: status/once/reconcile/cleanup; `unknown` preservado.
- [ ] Rollback DEV recusa pendências e não toca em OS.
- [ ] Documentação atualizada; `BLOCKED.md` só com bloqueio real.
- [ ] Suíte completa verde, sem novos skips.
- [ ] `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`; MAIN intocada.
