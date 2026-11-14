# Prompt — P0-AUTH: outbox como único caminho de e-mail

**Status:** pronto para gerar código.
**Branch:** `dev`.
**Base:** `42dce2d`.
**MAIN:** `3892e7b`, intocada.
**Flags:** `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`,
`AUTOSEG_UNIFIED_LOGIN=0`, `AUTOSEG_WEB_SESSION_DURABLE=0`.
**Pré-condição operacional:** a outbox `os_effect_outbox` instalada no banco
DEV de teste, com backup verificado. Sem isso, o caminho novo falha fechado e
o envio fica indisponível — que é o comportamento desejado.

## Contexto

O P0-AUTH close gate já está implementado na `dev`. A outbox existe em
`officina/core/os_effect_outbox.py`, com instalador, dispatcher, reconciliação e
testes. O que ainda existe é o caminho legado de envio de e-mail:

- campo `emails_adicionais` na tela e no handler;
- branch `not use_outbox` com envio automático pelo Gmail;
- chamadas diretas aos serviços de anexo/nota sem `connection`;
- documentação e testes que ainda descrevem o caminho antigo.

O objetivo desta fatia é eliminar esse caminho legado por completo. Não é para
adicionar uma flag, um fallback ou um shim: é para deixar **um único caminho**.

## Objetivo

Tornar `os_effect_outbox` o único caminho de envio de e-mail de OS e fazer o
sistema falhar fechado quando a outbox não estiver instalada.

## Proibido

- Manter qualquer envio automático fora da outbox.
- Manter o branch `not use_outbox` que chama Gmail.
- Manter `emails_adicionais` no caminho de OS/e-mail. O campo homônimo da
  importação Asaas não faz parte deste escopo.
- Usar `produtividade_email.destinatarios_json` como fallback de endereço.
- `try/except` que engole erro e segue por outro caminho.
- Flag que preserve o comportamento antigo permanentemente.
- `if admin` novo.
- Alterar a MAIN, ativar flags ou instalar schema em produção.
- Criar tabela nova ou alterar schema nesta fatia.

## Escopo

1. Remover o campo `emails_adicionais` do formulário de conclusão/salvar, do
   parser do handler, dos rascunhos, do JavaScript e dos testes.
2. Remover o caminho automático `not use_outbox` do writer de salvar/concluir.
   Se a outbox não estiver instalada e a ação exigir envio, falhar antes de
   qualquer mutação de OS, fila ou Gmail, com erro de domínio claro.
3. Reenvio manual: somente pela outbox. Sem e-mail avulso. Exigir nova
   `operation_key` e confirmação explícita de possível duplicata.
4. Dispatcher: `recipient_refs` obrigatório. Sem refs, falhar antes do provedor.
   `unknown` nunca é reenviado automaticamente.
5. Remover código morto, imports, textos de UI e documentação que ainda
   descrevam o caminho legado.
6. Não alterar o schema. Não criar tabela nova. Não mexer na MAIN.

## Arquivos prováveis

- `flavors/autoseg/modules/portal_prestador.py`
- `flavors/autoseg/modules/os_commands.py`
- `flavors/autoseg/web/portal.js`
- `officina/core/os_effect_outbox.py`
- `officina/core/produtividade_os.py`
- `officina/core/prestadores_ext.py`, se houver chamada direta
- `scripts/autoseg/install_os_effect_outbox.py`
- `scripts/autoseg/dispatch_os_effect_outbox.py`
- `tests/test_os_effect_outbox.py`
- `tests/test_p0_auth_close_gate.py`
- `tests/test_os_commands.py`
- `tests/test_rev12_correcoes.py`
- `docs/operations/P0_AUTH_DEV_FREEZE.md`
- `docs/operations/OBJECT_POLICY_ROLLOUT.md`

## Testes obrigatórios

- Sem outbox: salvar/concluir com destinatário falha fechado, não chama Gmail,
  não grava envio pendente e não altera a OS.
- Com outbox: grava a intenção na mesma transação do writer e só despacha
  depois do commit.
- `emails_adicionais` não existe mais na UI nem é aceito no backend.
- Reenvio manual sem outbox falha antes de enfileirar.
- Dispatcher sem `recipient_refs` falha antes do provedor.
- `unknown` não é reenviado automaticamente.
- Nenhuma chamada direta a Gmail a partir de writer de OS.
- Grep do caminho de OS/e-mail não encontra `emails_adicionais` (fora da
  importação Asaas), `not use_outbox` nem envio legado.

## Critérios de aceite

- Existe um único caminho de e-mail: outbox.
- O sistema falha fechado quando a outbox não existe.
- Nenhum comportamento antigo fica acessível por flag, campo oculto ou rota.
- Suíte focada e regressão passam.
- `py_compile`, `git diff --check` e `audit_comments --strict` passam.

## Formato da resposta do ChatGPT

1. Plano curto, sem código.
2. Depois do plano aprovado, diff completo.
3. Lista de testes executados e resultados.
4. Riscos e pontos que o revisor deve conferir.

## Checklist de revisão

Rejeitar imediatamente se:

- sobrou `if not outbox` com envio antigo;
- sobrou `emails_adicionais` no caminho de OS/e-mail;
- o handler aceita e-mail livre “por compatibilidade”;
- existe `except` que cai no Gmail;
- o dispatcher usa projeção como fallback de destinatário;
- a flag desliga o caminho novo em vez de ser só um gate de implantação;
- o teste cobre só o caminho feliz;
- a alteração mexe na MAIN ou no schema.
