# AUTOSEG — Changelog

## 9.6.0-dev.73 — preparação da primeira publicação pública — 2026-11-09 — develop

- **Documentação — site único:** auditoria do estado atual e arquitetura-alvo de conta/vínculo, prestadora/tenant, política por objeto e OS anônima. O AUTOSEG é a primeira prestadora de serviço do ecossistema Officina; site e GTK atuais são as sementes do Officina Web/GTK. Sem mudança de código nesta fase. Ver `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` e `docs/planning/OFFICINA_WEB_AND_GTK.md`.
- **Documentação — contrato web/GTK:** telas, campos, ações, permissões, validações e view models compartilhados; widgets, navegação e diálogos continuam nativos em cada plataforma. Adoção incremental, começando por uma lista de leitura; sem framework de UI e sem reescrita. Ver `docs/planning/WEB_GTK_SHARED_CONTRACT.md`.
- **Processo — gates de mudança:** o `AGENTS.md` passa a exigir ator, permissão, objeto/tenant, teste negativo, fonte única da regra, dinheiro canônico e delta de plataforma antes de codar. O roadmap congela expansão de plataforma até os P0 de autorização/OS/dinheiro; o ledger lista os gargalos concretos da migração.
- **Documentação — arquitetura de segurança:** documento vivo em `docs/security/SECURITY_ARCHITECTURE.md` com ativos, atores, fronteiras de confiança, sessões, autorização, exposição de rede, arquivos, dinheiro, segredos, logs, backup, resposta a incidentes, invariantes e riscos conhecidos. Não é certificação nem pentest; o estado atual e o alvo são separados.
- **Identidade — contrato read-only:** `identity.py` resolve prestador/cliente por e-mail ou CPF/documento, expõe `Membership` com papel e converte para `Principal`; `policy_shadow` passa a delegar a esse contrato. Sem schema, login, sessão ou UI nova; a próxima fatia é `accounts`/`account_links` atrás de flag.
- **Identidade — accounts opt-in:** `accounts.py` cria `accounts`, `account_identifiers`, `account_links` e `login_policy`; a migração legada é idempotente, transacional e tem `dry_run` sem tocar no banco original. Uma conta = um vínculo; o tenant inicial é `autoseg`. Ainda não altera login, sessão ou UI.
- **Login unificado — serviço:** `auth.py` autentica por e-mail, CPF, telefone ou nametag conforme a política, com fallback para os logins legados, verificação de hash, rejeição de conta inativa e mensagens sem enumeração. Não cria cookie, sessão, rota ou tela; a ligação ao site fica para a próxima fatia.
- **Financeiro em abas:** Resumo, A receber, Recebidos, Repasses e Empréstimos (último), com botão “Emprestar” no topo de A receber. Confirmar recebimento atualiza o item e os KPIs sem recarregar a página; empréstimos usam “Abrir” para o detalhe.
- **OS — finalizador financeiro:** quando um administrador conclui uma OS de outro responsável, o finalizador financeiro passa a ser o **responsável atual**, não o admin que clicou. O admin continua registrado como ator na auditoria. Se o novo responsável tinha uma parcela antiga de secundário, ela é absorvida no restante e não é contada duas vezes. Corrige a OS 261109003: João Lucas recebe R$ 100,00 e João Paulo, responsável, recebe R$ 1.600,00.
- **OS — taxa de visita opcional:** o formulário permite escolher **Cobrar** ou **Não cobrar** a taxa mínima de visita. Com **Não cobrar**, os custos percentuais continuam incidindo sobre o valor final e a mão de obra recebe o restante. Exemplo: total R$ 230,00, materiais R$ 89,00 e três custos de 10% = R$ 23,00 cada; mão de obra R$ 72,00. A escolha e o valor final negociado ficam gravados e o formulário reabre com os mesmos valores.
- **OS — composição itemizada:** a composição declarativa aceita itens customizados com nome e valor; o formulário preserva os itens e o PDF mostra o investimento detalhado. A OS 261109003 foi completada com o relatório da porta metálica e total de R$ 1.700,00.
- **OS — rascunho:** a composição declarativa salva como texto JSON pelo auto-save é normalizada ao abrir a OS; se o rascunho estiver inválido, a composição já gravada é preservada. Corrige o erro ao reabrir a OS 261109003 depois da troca de responsável.
- **CLI operacional:** `update` reinicia apenas o processo do site e deixa de encerrar túneis que aparecem como clientes das mesmas portas.
- **Composição:** o valor final é autoritativo; quando a hora técnica fica abaixo do mínimo configurado, a OS salva com aviso em vez de ficar em R$ 0,00.
- **Auto-save:** o erro real do servidor aparece na tela e o `portal.js` é versionado na URL para evitar cache antigo.
- **Site único — arquitetura-alvo:** documentado o fim dos portais separados de cliente/prestador, com OS rápida sem login e login único com detecção de papel. Esqueleto de permissões por objeto em `officina/application/object_policy.py`, sem integração; os portais atuais permanecem até a migração.
- **CLI operacional:** `./autoseg start|stop|status site|server|tunnel|all` para a MAIN e `./autoseg-dev ...` para DEV, com PIDs e logs em `~/Library/Application Support/AUTOSEG/cli`. Os comandos antigos continuam funcionando.
- **Credenciais:** senhas DEV removidas dos scripts visuais; agora vêm de `AUTOSEG_DEV_PROVIDER_PASSWORD` e `AUTOSEG_DEV_CLIENT_PASSWORD`.
- **Identidade comercial:** CNPJ e WhatsApp são configuráveis por `AUTOSEG_COMPANY_CNPJ` e `AUTOSEG_WHATSAPP`; o repositório público usa valores fictícios.
- **Privacidade:** IP privado, usuário local e nomes pessoais removidos de scripts e documentação.
- **Imagens:** captura GTK com contagem operacional removida do repositório público; metadados C2PA/XMP removidos dos logos.
- **Dados de teste:** e-mails e nomes padronizados para domínios `example`/`exemplo`.
- **CI:** workflows atualizados para o monorepo (`officina`, `flavors`, `tests`, `workaholic`) e para a suíte completa.
- **Histórico público:** a primeira publicação usará um único commit inicial; o histórico de desenvolvimento permanece no repositório privado de arquivo.
- **OS:** abrir, em rota e iniciar salvam o cliente escolhido no formulário antes de validar.
- **OS — ações rápidas:** Em rota e Iniciada aplicam com um clique, na mesma linha do preview do PDF; viram Cancelar rota quando o deslocamento está ativo. No celular ficam empilhados. Ícones SVG dos botões têm tamanho fixo e não invadem o layout.
- **OS pendente:** mesmo com início antigo registrado, Em rota e Iniciar OS voltam a aparecer; Iniciar registra novo início e muda a OS para Iniciada.
- **Permissões:** administradores têm as mesmas ações rápidas (Em rota, Iniciada, Cancelar rota) em OS de outro responsável, sem trocar a responsabilidade.
- **Financeiro:** prazo de recebimento com vencimento e destaque vermelho de atrasado.
- **OS pendente:** envia e-mail automático aos destinatários marcados e oferece reenvio com seleção de contatos e e-mail extra.
- **Fotos:** girar 90° atualiza a imagem na hora, sem recarregar a página.
- **Rascunho:** valores zerados e total negociado são restaurados corretamente ao reabrir a OS.
- **OS — situação:** o diálogo “Confirmar situação” não repete a situação atual nem oferece Em rota/Iniciada; reabrir para Aberta é exclusivo de administradores, e as demais ações ficam nos botões da ficha.
- **Meu Auto Financeiro:** contas a pagar separadas em individuais e compartilhadas, com formulários distintos; conta compartilhada exige participante e mostra convite quando falta integrante.
- **Empréstimos MAF no AUTOSEG:** cartão no financeiro do prestador, vínculo por código enviado ao e-mail, criação por e-mail, comprovante do credor opcional a qualquer momento, aceite independente do devedor, devolução com comprovante Pix e aceite/recusa do credor. Valores pessoais ficam fora do total da empresa.
- **Empréstimos no saldo pessoal:** o principal entra no extrato MAF do credor e do devedor e nas colunas pessoais A receber/Recebidos do AUTOSEG; nunca entra no caixa da empresa.
- **Financeiro unificado:** administradores veem o caixa da empresa dentro da aba Financeiro, com empréstimos por último; funcionários veem apenas o próprio financeiro.
- **PDF:** OS Pendente com R$ 0,00 vira relatório de diagnóstico, sem composição nem bloco financeiro; Pendente com valor vira orçamento, com composição e valores. O e-mail usa assunto e corpo correspondentes.
- **OS — valores:** o auto-save passa a persistir mão de obra, materiais e total negociado na própria OS, e não apenas no rascunho, para PDF e e-mail refletirem o que foi digitado. O servidor devolve a nova versão da OS e o formulário a reutiliza, evitando que a segunda alteração seja recusada pela verificação de concorrência.
- **Rateio e colaboradores:** nova aba depois de Mídias, disponível em qualquer OS, antes ou depois da conclusão. Responsável/finalizador ou administrador define técnicos secundários e valores; o colaborador vê somente leitura. Administrador pode incluir a si mesmo quando não for o finalizador; o finalizador recebe o restante automaticamente. A conclusão preserva o rateio já definido e o total da OS não pode ficar abaixo do valor rateado.
- **OS — composição:** o valor do serviço é autoritativo. Sem valor final informado, o total é mão de obra + materiais, e a composição apenas distribui esse valor; visita, percentuais e custos não são mais somados por cima. O campo “Total negociado” passa a ser exibido como **Valor final da OS**.
- **PDF:** a seção **Materiais utilizados** só aparece quando há materiais; a linha de materiais zerada sai da composição e as seções seguintes são renumeradas.
- **OS — solicitação original:** administradores passam a editar a solicitação original acima de Diagnóstico, em Situação e relatório. O mesmo texto aparece no chamado de origem e no PDF; a alteração é auditada. Para não administradores, o chamado de origem continua marcado como somente leitura e o campo editável não é exibido.
- **PDF — garantia:** o texto configurado como Garantia passa a ser uma seção numerada antes da composição do valor. Sem garantia, a composição continua sendo a seção 03.
- **Buscas:** páginas que já têm busca no servidor não exibem um segundo filtro de tabela.
- **Fotos:** miniaturas são geradas no upload e ganham cache privado versionado, reduzindo o tempo de abertura da OS.
- **Testes:** 361 testes OK, 1 skip.

## 9.6.0-dev.72 — feedbacks da DEV: cliente, encerramento e erros inline — 2026-11-08 — develop

- **Cliente na OS:** o formulário completo usa busca por nome com `datalist`, igual ao campo de material. Um nome novo cria cliente marcado como incompleto para completar depois.
- **Lista de clientes:** registros com `dados_incompletos=1` aparecem como **Dados incompletos** em vez de **Ativo**.
- **Encerramento:** a conclusão exige forma de pagamento, inclusive no núcleo usado pelo GTK e pelo site.
- **Destinatários:** nova opção **Não precisa de destinatário** permite concluir a OS sem e-mail e sem exigir endereço válido.
- **Erros:** login e formulários passam a enviar por `fetch`; falhas aparecem em toast/inline, preservando os campos digitados. O login ganhou mensagem inline e mantém o e-mail.
- **Layout:** os campos de atendimento, pagamento, urgência e mão de obra foram reorganizados para eliminar a área vazia abaixo de “Atendido por”.
- **Testes:** 343 testes OK, 1 skip; regressões novas para cliente incompleto, busca/criação, pagamento, destinatário e login.

## 9.6.0-dev.71 — dados fora do repositório — 2026-11-08 — develop

- **Banco fora do repositório:** servidor em produção usa `/var/lib/autoseg` (Linux) ou `/Library/Application Support/AUTOSEG` (macOS); DEV usa `<dados do usuário>/server-dev`; o GTK local usa `<dados do usuário>/local`.
- **Sem fallback para o repositório:** `base_dir()` não aponta mais para a raiz do projeto; importar `banco` diretamente nunca cria `dados.db` no Git.
- **DEV:** banco, anexos, PDFs, rascunhos, notas, logs, túneis e `composicao.yaml` migrados de `data/` para `~/Library/Application Support/AUTOSEG/server-dev`.
- **Comando:** `./autoseg paths` mostra os caminhos efetivos e os overrides ativos.
- **Permissões:** bancos e arquivos auxiliares do SQLite passam a `600`; pastas novas são criadas com `700`.
- **Scripts DEV:** geração de cadastros e reset de credenciais resolvem o banco pelo `runtime_config` e recusam rodar sem `AUTOSEG_DEV=1`.
- **Documentação:** novo `docs/operations/DATA_STORAGE.md` com caminhos, permissões, variáveis e backup.
- **Testes:** 338 testes OK, 1 skip; cobertura nova para as pastas de dados e para `configure_local`/`configure_server`.

## 9.6.0-dev.70 — raiz limpa e dados separados — 2026-11-08 — develop

- **Raiz:** não há mais módulos Python nem launchers soltos.
- **Comando único:** `./autoseg {dev|app|server|site|stop|check|test}`.
- **Launchers:** `.command`/`.sh` movidos para `scripts/autoseg/`.
- **Dados locais:** bancos, anexos, logs, rascunhos, notas, relatórios, túneis e configuração local movidos para `data/` (ignorado pelo Git).
- **DEV:** servidor e site usam `data/dados_teste/autoseg_teste.db`.
- **Testes:** 335 testes OK, 1 skip.

## 9.6.0-dev.70 — separação real de pacotes — 2026-11-08 — develop

- **Código organizado:** módulos genéricos foram para `officina/core`, `officina/application`, `officina/integration`, `officina/repositories` e `officina/telemetry`.
- **AUTOSEG:** portais, GTK, API, auth, feedback, fiscal, e-mail, túneis e integrações foram para `flavors/autoseg/modules`.
- **Web do flavor:** `portal.js` e o site estático foram para `flavors/autoseg/web`.
- **Testes:** todos movidos para `tests/`, com descoberta padronizada por `unittest discover`.
- **Launchers:** atualizados para os novos módulos; instaladores obsoletos removidos.
- **Raiz:** não há mais módulos Python soltos.
- **Testes:** 335 testes OK, 1 skip.

## 9.6.0-dev.70 — início da organização do monorepo — 2026-11-08 — develop

- **Novo layout:** criados `officina/` e `flavors/autoseg/` com documentação de limites.
- **AUTOSEG:** marca, configurações padrão e modelos YAML movidos para `flavors/autoseg/`.
- **Caminhos:** logo/ícones, políticas, numeração, completude, composição e modelos atualizados com fallback compatível.
- **Empacotamento:** AppImage e documentação de empacotamento apontam para os novos caminhos.
- **Documentação:** novo `docs/REPOSITORY_LAYOUT.md`; README e índice atualizados.
- **Testes:** 335 testes OK, 1 skip.

## 9.6.0-dev.67 — corrige login após validação de origem — 2026-11-08 — develop

- **Login:** navegadores que enviam `Origin: null` em formulários same-origin voltam a entrar; a checagem de origem continua bloqueando origens externas.
- **Teste:** regressão coberta para login com `Origin: null`.
- **Testes:** 335 testes OK, 1 skip.

## 9.6.0-dev.66 — endurecimento conforme auditoria — 2026-11-08 — develop

- **API desktop:** exige admin nas rotas de prestadores, estoque, empresa, composição, organizações e escritas financeiras; exige `AUTOSEG_DESKTOP_TOKEN` quando o bind não é loopback.
- **Clientes:** redefinir senha legada, desativar, excluir e mesclar ficam restritos a admin; organizações e vínculos também.
- **Limites:** corpo pré-autenticação reduzido para 64 KB e timeout de socket de 15 s nos três servidores.
- **IP real:** rate limit e auditoria usam `CF-Connecting-IP`/`X-Forwarded-For` quando a conexão é loopback.
- **Sessão legada:** troca de senha invalida sessões antigas do cliente.
- **PII:** removido o JSON com contatos de todos os clientes do formulário de OS; contato é buscado por cliente.
- **Operação:** permissões 700/600 nos diretórios operacionais, refs de backup com PII removidas e `git gc` executado.
- **Testes:** 335 testes OK, 1 skip.

## 9.6.0-dev.65 — associar cliente em OS de chamado — 2026-11-08 — develop

- **OS com “Cliente a definir”:** mesmo quando veio de um chamado, mostra o seletor “Cliente da OS” para associar o cliente real.
- **Pagamento em branco:** editar uma OS criada sem forma de pagamento não obriga mais a preencher o pagamento.
- **Testes:** 335 testes OK, 1 skip.

## 9.6.0-dev.64 — busca automática, composições e tema automático — 2026-11-08 — develop

- **Clientes e serviços:** uma única busca, sem botão; filtra automaticamente enquanto digita.
- **OS:** status diferentes de Pendente e Cancelada exigem cliente definido, não “Cliente a definir”.
- **Popup de situação:** sem a opção Cancelada e com ações alinhadas ao padrão dos diálogos.
- **Tema automático:** corrigido para seguir o sistema no login e no site; a detecção saiu do script inline bloqueado pela CSP.
- **Composição dos valores:** o seletor saiu de Materiais e foi para Situação e relatório; as composições (Total da OS e Visita mínima) agora são editáveis em Composição de valores.
- **Cliente na OS:** seletor em largura total acima de “Atendido por”, com resumo automático de e-mail, telefone e síndico.
- **Testes:** 335 testes OK, 1 skip.

## 9.6.0-dev.63 — abertura rápida, tema no login e mescla de clientes — 2026-11-08 — develop

- **OS rápida:** removidos “Atribuir prestador” e “Forma de pagamento”; a OS abre sem pagamento definido e o criador fica responsável.
- **Cliente na OS rápida:** busca automática ao digitar, sem botão “Buscar”; nome novo cria cliente com dados incompletos.
- **Mescla de clientes:** admin pode mesclar dois cadastros duplicados; OS e financeiro passam para o destino e a origem fica inativa.
- **Login:** segue automaticamente o tema do sistema, sem botões; a preferência manual fica em Configurações após entrar.
- **Testes:** 335 testes OK, 1 skip.

## 9.6.0-dev.62 — feedbacks abertos da DEV — 2026-11-08 — develop

- **Nova OS em uma tela:** cliente é opcional e pode ser associado depois; a OS usa o cadastro provisório “Cliente a definir”.
- **Duplicidade:** aviso para OS do mesmo cliente criada nos últimos 2 minutos, com opção explícita de criar outra e registro no histórico.
- **Cancelamento:** botão próprio, só com motivo e número da OS; não exige relatório técnico nem os demais campos.
- **Pendente:** não pede e-mail, não envia relatório e pode voltar de Iniciada para Pendente, encerrando o início do atendimento.
- **Relato técnico:** deixou de ser obrigatório para confirmar situação; para concluir basta o Serviço executado.
- **Responsável:** quem cria a OS já fica responsável; admin vê um select de responsável na Identificação e a troca já transfere, sem botão separado.
- **Situação da OS:** o bloco fixo saiu do formulário; “Confirmar situação da OS” abre um popup com Aberta, Em rota, Iniciada, Pendente, Concluída e Cancelada.
- **Abas da OS:** “Fotos e legendas” virou **Mídias**; Fechamento, nota fiscal e confirmação ficam nessa aba, e “Aplicar composição padrão” foi para Situação e relatório.
- **Fotos:** removido “+ Adicionar mais fotos”; cada foto existente ganhou **Remover foto** ao lado de Girar 90°.
- **Tema claro:** fundo neutro, botões cinza em vez de pretos e textos secundários mais legíveis.
- **Configurações:** nova página com tema e cor de acento salvos na conta, válidos só para o site; os controles saíram da barra lateral e Feedback/Sair ficaram menores, lado a lado.
- **Filtros:** selecionar uma opção já aplica o filtro; o botão “Filtrar” foi removido e a regra ficou registrada na documentação.
- **Popup de situação:** alinhado ao padrão visual dos demais diálogos.
- **YAML da OS:** botão **Importar relatório YAML** à esquerda de **Exportar relatório em YAML**; a exportação leva o modelo completo, com instruções, exemplo e os dados atuais da OS.
- **Total previsto:** a linha e a composição do valor acompanham “Aplicar composição padrão” na aba Situação e relatório.
- **Confirmação da OS:** o botão **Confirmar situação da OS** volta a ficar visível em todas as abas, mantendo Fechamento e nota fiscal em Mídias.
- **Fotos e legendas:** salvam automaticamente ao digitar ou selecionar arquivos; o botão “Salvar fotos e legendas” foi removido.
- **Abas da OS:** Identificação, Situação e relatório, Materiais, Fotos e legendas; ícones alinhados.
- **Materiais:** o campo Material pesquisa e autocompleta o estoque; ao escolher um item, quantidade, unidade e valor são preenchidos.
- **Tema:** modo automático pelo tema do host, claro/escuro e sete cores de acento.
- **Composição de valores:** editor estruturado por componente no lugar do YAML seco; YAML permanece em opção avançada.
- **Início do GTK:** ordens recentes com abertura direta, alinhado ao site.
- **Testes:** 335 testes OK, 1 skip; scripts de aceitação passando.

## 9.6.0-dev.61 — comando do site DEV — 2026-11-07 — develop

- **Site DEV separado:** `INICIAR_SITE_DEV.command` sobe Portal do Cliente em 8865 e Portal do Prestador em 8866.
- **Mesmo banco:** usa `dados_teste/autoseg_teste.db`, sem conflitar com a API headless do GTK em 8766.
- **Documentação:** README e HANDOFF explicam a diferença entre site, servidor e GTK.
- **Estado:** site, servidor e app GTK podem rodar juntos em DEV.

## 9.6.0-dev.60 — paridade de telas entre GTK e site — 2026-11-07 — develop

- **Site ganhou telas do GTK:** Prestadores, Estoque, Caixa da empresa e Composição de valores, visíveis apenas para admin.
- **GTK ganhou telas do site:** Notas fiscais e E-mails, com lista por OS e preparação do arquivo.
- **Paridade de prestador:** o conjunto de funções do prestador agora está espelhado; Conexões fica como configuração do cliente desktop.
- **Interface do site:** o desenho atual é o padrão; a documentação deixou de tratá-lo como experimental.
- **Testes:** novos testes HTTP das telas admin e teste da lista de relatórios no AppService; 316 testes OK, 1 skip.

## 9.6.0-dev.59 — visual do login e paridade de papéis — 2026-11-07 — develop

- **Logo removida do GTK:** a imagem não aparece mais no Início nem na tela de login.
- **Usuário logado:** nome, papel e e-mail ficam em linhas separadas com reticências; o botão Sair fica abaixo, sem cortar o texto.
- **Paridade documentada:** novo `docs/SURFACE_PARITY.md` compara GTK, Portal do Prestador e Portal do Cliente.
- **Regra de papel:** admin, funcionário/prestador e cliente; a permissão pertence ao papel, não à superfície.
- **Lacuna explícita:** a API identifica o prestador, mas ainda não aplica todas as regras admin × funcionário.
- **Testes:** 313 testes OK, 1 skip.

## 9.6.0-dev.58 — login oferece modo local e servidor — 2026-11-07 — develop

- **Escolha de modo:** a tela de login sempre mostra as opções **Local** e **Servidor**.
- **DEV:** abre com Servidor selecionado, mas permite escolher Local; o banco local só é criado/aberto ao escolher essa opção.
- **Sem banco local antecipado:** entrar direto no servidor não cria SQLite local.
- **Senha DEV:** `Prestador Alfa DEV` foi promovido a admin e teve a senha de teste redefinida; credenciais em `dados_teste/CREDENCIAIS_FICTICIAS_DEV.txt`.
- **Testes:** modos local/servidor, primeiro admin e sessão; 313 testes OK, 1 skip.

## 9.6.0-dev.57 — corrige crash da tela de login — 2026-11-07 — develop

- **Crash nativo corrigido:** `LoginWindow` usava `GtkWindow.set_child()` em um `Adw.ApplicationWindow`; libadwaita aborta na alocação de tamanho. Agora usa `set_content()`.
- **Diagnóstico:** relatórios de crash do macOS apontavam `adw_application_window_size_allocate`; a causa era a violação do contrato do `AdwApplicationWindow`.
- **Testes:** smoke/login local e servidor, logout e sessão; suíte mantém 313 testes OK, 1 skip.

## 9.6.0-dev.56 — login de prestador no GTK e sessão revogável — 2026-11-07 — develop

- **Login obrigatório:** o GTK abre na tela de login quando não há sessão válida.
- **Local ou servidor:** modo local usa conta do banco local; modo servidor usa `/api/v1/desktop/login`.
- **DEV servidor-only:** `AUTOSEG_DEV=1` não mostra a opção de banco local.
- **Primeiro admin local:** criação do primeiro administrador no modo local.
- **Identidade visível:** nome, e-mail e papel do prestador aparecem na barra lateral.
- **Logout:** revoga o token no servidor, apaga a sessão e volta ao login.
- **Sessão:** token revogável com validade de 12 h ou 30 dias com “Lembrar este dispositivo”; arquivo `0600`, sem senha.
- **API:** todas as rotas `/desktop` exigem Bearer token, exceto health e login.
- **Testes:** 313 testes OK, 1 skip; autenticação, token, logout, primeiro admin e arquivo de sessão.

## 9.6.0-dev.55 — modo DEV em servidor — 2026-11-07 — develop

- **API desktop:** `api_desktop.py` expõe clientes, OS, prestadores, financeiro, histórico, PJ, catálogo, estoque, caixa da empresa, composição e PDF.
- **Modo DEV:** `INICIAR_AUTOSEG_DEV.command` abre em modo servidor; `INICIAR_SERVIDOR_DEV.command` sobe a API com o banco de teste.
- **Sem banco local:** o GTK em modo servidor não cria nem abre o SQLite local.
- **DEV é servidor por padrão:** mesmo sem variável explícita, `AUTOSEG_DEV=1` usa `http://127.0.0.1:8766`.
- **Offline:** leituras degradam para listas vazias e a janela mostra banner de servidor indisponível; escritas falham sem fallback local.
- **Monitor:** verificação a cada 5 s avisa quando o servidor cai ou volta e recarrega os dados ao reconectar.
- **Conexões:** a opção “Banco local” desaparece no modo servidor e o endereço da API pode ser salvo e aplicado na hora.
- **Ações remotas:** assumir/iniciar OS, atribuir responsável, senha de cliente/prestador, PJ, PDF, catálogo, estoque e caixa passam pela API.
- **Testes:** 306 testes OK, 1 skip; smoke GTK offline e online.

## 9.6.0-dev.54 — documentação enxuta e organizada — 2026-11-07 — develop

- **Índice canônico:** `docs/README.md` concentra o que é atual.
- **Histórico separado:** readmes, revisões e planos antigos foram para `docs/archive/`.
- **Operação:** túnel, Gmail, Meu Auto Financeiro, banco de teste e YAML foram para `docs/operations/`.
- **Planejamento:** visão multicliente, sync, tenancy e guideline multiplataforma foram para `docs/planning/`.
- **Estado atual:** `docs/HANDOFF.md` foi reescrito como retomada curta; o histórico fica no changelog.
- **Limpeza:** removidas instruções de instaladores que não existem mais e versões antigas fixas.
- **Código:** `feedback_portal` lê o conhecimento em `docs/feedback/CONHECIMENTO.md`.

## 9.6.0-dev.53 — suíte limpa e scripts de aceitação atualizados — 2026-11-07 — develop

- **Suíte completa:** 301 testes, 0 falhas, 1 skip.
- **Três falhas antigas corrigidas:** `test_autoseg_http_novo`, `test_rev03_http` e `test_rev04_operacoes`.
- **Scripts atualizados:** `test_portal_v4.py`, `test_fluxo_v5.py`, `test_fluxo_v6.py`, `test_fluxo_v7.py`, `test_fluxo_cliente_v94.py` e `test_rev09_fluxo_os.py`.
- **Portal do cliente:** restaurada a constante `FUNCOES_RESPONSAVEL`, que causava HTTP 500 em `/cliente/vinculo/novo`.
- **Regressão:** `test_pf_pj_http` agora cobre o formulário de vínculo e o campo CNPJ.
- **Testes históricos:** `test_v9.py`, `test_v91.py`, `test_v92.py` e `test_v94_correcoes.py` ficam documentados como legado da arquitetura anterior à separação dos portais.

## 9.6.0-dev.52 — número único em todas as superfícies — 2026-11-07 — develop

- **Links do site:** `/os/<numero>` é canônico; `/os/<alias>` e `/os/<id>` redirecionam para ele.
- **Resolver central:** `repositorios/ordens.obter_por_token` aceita número, alias e id; número vence alias, alias vence id.
- **Formulários e ações:** detalhe, financeiro, histórico, PJ e anexos usam o número canônico.
- **PDF:** `<numero>.pdf`; relatório publicado `<numero>_relatorio_vN.pdf`; sem `OS_` e sem id.
- **E-mail:** assunto, corpo e nome do `.eml` usam o número.
- **GTK:** tabelas, diálogos e títulos exibem `numero_os`.
- **Testes:** `test_numero_publico.py` (2 OK), `test_rev12_correcoes.py` (47 OK, 1 skip), `test_pdf_relatorio.py` (8 OK), `test_numeracao*.py` (12 OK).

## 9.6.0-dev.51 — migração da numeração na DEV de teste — 2026-11-07 — develop

- **Migração real na DEV:** 17 OS de `dados_teste/autoseg_teste.db` convertidas para `YYMMDDNNN`; backup criado antes.
- **Números somente dígitos:** `261107001`, sem `OS-`.
- **Aliases:** números antigos preservados em `os_numero_alias`; documentos e referências históricas continuam localizáveis.
- **Estado de migração:** `numeracao_estado.ativo=1`; `banco.proximo_numero_os` usa o novo motor nesse banco.
- **MAIN intocada:** 23 registros continuam em `OS-00xx` até a janela de migração.
- **Ferramentas:** `numeracao_migracao.py`, `scripts/migrar_numeracao_os.py` e `test_numeracao_migracao.py`.
- **Testes:** 41 OK na suíte dirigida.

## 9.6.0-dev.50 — fundação da numeração configurável de OS — 2026-11-07 — develop

- **Política declarativa:** `numeracao.yaml` define modo, fuso, formato de data, sequência, letras, UUID, template custom e guarda de relógio.
- **Fuso padrão:** `America/Sao_Paulo`; a data da OS é a data local de criação.
- **Sequência:** engine transacional em `numeracao.py`, sem `MAX+1`, com limite diário configurável e erro claro ao esgotar.
- **Relógio:** atraso em relação à última OS emitida é rejeitado por padrão; modo `avisar` gera warning.
- **Ainda não ligado:** a criação real de OS continua no gerador antigo; ligar antes da migração criaria números misturados.
- **Testes:** `test_numeracao.py` (8 OK).

## 9.6.0-dev.49 — servidor e GUI do site separados na linguagem — 2026-11-07 — develop

- **Conceitos separados:** servidor de dados (`--api`) e GUI do site (`--site`). `--web` continua como alias antigo de `--site`.
- **Atalhos:** `INICIAR_SERVIDOR_API.command` sobe o servidor; `INICIAR_SITE.command` sobe a GUI do site. `INICIAR_SERVIDOR_WEB.command` foi removido.
- **GTK local limpo:** no modo local, botões e textos de portal/web ficam ocultos; a interface não menciona site nem o futuro Qt.
- **Conexões:** continua sendo a última aba; fala de servidor/API, não de site.
- **Transparência:** hoje a GUI do site ainda compartilha o processo com a API; a separação completa é uma fase posterior.
- **Testes:** smoke local-only e com portais: OK.

## 9.6.0-dev.48 — modo local limpo e Conexões no fim — 2026-11-07 — develop

- **Modo local explícito:** `INICIAR_AUTOSEG.command` e `INICIAR_AUTOSEG_DEV.command` fixam `AUTOSEG_WEB_ACCESS=0`; o app não sobe portais nem túnel.
- **Interface local:** no modo local, a página “Portal do cliente”, os links externos e os botões de túnel ficam ocultos. A home mostra “Site iniciado separadamente pelo terminal”.
- **Conexões no fim:** a aba **Conexões** é a última opção da barra lateral.
- **Teste de servidor:** continua disponível na aba Conexões, com health check e salvamento do endereço.
- **Testes:** smoke local-only e smoke com portais: OK.

## 9.6.0-dev.47 — tela de conexão no GTK — 2026-11-07 — develop

- **Nova página Conexão:** segue GTK4/libadwaita com `Adw.PreferencesPage`, `Adw.PreferencesGroup`, `Adw.EntryRow` e `Adw.ActionRow`.
- **Modo local:** explica que o banco é local e o site é iniciado separadamente.
- **Modo servidor:** campo de URL, teste de `/api/v1/health` e status com versão/modo.
- **Salvar endereço:** grava `connection.json` sem alterar o banco; o modo remoto de dados continua em preparação.
- **Sem login ainda:** a tela não finge autenticação; login/senha entram na fase N3/N4.
- **Testes:** smoke GTK local-only OK; página construída sem erro.

## 9.6.0-dev.46 — servidor headless e GTK local-only por padrão — 2026-11-07 — develop

- **Servidor no terminal:** `servidor_backend.py --api` sobe somente `/api/v1`, sem HTML, sem GTK e sem Cloudflare. `--web` sobe Officina Web + API.
- **API-only real:** novo `api_server.py` serve JSON e devolve 404 JSON para rotas não-API; não importa os portais HTML.
- **GTK limpo:** o padrão agora é local-only. O app não sobe os portais ao abrir; o site é iniciado separadamente.
- **Compatibilidade:** `AUTOSEG_WEB_ACCESS=1` e `INICIAR_AUTOSEG_COM_WEB.command` restauram o comportamento antigo.
- **Atalhos:** `INICIAR_SERVIDOR_API.command` e `INICIAR_SERVIDOR_WEB.command`.
- **Cloudflare:** continua opcional; o servidor não depende dele. Túneis são comodidade separada.
- **Testes:** `test_api_server.py` (2 OK), `test_web_access.py`, `test_application_service.py`, `test_runtime_config.py` (26 OK); smoke GTK local-only sem portas.

## 9.6.0-dev.45 — política de permissões em runtime — 2026-11-07 — develop

- **Política declarativa:** `policy.yaml` define papéis, permissões e escopo de campos (nome, telefone, endereço, e-mail, documento).
- **Runtime:** `application/policy.py` expõe `PolicyStore.reload()`, que troca a política ativa atomicamente sem reiniciar; política inválida mantém a anterior.
- **Field-level:** `employee` vê PII somente de cliente `involved`; mudar para `none` ou `own` é edição de YAML, não de código.
- **Testes:** `test_policy.py` cobre papéis, wildcard, escopo, reload em runtime e falha segura.
- **Ainda não ligado:** autenticação, UI de administração e enforcement no `AppService` continuam pendentes; a política é a fundação da Fase 0.

## 9.6.0-dev.44 — diálogo de OS sem SQL direto — 2026-11-07 — develop

- **GTK sem SQL:** `gtk_dialogos.py` deixou de executar SQL direto. Carregamento de OS, materiais, atendimento, encerramento, atribuição, responsáveis e formulários rápidos usam `AppService`/`LocalService`.
- **Escrita da OS:** a transação de salvar/atualizar OS, materiais, estoque, eventos, rascunho e encerramento foi movida para `application/os_write.py`, com teste de caracterização.
- **Leituras de contexto:** consultas dos diálogos foram para `application/desktop_context.py`, sem regra de negócio nova.
- **Números:** SQL direto em UI/HTTP caiu para 43 linhas, todas no site (`portal_prestador.py` e `servidor_web.py`). O shell GTK está em zero.
- **Testes:** 57 OK na suíte dirigida; smoke GTK local-only OK.

## 9.6.0-dev.43 — janela GTK sem SQL direto — 2026-11-07 — develop

- **Janela principal:** `gtk_app.py` não executa mais SQL direto. Histórico, PJ/chamados, prestadores, seletores de OS e lookup de cliente YAML usam `AppService`/`LocalService`.
- **Sem mudança de UI:** filtros, colunas, status, permissões visíveis e mensagens continuam iguais.
- **Separação:** o SQL restante do GTK está nos diálogos (`gtk_dialogos.py`), principalmente carregamento e gravação da OS, materiais e anexos.
- **Números:** SQL direto em UI/HTTP caiu de 117 para 86 linhas; `gtk_app.py` está em zero.
- **Testes:** 54 OK na suíte dirigida; smoke GTK local-only OK.

## 9.6.0-dev.42 — financeiro e OS ativas via AppService — 2026-11-07 — develop

- **Financeiro no contrato:** cartões, lista e marcação de recebimento do GTK usam `LocalService`; o SQL saiu de `gtk_app.py` para a camada de aplicação.
- **OS ativas no contrato:** a lista de OS abertas/iniciadas/pendentes usa `LocalService`, preservando filtro, ordem, colunas, responsável e aviso de dados incompletos.
- **Sem mudança de UI:** rótulos, valores, filtros e ações visíveis continuam iguais.
- **Separação:** o GTK agora usa o serviço em clientes, painel, Portal do Cliente, financeiro e lista de OS ativas. Escrita de OS, PJ, estoque e diálogos ainda acessam o banco diretamente.
- **Testes:** 53 OK na suíte dirigida; smoke GTK local-only OK. SQL direto em UI/HTTP caiu de 126 para 117 linhas.

## 9.6.0-dev.41 — campo de texto adicional configurável na OS — 2026-11-07 — develop

- **Campo genérico:** `ordens_servico.texto_adicional` guarda um texto livre por OS. O código não atribui significado fixo ao campo; ele pode conter garantia, condições de pagamento, aviso ou qualquer outro texto.
- **Configuração:** `texto_os.yaml` define `rotulo`, `titulo_pdf`, `padrao` e `ajuda`. O texto padrão começa vazio e pode ser decidido sem alterar código.
- **GTK e portal:** o campo aparece no cadastro/edição da OS, pré-preenhido com o padrão configurado em novas OS.
- **PDF:** a seção configurada aparece somente quando há texto, sem numeração fixa e sem hardcode de “garantia”.
- **Migração:** coluna aditiva e idempotente em `banco.criar_banco`; bancos antigos recebem o campo vazio.
- **Testes:** `test_texto_os.py` (4 OK), `test_pdf_relatorio.py` (7 OK) e testes relacionados (29 OK).

## 9.6.0-dev.40 — prazo de recebimento e atraso no financeiro — 2026-11-07 — develop

- **Prazo de recebimento:** cada lançamento em aberto no `/financeiro` ganhou um campo opcional de vencimento. O prazo fica salvo em `financeiro.vencimento` e pode ser alterado ou removido pelo finalizador ou administrador.
- **Atraso visível:** lançamentos em aberto com vencimento anterior a hoje aparecem como **Atrasado** em vermelho. Recebidos e cancelados não entram como atrasados.
- **Sem mudança de dinheiro:** valor, rateio, comissão, status de pagamento e cálculos não foram alterados; a mudança é de data e apresentação.
- **Auditoria:** alteração de vencimento gera evento na OS e registro em `portal_auditoria`.
- **Feedback:** FB-0001 do ciclo 2026-11 em `docs/feedback/PENDENCIAS_DEV.md`.
- **Testes:** `test_financeiro_vencimento.py` (4 OK) e testes relacionados de portal/financeiro (61 OK, 1 falha pré-existente em `test_autoseg_http_novo`).

## 9.6.0-dev.39 — fronteira de aplicação e portais fora do GTK — 2026-11-06 — develop

- **Separação GTK × servidor:** o GTK passa a consumir o contrato `AppService`; a primeira fatia cobre saúde, resumo do início, clientes (listar, obter e salvar) e os cartões/solicitações do Portal do Cliente. `LocalService` executa no processo, sem abrir porta HTTP.
- **Portais sob demanda:** `WebAccessManager` concentra o ciclo de vida do Portal do Prestador e do Portal do Cliente. O GTK não importa mais as classes dos portais no topo nem inicia servidores diretamente; o padrão continua com os portais ligados.
- **Modo local:** `--no-web` e `AUTOSEG_WEB_ACCESS=0` continuam abrindo o app sem portas 8765/8766. O botão do Portal do Cliente liga/desliga o servidor pelo manager.
- **Conexão futura:** `application/connection.py` registra modo local/remoto e URL do servidor. O modo remoto ainda expõe somente `health`; não há fallback silencioso para o banco local.
- **Comportamento preservado:** telas, rótulos, filtros, cálculos e HTML dos portais não mudaram. O SQL de OS/PJ/portal continua no lugar e será migrado em fatias seguintes.
- **Testes:** `test_application_service.py` + `test_web_access.py` + `test_integracao_clientes.py` + `test_repositorios_ordens.py` + `test_runtime_config.py` + `test_versionador.py` (41 OK); smoke GTK local-only e com portas efêmeras (exit 0); manager real com portais em portas efêmeras e `/api/v1/health` OK.

## 9.6.0-dev.38 — feedbacks 71–81, interface padrão e financeiro — 2026-11-06 — develop

- **Interface padrão:** o layout atual passa a ser o único em todas as páginas; a alternância de interface foi removida. O menu mobile abre em tela cheia, bloqueia a rolagem do fundo e mostra conta, ícones e textos maiores.
- **Rascunho automático:** o botão de salvar rascunho foi retirado. Alterações em campos, seleções, materiais e relatos são salvas automaticamente e restauradas ao reabrir a OS.
- **Administração:** administradores podem assumir e editar OS de outros prestadores, com auditoria; o botão Assumir OS aparece para eles.
- **Fechamento:** o bloco de situação do atendimento foi movido para a última aba (Situação e relatório / Fechamento).
- **Fotos:** o botão “+ Adicionar mais fotos” permanece disponível após o envio; a aba e a rolagem são preservadas.
- **Rateio pós-conclusão:** OS concluída ganhou a seção Rateio e repasses para incluir, editar ou remover parcelas de técnicos secundários, com validação do total e bloqueio depois de envio/confirmação.
- **Cancelamento de pagamento:** o financeiro ganhou “Cancelar pagamento”; o lançamento sai das listas e dos totais, preservando o histórico. A OS-0012 do Parque Ganzo foi cancelada manualmente.
- **Correções ao vivo:** horas e valores com vírgula são normalizados antes do cálculo; rascunhos antigos com vírgula foram convertidos; o menu mobile ficou compacto, sem nome duplicado e sem rolagem; a barra de ações não cobre mais o conteúdo; Em rota e Iniciar OS aparecem também no topo da OS.
- **Feedbacks 87–100:** menu mobile maior e sem rolagem; cancelamento de pagamento com confirmação e motivo; Meu Auto Financeiro removido do AUTOSEG; fluxo único de Nova OS com modal de sucesso; ações da OS alinhadas no mobile; abas com ícones em vez de números; histórico retrátil; textos redundantes de documentos/nota fiscal removidos; modelo de serviço apenas na criação; seletor de estoque com placeholder.
- **PDF de OS pendente:** o anexo do próximo e-mail passa a incluir o relatório técnico completo salvo no atendimento, além do resumo em três campos. OS concluídas, finalizadas e canceladas não foram alteradas.
- **Configuração de runtime:** portas, bind, TLS e caminhos-base dos portais passam por `runtime_config.py`, preservando os mesmos defaults (8765/8766 no MAIN, 8865/8866 no DEV), as mesmas variáveis de ambiente e o comportamento visual.
- **Clientes fora da UI:** as leituras de clientes do Portal do Prestador e a contagem do painel GTK passam por `integracao/clientes.py`; filtros, paginação, colunas e interface permanecem iguais.
- **Resumos de OS fora da UI:** painel, histórico, relatórios e solicitações do portal usam `repositorios/ordens.py`; consultas, ordem, limites e telas permanecem iguais.
- **GTK sem servidor web:** `--no-web` ou `AUTOSEG_WEB_ACCESS=0` abrem o app em modo local, sem as portas 8765/8766; o padrão continua com os portais ligados e os imports dos portais passam a ser sob demanda.
- **Testes:** `test_rev12_correcoes.py` (47 OK, 1 skipped), `test_feedback_portal.py` + `test_api_financeiro.py` + `test_meu_auto_financeiro.py` (40 OK), `test_produtividade_rev07.py` + `test_gmail_integracao.py` (16 OK), `test_autoseg_melhorias.py` + `test_composicao.py` + `test_pdf_relatorio.py` (41 OK).

## 9.6.0-dev.37 — Meu Auto Financeiro integrado ao Portal do Prestador — 2026-11-06 — develop

- **Meu Auto Financeiro:** módulo de finanças pessoais/familiares separado do Financeiro da empresa, disponível em `/auto-financeiro` no mesmo Portal do Prestador e no mesmo túnel. Usa a sessão do prestador; familiares entram por convite.
- **Menu:** item **Meu Auto Financeiro** no menu lateral, nos atalhos da Visão geral e no aplicativo GTK.
- **Dados próprios:** saldo individual/familiar, extrato, receitas e despesas, salários, contas compartilhadas, empréstimos, comprovantes e convites ficam em `meu_auto_financeiro.db`; os comprovantes em `meu_auto_financeiro_comprovantes/`.
- **Conciliação:** recebimentos AUTOSEG só entram quando o cliente é confirmado como recebido; repasses entram apenas no valor já confirmado pelo técnico secundário. OS com valor zero são aceitas na conciliação sem interromper a atualização. O módulo não altera OS, financeiro, estoque nem rateios do AUTOSEG.
- **Links públicos:** o painel de links mostra também a rota `/auto-financeiro` do portal do prestador.
- **Testes:** `test_meu_auto_financeiro.py` (6 OK), `test_rev12_correcoes.py` (44 OK, 1 skipped), `test_api_financeiro.py` (8 OK), `test_feedback_portal.py` (25 OK) e `test_rev05_seguro.py` (5 OK).

## 9.6.0-dev.36 — repasses somente após recebimento do cliente — 2026-11-06 — develop

- **Repasses a outros técnicos:** a seção só mostra OS cujo recebimento do cliente já foi confirmado pelo finalizador. Antes disso, o envio do repasse fica bloqueado.
- **Técnico secundário:** antes do recebimento do cliente, o item mostra **Aguardando cliente** e não exibe o botão de confirmação; depois do envio pelo finalizador, aparece **Confirmar que recebi**.
- **Navegação:** o número da OS na tabela de repasses agora é um link para abrir a OS correspondente.
- **Correção de dados:** o envio registrado indevidamente na OS-0012 antes do recebimento do cliente foi estornado e registrado no histórico; o valor será liberado normalmente após a confirmação do recebimento.
- **Testes:** `test_rev12_correcoes.py` (44 OK, 1 skipped), `test_produtividade_rev07.py` (9 OK) e `test_gmail_integracao.py` (7 OK).

## 9.6.0-dev.35 — CNPJ do prestador no PDF e nota fiscal automática — 2026-11-06 — develop

- **CNPJ no PDF:** o relatório usa o CNPJ do prestador responsável quando ele está no cadastro (`prestadores.documento`) ou nos dados bancários/cadastrais unificados; sem CNPJ, mantém o CNPJ padrão da AUTOSEG. O CNPJ explícito do cadastro tem prioridade.
- **Nota fiscal automática:** ao escolher o PDF em Fechamento, o arquivo é anexado automaticamente, sem botão extra, e o rascunho é salvo na mesma ação.
- **Fechamento:** após o anexo, a seção mostra “PDF anexado”, nome do arquivo, **Visualizar**, **Baixar** e **Remover PDF**; o botão de remover só aparece quando há PDF anexado.
- **Continuidade:** salvar rascunho ou anexar nota fiscal mantém a aba e a posição de rolagem da OS, em vez de voltar ao início.
- **Testes:** `test_rev12_correcoes.py` (43 OK, 1 skipped), `test_pdf_relatorio.py` + `test_gmail_integracao.py` (11 OK), `test_importacao_yaml.py` + `test_autoseg_melhorias.py` + `test_composicao.py` (37 OK).

## 9.6.0-dev.34 — urgência na OS rápida e atalhos na home — 2026-11-06 — develop

- **OS rápida:** após escolher o cliente, a criação agora permite selecionar a **Urgência** (Baixa, Normal ou Alta). O valor é gravado na OS e aparece no formulário completo.
- **OS completa:** o seletor de urgência também fica na aba Identificação; edições feitas por integrações antigas, sem o campo, preservam a urgência já salva em vez de rebaixar para Normal.
- **Home:** a Visão geral ganhou os dois atalhos com sinal de “+”: **+ Nova OS rápida** e **+ Nova OS**, no mesmo padrão da lista de ordens de serviço.
- **Testes:** `test_rev12_correcoes.py` (43 OK, 1 skipped), `test_importacao_yaml.py` + `test_produtividade_rev07.py` (9 OK), `test_gmail_integracao.py` + `test_fluxo_v6.py` + `test_composicao.py` (35 OK).

## 9.6.0-dev.33 — dados bancários unificados entre site, GTK e e-mail — 2026-11-06 — develop

- **Campo único:** o bloco **Dados bancários e cadastrais para cobrança** do Portal do Prestador agora lê e grava exatamente o mesmo campo do app GTK (`prestadores_config.dados_bancarios_texto`). Alterações feitas no site passam a valer no GTK e nos e-mails de cobrança.
- **Migração:** textos antigos salvos apenas pelo site (`produtividade_bancos`) são promovidos uma única vez para o campo oficial quando forem mais recentes; o texto do GTK é preservado quando for a edição mais nova.
- **E-mails:** o rascunho `.eml` também passa a incluir o texto livre de dados bancários, além dos campos estruturados, mantendo o mesmo conteúdo do envio via Gmail.
- **Links públicos:** a leitura dos túneis não perde mais a URL quando o log cresce com erros de requisição; o link é lido do início e do fim do log, mantendo os endereços atuais visíveis no aplicativo.
- **Testes:** `test_rev12_correcoes.py` (42 OK, 1 skipped), `test_gmail_integracao.py` (7 OK), `test_autoseg_melhorias.py` (9 OK) e `test_produtividade_rev07.py` (9 OK).

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

- **Relatório PDF:** mostra o CNPJ do prestador responsável; se ele não tiver CNPJ cadastrado, usa o CNPJ principal da AUTOSEG (CNPJ principal configurado). Também exibe o CPF/CNPJ do cliente.
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
- **CNPJ do prestador:** campo no cadastro desktop e em Integrações e pagamentos; o mesmo CNPJ pode repetir entre prestadores. O relatório mostra o CNPJ do responsável apenas quando válido e diferente do principal (CNPJ principal configurado); o orçamento usa sempre o CNPJ principal.
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
