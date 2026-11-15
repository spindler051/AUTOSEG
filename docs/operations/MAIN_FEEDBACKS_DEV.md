# Feedbacks da MAIN resolvidos na DEV

**Atualizado:** 2026-11-12
**Origem:** `portal_feedback` da MAIN, IDs 143–156 (12 pendentes).
**Branch:** `dev`
**Commit de código:** `100b555`
**Base:** `main` + P0-AUTH + limpeza do MAF
**MAIN:** `3892e7b`, intocada.

Os 12 feedbacks pendentes foram importados para a tabela `portal_feedback`
do banco DEV, com `status_dev` e `nota_dev`. **Os 12 estão corrigidos na DEV.**
Backup do estado atual:
`~/Library/Application Support/AUTOSEG/server-dev/dados_teste/autoseg_teste_after_main_feedbacks_20261112.db`.

## Resolvidos na DEV

| ID | Pedido | O que foi feito |
|---|---|---|
| 143 | Texto cinza no tema claro | Tema claro usa tons quase pretos no menu, navegação e conteúdo. |
| 144 | Mascarar valores no Recebidos | O botão “Ocultar valores” mascara KPIs, listas e tabelas do financeiro, inclusive o resumo. A máscara é visual: os totais reais continuam no servidor. |
| 145 | Máscara como toggle, sem recarregar | O botão “Ocultar valores” alterna sem reload e persiste no navegador; a máscara cobre KPIs, listas e tabelas. |
| 146 | Não marcar destinatários automaticamente | Checkboxes começam vazios; o formulário mostra o resumo dos selecionados; sem seleção e sem “Não precisa de destinatário”, a conclusão é recusada. |
| 147 | Sem dados bancários em OS de R$ 0,00 | E-mail e `.eml` omitem os dados bancários quando o total da OS é zero. |
| 149 | Financeiro volta para a primeira aba ao atualizar | A aba ativa é preservada em `sessionStorage` e restaurada no reload. |
| 150 | Foto da OS não carregava | A decisão de thumbnail/download agora é do `ObjectPolicy` (`document.download`), sem o fallback `participou or administrador`. Validado no DEV com a foto da OS 261109002: admin e autor recebem a imagem; funcionário sem vínculo é recusado. O arquivo foi copiado para o armazenamento local da DEV e o caminho da OS foi corrigido, com backup do banco. |
| 151 | Taxa mínima de visita como checkbox | Virou checkbox marcada por padrão; desmarcar remove a taxa. |
| 152 | Link do MAF dá erro | O AUTOSEG não renderiza mais o atalho `/auto-financeiro`; o MAF é o site separado. |
| 153 | Página `/auto-financeiro` não encontrada | A rota não é publicada pelo portal do AUTOSEG. |
| 154 | Caixa da empresa em aba separada, só admin | Aba “Caixa da empresa” separada; a visibilidade é decidida pela permissão `finance.view.all` da policy, não por um `if admin`. Admin recebe `*`; employee recebe apenas `finance.view.own`. |
| 156 | Dados bancários na sessão de finanças pessoais | A aba “Finanças pessoais” concentra os dados bancários/cadastrais. |

## Permissões

- **Caixa da empresa:** `_policy_allows` carrega a policy e resolve o papel pela identidade
  do prestador (`admin`/`employee`). Não há mais `if s.get('admin')` no caminho do caixa.
- **Anexos e miniaturas:** `read_anexo` e `read_anexo_thumb` sempre passam por
  `ObjectPolicy.require(..., 'download', ...)`. O principal vem de
  `_provider_context`; não existe mais o fallback `participou or administrador`.
- As flags `AUTOSEG_OBJECT_POLICY_ENFORCEMENT`, `AUTOSEG_UNIFIED_LOGIN` e
  `AUTOSEG_WEB_SESSION_DURABLE` continuam em `0` por padrão. O caminho de anexos
  usa a policy diretamente, sem depender da flag de enforcement.

## Em correção

Nenhum. O feedback 144 foi encerrado com a máscara visual: o valor fica
oculto no resumo, mas os totais reais não são alterados, por segurança
contábil.

## Como validar

1. Subir o DEV na branch `dev` com o banco DEV atual.
2. Abrir `/feedback/recebidos` e conferir os IDs 143–156.
3. Testar tema claro, financeiro, reenvio/conclusão de OS. A foto da OS 261109002 já foi validada no DEV.
4. Verificar que a MAIN continua parada/intocada até a homologação.

## Testes

- suíte completa: **718 OK · 1 skip**;
- `py_compile` e `audit_comments --strict`: OK;
- nenhum commit/push na MAIN; a branch fica em DEV.
