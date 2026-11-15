# Interface do Portal do Prestador

**Status:** interface padrão do Portal do Prestador no `develop`.
**Escopo:** site do prestador. A visão cliente usa a mesma shell, com módulos e permissões próprios.
**Não há mais alternância** entre interface clássica e experimental; a antiga
foi removida.

## Direção

- **Produto.** Ordens de serviço e trabalho para prestadores de segurança e
  automação, da solicitação ao relatório técnico e ao pagamento do técnico.
- **Caráter.** Exato, calmo, pronto para campo. Uma ficha de trabalho, não uma
  página de marketing.
- **Mundo.** Ferramentas grafite, notas em papel quente e uma ficha de
  atendimento sobre a bancada.
- **Momentos.** A ficha perfurada da OS e as abas de seção no editor.
- **Assinatura.** A ficha discreta da OS (número, situação, cliente,
  responsável, total e fotos) seguida dos cartões de Andamento, Rascunho e
  Importação.

## Estrutura

- Barra lateral fixa de 264 px, superfícies grafite quentes e borda fina.
- Navegação agrupada em Operação, Gestão e Registros, com ícones de linha.
- Usuário, feedback, logout e troca de interface no rodapé da barra lateral.
- Ações primárias em superfície clara; âmbar reservado ao item ativo, à aba
  selecionada, a um número-chave e aos pontos de situação.
- Sem gradientes, brilhos, sombras coloridas, emojis ou rótulos em caixa alta.
- Tipografia Avenir Next na interface e SF Mono em datas, IDs, metadados e
  números; espaçamento em escala de 4 px.
- Responsivo: a barra lateral vira navegação horizontal; a ficha da OS, o
  workflow e o editor empilham; tabelas mantêm rolagem própria.

## Páginas

### Login

Duas colunas: apresentação do produto à esquerda e formulário à direita. O
botão **Entrar** é claro, não âmbar. O login segue automaticamente o tema do
sistema, sem controles; depois de entrar, a preferência fica em Configurações.

### Visão geral

- Linha factual com prestador e data.
- Quatro números operacionais: OS abertas, iniciadas, pendentes e concluídas.
- Tabela **Ordens recentes** com pontos de situação e link direto.
- Painel financeiro com **A receber** (o número âmbar) e **Recebido**.
- Atalhos discretos e a divulgação do link público.

### Ordem de serviço

1. **Ficha da OS** — número, situação, cliente, abertura, responsável, total,
   fotos e preview do PDF.
2. **Workflow** — Andamento, Rascunho e Importação.
3. **Editor e coluna de contexto** — formulário à esquerda, contexto à direita.

Abas do editor:

| Aba | Conteúdo |
|---|---|
| Identificação | modelo, cliente, pagamento, valores, descrição e notas |
| Situação e relatório | solicitação original (somente admin), diagnóstico, execução, testes, relato interno, situação, destinatários, rateio e fechamento |
| Materiais | linhas de material, autocomplete do estoque e total previsto |
| Mídias | fotos existentes, novas fotos, legendas com salvamento automático, Fechamento e nota fiscal |

O fechamento (NF ou “não precisa de nota fiscal”) fica em Situação, junto da
conclusão. Para quem não é responsável, ações de salvar/concluir ficam ocultas
e o formulário de colaboração de fotos permanece. Cancelar exige apenas o
motivo e o número da OS; deixar pendente não exige destinatários.

A **solicitação original** aparece em dois lugares: no bloco “Chamado de
origem” e, para administradores, como campo editável acima de Diagnóstico. O
texto é o mesmo do PDF. Para não administradores, o bloco continua marcado
como “somente leitura” e o campo editável não é exibido. Ao corrigir o texto,
a OS, o chamado de origem e o PDF passam a mostrar a versão corrigida; a
alteração fica registrada no histórico.

A situação não fica aberta no formulário: **Confirmar situação da OS** abre um
popup com Aberta, Em rota, Iniciada, Pendente e Concluída. O botão
de confirmação fica visível em todas as abas; Fechamento e nota fiscal ficam
em Mídias. O admin tem um select de responsável na Identificação; escolher
outro prestador já transfere a OS, sem botão “Atribuir OS”.

A aba Identificação tem o seletor de cliente em largura total acima de
“Atendido por”, com resumo de e-mail, telefone e síndico. Para mudar para
qualquer situação exceto Pendente ou Cancelada, o cliente precisa estar
definido. Também tem **Importar relatório YAML** à esquerda de **Exportar
relatório em YAML**. A exportação devolve o modelo oficial completo, com
instruções, exemplo e os dados atuais da OS preenchidos.

A barra de ações é fixa no rodapé: **Salvar rascunho** como secundária e
**Confirmar situação da OS** como única primária.

### Nova OS

A abertura rápida tem uma única tela: nome do cliente com busca automática,
descrição e urgência. A busca de clientes e de serviços filtra enquanto se
digita, sem botão “Buscar”/“Pesquisar”. Não há botão “Buscar”, forma de pagamento nem atribuição
de prestador. Se o nome não existir, um cliente com dados incompletos é criado
para completar depois; se o cliente for omitido, a OS fica com “Cliente a
definir”. O cadastro do cliente permite mesclar dois cadastros duplicados. Se já
existir uma OS do mesmo cliente nos últimos dois minutos, o portal mostra um
aviso antes de criar outra.

### Configurações

A página **Configurações** guarda **Auto**, **Claro** e **Escuro**, com o modo
automático seguindo o tema do sistema, e sete cores de acento. A preferência
fica associada à conta do prestador e vale somente para o site; o GTK tem
aparência própria. Os botões Feedback e Sair ficam menores, lado a lado, no
rodapé da barra lateral.

### Regras de interface

- Filtros e seletores aplicam ao mudar; não criar botão **Filtrar**.
- Não duplicar uma ação: se o select de responsável já transfere, não criar
  botão **Atribuir OS**.
- Diálogos devem reutilizar o padrão visual do feedback, com título, opções
  claras e ações no rodapé.
- Ações destrutivas ficam identificadas em vermelho e pedem confirmação.
- **Erro nunca vira página nova.** Falhas de login, validação e operação devem
  aparecer em popup, toast ou mensagem inline; o formulário e o que foi digitado
  permanecem na tela. Vale para todas as rotas e formulários do site.
- Tema e acento pertencem a Configurações, não à navegação principal.

### Composição de valores

A tela lista os componentes com modo, valor, situação e ações de editar,
ativar, mover e excluir. O YAML continua disponível em “YAML avançado”, mas não
é mais a interface principal.

### Financeiro

Dois números compactos, aviso de PIX, tabela principal de recebíveis e grade
secundária em duas colunas.

### Listas e documentos

OS, clientes, serviços, prestadores, estoque, caixa, composição, notas, e-mails
e histórico usam a mesma estrutura de tabela/cartão. Busca e filtros são
secundários; só a ação real de criação é primária.

As páginas de **Prestadores**, **Estoque**, **Caixa da empresa** e
**Composição de valores** aparecem apenas para admin.

## O que não muda

- Sem migração de schema ou dados.
- Sem alteração de comportamento de OS, financeiro, estoque, feedback ou API.
- A visão cliente usa a mesma shell com navegação reduzida.
- A interface antiga do Portal do Prestador foi removida; não há rollback por
  cookie.

## Testes

`test_rev12_correcoes.py` cobre login, estrutura, ficha da OS, workflow, abas,
resumo renderizado e validação. `test_feedback_portal.py` e
`test_api_financeiro.py` cobrem feedback e API financeira.
