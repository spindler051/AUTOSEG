# AUTOSEG — Changelog

## 9.6.0-dev.32 — feedbacks 54–63, menu hambúrguer e fotos — 2026-11-06 — develop

- **Identificação:** Cancelar OS e Arquivar OS ficaram no fim da aba Identificação; Situação do atendimento e Assumir OS permanecem no topo. Administradores também podem cancelar OS nesse fluxo.
- **YAML da OS:** importação de relatório aparece somente na criação (OS rápida ou completa), não na edição; o formulário de criação é preenchido para revisão. OS existentes ganharam **Exportar relatório em YAML** acima das ações de cancelar/arquivar, com diagnóstico, execução, resultado, relato e materiais.
- **Fotos:** subir/descer é aplicado ao vivo (sem recarregar e sem voltar para a aba 01); “Incluir no PDF” é checkbox; a ordem é usada no PDF.
- **Desempenho de fotos:** o site passa a usar miniaturas JPEG em cache; o original permanece no banco. O PDF ganhou a opção **Comprimir fotos no PDF** (marcada por padrão); desmarcada, usa alta qualidade, sempre sem alterar o original.
- **Menu mobile:** no unslop, a navegação mobile fica dentro de um botão **☰ Menu** com lista vertical no estilo de configurações do Android, em vez de uma lista aberta no topo.
- **Lista de OS:** o filtro de ordenação aplica automaticamente, sem botão Aplicar; novas opções **Última alteração** e **Última abertura (lida por mim)**. Abrir uma OS registra a leitura por prestador.
- **YAML na criação:** as telas de OS rápida (após escolher o cliente) e OS completa oferecem importação antes de criar, sem salvar automaticamente.
- **Testes:** `test_rev12_correcoes.py` (40 OK, 1 skipped), `test_composicao.py` (28 OK), `test_feedback_portal.py` (25 OK), `test_api_financeiro.py` (8 OK), `test_autoseg_melhorias.py` (9 OK), `test_pdf_relatorio.py` (4 OK), `test_produtividade_rev07.py` (9 OK) e `test_importacao_yaml.py` (OK).

## 9.6.0-dev.31 — financeiro por OS em que participo e feedbacks recentes — 2026-11-06 — develop

- **Financeiro:** dados bancários passam a ser o primeiro bloco; “Lançamentos das OS em que participo” une OSs finalizadas e OSs em que o prestador é técnico secundário; duas colunas visíveis (A receber / Confirmar recebimento e Recebidos) com migração automática ao confirmar. O card separado de produção secundária foi absorvido.
- **Repasses:** “Repasses a outros técnicos” continua no financeiro do finalizador; ao registrar envio, o item aparece na coluna A receber do técnico secundário e, após confirmação, migra para Recebidos.
- **Fotos:** reordenação com botões subir/descer; “Incluir no PDF” agora é checkbox; a ordem é persistida e usada no PDF.
- **OS:** o cartão Andamento foi unido ao bloco Situação do atendimento na aba Identificação e deixou de aparecer nas outras abas; administradores podem arquivar OS ativas ou concluídas preservando histórico. OS arquivadas deixam de aparecer nas listas operacionais e nos lançamentos financeiros/API, mas os registros continuam no banco para auditoria.
- **Navegação:** cards da home, financeiro, nomes de clientes e linhas de OS ficaram clicáveis; a navegação mobile do unslop passou a ser vertical, sem rolagem horizontal.
- **Total previsto:** layout separado em uma linha própria, com valor destacado e sem quebra.
- **Feedback:** o formulário passa a anexar um diagnóstico técnico da tela (modo, aba, viewport, posição, total previsto e texto principal), visível na administração; o layout do Total previsto também foi corrigido.
- **Testes:** `test_rev12_correcoes.py` (38 OK, 1 skipped), `test_composicao.py` (28 OK), `test_feedback_portal.py` (25 OK), `test_api_financeiro.py` (8 OK), `test_autoseg_melhorias.py` (9 OK), `test_pdf_relatorio.py` (4 OK), `test_produtividade_rev07.py` (9 OK) e `test_importacao_yaml.py` (OK).

## 9.6.0-dev.30 — fotos da OS sem texto de atribuição — 2026-11-06 — develop

- **Fotos da OS:** o editor normal de fotos e legendas aparece para o responsável e para administradores, dentro da aba Fotos. Foi removido o cartão extra e todas as mensagens sobre “assumir/atribuir a OS”. Administradores editam fotos e legendas livremente; a responsabilidade da OS não muda e a conclusão continua com o responsável.
- **Permissão:** `/fotos` e `Girar 90°` aceitam responsável ou administrador; os demais prestadores veem as fotos em modo leitura.
- **Teste:** administrador adiciona foto em OS de outro prestador; não-admin recebe 403; a página não contém o texto “sem assumir”.

## 9.6.0-dev.29 — feedback no mobile unslop — 2026-11-06 — develop

- **Feedback no mobile:** no modo unslop em telas de até 980 px, o rodapé da sidebar fica oculto e o botão flutuante estava com `display:none`; agora o botão **Dê um feedback** volta a aparecer no canto inferior direito. No modo clássico ele já aparecia.
- **Teste:** a página unslop da OS verifica a regra responsiva que mantém o botão de feedback visível no mobile.

## 9.6.0-dev.28 — feedbacks 27–35, paridade do desktop e CI — 2026-11-06 — develop

- **Feedbacks 27–35:** correções de usabilidade e segurança no Portal do Prestador.
- **Rotação de fotos:** o PDF agora aplica a orientação EXIF (fotos de celular não saem mais giradas em 90°) e cada foto de OS ativa tem o botão **Girar 90°**, sem duplicar o anexo.
- **Feedback incompleto:** o texto digitado é salvo automaticamente como feedback incompleto no servidor, restaurado ao reabrir/recaregar e convertido no mesmo registro ao enviar. Cancelar descarta o rascunho; não há duplicatas.
- **Modo e aba:** feedbacks e aberturas guardam `ui_mode` e `aba`; o OpenTelemetry local registra `page_view` com modo e aba ativa. A administração mostra os dois campos.
- **Cancelamento de OS:** a situação fica no topo da aba Identificação e não oferece mais “Cancelado”. O cancelamento é um botão vermelho com diálogo em duas etapas (motivo + número da OS), validado também no servidor. O campo Motivo saiu da aba Situação.
- **Destinatários do relatório:** movidos para o topo da aba Situação.
- **Preview do PDF:** uma única ação na ficha da OS em unslop, com o texto **Baixar preview do PDF**; a interface clássica mantém o link no cartão de documentos.
- **Espaçamento unslop:** grupos de ações (Novo cliente, Novo orçamento, Nova OS) usam um contêiner com espaçamento consistente.
- **Paridade do desktop:** o GTK preserva a base modular ao salvar OS do portal, não sobrescreve o total negociado ao editar materiais e mantém a unidade dos materiais. Composições declarativas são protegidas.
- **Encerramento e recálculo:** concluir/cancelar preserva composições modulares; `recalcular_tudo` recalcula OSs na mesma base e mantém composições declarativas ou que não fecham com a nova configuração.
- **CI:** a main passa a rodar as suites atuais (`test_composicao`, `test_rev12_correcoes`, `test_feedback_portal`, `test_api_financeiro`, `test_autoseg_melhorias`, `test_pdf_relatorio` e `test_importacao_yaml.py`); o teste legado v9.4.1 deixa de ser executado.
- **Testes:** `test_rev12_correcoes.py` (34 OK, 1 skipped), `test_composicao.py` (28 OK), `test_feedback_portal.py` (25 OK), `test_api_financeiro.py` (8 OK), `test_autoseg_melhorias.py` (9 OK), `test_pdf_relatorio.py` (4 OK) e `test_importacao_yaml.py` (OK).
- **Publicação:** pendente de deploy na MAIN.

## 9.6.0-dev.27 — interface experimental unslop — 2026-11-05 — develop

- **Toggle no login:** a página de acesso do prestador ganhou **Ativar unslop**; com o modo ativo, mostra **Desativar unslop**. A preferência fica no cookie `autosseg_ui` e a interface atual continua sendo o padrão. O link aceita `next` e volta à mesma página mesmo com `Referrer-Policy: no-referrer`.
- **Nova casca:** sidebar fixa de 264 px, grupos de navegação, ícones de linha, superfícies grafite, acento âmbar e tipografia Avenir Next/SF Mono. Sem gradientes, brilhos, sombras coloridas, emoji ou caixa alta.
- **Visão geral redesenhada:** quatro indicadores operacionais, ordens recentes com status e datas consistentes, financeiro com um único número em âmbar e atalhos discretos. A ação primária é off-white; o âmbar fica para seleção e o número principal.
- **OS mais clara:** ficha da OS com número, status, cliente, responsável, total e fotos; três cartões de fluxo (Andamento, Rascunho, Importação); editor em abas com rail de documentos e histórico. O bloco **Fechamento** com nota fiscal e “Não precisa de nota fiscal” foi movido para a aba Situação.
- **Validação sem campo escondido:** em unslop o formulário usa `novalidate`; um handler de captura revela a aba do primeiro campo inválido, foca o campo e mostra um toast. Salvar rascunho usa `formnovalidate`. O fluxo AJAX e os erros em toast continuam.
- **Materiais com unidade livre:** a quantidade pode ficar vazia (item sem quantidade fixa; o valor informado vira o total do item). A unidade aceita sugestões (un, m, cm, mm, g, kg, L, ml, par, rolo, caixa, pacote) ou qualquer texto arbitrário. A unidade é persistida em `materiais_os.unidade` e aparece no PDF e no e-mail; o estoque ignora itens sem quantidade.
- **Composição modular por base:** `composicao.calcular_os` aceita bases configuradas no `composicao.yaml`: `total` (percentuais em linhas próprias) ou `visita` (percentuais dentro da visita). Cada base declara `componente` ou `campo` e `cobertura: separado|incluido`; um novo campo futuro entra como nova base, sem `if` no código. A OS escolhe a base no formulário, com padrão global configurável. O total negociado é autoritativo e não recebe desconto automático: se não cobrir a hora mínima de R$ 100,00, o formulário recusa com mensagem e pede ajuste. OS de garantia/cortesia com mão de obra zero mantêm o comportamento anterior.
- **Prévia da composição no formulário:** `GET /composicao/simular` devolve a composição; o formulário mostra o total e os componentes antes de salvar. O total negociado continua autoritativo.
- **Correção manual na MAIN — OS-0023:** caixa de passagem R$ 49,25; cabo 1 m; tubo termo retrátil 5 cm e R$ 5,00 no total; materiais R$ 65,00; base dos percentuais = visita mínima; visita R$ 250,00 incluindo administrativo R$ 25,00, operacional R$ 25,00 e risco R$ 25,00; hora técnica R$ 135,00; total R$ 450,00. Sem desconto. Ajuste posterior do usuário: caixa R$ 50,00, materiais R$ 65,75 e hora técnica R$ 134,25, mantendo o total e os percentuais. Os nomes não usam mais “sem quantidade fixa”. Backups: `backups/dados_antes_composicao_visita_os0023_20261105_231929.db` e `backups/dados_antes_quantidade_livre_os0023_20261105_233717.db`. Feedback registrado em `portal_feedback` id 26.
- **Financeiro e listas:** tabelas com ações discretas, filtros secundários, grade de cartões e cabeçalhos de tabela em 12 px. O visual clássico e o portal do cliente não mudam.
- **Rollback imediato:** `/ui/classic` restaura a interface atual e volta à mesma página; a documentação está em `docs/features/UNSLOP_UI.md`.
- **Paridade do desktop:** ao editar uma OS com composição modular, o aplicativo GTK preserva a base (`total`/`visita`) e recalcula com `calcular_os`, em vez de regravar a composição pela regra legada. OSs antigas, sem a marca modular no JSON, mantêm o comportamento explícito de materiais + mão de obra. A unidade dos materiais também é carregada e regravada; quantidade vazia continua vazia.
- **Encerramento seguro:** concluir ou cancelar uma OS não recalcula mais uma composição modular pela regra legada; a base e os filhos da visita são preservados.
- **Importação YAML:** materiais de OS aceitam `unidade` opcional (padrão `un`), sem perder a unidade ao importar.
- **Testes:** `test_rev12_correcoes.py` (33 OK, 1 skipped), `test_composicao.py` (27 OK), `test_feedback_portal.py` (22 OK), `test_api_financeiro.py` (8 OK), `test_autoseg_melhorias.py` (9 OK), `test_pdf_relatorio.py` (3 OK) e `test_importacao_yaml.py` (OK).
- **Publicação:** a `develop` foi publicada na `main` em `de2e123` (`9.6.0-dev.27`), com backup do banco e do `composicao.yaml` antes do deploy.

## 9.6.0-dev.26 — mensagem real dos erros e permissão da OS — 2026-11-05 — develop

- **Erro real no toast:** `self.erro` agora devolve JSON para requisições AJAX, então o toast mostra a mensagem exata do servidor em vez de “Não foi possível salvar”.
- **Log de validação:** erros esperados de POST são registrados em `portal_prestador.log`; exceções ao salvar rascunho também.
- **Permissão clara:** OS com outro responsável não mostra mais “SALVAR RASCUNHO” nem “Confirmar situação” para quem não é o técnico atribuído; mostra instrução para assumir ou pedir transferência.
- **Testes:** conclusão por técnico não responsável retorna JSON 403 com “Somente o técnico atribuído…” e não navega.

## 9.6.0-dev.25 — erros de formulário em toast e legendas corrigidas — 2026-11-05 — develop

- **Legendas de fotos:** os campos de legenda das fotos existentes agora ficam dentro do formulário colaborativo; salvar apenas a legenda não retorna mais “selecione uma foto”.
- **Erros sem perder dados:** formulários da OS e de fotos são enviados por AJAX; erros de validação/permissão voltam em JSON e aparecem como toast, mantendo o formulário, os textos e os arquivos selecionados na página.
- **Sem página de erro:** o servidor responde JSON para requisições `X-Requested-With: XMLHttpRequest`/`Accept: application/json`. O fallback HTML agora tem **“Voltar à página anterior”** em vez de “Voltar ao início”.
- **Testes:** edição de legenda por técnico não responsável, erro JSON sem navegação e regressões de OS/feedback.

## 9.6.0-dev.24 — preview do PDF em OS ativa — 2026-11-05 — develop

- **Preview do PDF:** OS ativa agora tem o botão **“Baixar preview do PDF (não publicado)”** na tela da OS e na lista de relatórios.
- **Sem publicação:** o preview gera o PDF atual, mas não cria `os_documentos`, não envia e-mail, não publica ao cliente e não altera o status da OS.
- **PDF final:** o link “Baixar PDF publicado” continua aparecendo somente após o encerramento e a publicação.
- **Testes:** geração de preview por técnico não participante, resposta `application/pdf`, ausência de documento publicado e status inalterado.

## 9.6.0-dev.23 — feedbacks 23–25: legendas, PDF e envio AJAX — 2026-11-05 — develop

- **Legendas colaborativas:** qualquer prestador ativo pode adicionar fotos e alterar legendas de fotos existentes sem assumir a OS, pela seção colaborativa.
- **PDF sem página de erro:** em OS ativa, a tela não mostra mais link para um PDF indisponível; exibe “Documento anterior” e “Após encerrar”. O link de PDF/e-mail/nota só aparece quando a OS está encerrada.
- **Feedback sem sair da página:** o envio usa AJAX, fecha o diálogo, limpa o rascunho e mostra um aviso na página atual. Em erro, o diálogo permanece aberto com a mensagem.
- **Servidor JSON:** `/feedback` responde JSON quando recebe `X-Requested-With: XMLHttpRequest` ou `Accept: application/json`, mantendo a confirmação HTML para navegadores sem JavaScript.
- **Testes:** envio AJAX, edição de legenda por técnico não responsável, ausência de link de PDF em OS ativa e regressões de feedback/OS.

## 9.6.0-dev.22 — feedbacks 9–22: YAML, orçamento, OS rápida e fotos — 2026-11-05 — develop

- **YAML sem dependência do nome:** a importação de cliente e serviço não exige mais extensão `.yaml/.yml` no nome do arquivo; o conteúdo é validado e erros aparecem na própria tela, com orientação para `ERR_UPLOAD_FILE_CHANGED`.
- **Orçamento mais completo:** validade em dias e condições/observações opcionais no formulário e no PDF.
- **OS rápida sem formulário automático:** após criar, o prestador vê “OS aberta com sucesso” com link para abrir depois, em vez de cair no formulário de preenchimento.
- **Fotos sem assumir a OS:** qualquer prestador ativo pode adicionar fotos e legendas por um formulário colaborativo; a responsabilidade da OS não muda. A edição de legendas existentes continua com o responsável.
- **Identificação da OS:** a tela mostra o número da OS e o identificador interno do link (`/os/{id}`), reduzindo a confusão entre OS-0023 e `/os/25`.
- **Feedback com estado de envio:** o diálogo mostra “Enviando...” ou “Aguardando IA...” e o auto-refresh permanece pausado, evitando a sensação de congelamento.
- **Testes:** importação YAML sem extensão, orçamento com validade/condições, OS rápida com tela de sucesso, fotos por técnico não responsável e regressões de feedback/OS.
- **Fora do MAIN:** correções apenas em `develop`; o MAIN permanece em `9.6.0-dev.20`.

## 9.6.0-dev.21 — API financeira somente leitura — 2026-11-05 — develop

- **API `/api/v1`:** expõe o financeiro do prestador autenticado — resumo, lançamentos de OS, rateios como técnico secundário e repasses a pagar — em JSON, com valores em centavos inteiros, datas ISO, paginação por cursor e OpenAPI 3.1.
- **Tokens Bearer:** tokens `autoseg_fin_...` são criados pelo CLI `api_financeiro.py`, armazenados apenas como SHA-256, revogáveis, com escopo `financeiro:read` e auditoria em `api_acessos`. A API não usa cookie de sessão e é somente leitura.
- **Contrato Unix:** endpoints pequenos, `curl`/`jq`, erros JSON, CORS opcional por `AUTOSEG_API_ORIGINS`, limite de 120 req/min por token e documentação em `docs/features/API_FINANCEIRO.md`.
- **Testes:** `test_api_financeiro.py` cobre saúde/OpenAPI, token ausente/inválido/revogado, prestador inativo, isolamento entre prestadores, centavos, paginação sem duplicatas, filtros, repasse em duas etapas, POST rejeitado e CORS.
- **Fora do MAIN:** a API fica apenas em `develop`; a `main` permanece com as correções de feedback da versão `9.6.0-dev.20`.

## 9.6.0-dev.20 — correções dos feedbacks e caixa da empresa — 2026-11-05 — develop

- **Repasses em duas etapas:** o finalizador registra o envio integral (sem editar o valor já definido no rateio); o técnico secundário confirma o recebimento no próprio financeiro. O valor só entra como recebido após essa confirmação.
- **Ordenação das OS:** a página **Ordens de serviço ativas** ganhou ordenação por situação (iniciadas e pendentes primeiro), data, cliente ou número.
- **Feedback direto:** o envio mostra uma confirmação simples, sem abrir a tela de triagem; a resposta da IA, quando pedida, continua visível.
- **Rascunho da OS:** o auto-refresh é pausado durante o envio de formulários e o botão **SALVAR RASCUNHO** mostra “SALVANDO...” para evitar a sensação de congelamento.
- **Caixa da empresa:** “saldo em caixa” passou a **saldo do controle** (capital − despesas, não saldo bancário), aportes ganharam **finalidade** e os R$ 130,00 iniciais foram registrados como gasto a detalhar no MAIN.
- **Testes:** `test_empresa_financeiro.py` (6), `test_feedback_portal.py` (21), `test_produtividade_rev07.py` (9), `test_rev12_correcoes.py` (26) e `test_autoseg_melhorias.py` (9).

## 9.6.0-dev.19 — caixa da empresa dentro de Materiais e estoque — 2026-11-05 — develop

- **Aportes de investidores:** a aba **Materiais e estoque** ganhou a seção **Caixa e investimentos**, com aporte de capital por investidor, sem devolução automática e sem misturar com receita de OS.
- **Despesas da empresa:** compras de material, despesas com API (incluindo DeepSeek) e outras despesas, com data, categoria, valor e observação.
- **Material sem SKU:** o campo SKU do cadastro de material passou a ser explicitamente opcional; o caixa não exige SKU, quantidade ou movimentação de estoque.
- **OS apenas como referência:** uma compra de material pode ser vinculada a uma OS, mas isso não altera custo, estoque, financeiro ou PDF da OS.
- **Saldo separado:** o resumo mostra capital investido, despesas e saldo; receitas de OS continuam no Financeiro e não entram nesse saldo.
- **Histórico preservado:** lançamentos são arquivados, não apagados.
- **Banco aditivo:** nova tabela `empresa_movimentos`, criada com `CREATE TABLE IF NOT EXISTS`; nenhuma tabela existente foi alterada.
- **Testes:** `test_empresa_financeiro.py` cobre aportes, despesas, saldo, vínculo com OS sem alterar custo, validação e arquivamento.
- **Documentação:** `docs/features/CAIXA_EMPRESA.md`.

## 9.6.0-dev.18 — feedback não se perde no auto-refresh da página de OS — 2026-11-04 — develop

- **Sem `meta refresh`:** a página **Ordens de serviço ativas** deixou de usar `<meta http-equiv="refresh" content="20">`, que recarregava a página inteira e fechava o diálogo de feedback. O servidor agora emite um marcador inerte (`meta name="autoseg-auto-refresh"`).
- **Refresh controlado:** `portal.js` agenda a atualização e a pausa enquanto o diálogo de feedback estiver aberto, houver campo de formulário em uso ou a aba estiver oculta. Ao fechar o diálogo ou sair do campo, o contador recomeça.
- **Rascunho local:** o texto e a marcação de “resposta por IA” são salvos em `sessionStorage` a cada alteração e restaurados após recarregar ou navegar na mesma aba. Se o diálogo estava aberto, ele reabre com o texto.
- **Limpeza segura:** o rascunho só é apagado após envio bem-sucedido (redirecionamento para `/feedback/{id}`) ou ao clicar em **Cancelar**. Erro de validação preserva o texto.
- **Testes:** `test_portal_feedback.js` cobre pausa do refresh, restauração do rascunho, limpeza após envio, preservação após erro e cancelamento; `test_feedback_portal.py` verifica o HTML servido sem `http-equiv` e executa o teste Node.
- Nenhuma alteração de banco ou de schema.

## 9.6.0-dev.17 — IA do feedback via OpenCode com provedor trocável — 2026-11-04 — develop

- **Provedor padrão em DEV:** a resposta opcional do feedback agora usa o chat local do OpenCode por meio do endpoint transitório `/api/session/{id}/generate`; a pergunta e a resposta não são acrescentadas ao histórico da conversa.
- **Troca de API sem tocar no fluxo:** a camada `feedback_ai.py` isola os provedores `opencode` e `deepseek` atrás de `generate(prompt)`. Para usar outra API, basta implementar o provedor, registrá-lo em `PROVIDERS` e mudar `AUTOSEG_FEEDBACK_AI_PROVIDER`; rotas, banco, UI e anonimização não mudam.
- **Configuração local:** o chat e a URL do OpenCode ficam em `feedback_ia.local.json`, ignorado pelo Git; `feedback_ia.example.json` documenta o formato. A senha do serviço é lida de `~/.config/opencode/service.json` ou de variável de ambiente e nunca é gravada no banco ou nos logs.
- **Fallback preservado:** sem sessão, sem credencial, com provedor desconhecido, IA desligada ou serviço indisponível, o feedback continua salvo e a tela mostra um aviso amigável.
- **UI neutra:** o diálogo e o detalhe falam em “resposta da IA”, sem acoplar o texto ao nome do fornecedor.
- **Testes:** `test_feedback_portal.py` cobre o endpoint transitório do OpenCode, autenticação Basic, seleção do DeepSeek, provedor desconhecido, IA desligada e ausência de sessão.
- **Documentação:** `docs/features/FEEDBACK_PORTAL.md`, `docs/features/OPEN_TELEMETRY.md`, `docs/feedback/PENDENCIAS_DEV.md`, `docs/HUMAN_CENTERED_DECISIONS.md` e `telemetry/README.md` atualizados.
- Nenhuma alteração no MAIN; implementação apenas em `develop`. Revisão jurídica/privacidade continua necessária antes de produção.

## 9.6.0-dev.16 — canal de feedback do Portal do Prestador — 2026-11-04 — develop

- **Botão global:** todas as páginas autenticadas do Portal do Prestador mostram **“Dê um feedback”**, com diálogo sem sair da tela; o Portal do Cliente e a página de login não exibem o canal.
- **Registro de suporte:** cada envio guarda prestador, página (somente o caminho, sem query string), dispositivo, navegador, sistema, hash da sessão e IP minimizado. O IP completo só é gravado com `AUTOSEG_FEEDBACK_IP_MODE=full`.
- **Resposta opcional por IA:** uma caixa permite pedir resposta do assistente configurado. A IA recebe apenas o texto anonimizado e o mapa de telas em `feedback_conhecimento.md`; sem configuração o feedback é salvo e a resposta fica indisponível.
- **Anonimização:** CPF, CNPJ, e-mail, telefone, CEP, endereço e nomes após rótulos comuns são removidos antes de qualquer chamada externa. O texto original permanece apenas no banco local para revisão humana.
- **Triagem humana:** administradores acessam `/feedback/recebidos`, filtram por situação, leem o contexto técnico e marcam **Pendente na DEV** apenas quando o relato identifica um problema ou melhoria real. A classificação da IA é uma sugestão.
- **Backlog documentado:** `/feedback/pendencias.md` exporta somente relatos anonimizados e notas de triagem; o processo está em `docs/feedback/PENDENCIAS_DEV.md`. Nenhum item é commitado ou implantado automaticamente.
- **Telemetria opcional:** eventos `feedback_open`, `feedback_submit`, `feedback_ai_reply`, `feedback_ai_error` e `feedback_triage` usam o contrato existente e só são gravados com `AUTOSEG_TELEMETRY=local`. A telemetria geral continua desligada por padrão.
- **Sem efeitos colaterais:** feedback não cria OS, financeiro, estoque, e-mail ou nota fiscal; as tabelas são aditivas e o recurso pode ser desligado removendo as rotas.
- **Testes:** novo `test_feedback_portal.py` cobre botão/diálogo, ausência no portal do cliente, anonimização, IA mockada, triagem, exportação, permissões e telemetria local.
- **Documentação:** `docs/features/FEEDBACK_PORTAL.md`, `docs/feedback/PENDENCIAS_DEV.md`, `docs/features/OPEN_TELEMETRY.md` e `telemetry/README.md` atualizados.
- Nenhuma alteração no MAIN; implementação apenas em `develop`. Revisão jurídica/privacidade ainda necessária antes de produção.

## 9.6.0-dev.15 — orçamento com vários itens e YAML — 2026-11-04 — develop

- **Vários serviços:** o orçamento agora aceita uma lista de serviços do catálogo, cada um com sua quantidade, em vez de um único serviço.
- **Materiais adicionais:** permite incluir vários materiais do estoque, com quantidade, preço de venda ativo e total calculado no servidor.
- **PDF itemizado:** o orçamento mostra serviços, materiais adicionais, subtotais e total; serviços continuam incluindo os materiais do próprio catálogo.
- **YAML de orçamento:** novo `modelo_orcamento.yaml` com instruções detalhadas, dicionário de campos, limites, garantias, erros comuns e exemplos; o envio deve conter somente `versao` e `orcamento`, como o modelo de relatório.
- **Garantias:** o YAML não aceita preços, não cria OS, não cria financeiro e não movimenta estoque; IDs/nomes são resolvidos apenas em registros ativos.
- **Busca de cliente:** o campo `busca-cliente-os` agora funciona também no orçamento, reutilizando o mesmo filtro do formulário de OS.
- **Testes:** novo `test_orcamento_multiplo.py` cobre múltiplos serviços/materiais, PDF, YAML, modelo oficial e rejeições de segurança.
- Nenhuma alteração no MAIN; implementação apenas em `develop`.

## 9.6.0-dev.14 — busca de cliente no orçamento — 2026-11-04 — develop

- **Novo orçamento:** a escolha do cliente agora tem o mesmo campo de busca já usado no formulário de OS (`busca-cliente-os`).
- **Lista completa:** mantém até 500 clientes ativos para não esconder clientes; a produção tem 461 ativos. A busca filtra a lista inteira.
- **Sem componente novo:** a busca local e o seletor continuam sendo os mesmos já implementados no portal do prestador.
- **Sem mudança no MAIN:** implementação apenas em `develop`; servidor e banco de produção intactos.

## Documentação — plano de correção financeira pela UI — 2026-11-04

- **Problema:** hoje não é possível apagar/consolidar uma OS concluída nem ajustar rateio depois da conclusão pela interface.
- **Proposta:** no desktop GTK, duas ações explícitas — **Ajustar rateio** na OS correta e **Anular OS** na duplicada.
- **Segurança:** sem exclusão física de histórico; anulação preserva OS, eventos, PDFs e auditoria; portal do prestador continua somente leitura.
- **Próxima mudança DEV:** contratos de backend, depois diálogos GTK e teste de regressão em cópia do banco.
- Nenhuma mudança de comportamento ou no servidor de produção.

## 9.6.0-dev.13 — status Iniciada ao começar o atendimento — 2026-11-04 — develop

- **Novo status:** ao clicar em `INICIAR OS` ou `Iniciar atendimento`, a OS passa de `Aberta`/`Pendente` para **`Iniciada`** na mesma transação.
- **Status ativos:** `Iniciada` é tratada como OS ativa em listas, atribuição, rascunhos, fotos, importação YAML, encerramento e financeiro; não entra no histórico até ser concluída ou cancelada.
- **Dashboards:** desktop e Portal do Prestador mostram a contagem de OS iniciadas; o histórico separa iniciadas de abertas/pendentes.
- **Dados existentes:** OS já iniciadas que continuavam como `Aberta` são migradas de forma idempotente. OS marcadas explicitamente como `Pendente` permanecem pendentes.
- **Contrato:** testes cobrem a transição, a idempotência e o encerramento a partir de `Iniciada`.
- Nenhum valor, PDF, e-mail ou lançamento financeiro é alterado por esta mudança.

## Documentação — nome do produto e contrato de CLI — 2026-11-04

- **CLI sem ambiguidade:** `workaholic` fica como CLI; a GUI usa `workaholic-gtk` (ou o nome próprio do app, se houver nome separado). Nada de symlink que abre GUI ou CLI conforme o ambiente.
- **Nome do produto:** documentada a preocupação de colisão — “workaholic” tem centenas de repositórios no GitHub, usuário/organização já existentes e conotação negativa; PyPI estava livre, mas isso não basta.
- **Critérios e candidatos:** critérios de nome, shortlist exploratória e necessidade de checagem de marca/domínio antes da decisão.
- **Officina:** avaliado como candidato forte para o app GTK; PyPI livre, mas já existe organização `officina` no GitHub, cerca de 614 repositórios e necessidade de checagem de marca/Flathub.
- **App ID:** `io.github.burtvadr.Officina` é válido se o repositório for `github.com/burtvadr/Officina` e o Metainfo usar o mesmo ID. Flathub não exige GitHub; exige um ID reverse-DNS e controle do domínio/namespace.
- **Conta pessoal:** `burtvadr` é a conta pessoal do desenvolvedor; o repositório dedicado do Officina ainda será criado. O ID é provisório até o repositório e o Metainfo existirem.
- **Separação sugerida:** `workaholic` fica como CLI do motor; `officina` seria o app GTK; `autoseg` o flavor de segurança — se as checagens passarem.
- **Decisão adiada:** o nome do app genérico/plataforma continua TBD; Workaholic permanece como nome do motor/protótipo por enquanto.
- Nenhuma mudança funcional.

## Documentação — proposta de telemetria aberta e esqueleto — 2026-11-04

- **Feature request:** `docs/features/OPEN_TELEMETRY.md` descreve telemetria opcional, desligada por padrão, para diagnóstico e investigação de abuso/segurança.
- **Privacidade:** somente campos declarados; sem fingerprint oculto (canvas/WebGL/áudio/fontes), sem conteúdo de formulário, cookies, tokens, teclado ou screenshots.
- **Controles:** opt-in do administrador, aviso ao usuário, retenção curta, acesso auditado, exportação/deleção e modo local-first.
- **Realidade legal:** o documento diferencia fingerprinting legal com base/transparência de condutas de alto risco; inclui tiers 0–3 e uma lista de itens proibidos por política, não por serem automaticamente crimes.
- **Esqueleto:** pacote `telemetry/` com contratos, allowlist, sanitização de URL, truncamento/hash de IP e sink no-op; **não integrado** aos portais ou ao GTK.
- Nenhuma coleta ou transmissão de dados foi ativada.

## Documentação — plano de migração para inglês — 2026-11-04

- **Plano:** `docs/ENGLISH_MIGRATION_PLAN.md` com fases, regras de compatibilidade, glossário e definição de pronto.
- **Código x usuário:** código e docs de desenvolvedor em inglês; interface continua em português via tradução.
- **Compatibilidade:** rotas, banco, variáveis de ambiente, YAML e lançadores antigos continuam funcionando.
- **Sem renomear e migrar na mesma mudança:** uma PR para a fatia, outra para o nome.
- Nenhuma mudança funcional.

## Documentação — decisões centradas em humanos — 2026-11-04

- **Processo de decisão:** novo `docs/HUMAN_CENTERED_DECISIONS.md` registra que a IA não decide sozinha questões irreversíveis de produto/arquitetura e que decisões dependentes de valor humano ficam adiadas até haver evidência de uso, pilotos ou protótipos.
- **Perguntas adiadas:** as três decisões pendentes (primeira fatia, contrato de módulos e cadência de migração) foram registradas com critérios de evidência e gatilhos de revisão.
- **Feedback humano:** o processo inclui observação de uso real, histórico de suporte, pilotos, protótipos e comparação com softwares bem feitos; telemetria não substitui valores humanos. O guia prático está em `docs/USER_FEEDBACK_GUIDE.md`.
- **Agentes:** `AGENTS.md`, playbook, ledger e template de PR atualizados para impedir decisões irreversíveis tomadas apenas por IA.
- Nenhuma mudança funcional.

## Documentação — fluxo de agentes e migração incremental — 2026-11-04

- **Regra para agentes:** novo `AGENTS.md` com a regra “uma mudança, um delta de plataforma”, preservação de comportamento, Workaholic fit check e definição de pronto.
- **Playbook:** `docs/PLATFORM_MIGRATION_PLAYBOOK.md` com receita de migração por fatia, testes de caracterização, adaptadores, rollback e anti-padrões.
- **Ledger:** `docs/PLATFORM_MIGRATION_LEDGER.md` com o estado real das fatias (clientes parcialmente migrado; catálogo, OS, financeiro e prestadores ainda legados).
- **GitHub:** templates de pull request e issue para registrar o delta de plataforma e o fit no Workaholic.
- Nenhuma mudança funcional nesta rodada.

## Documentação — visão de produto, plataforma genérica e 0BSD — 2026-11-04

- **Visão de produto:** novo `docs/PRODUCT_VISION.md` descreve a separação entre o motor Workaholic, o app GTK genérico, a distribuição AUTOSEG e os módulos de locale/fiscal.
- **Licença:** `LICENSE` raiz com 0BSD para o código original do projeto; o Workaholic mantém sua licença própria em `workaholic/LICENSE`.
- **README:** novo `README.md` com estado atual, direção, licença e links de documentação.
- **Workaholic:** status registrado explicitamente — não abandonado, mas hoje integrado apenas na fatia de clientes.
- **Sem mudanças funcionais:** nenhuma tela, regra de negócio ou dado foi alterado nesta rodada.

## 9.6.0-dev.12 — remoção completa do app Tkinter — 2026-11-03 — develop

- **Removido o frontend Tkinter:** `app.py`, `desktop_v9.py`, `desktop_operacoes.py`, `test_tk_v6.py`, `test_tk_v9.py` e `INICIAR_AUTOSEG_TK.command` saíram do código.
- **Bootstrap:** `autoseg_app.py` agora inicia o `gtk_app.py` (GTK4/libadwaita), sem `tkinter`.
- **Lançadores e instaladores:** `INICIAR_AUTOSEG_DEV.command`, `VERIFICAR_AUTOSEG_DEV.command`, `ATUALIZAR_AUTOSEG_V9_4.command` e `INSTALAR_REV04_DEV.command` foram ajustados para não exigir mais `app.py`.
- **Instaladores obsoletos:** removidos `INSTALAR_AUTOSEG_V9_2_BASE.command` e a variante `2`, que instalavam o frontend antigo.
- **Nenhum módulo ativo importa `tkinter`.** O GTK é o único frontend desktop.
- Documentação ativa atualizada para não indicar fallback Tkinter.

## 9.6.0-dev.11 — numeração consistente em PDFs, e-mails e notas — 2026-11-03 — develop

- **PDF publicado:** o nome do arquivo passa a usar o número da OS (`OS-0014_relatorio_v2.pdf`) em vez do ID interno (`OS_16...`). O conteúdo do PDF já usava o número correto.
- **E-mail e nota fiscal:** os rascunhos `.eml` e `.json` também usam o número da OS no nome.
- **Chamado de origem:** a tela da OS rotula o protocolo do chamado como “Chamado de origem”, deixando explícito que ele não é o número da OS.
- **Migração:** os PDFs já publicados no MAIN foram renomeados e os caminhos em `os_documentos` atualizados, preservando o SHA-256.
- Teste novo em `test_rev12_correcoes.py`.

## 9.6.0-dev.10 — financeiro por produção do prestador — 2026-11-03 — develop

- **A receber por prestador:** os KPIs “A receber” e “Recebido” agora mostram somente a parcela própria do prestador. Nas OS que ele finalizou, é o valor bruto menos os rateios dos técnicos secundários; nos rateios em que ele é secundário, é a parcela dele.
- **Tabela transparente:** os lançamentos das OS finalizadas passam a exibir “Valor bruto” e “Minha parcela” lado a lado.
- **Técnico secundário:** a aba financeira mostra “Minha produção como técnico secundário”, com valor, repasses já registrados e restante.
- Teste HTTP novo em `test_rev12_correcoes.py` cobrindo finalizador e técnico secundário.

## 9.6.0-dev.9 — custo real de material em garantia — 2026-11-03 — develop

- **Custo x valor cobrado:** novo campo “Custo real dos materiais (R$) — interno, não cobrado” na OS (GTK e Portal do Prestador). Ele registra o custo do material sem entrar no total cobrado nem no financeiro.
- **Garantia sem cobrança de material:** o valor cobrado dos materiais pode ficar em `0,00`; o custo real fica registrado para controle interno e a OS conclui com total `0,00`, sem lançamento financeiro.
- **Migração aditiva:** coluna `ordens_servico.custo_materiais` (REAL, padrão 0), sem alterar OS existentes.
- **OS-0021 do MAIN:** material com custo interno de R$ 75,50 e valor cobrado `0,00`; o lançamento de R$ 75,50 a receber foi removido.
- Testes atualizados em `test_rev12_correcoes.py`.

## 9.6.0-dev.8 — orçamento avulso, garantia 0,00 e YAML autoexplicativo — 2026-11-03 — develop

- **Situação e pagamento sem padrão:** o formulário da OS (GTK e Portal do Prestador) abre com “Selecione a situação” e “Selecione a forma de pagamento”. Não existe mais “Concluída” nem “PIX” pré-selecionados; salvar sem escolher é bloqueado.
- **Orçamento na seção de clientes:** botão “Novo orçamento” na lista e no cadastro do cliente. Escolhe cliente, serviço/produto do catálogo e quantidade; gera o PDF padrão de orçamento **sem criar OS** e sem lançamento financeiro.
- **Garantia com mão de obra 0,00:** o valor zero é aceito e não é tratado como campo vazio. A OS conclui com material cobrado e mão de obra gratuita; o financeiro recebe apenas o valor dos materiais.
- **Garantia total:** quando o total é 0,00, a OS conclui sem criar lançamento financeiro de R$ 0,00.
- **YAML:** modelo `modelo_relatorio_os.yaml` reescrito com instruções completas, dicionário de tags, regras de materiais, cenário de garantia, checklist e exemplos. Material com `quantidade` ou `valor_unitario` nulo continua sendo rejeitado, agora com mensagem que orienta a remover o item ou informar o dado.
- **Exemplo corrigido:** `relatorio_os_preenchido_corrigido.yaml` remove os materiais sem quantidade/preço e mantém apenas o cabo, que tem valores válidos.
- Testes novos em `test_rev12_correcoes.py`.

## 9.6.0-dev.7 — status acima do rascunho e PDF/e-mail de OS pendente — 2026-11-03 — develop

- **Portal do Prestador:** o status da OS agora aparece logo acima dos botões de ação (inclusive o SALVAR RASCUNHO), na ordem da página.
- **OS pendente:** ao registrar a situação "Pendente", o relatório parcial é publicado em PDF e enviado ao(s) destinatário(s) selecionado(s), com assunto e corpo indicando "atendimento pendente".
- Teste novo em `test_rev12_correcoes.py`.

## 9.6.0-dev.7 — cabeçalho do Portal do Cliente — 2026-11-03 — develop

- **Portal do Cliente:** o topo passa a exibir apenas a logo AUTOSEG, maior, sem os textos "Gestão de Serviços" e "AUTOMAÇÃO E SEGURANÇA · Portal de Serviços". O Portal do Prestador permanece como estava.

## 9.6.0-dev.7 — composição declarativa no YAML — 2026-11-03 — develop

- **Composição sob demanda:** o YAML da OS pode trazer um bloco `composicao` (pai + `filhos`). Só os componentes declarados aparecem no PDF; os demais deixam de ser exibidos com R$ 0,00.
- **Hierarquia:** o pai pode ser valor ou percentual do total; os filhos podem ser valor, percentual do pai ou `residual: true` para fechar o valor do pai.
- **Agente:** o bloco pode ser preenchido por um agente a partir da explicação de alto nível da OS, sem configuração manual.
- **Encerramento:** a composição declarativa é preservada ao concluir a OS (não é sobrescrita pelo cálculo padrão).
- **PDF:** filhos recuados e em cinza sob o componente pai; total continua batendo com o valor da OS.
- Testes novos em `test_composicao.py` e `test_importacao_yaml.py`.

## 9.6.0-dev.7 — CNPJ e documento nos PDFs — 2026-11-03 — develop

- **Relatório PDF:** mostra o CNPJ do prestador responsável; se ele não tiver CNPJ cadastrado, usa o CNPJ principal da AUTOSEG (23.864.393/0001-87). Também exibe o CPF/CNPJ do cliente.
- **Orçamento PDF:** passa a exibir o CPF/CNPJ do solicitante (cliente), além do CNPJ da AUTOSEG.
- **Nota fiscal:** o bloco "Não precisa de nota fiscal" ficou em destaque na tela de finalização da OS; a conclusão exige NF anexada ou essa opção marcada.

## 9.6.0-dev.7 — nota fiscal confiável, YAML tolerante e PDF — 2026-11-03 — develop

- **Nota fiscal (correção crítica):** removido o descarte silencioso da nota fiscal no envio de e-mail. Antes, se o arquivo da nota não pudesse ser lido, o e-mail seguia sem o anexo e ainda assim era marcado como enviado. Agora, quando há nota fiscal associada à OS, ela **deve** ser anexada; falha de leitura interrompe o envio e registra `falhou` com erro claro — nunca um falso sucesso.
- **Transparência do envio:** o corpo do e-mail agora informa explicitamente se a nota fiscal foi anexada ou se nenhuma nota fiscal foi associada à OS, e a montagem verifica existência/leitura/validade dos PDFs antes de enviar.
- **Importador YAML (relatório):** `materiais: null`, `materiais: []` e `materiais` ausente são aceitos como ausência de lançamento financeiro. Valor não-lista gera `O campo "materiais" deve ser uma lista.`; materiais incompletos geram erros específicos e numerados (`Material N: campo "…" não informado/inválido`). Nenhum campo ausente recebe zero automático e descrições em texto livre não viram lançamentos financeiros.
- **PDF do relatório:** fotografias maiores (largura útil da página, proporção preservada, maior resolução) e tabela de composição mantida unida com a linha TOTAL para evitar linha órfã na página seguinte.
- **Nota fiscal opcional:** a OS só pode ser concluída se houver nota fiscal anexada ou se o prestador marcar "Não precisa de nota fiscal". Após a conclusão, é possível anexar/atualizar a NF e reenviar o e-mail.
- **Composição de valor:** adicionada a "Taxa de deslocamento" (R$ 50) e "valor mínimo de visita" ajustado para R$ 250. Os PDFs passam a exibir "Composição do valor (valor estimado)".
- Testes novos em `test_importacao_yaml.py`, `test_gmail_integracao.py`, `test_pdf_relatorio.py` e `test_rev12_correcoes.py`.

## 9.6.0-dev.6 — nota fiscal e imagens no reenvio — 2026-11-03 — develop

- **Nota fiscal após a conclusão:** a página de detalhes da OS passa a permitir anexar/atualizar a nota fiscal mesmo depois de encerrada (responsável ou administrador), para que ela fique fixa no arquivamento da OS.
- **Reenvio de e-mail:** ao reenviar, o relatório é republicado com as imagens/legendas atuais e a nota fiscal anexada é incluída no e-mail — a nota e as imagens não se perdem mais no reenvio.
- Teste novo em `test_rev12_correcoes.py` (NF após conclusão + reenvio com NF).

## 9.6.0-dev.6 — ícone de desenvolvimento — 2026-11-03 — develop

- **Ícone DEV:** o ambiente de desenvolvimento passa a usar `icone_devel.png` (selo dos PDFs, favicon dos portais e ícone da janela). O MAIN continua usando `icone.png`. Há fallback automático para o outro ícone quando um deles não existir.

## 9.6.0-dev.6 — cadastro de CNPJ do prestador — 2026-11-03 — develop

- **Integrações e pagamentos:** o campo "Provedor de envio" passou de texto livre para um menu suspenso com as opções válidas (vazio, SMTP, Microsoft Graph, Gmail API, Outro), evitando "Configuração inválida" por valor digitado fora da lista.
- O salvamento agora separa o erro do **CNPJ** (título "CNPJ inválido") do erro de **configuração** (título "Configuração inválida"), deixando claro qual campo precisa de atenção.
- O CNPJ do prestador continua validado (dígitos verificadores) e aceita o mesmo CNPJ em vários prestadores.

## 9.6.0-dev.6 — envio para múltiplos destinatários em DEV — 2026-11-03 — develop

- **E-mail de conclusão:** removido o desvio de DEV que substituía todos os destinatários por um único e-mail de teste (`email_teste_dev`). Agora todos os destinatários selecionados recebem o e-mail no campo **Para**, também no ambiente de desenvolvimento. A proteção contra domínios de teste (`example.*`, `.invalid`, `.test`, `.localhost`) continua ativa.
- Teste novo em `test_gmail_integracao.py` garante que, em DEV, a lista de destinatários não é colapsada.

## 9.6.0-dev.6 — composição financeira e destinatários — 2026-11-03 — develop

- **Composição do valor (relatório e orçamento):** a composição agora respeita a mão de obra e os materiais reais da OS/serviço. Antes, os componentes padrão (hora técnica, taxa de visita, custos e margem) eram aplicados por cima e, quando o total era menor, tudo era proporcionalizado, gerando percentuais incorretos.
  - `composicao.calcular` recebe `mao_obra_centavos`; quando informado, materiais e mão de obra são os valores reais e os demais componentes ficam zerados (o residual fecha o total).
  - OS 100% materiais → Materiais 100% e demais componentes R$ 0,00; idem para 100% mão de obra e composições mistas.
  - Valores em centavos com `Decimal` e soma dos componentes exatamente igual ao total.
  - Aplicado na gravação da OS, no encerramento, no catálogo, no orçamento e no recálculo em lote.
- **Destinatários:** o e-mail de conclusão passa a expor todos os destinatários selecionados no campo **Para** de um único e-mail (removido o envio em BCC e o texto que o mencionava).
- Testes novos em `test_composicao.py` (100% materiais, 100% mão de obra, misto e com sobra) e em `test_rev12_correcoes.py` (composição 100% materiais nos PDFs de relatório e orçamento).

## 9.6.0-dev.6 — rascunho, nota fiscal e destinatários — 2026-11-03 — develop

- **Rascunho do Portal Prestador:** corrigida a recuperação automática dos campos ao reabrir a OS (a referência ao prestador logado estava indefinida, o que descartava o rascunho em silêncio). Agora os campos preenchidos — inclusive via YAML — reaparecem corretamente.
- **Destinatários e e-mail adicional:** a seleção de destinatários e o campo “E-mails adicionais” voltam marcados/preenchidos ao reabrir a OS, e a lista final da conclusão usa todos os selecionados (cliente, síndico, administradora e extras), não apenas o cliente.
- **Nota fiscal:** anexar o PDF deixa de recarregar a página e de apagar o rascunho — os campos já preenchidos são preservados. O botão “SALVAR RASCUNHO” também grava a nota fiscal anexada no mesmo envio.
- Testes novos em `test_rev12_correcoes.py` (rascunho, destinatários, nota fiscal).

## 9.6.0-dev.6 — correções de portal, PDF, CNPJ e exclusões — 2026-11-03 — develop

- **Portal Prestador — OS rápida:** busca por nome, CNPJ/CPF, cidade ou e-mail e lista em cartões, no mesmo padrão do Portal Cliente; a OS continua nascendo **Aberta**.
- **PDF do relatório:** corrigida a exibição literal de `<b> TOTAL <B> ...` na composição do valor; o total agora é impresso em negrito normal.
- **CNPJ do prestador:** campo no cadastro desktop e em Integrações e pagamentos; o mesmo CNPJ pode repetir entre prestadores. O relatório mostra o CNPJ do responsável apenas quando válido e diferente do principal (23.864.393/0001-87); o orçamento usa sempre o CNPJ principal.
- **Orçamento PDF:** faixa preta atrás do logo para dar contraste às partes brancas/transparentes do `logo.png`.
- **Desktop GTK4:** botões “Excluir material” e “Excluir serviço”. Material com histórico é arquivado para preservar auditoria; sem histórico é removido. Serviço sai do catálogo e OS antigas mantêm os valores gravados.
- **Serviços e valores (Portal Prestador):** botão de exclusão do serviço, com confirmação.
- **E-mail:** e-mails adicionais digitados manualmente entram na lista final (sem serem ignorados); envios para domínios de teste/exemplo (`example.*`, `.test`, `.invalid`, `.localhost`) são bloqueados antes da rede para evitar devoluções.
- Testes novos em `test_rev12_correcoes.py`; `test_rev09_fluxo_os.py` não dispara mais envios reais.

## 9.6.0-dev.6 — ajustes de interface e status — 2026-11-03 — develop

- Chamado PJ rápido sem login com busca e cartões de condomínios/empresas (mesmo padrão da página com cadastro).
- Botão de chamado rápido em destaque na página inicial do Portal Cliente.
- OS de chamado de cliente nasce **Aberta**; só fica **Pendente** ao ser iniciada e encerrada como pendente.
- Portais mobile-first: tabelas empilhadas, sem rolagem horizontal, navegação e formulários verticais.
- Rascunho único no Portal Prestador; upload de NFS-e abaixo das fotos.
- NFS-e anexada no e-mail automático e no `.eml`; botão de reenvio com anexos.
- Em DEV, envios automáticos são centralizados em `dados_teste/email_teste.txt` (evita example.com).
- Logins DEV restaurados com os 8 usuários/senhas fornecidos.


## 9.6.0-dev.6 — REV12 — 2026-11-02 — develop

- **Portal Cliente:** alteração da própria senha (senha atual, nova e confirmação; hash PBKDF2; invalidação das demais sessões).
- **Chamados de condomínio:** nome completo e telefone do solicitante obrigatórios, normalizados e gravados no chamado e na OS; identificação conservadora (apenas a própria conta é reconhecida automaticamente; divergências seguem para análise da AUTOSEG).
- **E-mail — múltiplos destinatários:** checkboxes para cliente, síndico e administradora/imobiliária, e-mails adicionais, deduplicação, registro da lista final e envio em BCC.
- **PDFs:** logo.png no cabeçalho e icone.png como selo em todas as páginas do relatório técnico e do orçamento.
- **Nota fiscal:** upload de PDF por OS, validação, deduplicação por SHA-256, download autorizado (prestador, síndico/gestor e cliente PF) e anexo no e-mail.
- **E-mail:** dados bancários do prestador responsável (favorecido, banco, agência, conta, Pix e texto livre), sem dados fixos.
- **Desktop GTK4:** botão “Atribuir síndico/gestor” na aba Clientes, reutilizando o mesmo núcleo do Portal Prestador (`cadastros_v9.atribuir_responsavel`).
- Testes novos em `test_rev12_melhorias.py` e ampliação de `test_gmail_integracao.py`.

Pendente: homologação manual no Mac, envio real de e-mail e promoção para main.

## 9.6.0-dev.5 — REV11 — 2026-11-02 — develop/main

- **Interface GTK4/libadwaita** adotada como padrão (branch `feature/gtk4-libadwaita` mesclada): `gtk_app.py`, `gtk_comum.py`, `gtk_dialogos.py`, mesmo backend/banco/regras.
- **Envio automático e assíncrono do relatório por Gmail** ao concluir a OS:
  - `gmail_service.enviar_relatorio_os_concluida` envia o PDF em thread separada e registra status/message_id em `produtividade_email`.
  - Acionado no Portal Prestador e nos desktops GTK4 e Tkinter.
  - Bibliotecas do Google importadas sob demanda; falhas não travam a interface e ficam registradas.
  - `AUTOSEG_GMAIL_DESATIVADO=1` desliga o envio para testes sem rede.
- Inicializadores GTK4 em `/Applications` (clique único): `AUTOSEG.app` (main) e `AUTOSEG DEV.app` (develop).
- Testes: `test_gmail_integracao.py` (enviado, falhou, desativado) e smoke do app GTK4 no macOS.

Pendente: homologação manual do envio real (destinatário válido) e liberação de versão estável.


## 9.6.0-dev.4 — REV10 — 2026-11-02 — develop

- **SALVAR RASCUNHO** agora aparece em destaque no topo e no rodapé do formulário da OS no Portal Prestador, além do desktop. Salva diagnóstico, execução, resultado, relatório, materiais, valores, observações, fotos e legendas sem alterar o status.
- **Legendas de fotos antes da finalização:** cada foto nova mostra prévia e campo “Legenda da foto”; fotos já salvas no rascunho reaparecem com a legenda editável.
- `os_anexos` recebeu `chave` e `sha256`; reenvios do mesmo arquivo atualizam a legenda em vez de duplicar a foto no SQLite.
- A legenda é associada à foto por chave/hash e incluída no PDF final (validado com extração de texto do PDF).
- O rascunho persiste após reiniciar o servidor e é recuperado ao reabrir a OS; teste visual com Chrome/Playwright e teste HTTP automatizado.
- Rodapé do Portal Prestador passa a exibir a versão em execução.

Pendente: homologação manual do usuário e promoção para main.

## 9.6.0-dev.3 — REV09 — 2026-11-02 — develop (validação local)

Fluxo de OS separado em ações independentes:

- **ASSUMIR OS** atribui responsável e horário sem iniciar o atendimento.
- **EM ROTA** registra o deslocamento em `os_deslocamentos`, é idempotente, aparece no Portal Prestador e no Portal Cliente e pode ser cancelado pelo responsável.
- **INICIAR OS** registra o início efetivo, encerra o deslocamento ativo e permite retomada de OS pendente. O fluxo antigo "INICIAR OS — ASSUMIR AUTOMATICAMENTE" foi removido.
- **SALVAR RASCUNHO** no Portal Prestador e no desktop, com persistência dos campos técnicos, materiais, valores e fotos em `produtividade_rascunhos` e `os_rascunhos_web`. Recuperação após reiniciar o servidor testada.
- Portal Prestador exibe Em rota na lista; Portal Cliente exibe Em rota na lista e no detalhe.
- Importação/rateio financeiro e financeiro pessoal do REV07 preservados, incluindo bloqueio de rateio fora da conclusão.
- Importação YAML, pré-visualização, desfazer, catálogo e estoque mantidos dos REV06/REV08.
- Testes novos em `test_rev09_fluxo_os.py` cobrem assumir, em rota, início, rascunho após reinício, conclusão, pendência, cancelamento, YAML sem gravação, PDF autorizado e bloqueio de terceiros.

Pendente: homologação manual das interfaces no Mac, envio Gmail real (depende de OAuth), nota fiscal (somente rascunho) e itens ainda parciais descritos em `ROADMAP.md`.

## 9.6.0-dev.2 — REV08 — 2026-11-02 — develop (validação local pendente)

- Importação YAML de materiais transacional, sem gravações parciais em falhas.
- Materiais de Serviços e Valores integrados ao catálogo único sem alterar estoque ou preços já cadastrados.
- Busca normalizada por nome/código e alertas de estoque negativo/mínimo na interface desktop.
- Prévia e desfazer YAML no Portal Prestador, com proteção dos campos preenchidos na aba; fotos não enviadas continuam exigindo novo upload.
- Correção de teste antigo do Portal Cliente e bloqueio de disparo acidental de Gmail durante descoberta de testes.
- Testes unitários novos; nenhum banco real foi acessado na validação.

Pendente: homologar interfaces no Mac; não estão implementados integralmente os 78 requisitos. Não atualizar main.

## 9.6.0-dev.1 — REV08 — 2026-11-02 — develop

Introduzidos metadados de versão, versionador com controle de branch, testes, CI no develop e checklist de 78 requisitos.

Estado: PREPARAÇÃO. Não há migrações SQLite ou mudanças nos módulos operacionais. Os 78 requisitos continuam em homologação pendente. O branch main não deve ser atualizado antes de testes.

Bloqueio: reconciliar alterações e arquivos não publicados do Mac antes de sincronizar o código remoto com o DEV local.
