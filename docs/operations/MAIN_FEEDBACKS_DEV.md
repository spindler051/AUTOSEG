# Feedbacks da MAIN resolvidos na DEV

**Atualizado:** 2026-11-12
**Origem:** `portal_feedback` da MAIN, IDs 143–156 (12 pendentes).
**Branch:** `fix/main-feedbacks-dev`
**Commit de código:** `0531d5f`
**Base:** `feat/p0-auth-close-gate` (`4a83546`)
**MAIN:** `3892e7b`, intocada.

Os 12 feedbacks pendentes foram importados para a tabela `portal_feedback`
do banco DEV, com `status_dev` e `nota_dev`. Backup do estado atual:
`~/Library/Application Support/AUTOSEG/server-dev/dados_teste/autoseg_teste_after_main_feedbacks_20261112.db`.

## Resolvidos na DEV

| ID | Pedido | O que foi feito |
|---|---|---|
| 143 | Texto cinza no tema claro | Tema claro usa tons quase pretos no menu, navegação e conteúdo. |
| 146 | Não marcar destinatários automaticamente | Checkboxes começam vazios; o formulário mostra o resumo dos selecionados; sem seleção e sem “Não precisa de destinatário”, a conclusão é recusada. |
| 147 | Sem dados bancários em OS de R$ 0,00 | E-mail e `.eml` omitem os dados bancários quando o total da OS é zero. |
| 149 | Financeiro volta para a primeira aba ao atualizar | A aba ativa é preservada em `sessionStorage` e restaurada no reload. |
| 151 | Taxa mínima de visita como checkbox | Virou checkbox marcada por padrão; desmarcar remove a taxa. |
| 152 | Link do MAF dá erro | O AUTOSEG não renderiza mais o atalho `/auto-financeiro`; o MAF é o site separado. |
| 153 | Página `/auto-financeiro` não encontrada | A rota não é publicada pelo portal do AUTOSEG. |
| 154 | Caixa da empresa em aba separada, só admin | Aba “Caixa da empresa” separada e visível apenas para administradores. |
| 156 | Dados bancários na sessão de finanças pessoais | A aba “Finanças pessoais” concentra os dados bancários/cadastrais. |

## Em correção

| ID | Pendência |
|---|---|
| 144 | A máscara “Ocultar valores” já existe, é um toggle e persiste no navegador. Falta decidir se os itens mascarados devem ser excluídos do resumo, não apenas ocultados visualmente. |
| 145 | O toggle funciona sem reload; a mesma decisão de “não contar no resumo” acima continua pendente. |
| 150 | O arquivo da foto da OS 261109002 existe. A rota de thumbnail/download foi liberada para administradores, não só para participantes. Falta validar a foto específica no DEV. |

## Como validar

1. Subir o DEV na branch `fix/main-feedbacks-dev` com o banco DEV atual.
2. Abrir `/feedback/recebidos` e conferir os IDs 143–156.
3. Testar tema claro, financeiro, reenvio/conclusão de OS e a foto da OS 261109002.
4. Verificar que a MAIN continua parada/intocada até a homologação.

## Testes

- suíte completa: **724 OK · 1 skip**;
- `py_compile` e `audit_comments --strict`: OK;
- nenhum commit/push na MAIN; a branch fica em DEV.
