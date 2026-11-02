# AUTOSEG — KNOWN_ISSUES

Atualizado em 30/10/2026. Ambiente alvo: branch `develop`, SQLite fictício. **Não aplicar migração ou limpeza automática na produção.**

## Defeitos e inconsistências relatados

| ID | Problema | Prioridade | Situação neste pacote |
|---|---|---|---|
| KI-001 | Cliente recém-criado não aparece nas organizações pesquisáveis pelo cliente | Crítica | **Correção implementada** no cadastro administrativo desktop/web; requer teste de interface no Mac |
| KI-002 | Dois fluxos (`clientes` e `v9_organizacoes`) confundem condomínio administrativo, pré-cadastro e vínculos | Crítica | **Parcial**: sincronização incremental sem mesclagem perigosa; reconciliação dos legados pendente |
| KI-003 | Validação/vinculação entre condomínios e clientes errados | Crítica | **Proteção parcial**: bloqueio de documentos incompatíveis, nomes/documentos visíveis e confirmação; revisar associações anteriores |
| KI-004 | Chamados de condomínio registrados no portal do cliente não aparecem nas OS pendentes | Crítica | **Cobertura automatizada e recuperação inicial** adicionadas; código existente já criava OS no ato, avaliar cenário real no Mac |
| KI-005 | Não é possível abrir OS para condomínio de pré-cadastro incompleto | Crítica | **Coberto no fluxo atual**: gera cliente provisório + OS pendente; teste HTTP com cliente fictício aprovado; requer validação no Mac |
| KI-006 | Não é possível trocar/corrigir a vinculação da OS quando o condomínio informado está incorreto | Alta | **Pendente**: exige preservar a solicitação original e trilha de auditoria |
| KI-007 | Cadastro de prestador exige rolagem para encontrar o condomínio/cliente na criação da OS | Alta | **Implementado**: busca no seletor da OS, com revisão do usuário |
| KI-008 | Materiais obrigatórios no formulário do relatório mesmo quando não utilizados | Alta | **Implementado**: inicialmente zero itens e botão opcional para acrescentar |
| KI-009 | Não é possível remover fotos selecionadas sem descartar todo o relatório | Alta | **Implementado** para fotos ainda não enviadas nos portais desktop/prestador; anexos históricos permanecem preservados |
| KI-010 | Pedidos PF/PJ precisam ficar visíveis como solicitações pendentes aos prestadores | Crítica | **Teste HTTP ponta a ponta** de PJ; PF tem OS `Aberta` e entra na lista de ativas; precisa verificação real de ponta a ponta |
| KI-011 | Excluir cadastros sem OS sem gerar referências órfãs | Alta | **Implementado com bloqueios** para OS, vínculos, chamados, contas PF; desativação para históricos |
| KI-012 | Busca ausente ou inconsistente nas telas que exibem listas | Alta | **Parcial**: busca client-side nas tabelas carregadas do prestador e busca na seleção de cliente da OS; servidor/paginação/desktop restante pendentes |

## Riscos adicionais encontrados durante análise do ZIP

- **R-01**: A importação dos clientes históricos para `v9_organizacoes` é executada na inicialização; registros duplicados antigos **não são automaticamente fundidos**. Fazer revisão por CNPJ, nome, endereço, vínculo e OS antes de qualquer mesclagem.
- **R-02**: Testes legados pressupõem rotas `/cliente` e `/pj` dentro da porta 8766 ou rótulos antigos, mas na versão atual o Portal do Cliente funciona na porta **8765** (ou **8865** no DEV). Esses testes falham por diferenças arquiteturais históricas; substituir por testes atualizados, não reintroduzir as rotas antigas.
- **R-03**: Fotos anexadas em OS concluídas podem estar referenciadas por PDFs históricos. Não deletar esses arquivos sem uma política de retenção e preservação documental.
- **R-04**: Concluir uma OS envolve transações de banco e arquivos PDF/anexos. Falhas de disco/geração merecem testes de recuperação antes de ampliar a publicação.
- **R-05**: Há referências legadas a URLs/portas fixas 8765/8766 e configurações de túneis. DEV mantém Cloudflare bloqueado por ambiente, mas uma auditoria abrangente é necessária antes de expor instâncias na internet.
- **R-06**: Os testes não substituem revisão e atualização dos vínculos errados já existentes (ex.: condomínios confundidos com clientes fictícios). Não usar fusão automática por semelhança do nome.

## Padrão para encerrar defeitos

Para mover um item para **Resolvido**: teste automatizado em SQLite temporário; teste manual na interface do Mac; verificação de regressão nos dois portais; backup antes da aplicação; evidência de comportamento esperado. Só depois abrir PR de `develop` para `main`.

## Revisão 02 — relação PF/PJ (30/10/2026)

| ID | Requisito / risco | Estado da Revisão 02 |
|---|---|---|
| KI-029 | Apenas operador desktop/prestador pode nomear responsável PF de um condomínio ou empresa | **Implementado** via nova tabela `v9_responsaveis` e telas dedicadas; pendente teste visual no Mac |
| KI-030 | Síndico/gestor nomeado acessa todas as OS da sua organização, inclusive pedidos de terceiros e aberturas administrativas | **Implementado**; se cliente PJ estiver ambiguamente vinculado, OS sem vínculo inequívoco ficam ocultas, por segurança |
| KI-031 | Morador/funcionário não ganha privilégios de gestor ao solicitar vínculo, registrar CNPJ ou ser aprovado genericamente | **Implementado**: papel administrativo depende de nomeação explícita |
| KI-032 | Revogação/substituição de síndico/gestor e auditoria da alteração | **Implementado**; somente uma nomeação ativa por organização |
| KI-033 | Cliente PF administrativo sem login por CPF não pode ser nomeado diretamente | **Limitação intencional**: conta PF com CPF e senha precisa existir; não criar vínculo automático por CPF sem verificar identidade |
| KI-034 | Senha do prestador perdida não pode ser trocada sem apagar cadastro | **Implementado** no desktop, com invalidação de sessões web antigas |

**ATENÇÃO: migração de permissão.** Vínculos antigos em `v9_vinculos` com papel Síndico/Administrador, mesmo `Aprovado`, **não** conferem mais acesso global. O operador deve revisar e nomear explicitamente a PF certa em `v9_responsaveis`. Isso é deliberado para evitar vazamento de OS em cadastros confundidos.

---

## Revisão 03 — 31/10/2026 (DEV, ainda não homologada)

- **Corrigido em código:** cadastro PJ e OS pendente em um único fluxo HTTP e transação, com telefone; cadastro na lista principal; navegação sem análise de chamados; organização e clientes sincronizados no registro. Confirmar em testes manuais no Mac.
- **Corrigido em código:** modelos YAML baixáveis, máscaras CPF/CNPJ, catálogo de serviços e orçamento estimativo PDF, botões de prestadores reposicionados e textos web responsivos.
- **Pendente:** mesclagem auditada de cadastros legados duplicados; remoção total de código legado somente após migração; Gmail OAuth e envio real; validação visual em todas as resoluções; integração NF; consulta CNPJ; backup automatizado.
- **Regra preservada:** nomeação de responsável permanece exclusiva do prestador/desktop. Abrir cadastro ou solicitar uma OS não concede acesso geral ao condomínio.

---

## Revisão 04 — 31/10/2026 (DEV, implementação em testes)

| ID | Solicitação / defeito | Resultado REV04 | Pendências |
|---|---|---|---|
| KI-035 | YAML de relatório exigia mesmo número de OS e rejeitava modelos genéricos | **Corrigido em código:** número não é mais necessário; número legado ignorado; campos preenchidos preservados por padrão | Teste no Safari/macOS |
| KI-036 | Erros YAML recarregavam tela de erro genérica | **Parcial:** erros de YAML de relatório mostram novamente formulário da OS; erro de catálogo permanece no próprio formulário | Preservar alterações não salvas feitas antes de selecionar YAML em todos os fluxos |
| KI-037 | Catálogo obriga delimitador `Nome \| Qtd \| Preço` e apaga o formulário no erro | **Corrigido para o Portal do Prestador:** campos estruturados e mensagem de erro na própria tela, com dados preservados | Auditoria de outros formulários |
| KI-038 | Falta YAML para cadastrar serviços | **Implementado:** modelo, importação e prévia em Serviços e Valores e no editor desktop | Exportação YAML sob demanda |
| KI-039 | Serviços e Valores abre navegador quando acessado pelo desktop | **Implementado:** editor Tkinter local, com criação/edição, arquivar/reativar e YAML | Revisão visual no macOS |
| KI-040 | Não existe estoque de materiais administrável só pelo desktop | **Implementado:** cadastro, preço custo/venda, SKU, mínimo, movimentações e histórico **somente desktop** | Relatórios de inventário e exportação |
| KI-041 | Material lançado em OS não integra estoque / precisa permitir negativo | **Implementado:** baixa automática na gravação da OS, saldo negativo, produto novo automático, ajuste de diferenças e estorno no cancelamento | Validar operação concorrente e regras de inventário físico |
| KI-042 | Materiais de versões antigas poderiam ser baixados duas vezes | **Mitigado:** referência inicial sem baixa retroativa; edição futura movimenta só diferença | Auditar situação inicial de cada estoque real antes de migrar produção |
| KI-043 | Status de solicitação diferente do status da OS associada | **Corrigido na apresentação do cliente:** quando a OS existe, mostrar seu estado real; CSS aumenta largura da coluna | Consolidar estados internos históricos sem perda |
| KI-044 | Endereço/descrição repetido três vezes em OS já criada | **Não reproduzido**; os dados originais permanecem imutáveis; investigar entrada vs. montagem sem sobrescrever os registros | Diagnóstico a partir de logs de casos específicos |
| KI-045 | Alguns botões e selects do desktop/Safari ficam cortados ou desalinhados | **Parcial:** select de tipo/status do cliente agrupado corretamente; novos editores dimensionáveis; largura da coluna Situação ajustada | Inspeção visual no Safari/macOS em resoluções menores |

**Limites REV04:** Ainda não há Gmail OAuth, envio real por API, NF eletrônica, consulta CNPJ pública, limpeza automática de clientes duplicados, backup recorrente com política de retenção, edição segura de condomínio já vinculado a OS histórica ou correção garantida de todos os problemas visuais reportados. Todos exigem novos testes e regras específicas. A produção não foi modificada.
