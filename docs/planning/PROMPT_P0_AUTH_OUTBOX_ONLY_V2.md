# Prompt — P0-AUTH outbox only (v2, correções da revisão)

**Base:** `f49bb5d` (inclui o guard de ambiente corrigido) · **Branch:** `dev` · **MAIN:** `3892e7b`, intocada.
**Flags:** `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`,
`AUTOSEG_UNIFIED_LOGIN=0`, `AUTOSEG_WEB_SESSION_DURABLE=0`.
**Outbox:** o código existe, mas a tabela NÃO está instalada no DEV nem na MAIN.

## Contexto

O patch v1 foi aplicado num worktree temporário e reprovado na revisão. A
direção está correta, mas ele deixou consumidores do caminho antigo, testes
quebrados e um fallback silencioso. Corrija o patch sobre a mesma base, sem
reintroduzir compatibilidade.

## Correções obrigatórias

1. **GTK**
   - `flavors/autoseg/modules/gtk_app.py:1034` ainda chama
     `gmail_service.enviar_relatorio_os_concluida`, que foi removida.
   - Não deixe `except Exception: pass` escondendo a falha.
   - Se o modo local do GTK não tiver outbox, o envio deve falhar de forma
     visível e explícita, ou o caminho de e-mail local deve ser removido com
     mensagem clara. Não pode existir envio direto nem silêncio.
   - Não altere o MAF; `maf_loans.py` é outro produto.

2. **Sem destinatário x sem endereço válido**
   - `os_commands.py` grava `sem_destinatario` quando não há endereço válido,
     mesmo que o usuário não tenha marcado o checkbox.
   - Corrija: só registrar `sem_destinatario` quando o checkbox estiver
     explicitamente marcado.
   - Se o checkbox não estiver marcado e nenhum contato tiver e-mail válido,
     falhar antes de qualquer mutação da OS, com erro claro.
   - Não criar um “pendente” vazio nem um fallback silencioso.
   - Não gravar linha em `produtividade_email` quando não houver envio.
     `test_feedback_dev` exige zero linhas em `Pendente` e em
     `sem_destinatario`.

3. **Rascunhos**
   - O patch só rejeita `emails_adicionais` em `_write_action_salvar`.
   - `_write_save_draft` e `_write_autosave_draft` também precisam rejeitar o
     campo antes de gravar rascunho, com 400/JSON, sem persistir nada.
   - `test_rascunho_rejeita_email_adicional` deve voltar a passar.

4. **Testes legados**
   - Atualizar `tests/test_gmail_integracao.py` para o caminho da outbox:
     instalar a outbox no banco temporário, enfileirar com `recipient_refs`,
     despachar por `gmail_service.enviar_operacao_outbox` e manter a cobertura
     de múltiplos destinatários, nota fiscal, dados de pagamento, arquivo
     faltante e modo desativado.
   - Atualizar `tests/test_produtividade_rev07.py`: remover os testes de
     `destinatarios_conclusao`/`destinatarios_para_os` e cobrir
     `contatos_email_os`/refs da outbox, ou afirmar explicitamente que os
     helpers legados não existem.
   - Atualizar `tests/test_rev12_melhorias.py` da mesma forma.
   - Atualizar `tests/test_p0_auth_dispatcher.py` para passar
     `recipient_refs=['cliente']` em `enqueue_email`.
   - Atualizar `tests/test_feedback_dev.py`: `Pendente` e `sem_destinatario`
     não podem criar linha em `produtividade_email`.
   - Rodar também `tests/test_rev12_correcoes.py`; o caso de rascunho com
     `emails_adicionais` deve retornar 400.
   - Corrigir `tests/test_p0_auth_close_gate.py::test_close_without_recipients_does_not_require_email_outbox`:
     o payload precisa de `descricao` ou usar a OS já existente. O teste atual
     falha antes de exercitar a outbox.
   - Não manter testes do caminho antigo só para “compatibilidade”.

5. **API de reenvio**
   - `manual_email_retry` deve exigir `recipient_refs` sem default `None`.
   - Atualizar chamadas e testes.
   - `enqueue_email` não pode aceitar lista vazia.
   - `enviar_operacao_outbox` continua rejeitando refs desconhecidas,
     duplicadas e vazias.

6. **Validação**
   - Rodar a suíte completa no repositório inteiro, não só os 5 testes da
     outbox.
   - Reportar contagem exata, incluindo skips.
   - A suíte completa do v1 deu **706 testes, 13 erros, 3 falhas e 1 skip**;
     o v2 só é aceitável com suíte completa verde.
   - Rodar `py_compile`, `git diff --check`, `audit_comments --strict`.
   - Confirmar por busca que o writer de OS não chama Gmail direto e que
     `enviar_relatorio_os_concluida`/`destinatarios_*` não têm consumidores
     restantes.
   - Confirmar que o campo homônimo da importação Asaas permanece.

## Proibido

- Reintroduzir `emails_adicionais` no caminho de OS.
- Reintroduzir `not use_outbox` ou qualquer envio direto pelo Gmail.
- Criar shim/compatibilidade para funções removidas.
- `except` que engole falha de envio.
- Fallback de `recipient_refs` para projeção.
- Alterar schema, ativar flags, mexer na MAIN ou no MAF.
- Aceitar e-mail avulso no reenvio.

## Critérios de aceite

- Um único caminho de e-mail: outbox.
- Sem outbox e com destinatário: falha fechada antes de mutação.
- Sem destinatário explícito: não exige outbox.
- Sem endereço válido e sem checkbox: erro explícito, não `sem_destinatario`.
- Nenhum consumidor do caminho antigo.
- Suíte completa verde, com contagem e skips informados.
- Diff sem schema, sem flags e sem MAIN.

## Formato da resposta

1. Plano curto, sem código.
2. Depois do plano aprovado, diff completo.
3. Lista de testes executados, com resultados e contagem.
4. Riscos e pontos de revisão.
