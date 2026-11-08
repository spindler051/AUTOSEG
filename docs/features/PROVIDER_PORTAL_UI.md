# Interface do Portal do Prestador

**Status:** interface padrão do Portal do Prestador no `develop`.
**Escopo:** site do prestador. O Portal do Cliente mantém a interface antiga.
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
botão **Entrar** é claro, não âmbar.

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
| Situação e relatório | diagnóstico, execução, testes, relato interno, situação, destinatários, rateio e fechamento |
| Materiais | linhas de material, seletor de estoque recolhido e total previsto |
| Fotos e legendas | fotos existentes, novas fotos e legendas com salvamento automático |

O fechamento (NF ou “não precisa de nota fiscal”) fica em Situação, junto da
conclusão. Para quem não é responsável, ações de salvar/concluir ficam ocultas
e o formulário de colaboração de fotos permanece. Cancelar exige apenas o
motivo e o número da OS; deixar pendente não exige destinatários.

A barra de ações é fixa no rodapé: **Salvar rascunho** como secundária e
**Confirmar situação da OS** como única primária.

### Nova OS

A abertura rápida tem uma única tela: busca de cliente, cliente opcional
(“Cliente a definir”), descrição, pagamento, urgência e responsável. Se já
existir uma OS do mesmo cliente nos últimos dois minutos, o portal mostra um
aviso antes de criar outra.

### Tema

O rodapé da barra lateral oferece **Auto**, **Claro** e **Escuro**, com o modo
automático seguindo o tema do sistema, e sete cores de acento. A preferência
fica no navegador e não altera o servidor.

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
- O Portal do Cliente continua com a interface antiga.
- A interface antiga do Portal do Prestador foi removida; não há rollback por
  cookie.

## Testes

`test_rev12_correcoes.py` cobre login, estrutura, ficha da OS, workflow, abas,
resumo renderizado e validação. `test_feedback_portal.py` e
`test_api_financeiro.py` cobrem feedback e API financeira.
