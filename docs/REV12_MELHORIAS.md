# AUTOSEG REV12 — Sete melhorias

Versão: 9.6.0-dev.6 (REV12)
Branch: `develop` (sem merge na `main` nesta revisão)

## 1. Portal Cliente — alteração da própria senha

- Rota `/cliente/senha` (GET/POST) e link no painel/perfil.
- `cliente_fluxo_v94.alterar_senha` valida senha atual (PBKDF2), exige nova senha com 10+ caracteres, letras e números, bloqueia reutilização e grava somente o hash.
- As demais sessões são invalidadas; a sessão atual recebe o novo hash.
- Teste HTTP: senha antiga deixa de autenticar; a nova entra.

## 2. Chamado de condomínio — nome e telefone obrigatórios

- Formulários do Portal Cliente (`chamado_form`, `formulario_org`) e do portal PJ legado exigem nome completo e telefone com DDD.
- `cadastros_v9.registrar_chamado` normaliza/valida os dois campos, grava em `v9_chamados.solicitante_nome/solicitante_telefone` e inclui na OS (`observacoes` e `os_solicitacoes`).
- Identificação conservadora: apenas a própria conta é reconhecida automaticamente; nome/telefone divergentes geram `solicitante_identificacao='pendente'` e seguem para análise da AUTOSEG. Nenhuma pessoa é vinculada por coincidência.

## 3. E-mail para múltiplos destinatários

- Checkboxes no formulário da OS para cliente, síndico e administradora/imobiliária, com os e-mails cadastrados.
- Campo de e-mails adicionais (separados por vírgula).
- `produtividade_os.destinatarios_para_os` deduplica, valida e não sobrescreve a seleção com o síndico.
- A lista final é registrada em `produtividade_email`; todos os destinatários são expostos no campo Para de um único e-mail.
- Teste: quatro destinatários selecionados são registrados e enviados juntos.

## 4. Identidade visual nos PDFs

- `pdf_identidade.py` localiza `logo.png`/`icone.png` na pasta de dados, no bundle ou no código.
- Relatório técnico: logo proporcional no cabeçalho e selo no canto superior direito de todas as páginas.
- Orçamento: mesmo cabeçalho e selo em todas as páginas.
- Teste com `pypdf`: relatório de 2 páginas com 2 imagens na página 1 e selo na página 2; orçamento de 2 páginas idem.
- Evidência visual: `~/AUTOSEG_DIST/evidencias/rev12_relatorio_p1.png`.

## 5. Nota fiscal em PDF

- Tabela `os_notas_fiscais` e pasta `notas_fiscais/`.
- Upload no Portal Prestador (`/os/{id}/nota-fiscal`) com validação de PDF e limite de 20 MB.
- Deduplicação por SHA-256; download somente para responsável/administrador no portal e para cliente PF/síndico autorizado no Portal Cliente.
- A última NFS-e é anexada automaticamente ao e-mail de conclusão (`caminho_pdf_nf`).
- Teste HTTP: upload, deduplicação, download e bloqueio de terceiro.

## 6. Dados bancários no e-mail

- `gmail_service._dados_pagamento_html` busca o prestador responsável da OS e exibe favorecido, instituição, agência, conta, Pix e texto livre, sem dados fixos.
- Quando não cadastrados, informa a ausência.
- Teste: e-mail capturado contém “Favorecido Teste” e “pix-teste”, sem dados de outro prestador.

## 7. Desktop GTK4 — atribuir síndico/gestor

- Botão “Atribuir síndico/gestor” na aba Clientes.
- `DialogoResponsavel` lista condomínios/empresas e contas PF ativas, mostra o responsável atual e permite nomear/trocar/remover.
- Usa `cadastros_v9.atribuir_responsavel` e `remover_responsavel`, o mesmo núcleo do Portal Prestador.
- Teste de integração confirma a persistência em `v9_responsaveis` e o vínculo aprovado; o Portal Prestador lê a mesma tabela.

## Testes

`test_rev12_melhorias.py` (6 testes) e `test_gmail_integracao.py` (4 testes) passam. Regressões principais (`test_rev09_fluxo_os`, `test_fluxo_v7`, `test_autoseg_melhorias`, `test_produtividade_rev07`, `test_completude`, `test_integracao_clientes`, `test_importacao_yaml`, `test_pf_pj_http`, `test_pf_pj_responsaveis`, `test_cadastro_v951`, `test_tk_v9`) passam. O app GTK4 foi iniciado em smoke test com as novas telas.

## Limitações

- O botão/disco do GTK foi verificado por inicialização do app e teste do núcleo compartilhado; não houve clique automatizado no diálogo nativo.
- Envio real de e-mail não foi disparado nos testes automatizados (mock).
- `test_v9` e `test_v91` ainda falham em asserções antigas de texto/regra já incompatíveis antes desta revisão.
