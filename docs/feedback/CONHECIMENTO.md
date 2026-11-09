# Conhecimento do AUTOSEG para respostas de feedback

Este arquivo é a base de conhecimento usada pelo assistente de feedback do
Portal do Prestador. Ele deve ser atualizado quando uma tela, rota ou regra
mudar. O assistente não recebe acesso ao banco de produção; ele responde apenas
com este mapa e com o relato anonimizado.

## Visão geral

O AUTOSEG é um sistema brasileiro de gestão de serviços para prestadores,
técnicos, condomínios e empresas. Ele tem dois portais web separados:

- **Portal do Prestador** (porta 8766): login por e-mail e senha; clientes,
  ordens de serviço, catálogo, financeiro, notas, e-mails e histórico.
- **Portal do Cliente** (porta 8765): login por CPF e senha; solicitações,
  acompanhamento, orçamento e chamados. É um site separado e não compartilha a
  sessão do prestador.

O aplicativo desktop GTK usa o mesmo banco SQLite e oferece funções
administrativas que não existem no portal web, como cadastro de prestadores,
atribuição administrativa de OS e correções financeiras.

## Mapa de telas do Portal do Prestador

### Início / Painel principal

Mostra contadores de OS abertas, iniciadas, pendentes e concluídas, valores a
receber e recebidos, clientes ativos e atalhos. A tela é apenas um resumo; as
ações ficam nas páginas específicas.

### Clientes

- Lista com busca por nome, CPF/CNPJ, cidade ou e-mail.
- Cadastro e edição de pessoa física ou jurídica.
- Campos de contato, síndico, administradora, endereço e observações.
- Busca de cliente no formulário de OS e no orçamento usa o campo
  `busca-cliente-os`.
- Importação de cliente por YAML: pré-preenche o formulário, sem salvar.
- Nomeação de síndico/gestor e vínculos de organizações.
- O cadastro de prestadores é feito somente no aplicativo desktop.
- Na OS, o cliente é pesquisado por nome enquanto se digita, no mesmo padrão
  do campo de material. Se o nome não existir, a OS cria um cliente com dados
  incompletos para completar depois.
- Clientes provisórios aparecem na lista como **Dados incompletos**, não como
  **Ativo**.

### Ordens de serviço (OS)

- Status: `Aberta`, `Iniciada`, `Pendente`, `Concluída`, `Cancelada`.
- `Iniciada` é uma OS ativa; ao iniciar o atendimento, a OS deixa de ser
  `Aberta`/`Pendente` e passa a `Iniciada`.
- A OS pode ser atribuída a um técnico, assumida, marcada em rota e ter fotos,
  anexos e relatório técnico.
- O encerramento exige relatório/serviço executado, forma de pagamento e nota
  fiscal ou a opção “não precisa de nota fiscal”.
- O relatório pode ser concluído sem destinatário quando a opção
  “Não precisa de destinatário” estiver marcada; nesse caso nenhum e-mail é
  registrado.
- O PDF do relatório é publicado após o encerramento e pode ser baixado no
  histórico.
- A importação de relatório por YAML só pré-preenche a OS ativa; não encerra,
  não altera status e não salva sozinha.
- O e-mail é gerado como rascunho `.eml`; não é enviado automaticamente no
  fluxo manual. O aplicativo pode disparar o e-mail de conclusão quando o
  prestador configurou o Gmail.
- A nota fiscal no portal é um rascunho JSON para futura NFS-e; não é documento
  fiscal válido.

### Orçamento

- Fica em **Clientes → Novo orçamento**.
- Aceita vários serviços do catálogo, cada um com quantidade.
- Aceita vários materiais adicionais do estoque, com quantidade.
- O preço vem sempre do catálogo/estoque ativo; o formulário e o YAML não
  enviam preço.
- Serviços já incluem os materiais cadastrados dentro do próprio serviço;
  materiais adicionais são cobrados separadamente.
- Gera um PDF estimativo, não vinculante, sem criar OS, financeiro ou baixa de
  estoque.
- Importação por YAML: o arquivo enviado deve ter somente `versao` e
  `orcamento`; as seções `instrucoes`, `modelo` e `exemplo` são guia e devem ser
  removidas. O YAML só pré-preenche a tela.
- Limites: 20 serviços, 50 materiais adicionais, quantidade de serviço de 1 a
  20, quantidade de material maior que zero até 1.000.
- O modelo oficial fica em `/modelos/orcamento.yaml`.

### Serviços e valores

- Catálogo de serviços com descrição, preço base de mão de obra e materiais
  internos.
- O preço do serviço inclui os materiais cadastrados nele.
- Modelo de relatório técnico por serviço é uma sugestão editável.
- Importação de serviço por YAML: pré-preenche o formulário.
- Serviços podem ser arquivados, reativados ou excluídos; exclusão é definitiva
  e deve ser usada com cuidado.

### Financeiro

- Mostra lançamentos das OS que o prestador finalizou, com valor bruto, parcela
  própria, forma de pagamento, status e vencimento.
- “Confirmar recebimento” só deve ser usado depois de verificar o pagamento;
  PIX não comprova recebimento sozinho.
- Rateios entre técnicos são descontados da parcela própria.
- Repasses manuais a colegas podem ser registrados.
- Dados bancários/Pix para e-mail de cobrança são editáveis.
- O financeiro do portal é restrito ao que o prestador participou; não é o
  caixa global da empresa.

### Solicitações PJ

- Pedidos de abertura de OS feitos por condomínios/empresas sem cadastro de
  pessoa física.
- Ficam “Aguardando verificação”; aceitar cria uma OS `Aberta`, recusar exige
  motivo.
- O histórico mostra a decisão e o vínculo com a OS.

### Notas fiscais

- Lista OS e permite preparar um rascunho JSON para futura integração NFS-e.
- O arquivo não é documento fiscal válido e não substitui o sistema fiscal.
- Anexar uma nota fiscal PDF à OS é diferente de emitir NFS-e.

### E-mails

- Prepara um arquivo `.eml` com o PDF do relatório anexado.
- Não envia automaticamente pelo fluxo de rascunho.
- O envio automático de conclusão depende da configuração de Gmail do
  prestador.

### Histórico e relatórios

- OS encerradas, relatórios publicados e PDFs centralizados.
- Permite baixar o PDF ou abrir a OS para republicar.
- Anexos só são enviados durante o fluxo de encerramento.

### Portal do Cliente

- Site separado, na porta 8765.
- Login por CPF e senha; não usa a sessão do prestador.
- Permite solicitar atendimento, acompanhar OS, pedir orçamento e consultar
  documentos públicos.
- Solicitações do cliente aparecem no Portal do Prestador e no desktop.
- O cliente não vê dados financeiros internos nem rateios.

## YAML

- Todos os modelos usam UTF-8, até 64 KB, `versao: 1`.
- Não usam âncoras (`&`), aliases (`*`), múltiplos documentos (`---`) nem TAB.
- Campos desconhecidos são rejeitados.
- Importar YAML nunca cria OS, financeiro, estoque ou envio de e-mail; sempre
  mostra uma prévia para revisão humana.
- Modelos oficiais: `/modelos/cadastro.yaml`, `/modelos/relatorio.yaml`,
  `/modelos/servico.yaml`, `/modelos/orcamento.yaml`.

## Segurança e permissões

- O portal usa CSRF em formulários e sessão por cookie `HttpOnly`.
- Ações sensíveis geram auditoria com o prestador autenticado.
- Erros de login e de formulários aparecem como toast ou mensagem inline,
  preservando os campos digitados; não devem abrir uma página de erro.
- O cadastro de prestadores é bloqueado no portal web.
- O acesso ao financeiro, notas e anexos é restrito ao responsável pela OS ou
  administrador, conforme a ação.
- O Portal do Prestador não deve ser usado para cadastrar clientes de terceiros
  sem autorização.

## Limitações conhecidas

- O portal web não faz atribuição administrativa de OS; isso é feito no
  desktop.
- O e-mail e a NFS-e ainda dependem de APIs externas e configuração.
- Não há exclusão física de OS concluída pela interface; correções financeiras
  são planejadas no desktop.
- O orçamento é estimativo e não cria contrato, cobrança ou reserva de estoque.
- A resposta por IA pode errar. Ela não altera o sistema, não promete prazo e
  não substitui a revisão humana.

## Como responder a um feedback

1. Identifique a página e o fluxo citado.
2. Procure a função no mapa acima antes de dizer que ela não existe.
3. Se a função existe em outro lugar, explique o caminho.
4. Se parece um problema real, descreva o comportamento esperado e diga que o
   relato será registrado para revisão na DEV.
5. Se for dúvida, explique o passo a passo.
6. Se for melhoria, reconheça a sugestão e diga que ela será avaliada; não
   prometa implementação.
7. Se o relato estiver incompleto, peça a informação que falta sem solicitar
   dados pessoais.
