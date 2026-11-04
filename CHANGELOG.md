# AUTOSEG — Changelog

## 9.6.0-dev.14 — busca de cliente no orçamento — 2026-11-04 — develop

- **Novo orçamento:** a escolha do cliente agora tem o mesmo campo de busca já usado no formulário de OS (`busca-cliente-os`).
- **Lista menor:** o orçamento carrega até 100 clientes ativos, como o formulário de OS, em vez de 500.
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
