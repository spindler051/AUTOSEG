# P0-AUTH-CLOSE-GATE-FIXES — corrigir o B6 encerrado, o TOCTOU do PDF e o rollback

**Status:** próximo passe; a entrega `p0-auth-close-gate` foi revisada e **não
fecha o gate**.
**Base:** checkout `9131f9f` com o patch `p0-auth-close-gate.patch` aplicado
(a entrega de 18 arquivos, 708 testes).
**Não integrar na `main`.** Trabalho em DEV/branch; sem commit/push.
**Uso:** colar no ChatGPT. A entrega final deve ser um patch **cumulativo contra
`9131f9f`** (incluindo o close-gate anterior + estas correções), não um patch
sobre patch.

## 1. Estado aceito

O passe anterior aplicou 18/18 arquivos idênticos e passou:

- foco: 189 OK · 1 skip e 110 OK · 1 skip;
- suíte completa: 708 OK · 1 skip;
- `py_compile`, `audit_comments --strict` e `git diff --check` limpos;
- flag `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`; MAIN intocada.

**Preserve esses 708 testes e o comportamento aceito.** O que falta são os
cinco achados abaixo, com testes que a suíte atual não cobre.

## 2. Bloqueio P0 — `publico` em OS encerrada

`flavors/autoseg/modules/os_commands.py` (`_write_publish_attachment`, por volta
das linhas 469–483) exige:

```python
if not current or current['status'] not in ext.ATIVAS:
    raise PermissionError('OS encerrada: publicação de anexo bloqueada.')
```

Mas o único formulário que envia para `/os/<id>/anexo/<aid>/publico` é
renderizado em `flavors/autoseg/modules/portal_prestador.py` (por volta da
linha 2792) justamente quando a OS **não** está ativa:

```python
if anexos and d['status'] not in ext.ATIVAS:
```

Reprodução confirmada: OS `Concluída` + POST `/publico` →
`PermissionError`. O teste atual usa OS `Aberta` e não cobre o fluxo real.

**Correção obrigatória:**

- remover o check de `ATIVAS` (ou permitir encerrada);
- manter `_transaction_guard(...)` e `cad9.aprovar_anexo(..., connection=c,
  pid=session['pid'])`, que já checam arquivada, vínculo e responsável/admin;
- adicionar teste com OS `Concluída` (e, se possível, `Pendente`/`Cancelada`)
  provando que a visibilidade/legenda e o evento são gravados;
- manter a negação para OS arquivada e para não-responsável/não-admin;
- flags `0` e `1`.

## 3. PDF — fechar a janela entre link e `os_documentos`

`officina/core/os_effect_outbox.py` (`publish_pdf`, por volta das linhas
321–389) faz:

1. uma transação verifica status/arquivada e executa `os.link(stage, target)`;
2. uma **segunda** transação insere `os_documentos` e atualiza a outbox.

Se a OS for cancelada/arquivada entre as duas, o PDF é publicado mesmo assim.
O teste exigido (“status muda entre claim e publicação”) não existe.

**Correção obrigatória (preferência):** unificar a verificação de status, o
`os.link`, a inserção em `os_documentos`, o upsert de `os_entregas` e o
`done` da outbox na **mesma** `BEGIN IMMEDIATE`. Se não for possível, revalidar
status/arquivada dentro da segunda transação antes de inserir.

**Teste determinístico:** injetar uma mudança de status entre o link e a
confirmação (ou concorrer com a publicação) e provar que:

- a operação termina `failed`;
- nenhuma linha nova em `os_documentos`;
- nenhum PDF novo é aceito como publicado;
- um retry posterior não duplica a versão reservada;
- se o arquivo já tiver sido linkado, ele é reconciliado/descartado sem
  sobrescrever um PDF publicado.

## 4. Rollback — referências de destinatários não podem virar e-mails

`os_commands.py` (por volta da linha 1027) grava referências
(`['cliente']`, `['sindico']`, ...) em
`produtividade_email.destinatarios_json`. O rollback
(`scripts/autoseg/install_os_effect_outbox.py`, por volta das linhas 51–58) só
dropa a outbox. Depois disso, o caminho legado de reenvio
(`os_commands.py`, por volta da linha 1279) lê essas referências como se fossem
e-mails; sem seleção explícita, tenta enviar para `"cliente"`.

**Correção preferida:** manter `produtividade_email.destinatarios_json` com
e-mails (compatível com o legado) e guardar as referências no payload mínimo da
outbox, em um campo permitido como `recipient_refs` (lista de
`cliente|sindico|administradora`, sem PII). `gmail_service.enviar_operacao_outbox`
resolve as referências a partir do payload no despacho.

**Alternativa:** converter as referências em e-mails antes do `DROP TABLE` do
rollback, resolvendo os contatos atuais; se um contato não existir, falhar o
rollback com mensagem clara.

**Teste:** enviar com referências, concluir, rodar `--rollback`, e provar que o
reenvio legado (sem seleção explícita) usa e-mails válidos e nunca a string
`"cliente"`. Cobrir também o reenvio manual com seleção explícita.

## 5. Projeção `os_entregas` ao publicar nova versão do PDF

`officina/core/os_effect_outbox.py` (por volta das linhas 378–380) preserva
`email_status` terminal (`enviado`, `falhou`, `unknown`, `sem_destinatario`)
mesmo quando `documento_id` muda para uma versão nova do PDF. A nova versão não
foi enviada, mas a projeção continua dizendo `enviado`.

**Correção:** preservar o status terminal apenas quando o `documento_id` for o
mesmo; ao publicar uma versão nova, voltar para `aguardando_api` (se houver
e-mail) ou `email_nao_cadastrado`. O reenvio manual continua reutilizando o
último PDF, sem criar versão nova.

**Teste:** publicar v1, marcar `os_entregas.email_status='enviado'`, publicar
v2 e provar que `documento_id` mudou e `email_status` voltou para
`aguardando_api`/`email_nao_cadastrado`; publicar novamente o mesmo documento
não deve resetar.

## 6. Operação — recuperação imediata de quarentena

`cleanup_orphan_trash` usa idade mínima de 1 hora e o CLI
`dispatch_os_effect_outbox.py` não expõe `--minimum-age` nem um restore
explícito. Um crash antes do commit deixa a foto em quarentena e ela não é
restaurada imediatamente.

**Correção:** adicionar `--minimum-age` (segundos) ou `--restore-quarantine
<operation_key>` ao dispatcher, com padrão seguro de 3600 s e uso explícito
para recuperação controlada. Documentar no `OBJECT_POLICY_ROLLOUT.md` e no
`NOTES.md`.

**Teste:** quarentenar um arquivo, rodar a recuperação com idade 0/restore
explícito e provar que o arquivo volta ao caminho original; sem a opção, o
comportamento antigo (1 h) permanece.

## 7. Documentação

- `docs/operations/OBJECT_POLICY_ROLLOUT.md`: remover a contradição da seção
  “Limites restantes” (por volta da linha 171), que ainda diz que exclusão/
  rotação de anexos não estão cobertas; refletir o estado real e o residual do
  caminho sem `connection` se ele continuar existindo.
- `NOTES.md`: mapa writer → transação → efeito, decisão de refs no payload,
  reset de `os_entregas` por versão, recuperação de quarentena.
- `TESTES.md`, `CHANGELOG.md`, `docs/HANDOFF.md`,
  `docs/PLATFORM_MIGRATION_LEDGER.md`: registrar a correção e os testes.
- `BLOCKED.md`: manter apenas bloqueios reais; não declarar o gate fechado se
  alguma garantia continuar residual.

## 8. Proibido

- Tocar na `main`, portas 8765/8766, dados reais, produção, GTK ou portal
  legado.
- Ativar `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` ou migrar fora de DEV.
- Criar tabela/coluna nova; o schema existente da outbox deve bastar. Refs vão
  no payload, não em schema.
- Recriar shim, fallback, flag ou segundo caminho de autorização.
- Efeito externo antes do commit ou sem idempotência/recuperação.
- Enfraquecer, remover ou pular teste para passar.
- Commit/push.

## 9. Testes obrigatórios

Além dos testes existentes:

- `test_publish_attachment_on_closed_os` (B6, OS `Concluída`, flags 0/1);
- `test_pdf_status_change_is_atomic_with_document_insert`;
- `test_rollback_keeps_legacy_email_recipients`;
- `test_new_pdf_version_resets_email_status`;
- `test_quarantine_restore_with_minimum_age_zero`.

Rodar:

```bash
PYTHONPATH=.:tests .venv/bin/python -m unittest \
  tests.test_p0_auth_close_gate tests.test_p0_auth_dispatcher \
  tests.test_os_effect_outbox tests.test_os_effect_outbox_files \
  tests.test_p0_auth_final_races tests.test_os_commands \
  tests.test_rev12_correcoes tests.test_gmail_integracao -v
```

```bash
TMP=$(mktemp -d)
AUTOSEG_DEV=1 AUTOSEG_SERVER_DATA="$TMP" AUTOSEG_USER_DATA="$TMP" \
AUTOSEG_LOCAL_DATA="$TMP" PYTHONPATH=.:tests \
python3 -m unittest discover -s tests -p 'test_*.py'
```

```bash
python3 -m py_compile flavors/autoseg/modules/os_commands.py \
  flavors/autoseg/modules/portal_prestador.py \
  flavors/autoseg/modules/gmail_service.py \
  officina/core/prestadores_ext.py officina/core/os_effect_outbox.py \
  officina/core/produtividade_os.py officina/core/fluxo_os.py \
  scripts/autoseg/dispatch_os_effect_outbox.py \
  scripts/autoseg/install_os_effect_outbox.py
python3 scripts/audit_comments.py --strict
git diff --check
```

Alvo: **708 + novos testes, 0 falhas, 1 skip existente**, sem novos skips.

## 10. Entrega

ZIP com:

- `changed-files/` completos;
- `p0-auth-close-gate-fixes.patch` **cumulativo contra `9131f9f`**,
  incluindo o close-gate anterior e estas correções;
- `CHANGED_FILES.txt`;
- `TEST_RESULTS.txt` com focado, regressão e suíte completa;
- `NOTES.md` com o mapa de atomicidade, decisão de refs, reset de projeções e
  recuperação de quarentena;
- `BLOCKED.md` se houver bloqueio real.

Sem `.git`, banco, anexos, PDFs de produção, logs, tokens ou credenciais.
Nenhum commit/push.

## 11. Checklist de aceite

- [ ] B6 `publico` funciona em OS `Concluída`/encerrada, com evento e
      visibilidade.
- [ ] B6 continua negando OS arquivada e não-responsável/não-admin.
- [ ] PDF: status/arquivada e inserção de `os_documentos` não têm janela entre
      transações.
- [ ] Rollback mantém reenvio legado com e-mails válidos.
- [ ] Nova versão de PDF reseta `os_entregas.email_status`.
- [ ] Quarentena tem recuperação imediata controlada.
- [ ] Documentação sem contradição; `BLOCKED.md` honesto.
- [ ] Suíte completa verde; flag 0; MAIN intocada.
