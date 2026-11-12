# P0-AUTH-CLOSE-GATE-HARDENING — lease-safe cleanup e UX do reenvio

**Status:** passe curto de hardening; a entrega `p0-auth-close-gate-fixes`
foi aceita para DEV/homologação.
**Base:** branch `feat/p0-auth-close-gate`, commit `7986659`, mais este prompt.
**Não integrar na `main`.** Trabalho em DEV/branch; sem commit/push.
**Uso:** colar no ChatGPT. A entrega deve ser um patch **incremental contra o
checkout deste ZIP** (o commit que adiciona este prompt); não reabra os cinco
itens já corrigidos.

## 1. Estado aceito

- 18/18 arquivos idênticos ao `changed-files/` da entrega anterior;
- foco/regressão: 118 OK · 1 skip;
- suíte completa: **716 OK · 1 skip**;
- `py_compile`, `audit_comments --strict` e `git diff --check` limpos;
- flag `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`; MAIN intocada.

**Preserve tudo isso.** Este passe corrige apenas dois resíduos.

## 2. Hardening — cleanup do PDF não pode apagar target de outro worker

`officina/core/os_effect_outbox.py` (`publish_pdf`, bloco `except`, por volta
das linhas 410–425) faz:

```python
if linked and not committed and target is not None:
    with ext.db(banco) as c:
        recorded = c.execute('''SELECT 1 FROM os_documentos WHERE os_id=?
            AND tipo='relatorio_pdf' AND versao=?''',
            (claimed['os_id'], claimed['version_reserved'])).fetchone()
    if not recorded:
        target.unlink(missing_ok=True)
```

O `recorded` é uma leitura fora de transação e não prova que a operação ainda
pertence a este worker. Se a transação falhar depois do `os.link` e o lease
expirar, outro worker pode ter assumido a mesma `operation_key` e estar
publicando. Este cleanup pode remover o `target` que o segundo worker acabou de
linkar, antes de ele inserir `os_documentos`, deixando uma linha apontando para
arquivo ausente.

**Correção obrigatória:**

- extrair o cleanup para um helper testável, por exemplo
  `_discard_new_pdf_target(banco, operation, claim_token, target)`;
- dentro de uma transação `BEGIN IMMEDIATE`, reler
  `os_effect_outbox.state` e `claim_token`;
- só remover o `target` se a operação ainda estiver `processing` com o
  **mesmo** `claim_token` deste worker, e se não existir `os_documentos` para
  `(os_id, tipo, versao)`;
- se outro worker assumiu (`claim_token` diferente) ou a operação já mudou de
  estado, **não remover** o arquivo; deixar para a reconciliação por hash do
  retry, que já falha fechado em conflito;
- nunca remover um target que já tenha linha em `os_documentos`;
- não alterar a garantia de crash: órfão após queda continua sendo comparado
  por SHA-256 no retry, nunca adotado às cegas.

**Testes obrigatórios:**

- `test_pdf_cleanup_does_not_remove_target_owned_by_another_worker`:
  simular a operação `processing` com outro `claim_token` e um target recém
  linkado; chamar o helper e provar que o target permanece;
- `test_pdf_cleanup_removes_own_target_after_metadata_failure`: com o mesmo
  `claim_token`, provar que o target é removido e nenhum `os_documentos`
  sobrevive;
- `test_pdf_cleanup_never_removes_recorded_document`: com linha em
  `os_documentos`, o target não é removido;
- manter o teste de retry após crash e o de conflito de hash.

## 3. UX — esconder “Outro e-mail” no modo recuperável

`flavors/autoseg/modules/portal_prestador.py` (formulário de
`/os/<id>/reenviar-email`, por volta das linhas 2860–2885) ainda renderiza o
campo `emails_adicionais` mesmo quando a outbox está instalada. O handler
rejeita esse campo no modo recuperável, mas o operador só descobre depois de
enviar.

**Correção obrigatória:**

- quando `outbox_ready` for verdadeiro, não renderizar o label/input
  `emails_adicionais`;
- mostrar uma nota curta: “No modo recuperável, use apenas contatos
  cadastrados; e-mails avulsos precisam ser cadastrados no cliente”;
- quando a outbox **não** estiver instalada, manter o campo e o comportamento
  legado;
- o handler continua rejeitando `emails_adicionais` forjado no modo
  recuperável; não confie só na UI.

**Testes obrigatórios:**

- `test_manual_resend_hides_additional_email_in_outbox_mode`: com outbox
  instalada, GET da OS não contém `name="emails_adicionais"`;
- `test_manual_resend_keeps_additional_email_in_legacy_mode`: sem outbox, o
  campo continua presente;
- POST forjado com `emails_adicionais` no modo recuperável continua falhando
  sem enfileirar operação.

## 4. Proibido

- Tocar na `main`, portas 8765/8766, dados reais, produção, GTK ou portal
  legado.
- Ativar `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` ou migrar fora de DEV.
- Criar tabela/coluna nova ou alterar schema.
- Recriar shim, fallback, flag ou segundo caminho de autorização.
- Reabrir ou enfraquecer os testes dos cinco itens já aceitos.
- Commit/push.

## 5. Testes

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

Alvo: **716 + novos testes, 0 falhas, 1 skip existente**, sem novos skips.

## 6. Entrega

ZIP com:

- `changed-files/` completos;
- `p0-auth-close-gate-hardening.patch` incremental contra o checkout deste
  ZIP;
- `CHANGED_FILES.txt`;
- `TEST_RESULTS.txt` com focado, regressão e suíte completa;
- `NOTES.md` com a decisão do lease-safe cleanup e a condição de UI;
- `BLOCKED.md` se houver bloqueio real.

Sem `.git`, banco, anexos, PDFs de produção, logs, tokens ou credenciais.
Nenhum commit/push.

## 7. Checklist de aceite

- [ ] Cleanup do PDF só remove target do próprio worker/lease.
- [ ] Target de outro worker ou documento registrado nunca é removido.
- [ ] Campo “Outro e-mail” some no modo recuperável e permanece no legado.
- [ ] POST forjado continua rejeitado.
- [ ] Testes novos + 716 existentes verdes; 1 skip.
- [ ] Flag 0, MAIN intocada, sem schema novo.
