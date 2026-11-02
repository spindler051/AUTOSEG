# AUTOSEG — ROADMAP

Versão de trabalho: revisão incremental de 30/10/2026. Marcação: **Implementado no pacote** = código preparado e testes locais; **parcial** = requer outras etapas; **planejado** = não disponível nesta entrega.

| ID | Funcionalidade | Prioridade | Situação |
|---|---|---|---|
| KI-013 | Selecionar, remover e gerenciar imagens da OS/relatório | Alta | **Parcial**: remover seleção antes de enviar no desktop e prestador; exclusão/retificação de anexos já gravados exige política de arquivo |
| KI-014 | Enviar relatório + dados bancários por e-mail | Alta | **Parcial**: rascunho `.eml` existente agora usa dados do prestador; envio automático/API **não ativado** |
| KI-015 | YAML para preencher relatório de OS com materiais opcionais | Alta | **Implementado** no Portal do Prestador (pré-visualiza; humano confirma) |
| KI-016 | YAML para preencher cadastro do cliente | Alta | **Implementado** no Portal do Prestador (pré-visualiza; humano salva) |
| KI-017 | Consulta de fontes públicas por CNPJ e importação assistida | Média | Planejado: fonte confiável, consentimento, revisão dos dados e limites de consulta |
| KI-018 | Configurações bancárias e referência de credenciais da API por prestador no desktop | Alta | **Parcial**: tela e tabela por prestador; integrações efetivas SMTP/Graph/Gmail planejadas |
| KI-019 | Salvamento automático de rascunhos de relatórios e OS | Alta | Planejado: sincronização segura com versões, prevenção de dados perdidos e privacidade |
| KI-020 | Auditoria de todas as alterações | Alta | **Parcial**: auditoria existente e eventos; ampliar para pré-cadastros, retificação e administração |
| KI-021 | Detectar duplicados antes de salvar | Crítica | **Parcial**: CNPJ exato e vínculo impedem duplicidade; sugestões de duplicidade por nome/endereço com revisão humana pendentes |
| KI-022 | Backups automáticos consistentes e restauração verificada | Crítica | Planejado: SQLite backup API, cópias de anexos, restauração testada, cópias fora da pasta do app |
| KI-023 | Controle refinado de permissões por usuário/prestador | Crítica | Planejado: papéis, autorização por OS e registros de ações administrativas |
| KI-024 | Histórico de envio de e-mails, falha e reenvio | Média | Planejado, antes do envio via API |
| KI-025 | Exportação de cadastros e relatórios em YAML padronizado | Alta | **Parcial**: arquivos de modelo e importação; exportação automatizada ainda não implementada |
| KI-026 | Ciclo de OS padronizado do pedido ao encerramento | Alta | **Parcial**: solicitações PF/PJ -> OS; migração de status e autorização precisam de revisão |
| KI-027 | Verificações de integridade entre clientes, organizações, vínculos e OS | Crítica | **Parcial**: proteções transacionais novas; ferramenta de auditoria/reconciliação pendente |
| KI-028 | Testes automatizados e regressão dos fluxos importantes | Alta | **Parcial**: oito testes de unidade + teste HTTP + testes existentes; ampliar HTTP e testes com interface no Mac |

## Sequência sugerida

1. **Dados e OS:** estabilizar vínculos e garantir lista de pendências; não mesclar registros antigos automaticamente.
2. **Experiência do prestador:** completar buscas do lado do servidor, rascunhos, fotos e revisão de formulários.
3. **YAML e CNPJ:** validação, importação, exportação, revisão, auditoria de alterações.
4. **Pagamentos e comunicação:** credenciais fora do SQLite/Git, provedores de e-mail, envio explícito, registro de entregas.
5. **Qualidade e operações:** backups, restauração, cobertura de testes, acessibilidade, revisão de segurança da publicação na internet.

O Portal do Cliente mantém seu desenho visual atual. Melhorias nele serão pontuais e motivadas por fluxos que falharem nos testes.

## Revisão 02 — concluído apenas em desenvolvimento

- Novo controle explícito PF (login CPF) → responsável → condomínio/empresa.
- Visão das OS administrativas e dos pedidos de moradores/funcionários para PF nomeada, com autorização por organização.
- Nomeação e revogação pelo desktop e Portal do Prestador; mudança registrada em histórico.
- Tratamento conservador de organizações com cliente duplicado ou CNPJ divergente: não disponibilizar OS potencialmente alheias.
- Gerador local de 5 PF, 5 PJ e 3 prestadores fictícios, sem banco incluído no pacote.
- Redefinição administrativa de senha de prestador no desktop.

**Ainda pendentes:** reconciliação de vínculos reais, contas PF comerciais sem login, auditoria completa, backups automáticos, envio via API, consultas CNPJ web e demais itens parciais descritos acima. Nunca liberar `main` antes da homologação manual com dados seguros.

---

## Revisão 03 — implementação incremental

- [x] Cadastro PJ + telefone + primeira OS em uma única tela para o cliente.
- [x] Cadastro principal de cliente recebe PJ imediatamente, com vínculo seguro à organização.
- [x] Remoção dos dois menus antigos da navegação principal do prestador; continuidade dos registros históricos.
- [x] Catálogo de serviços, preços e materiais editáveis pelo prestador.
- [x] Relatório padrão do catálogo como sugestão opcional no editor de OS.
- [x] Orçamento PDF estimativo pelo portal do cliente (sem pagamento, imposto ou vínculo contratual).
- [x] Download de modelos YAML na interface do prestador.
- [x] Reposicionamento dos controles desktop e melhoria da quebra de texto no web.
- [ ] Auditoria visual macOS e Safari em múltiplos tamanhos de tela.
- [ ] Consolidação dos cadastros legados inconsistentes, com revisão humana.
- [ ] Gmail OAuth por prestador, envio real, auditoria e testes de entrega.
- [ ] Consulta externa de CNPJ com fonte/consentimento e conferência antes de salvar.

---

## Revisão 04 — estabilidade, YAML, serviços no desktop e estoque

**Implementado na DEV (ainda requer homologação no Mac):**

- [x] Relatório YAML reutilizável em qualquer OS, sem número, campos já preenchidos preservados por padrão; opção explícita para substituir.
- [x] Importação YAML de serviços com modelo oficial, prévia e validação.
- [x] Catálogo web com linhas de material separadas, sem `|`, permitindo zero itens.
- [x] Mensagem de erro de catálogo dentro do formulário, sem perder o preenchimento.
- [x] Editor Tkinter de Serviços e Valores, independente do navegador.
- [x] Módulo Tkinter Materiais e Estoque, fora da navegação web e sem rotas CRUD no portal.
- [x] Integração estoque ↔ materiais de OS (desktop e prestador) com transação, ajustes diferenciais, saldo negativo e histórico.
- [x] Estoque preexistente em OS antigas registrado como linha de base **sem baixar novamente**.
- [x] Selecionar material cadastrado na OS (desktop e prestador), sem mostrar custo/saldo no portal.
- [x] Estado da OS apresentado ao cliente em lugar do estado antigo do chamado, quando há OS.
- [x] Correções pontuais de alinhamento de cliente, coluna status e teste de interface Tk com display virtual.

**Manter planejado / parcialmente atendido:**

- [ ] Testes visuais reais no Safari e no macOS Intel com banco fictício (obrigatório antes de produção).
- [ ] Revisão segura de organizações e vínculos legados erroneamente associados; não fundir automaticamente.
- [ ] Permitir alterar condomínio de uma OS, com trilha de auditoria e preservação da solicitação original.
- [ ] Identificar origem da duplicação do endereço em OS específicas, sem modificar conteúdo histórico sem verificação.
- [ ] Exportar cadastros e serviços para YAML, rascunho automático de relatórios e revisão geral de todos os erros de formulário.
- [ ] Rotina de backup periódico e restauração automatizada, com arquivos PDF/anexos e teste de recuperação.
- [ ] Gmail OAuth por prestador, secrets no Keychain, confirmação antes de enviar, log de envio, tratamento de duplicações.
- [ ] Regras avançadas de estoque: reserva, devolução parcial, inventário físico e acompanhamento de materiais comprados para uma OS.
- [ ] Controle de acessos administrativos refinado, auditoria completa e segurança de publicação externa.

O Portal do Cliente permanece visualmente igual, com ajuste pontual do texto de estado das OS.
