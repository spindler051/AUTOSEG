# Protocolo de trabalho: vocabulário, fluxo e requisitos configuráveis

**Status:** planejamento de longo prazo. **Nenhuma alteração de código foi
feita ou autorizada por este documento.**
**Data:** 2026-11-08
**Âmbito:** Workaholic, Officina e flavors (AUTOSEG e futuros).
**Documento relacionado:** `workaholic/docs/adr/0002-semantic-work-protocol.md`.

## 1. Resumo executivo

O mesmo conceito pode se chamar **ordem de serviço**, **serviço**, **trabalho**,
**comissão**, **projeto** ou **job** dependendo da profissão, do país e do
flavor. O mesmo vale para papéis (**prestador**, **funcionário**, **artista**,
**técnico**), para o fluxo (aberta, em rota, iniciada, pendente, concluída) e
para o que é obrigatório para encerrar (forma de pagamento, nota fiscal,
relatório, aprovação do cliente, arquivo final etc.).

Hoje esses termos estão no código e no banco. Isso cria três problemas:

1. **Acoplamento:** qualquer flavor novo precisa copiar ou alterar telas,
   regras e mensagens para mudar palavras.
2. **Ambiguidade:** “serviço” pode significar o item de catálogo ou a unidade
   de trabalho; “OS” pode ser inadequado para artes, música, TI ou reparos.
3. **Fluxo rígido:** os estados e requisitos atuais são os do AUTOSEG, não os
   do domínio genérico.

A direção proposta é separar quatro coisas que hoje estão misturadas:

- **identidade semântica:** `work_item`, `party`, `assignment`, `state_kind`,
  `requirement`, `capability`;
- **apresentação:** o texto que o usuário vê, resolvido por um léxico;
- **protocolo:** o fluxo, os campos, os requisitos e as permissões de um tipo
  de trabalho;
- **persistência e integrações:** adaptadores, tabelas legadas, APIs e
  documentos.

O **Workaholic** deve continuar sendo o motor genérico, sem saber o que é
“prestador”, “OS” ou “comissão”. A **Officina** é o lugar natural do protocolo
de produto: vocabulário, composição de perfis, fluxo, requisitos, papéis e
capacidades. Cada **flavor** fornece um perfil concreto (AUTOSEG, artes,
eletricista, TI etc.) e a localização.

> Regra de ouro: **nenhuma regra de negócio pode depender de uma palavra
> exibida ao usuário**. O código e o banco usam IDs semânticos; o texto é
> resolvido na borda.

## 2. Princípios de projeto

1. **IDs semânticos, rótulos na borda.** `work_item`, `state_kind=active`,
   `capability=work_item.transition.finish` são estáveis. “Ordem de serviço”,
   “Comissão” e “Trabalho” são dados de apresentação.
2. **Configuração declarativa e validada.** Perfis são dados versionados,
   validados e testados; não são código arbitrário executado por usuário.
3. **Engine não conhece flavor.** O Workaholic não importa Officina nem
   AUTOSEG; o flavor não altera o núcleo.
4. **Identidade e URLs não mudam com o rótulo.** Trocar “OS” por “Comissão”
   não pode quebrar links, APIs, números, PDFs ou integrações.
5. **Requisitos são aplicados no servidor.** A interface pode mostrar a
   pendência, mas não pode ser a única barreira.
6. **Documentos emitidos são snapshots.** Um PDF antigo não é reescrito quando
   o vocabulário muda; novas emissões usam o léxico vigente.
7. **Compatibilidade primeiro.** A migração é por adaptadores, uma fatia por
   vez; não há big-bang de banco, rotas ou nomes de tabelas.
8. **Dois perfis contrastantes antes de generalizar.** AUTOSEG (eletricista)
   e comissão de arte devem validar o desenho antes de criar uma DSL enorme.
9. **Estado não é rótulo nem premissa de comportamento.** O significado
   (`state_kind`) é separado do nome exibido e do texto da transição.
10. **Testes falam a linguagem do protocolo.** Testes não devem afirmar
    “Ordem de serviço”; devem afirmar `work_item`, `state_kind=done`,
    `requirement=payment_method`.

## 3. Limites entre Workaholic, Officina e flavor

### 3.1 Workaholic — mecânica genérica

Responsabilidades futuras (algumas já existem no protótipo):

- identidade de registros, versão otimista, criação/leitura/atualização;
- schemas de campos, tipos, validação, relações e arquivamento;
- grafo de estados e transições, desde que expresso em IDs semânticos;
- contratos de eventos/auditoria;
- primitivas genéricas de requisito (campo presente, anexo presente etc.);
- persistência (YAML, SQLite e futuros backends);
- contratos de extensão sem dependência de GUI ou país.

O Workaholic **não** deve conhecer:

- “OS”, “ordem de serviço”, “comissão”, “prestador”, “síndico”;
- “diagnóstico”, “relatório técnico”, “nota fiscal”, “PIX”;
- regras fiscais brasileiras;
- layouts, telas, formulários ou textos;
- permissões de um flavor específico.

### 3.2 Officina — protocolo de produto

A Officina é a camada que transforma primitivas genéricas em um **modelo de
trabalho utilizável**. Responsabilidades propostas:

- carregar e validar **perfis de trabalho** (`work profiles`);
- resolver o **léxico** por locale, flavor e workspace;
- compor **field groups** e seções de interface;
- definir **papéis/capabilities** e escopos de visibilidade;
- orquestrar **requisitos de conclusão** e seus avaliadores;
- mapear transições para ações de aplicação (publicar PDF, enviar e-mail,
  reservar estoque, lançar financeiro etc.);
- expor contratos de aplicação para GTK, web, CLI e futuros clientes.

A Officina pode até ser considerada o “sistema operacional do trabalho”: ela
não executa o trabalho, mas define o protocolo que os flavors usam.

### 3.3 Flavor — configuração e distribuição

O AUTOSEG (e qualquer flavor futuro) fornece:

- identidade visual, nome, empacotamento e canais;
- escolha do perfil ativo e dos tipos de trabalho;
- léxico padrão em `pt-BR` e outros locales;
- fluxo e requisitos do seu domínio;
- grupos de campos e modelos de documento;
- papéis e presets de permissão;
- módulos de locale/vertical (CPF/CNPJ, NF-e, PIX etc.);
- integrações específicas.

Um flavor **não** deve precisar de `if flavor == "autoseg"` no núcleo. Se
precisar, o protocolo ainda está incompleto.

### 3.4 Clientes

GTK, web, CLI e futuros clientes:

- consomem o perfil resolvido (rótulos, campos, transições, requisitos);
- renderizam os componentes genéricos;
- não decidem se uma OS pode ser concluída;
- não montam frases de negócio por concatenação;
- não têm cópias de regras de flavor.

### 3.5 Direção das dependências

```text
Workaholic (engine)
      ▲
      │ contratos genéricos
Officina (protocolo de produto)
      ▲
      │ perfis, léxico, requisitos
Flavor (AUTOSEG, artes, ...)
      ▲
      │ configuração e branding
Clientes (GTK, web, CLI)
```

O fluxo nunca é invertido. O Workaholic não importa Officina; a Officina não
importa AUTOSEG; o flavor pode importar contratos da Officina e do Workaholic.

## 4. Vocabulário canônico

Estes termos são a base do protocolo. Os nomes em código são em inglês; a
documentação pode traduzi-los.

| Termo canônico | Significado | Exemplos de rótulo |
|---|---|---|
| `work_item` | unidade de trabalho gerenciada | ordem de serviço, serviço, trabalho, comissão, projeto, job |
| `work_item_type` | tipo de trabalho com perfil próprio | `service_order`, `commission`, `repair`, `project` |
| `party` | pessoa ou organização envolvida | cliente, contratante, condomínio, pagador, beneficiário |
| `party_role` | papel de uma parte no trabalho | solicitante, cliente, pagador, destinatário |
| `actor` | usuário que opera o sistema | prestador, funcionário, artista, técnico, gestor |
| `assignment` | vínculo de um actor com o trabalho | responsável, colaborador, subcontratado |
| `workflow` | grafo versionado de estados e transições | fluxo da OS, fluxo da comissão |
| `state` | nó do fluxo | Aberta, Em rota, Iniciada, Pendente, Concluída |
| `state_kind` | significado semântico do estado | `open`, `active`, `waiting`, `done`, `cancelled` |
| `transition` | ação que muda de estado | iniciar, pausar, concluir, cancelar, reabrir |
| `requirement` | condição para permitir uma transição | pagamento, relatório, arquivo final, aprovação |
| `evidence` | prova que satisfaz um requisito | campo preenchido, anexo, assinatura, aprovação |
| `waiver` | dispensa explícita de um requisito | “não precisa de nota fiscal” |
| `capability` | permissão atômica | `work_item.finish`, `finance.view` |
| `role_preset` | conjunto nomeado de capabilities | administrador, prestador, funcionário, artista |
| `lexicon` | catálogo de termos localizados | pt-BR do AUTOSEG, en do flavor artes |
| `profile` | composição de tipo, fluxo, campos, papéis e requisitos | perfil AUTOSEG eletricista |
| `document_kind` | tipo de documento/anexo | relatório, nota fiscal, entrega final, referência |
| `public_identifier` | identificador exibível e linkável | `OS-0012`, `CMD-0007`, `#A19F` |

### 4.1 “Serviço” é ambíguo

Hoje “serviço” pode significar:

- o **item de catálogo** (`catalogo_servicos`: instalação, manutenção);
- a **unidade de trabalho** (`ordens_servico`);
- o **tipo de trabalho** (serviço de campo versus comissão).

O protocolo deve manter chaves distintas:

- `catalog_service` — item vendável do catálogo;
- `work_item` — trabalho executado;
- `work_item_type` — tipo de trabalho.

Nenhum flavor deve resolver a ambiguidade por texto; deve escolher a chave
correta e o léxico deve exibir o termo adequado ao contexto.

## 5. Terminologia e léxico

### 5.1 O que é um termo

Um termo não é uma string solta. Ele precisa carregar contexto suficiente para
frases corretas:

```yaml
# Ilustrativo. A sintaxe final não está congelada.
terms:
  work_item:
    one: "ordem de serviço"
    other: "ordens de serviço"
    short: "OS"
    article: "a"
    gender: feminine
    aliases: ["OS", "ordem", "serviço"]
  actor.provider:
    one: "prestador"
    other: "prestadores"
    article: "o"
    gender: masculine
  action.finish:
    one: "Concluir OS"
    other: "Concluir OSs"
```

Além das formas, o léxico deve oferecer **mensagens completas por contexto**.
Isso evita concatenar artigo + substantivo + preposição:

```yaml
messages:
  work_item.create: "Nova {work_item}"
  work_item.finish: "Concluir {work_item.short}"
  work_item.finished_at: "{work_item} concluída em {date}"
  work_item.missing_requirement: "Para concluir a {work_item}, {requirement}."
```

A frase inteira é traduzida/revisada; o código só fornece a chave e os
parâmetros. Isso resolve português, inglês e futuros idiomas com gênero,
número e ordem gramatical diferentes.

### 5.2 Precedência de resolução

Ordem proposta, do mais específico para o mais geral:

1. substituição do **workspace/tenant** (quando permitida);
2. léxico do **flavor**;
3. léxico padrão da **Officina** para o locale;
4. fallback em inglês;
5. chave semântica visível apenas em desenvolvimento/teste.

A localização do **idioma** (`pt-BR`, `en`, `es`) é uma decisão separada do
nome do produto. Um usuário pode usar o AUTOSEG em inglês sem perder o termo
“prestador” definido pelo flavor, se o flavor tiver tradução.

### 5.3 O que pode ser renomeado sem migração

Pode mudar sem tocar em dados:

- o rótulo singular/plural de `work_item`;
- o rótulo de papéis (`prestador`, `artista`, `funcionário`);
- o nome de estados (`Em rota` → `A caminho`);
- o texto de botões, títulos, filtros e mensagens;
- o texto de documentos **novos**;
- a ordem visual de campos e seções (se o perfil permitir);
- os aliases de busca.

Exige migração ou compatibilidade:

- IDs de estado e transição;
- `state_kind` de um estado existente;
- chaves de campos persistidos;
- formato/número público;
- rotas públicas e contratos de API;
- requisitos retroativos;
- permissões e capabilities.

### 5.4 Identificadores e URLs estáveis

O código e os links públicos **não** devem ser derivados do rótulo. Exemplo:

```text
GET /work-items/01J...          # canônico
GET /work-items/01J.../history
GET /api/v1/work-items/01J...
```

O AUTOSEG mantém `/os/...` como alias compatível. Um flavor de artes pode
expor um alias público `/comissoes/...` se quiser, mas ele redireciona para o
mesmo identificador canônico. O identificador público (`OS-0012`, `CMD-0007`)
é um dado separado do ID interno; o prefixo/formato pertence ao perfil de
numeração.

Regras:

- links já enviados por e-mail, PDFs e QR codes continuam funcionando;
- trocar o rótulo não muda a URL;
- a API usa IDs semânticos e campos estáveis;
- aliases são declarados, não inferidos do texto;
- o número público nunca é reutilizado; aliases antigos são preservados.

### 5.5 Busca, suporte e legado

A busca deve indexar:

- o rótulo atual;
- plural, abreviação e aliases;
- termos antigos conhecidos;
- o identificador público;
- o nome do tipo de trabalho.

Assim, um usuário que digitou “OS” continua encontrando “Comissão” após a
mudança. O mesmo vale para a base de conhecimento do feedback: ela deve
explicar o novo termo e manter o antigo como alias.

### 5.6 Documentos, auditoria e snapshots

- **PDFs e e-mails já emitidos não são reescritos.** Eles guardam o texto da
  época.
- **Novas emissões** usam o léxico vigente.
- **Eventos de auditoria** guardam a chave semântica + parâmetros
  (`work_item.finished`, `state_kind=done`), não apenas a frase renderizada.
- O visualizador de histórico pode mostrar o rótulo atual e, opcionalmente, o
  rótulo histórico (“Concluída” na época).
- Documentos com valor legal podem guardar um snapshot do léxico/versão do
  perfil para reprodução fiel.

### 5.7 Workspace versus usuário

Recomendação inicial:

- **idioma:** preferência do usuário;
- **termos do domínio:** decisão do workspace/admin;
- **renomeação livre por usuário:** não no primeiro ciclo.

Permitir que cada usuário chame a mesma coisa de um jeito diferente fragmenta
suporte, treinamento, busca e auditoria. Um alias pessoal de exibição pode ser
estudado depois, mas nunca deve alterar dados, rotas ou regras.

### 5.8 Exemplos de léxico

**AUTOSEG / eletricista**

```yaml
work_item:
  one: "ordem de serviço"
  short: "OS"
actor.provider: "prestador"
party.customer: "cliente"
states:
  aberta: "Aberta"
  em_rota: "Em rota"
  iniciada: "Iniciada"
  pendente: "Pendente"
  concluida: "Concluída"
  cancelada: "Cancelada"
```

**Artes / comissão**

```yaml
work_item:
  one: "comissão"
  other: "comissões"
  short: "CMD"
actor.provider: "artista"
party.customer: "cliente"
states:
  solicitada: "Solicitada"
  orcada: "Orçada"
  aprovada: "Aprovada"
  em_producao: "Em produção"
  revisao: "Em revisão"
  entregue: "Entregue"
  cancelada: "Cancelada"
```

**Genérico / trabalho**

```yaml
work_item:
  one: "trabalho"
  other: "trabalhos"
  short: "TRB"
actor.provider: "profissional"
party.customer: "contratante"
```

Nenhum desses exemplos exige mudar o código do Workaholic.

## 6. Protocolo de fluxo

### 6.1 `state_kind`: o significado por trás do rótulo

Estados são livres, mas cada estado declara um **kind** semântico. O núcleo usa
o kind para decisões genéricas; o flavor usa o rótulo para a interface.

Conjunto mínimo proposto:

| Kind | Significado | Exemplos |
|---|---|---|
| `draft` | ainda não confirmado | rascunho, orçamento em edição |
| `open` | criado, aguardando início | Aberta, Solicitada |
| `active` | trabalho em andamento | Iniciada, Em rota, Em produção |
| `waiting` | bloqueado aguardando terceiro/evento | Pendente, Em revisão, Aguardando peça |
| `done` | encerrado com sucesso | Concluída, Entregue, Publicada |
| `cancelled` | encerrado sem sucesso | Cancelada, Recusada, Não realizada |

`archived` **não é estado**: é um flag ortogonal de visibilidade/preservação.
“Atrasado” também não é estado: é um **flag calculado** (vencimento, SLA), para
não multiplicar estados e não confundir atraso com etapa do trabalho.

Um fluxo pode ter vários estados do mesmo kind:

- `Em rota` e `Iniciada` são ambos `active`;
- `Pendente` e `Aguardando aprovação` são ambos `waiting`;
- `Entregue` e `Publicada` podem ser ambos `done`.

Isso preserva a riqueza do flavor sem obrigar o núcleo a conhecer cada nome.

### 6.2 Invariantes mínimas

Todo workflow válido deve:

1. ter um estado inicial explícito;
2. ter pelo menos um estado `done` e um `cancelled`;
3. declarar todas as transições com origem e destino existentes;
4. não ter transições saindo de `done`/`cancelled`, exceto uma transição
   explícita de reabertura;
5. permitir que o flavor adicione estados, labels e transições sem tocar no
   núcleo;
6. manter IDs de estado estáveis entre versões;
7. registrar toda transição com actor, timestamp, estado anterior, novo estado,
   motivo e metadados;
8. validar a transição no servidor, inclusive concorrência e idempotência.

O núcleo **não** deve impor uma ordem linear. Fluxos com retorno
(`Pendente → Iniciada`), aprovação, revisão e reabertura são permitidos se
declarados.

### 6.3 Transições

Uma transição declara:

```yaml
transitions:
  iniciar:
    from: [aberta, pendente]
    to: iniciada
    label: "Iniciar OS"
    capabilities: [work_item.transition.start]
    requirements: [cliente_definido]
    effects: [registrar_inicio, parar_deslocamento]
  concluir:
    from: [iniciada, pendente]
    to: concluida
    label: "Concluir OS"
    capabilities: [work_item.transition.finish]
    requirements: [servico_executado, forma_pagamento, evidencia_fiscal]
    effects: [publicar_pdf, registrar_financeiro]
  cancelar:
    from: [aberta, iniciada, pendente]
    to: cancelada
    label: "Cancelar OS"
    capabilities: [work_item.transition.cancel]
    requirements: [motivo_cancelamento]
    effects: [registrar_cancelamento]
  reabrir:
    from: [concluida, cancelada]
    to: aberta
    label: "Reabrir OS"
    capabilities: [work_item.transition.reopen]
    requirements: [motivo_reabertura]
```

Regras de desenho:

- `effects` são executados pela Officina/aplicação, não pelo Workaholic puro;
- efeitos precisam ser idempotentes ou transacionais;
- uma transição não deve existir só para mudar um rótulo;
- permissões e requisitos são independentes: uma pessoa pode ter permissão e
  ainda faltar um requisito;
- a interface recebe `allowed_transitions` e `missing_requirements` do
  servidor, não replica a lógica.

### 6.4 Exemplos de fluxos

**AUTOSEG (atual, preservado)**

```text
Aberta(open) ──► Em rota(active) ──► Iniciada(active) ──► Concluída(done)
     │                 │                    │
     └─────────────────┴──► Pendente(waiting) ──► Iniciada(active)
     └──────────────────────────────────────────► Cancelada(cancelled)
```

**Artes / comissão**

```text
Solicitada(open) ──► Orçada(waiting) ──► Aprovada(active)
       │                                      │
       │                                      ▼
       │                              Em produção(active)
       │                                      │
       │                                      ▼
       └──► Recusada(cancelled)        Em revisão(waiting)
                                              │
                                              ▼
                                         Entregue(done)
```

**Mínimo genérico**

```text
Aberto(open) ──► Iniciado(active) ──► Concluído(done)
     └──────────────────────────────► Cancelado(cancelled)
```

O AUTOSEG mantém seu fluxo atual como perfil; um flavor de artes usa outro
perfil; um eletricista pode usar o perfil AUTOSEG; um técnico de TI pode criar
`Diagnóstico`, `Aguardando peça` e `Testes` como estados ou como campos,
conforme a necessidade — a decisão é do perfil, não do núcleo.

### 6.5 Flags versus estados

Nem tudo precisa ser estado. Exemplos:

- **Em rota:** pode ser um estado `active` ou um flag `on_the_way` com
  timestamp; se a UI e os relatórios precisam de transição e histórico, estado
  é mais expressivo;
- **Atrasado:** sempre um flag calculado (`due_at < now` e não concluído);
- **Urgente:** campo/flag, não etapa;
- **Pago:** evidência/flag financeiro; a transição para `done` pode exigir ou
  não pagamento;
- **Arquivado:** flag de ciclo de vida.

O protocolo deve permitir ambos, mas a recomendação é: **estado só quando há
mudança de etapa com significado de fluxo e histórico**; o resto é campo,
flag ou evidência.

### 6.6 Versionamento de workflow

Mudar um fluxo em produção é uma migração, não um simples deploy.

- O perfil tem `version`.
- Cada work item guarda `workflow_id` e `workflow_version`.
- Itens antigos continuam no fluxo antigo até uma migração explícita.
- IDs de estado nunca são reutilizados.
- Renomear rótulo é seguro; mudar `state_kind` de um estado existente é
  quebra de contrato.
- Remover estado exige plano para itens que estão nele.
- Um estado desconhecido (cliente antigo) é lido em modo somente leitura e não
  é sobrescrito.
- O rollback do perfil deve ser possível; migrações de estado são auditadas.

### 6.7 Eventos, auditoria e notificações

Toda transição gera um evento semântico, por exemplo:

```json
{
  "event": "work_item.transitioned",
  "work_item_id": "...",
  "from": "iniciada",
  "to": "concluida",
  "from_kind": "active",
  "to_kind": "done",
  "actor_id": "...",
  "reason": "",
  "at": "2026-11-08T..."
}
```

Consequências:

- relatórios e métricas usam `state_kind`, não o rótulo;
- notificações resolvem o texto no momento do envio;
- integrações recebem IDs e kinds, não “Concluída”;
- a auditoria não quebra quando o flavor renomeia um estado;
- o histórico do usuário pode exibir o rótulo da época.

### 6.8 Concorrência, idempotência e concorrência de atores

- toda transição usa a versão do work item (optimistic locking);
- o cliente envia uma chave de idempotência para evitar duplo clique/retry;
- transições concorrentes: uma vence; a outra recebe conflito e recarrega;
- efeitos externos (e-mail, pagamento, estoque) precisam de política de
  exactly-once ou compensação;
- transições automáticas e timers futuros devem usar o mesmo registro de
  eventos, com actor `system`;
- aprovações podem exigir múltiplos atores/quórum; o workflow deve declarar
  isso, não a interface.

### 6.9 Status externo versus interno

Portais, clientes e integrações podem ver um status simplificado:

- interno: `Aguardando aprovação do síndico` (waiting);
- externo/cliente: `Em análise` (waiting);
- API: `waiting` + `external_label_key`.

O perfil pode declarar `customer_visible` e um mapa de status externo. Isso
evita expor detalhes internos e permite que o cliente veja uma linguagem mais
simples sem perder a riqueza interna.

## 7. Requisitos de conclusão

### 7.1 Modelo

Um requisito é uma condição declarativa com:

- `id` estável;
- `kind` (campo, anexo, aprovação, pagamento, documento, custom);
- `severity` (`blocking`, `warning`, `info`);
- `applies_to` (transição, tipo, condição);
- `message_key`;
- `field`/`document_kind`/`capability` quando aplicável;
- `waivable` e `waiver_capability`;
- versão/perfil.

Exemplo ilustrativo:

```yaml
completion:
  requirements:
    forma_pagamento:
      kind: field_present
      field: payment_method
      severity: blocking
      message: "Selecione a forma de pagamento."
    servico_executado:
      kind: field_present
      field: execution_report
      severity: blocking
      message: "Preencha o serviço executado."
    evidencia_fiscal:
      kind: any_of
      severity: blocking
      message: "Anexe a nota fiscal ou marque que não precisa."
      options:
        - kind: attachment_present
          document_kind: invoice
        - kind: waiver
          id: sem_nota_fiscal
    entrega_final:
      kind: attachment_present
      document_kind: final_deliverable
      severity: blocking
      message: "Anexe o arquivo final da comissão."
    aprovacao_cliente:
      kind: approval
      actor_role: customer
      severity: blocking
      message: "Aguardando aprovação do cliente."
```

### 7.2 Tipos de requisito

Começar pequeno, com tipos bem definidos:

- `field_present` / `field_valid`;
- `attachment_present` / `attachment_count` / `attachment_kind`;
- `party_role_present`;
- `assignment_present`;
- `approval` (ator, papel, quórum);
- `payment_status` / `amount_paid` (via adaptador financeiro);
- `document_issued` (NF-e etc., via módulo de locale);
- `child_work_items_done` (para trabalhos compostos);
- `waiver` (dispensa explícita);
- `custom` (extensão registrada e revisada).

Avaliadores de integração (pagamento, fiscal) ficam na Officina/módulos, não no
Workaholic.

### 7.3 Resultado estruturado

A avaliação deve retornar algo como:

```json
{
  "allowed": false,
  "requirements": [
    {"id": "forma_pagamento", "status": "missing", "message_key": "..."},
    {"id": "servico_executado", "status": "satisfied"},
    {"id": "evidencia_fiscal", "status": "waived", "waived_by": "..."}
  ]
}
```

A interface usa isso para:

- mostrar um checklist antes de concluir;
- destacar o campo que falta;
- explicar por que a transição está bloqueada;
- permitir dispensa quando autorizada;
- nunca “adivinhar” a regra no cliente.

### 7.4 Waivers

“Não precisa de nota fiscal” é um waiver, não um campo booleano solto.

- tem ID, motivo, ator, timestamp e versão do requisito;
- exige capability específica;
- aparece na auditoria e no PDF/documento quando aplicável;
- pode expirar ou ser revogado;
- não reescreve documentos antigos;
- não pode ser autoaprovado pelo cliente.

### 7.5 Exemplos por domínio

| Domínio | Requisitos de conclusão (exemplo) |
|---|---|
| AUTOSEG eletricista | serviço executado, forma de pagamento, relatório/fotos, NF ou waiver |
| Encanador | serviço executado, materiais, forma de pagamento, NF ou waiver |
| Artista 2D/3D | especificação final, arquivo entregue, aprovação do cliente, direitos de uso, pagamento/entrada quando configurado |
| Técnico de TI | diagnóstico, peças/serial, testes, termo de entrega, forma de pagamento |
| Músico/DJ | setlist/arquivos, local/horário, aprovação, pagamento |
| Projeto genérico | marco entregue, aprovação, documentação |

O núcleo não deve ter `if autoseg`; ele recebe um perfil com requisitos.

### 7.6 Versionamento e itens antigos

- Requisitos são versionados junto com o perfil.
- Itens já concluídos **não** são invalidados por um requisito novo.
- Reabrir um item pode aplicar o perfil atual ou o perfil da época; isso é uma
  decisão explícita do perfil.
- Requisitos obrigatórios novos em itens abertos devem gerar aviso e plano de
  migração; não podem bloquear silenciosamente uma operação já em andamento.
- Waivers antigos continuam válidos para o item e a versão em que foram
  registrados.

## 8. Papéis, partes e permissões

### 8.1 Separação

- **party:** quem é o cliente/contratante/pagador/beneficiário;
- **actor:** quem opera o sistema;
- **assignment:** quem é responsável/colaborador naquele trabalho;
- **role_preset:** um conjunto nomeado de capabilities;
- **capability:** uma permissão atômica e estável.

Não usar o rótulo para decidir permissão. “Prestador” e “artista” podem ter o
mesmo preset `primary_worker` com rótulos diferentes; “funcionário” pode ser
um preset com escopo restrito; “admin” é um preset de governança.

### 8.2 Capabilities iniciais sugeridas

```text
work_item.view.own
work_item.view.participating
work_item.view.all
work_item.create
work_item.edit
work_item.assign
work_item.transition.start
work_item.transition.finish
work_item.transition.cancel
work_item.transition.reopen
work_item.waive_requirement
party.manage
finance.view
finance.manage
document.issue
settings.manage
```

O perfil pode adicionar capabilities específicas, mas as genéricas devem ser
estáveis.

### 8.3 Escopos de visibilidade

- próprio;
- atribuído;
- participante;
- equipe/organização;
- tenant/workspace;
- todos (admin).

O AUTOSEG atual tem admin, prestador, funcionário e cliente; o protocolo deve
permitir esse arranjo e também:

- artista autônomo (um ator principal);
- estúdio com gerente, artistas e financeiro;
- empresa de TI com técnicos e atendentes;
- cliente corporativo com múltiplos usuários;
- prestador terceirizado.

### 8.4 Field-level permissions

Além de “pode editar a OS”, o perfil deve permitir:

- campo visível apenas para admin (custo interno);
- campo editável apenas em determinado estado;
- documento visível ao cliente somente após aprovação;
- histórico interno separado do relatório externo.

Isso precisa ser validado no servidor, não só escondido na UI.

### 8.5 Rótulos de papéis

Um papel pode ter rótulos contextuais:

- `actor.primary_worker`: prestador, artista, técnico, eletricista;
- `actor.employee`: funcionário, assistente, colaborador;
- `party.customer`: cliente, contratante, comitente;
- `actor.manager`: administrador, gestor, produtor.

O mesmo usuário pode acumular papéis; a UI mostra o papel relevante no
contexto, não uma string fixa no código.

## 9. Campos, grupos e composição da interface

### 9.1 Campos-base versus grupos de domínio

Campos-base (comuns a quase todo trabalho):

- título/descrição;
- cliente/parte principal;
- responsável/equipe;
- estado;
- datas de abertura, início, conclusão, cancelamento;
- valor/moeda (opcional);
- anexos;
- observações;
- histórico.

Grupos de domínio (selecionados pelo perfil):

- `service_details` (AUTOSEG: diagnóstico, serviço executado, testes);
- `art_spec` (dimensões, estilo, referências, direitos, revisões);
- `device_repair` (aparelho, serial/IMEI, peças, garantia);
- `event_production` (local, horário, setlist, rider);
- `project_plan` (marcos, dependências, entregáveis).

Cada grupo:

- tem ID e versão;
- declara campos tipados, validações e widgets sugeridos;
- pode ser reutilizado por vários tipos;
- pode ter seções e ordem;
- pode declarar visibilidade por papel/estado;
- pode declarar requisitos.

### 9.2 Seções e navegação

Em vez de abas hardcoded “Identificação / Situação e relatório / Materiais /
Mídias”, o perfil declara seções:

```yaml
sections:
  - id: overview
    label: "Resumo"
  - id: service
    label: "Serviço"
    fields: [service_details]
  - id: media
    label: "Mídias"
    fields: [photos]
  - id: documents
    label: "Documentos"
    fields: [documents]
  - id: history
    label: "Histórico"
```

O AUTOSEG mantém o layout atual como perfil padrão. O artista pode ter
“Briefing”, “Referências”, “Revisões”, “Entrega” e “Direitos”. O técnico de TI
pode ter “Aparelho”, “Diagnóstico”, “Peças”, “Testes” e “Garantia”.

### 9.3 Listas, filtros e busca

As colunas e filtros também vêm do perfil:

- título do trabalho, parte principal, estado, responsável, prazo, valor;
- filtros por `state_kind`, tipo, responsável, período;
- busca por ID público, título, parte e aliases do léxico.

O núcleo pode oferecer uma lista genérica configurável; cada cliente renderiza
com seu toolkit.

### 9.4 Documentos e templates

- `document_kind` define o tipo (relatório, nota, entrega, referência, contrato);
- o perfil declara templates e requisitos;
- o template usa chaves do léxico e campos do work item;
- PDFs antigos ficam imutáveis;
- o mesmo documento pode ter versões e um status de publicado;
- documentos fiscais são módulos de locale, não campos do núcleo.

## 10. Persistência, API e compatibilidade

### 10.1 Registro canônico ilustrativo

```json
{
  "id": "01J...",
  "type": "service_order",
  "profile": "autoseg.electrician",
  "profile_version": 3,
  "workflow": "autoseg.service_order",
  "workflow_version": 5,
  "state": "iniciada",
  "state_kind": "active",
  "public_identifier": "OS-0012",
  "parties": [
    {"role": "customer", "party_id": "..."}
  ],
  "assignments": [
    {"role": "responsible", "actor_id": "..."}
  ],
  "fields": {},
  "documents": [],
  "requirements": [],
  "created_at": "...",
  "updated_at": "...",
  "version": 7
}
```

Este é um contrato conceitual, não uma decisão de schema final.

### 10.2 Persistência incremental

Não renomear tabelas e colunas agora.

Fase inicial:

- manter `ordens_servico`, `clientes`, `prestadores` e tabelas atuais;
- adicionar metadados genéricos por adaptador (tipo, perfil, workflow, versão,
  state_kind) quando a fatia for migrada;
- mapear estado legado → `state_kind` em uma tabela/configuração;
- manter escritas legadas e pontes de leitura.

Fase futura:

- Workaholic pode usar `records` ou tabelas normalizadas genéricas;
- a migração de dados é um projeto separado, com backup e rollback;
- nenhuma migração de persistência é necessária para começar a usar o léxico.

### 10.3 API

- APIs novas usam `/work-items` e IDs semânticos;
- APIs antigas `/os` continuam como aliases compatíveis;
- campos como `status` podem ser mantidos como strings legadas na borda;
- respostas novas incluem `state_kind`, `allowed_transitions` e
  `missing_requirements`;
- eventos usam `work_item.completed` etc., não o rótulo;
- clientes antigos continuam funcionando durante a janela de depreciação.

### 10.4 Multi-tenant, offline e versionamento

- cada workspace escolhe um perfil e uma versão;
- work items guardam a versão usada;
- clientes offline recebem o perfil empacotado e a versão;
- conflito de perfil em sync não altera itens silenciosamente;
- perfis podem ser atualizados, mas itens abertos têm política de migração;
- um tenant não pode ver/alterar o perfil de outro.

### 10.5 Efeitos colaterais

Transições podem disparar:

- financeiro (criar recebível, confirmar pagamento);
- estoque (baixar materiais);
- documentos (publicar PDF);
- e-mail/notificação;
- integrações fiscais;
- webhooks.

Isso exige:

- transação local para o que é local;
- outbox/idempotência para o que é externo;
- compensação em cancelamento/reabertura;
- auditoria de cada efeito;
- nenhum efeito crítico apenas no cliente.

## 11. Catálogo de edge cases

### 11.1 Terminologia

- **Gênero e artigo:** “a OS”, “o serviço”, “a comissão”, “o trabalho”. Evitar
  concatenação; usar mensagens completas.
- **Plural irregular:** “ordens de serviço”, “comissões”, “trabalhos”.
- **Abreviação:** “OS” pode ser lida como sistema operacional; o perfil deve
  declarar a abreviação e o contexto.
- **Palavra ambígua:** “serviço” (catálogo × trabalho) e “comissão” (remuneração
  × obra) precisam de chaves distintas.
- **Mudança de nome com links antigos:** aliases e IDs estáveis.
- **PDFs antigos:** não reescrever; novas emissões usam o novo termo.
- **Busca:** indexar termos antigos e novos.
- **Idioma misto:** equipe em `pt-BR`, cliente em `en`; locale por usuário e
  léxico por workspace.
- **RTL e línguas sem plural simples:** não concatenar; usar mensagens/ICU.
- **Acessibilidade:** expandir abreviações; não depender de ícone/cor para
  estado.
- **Testes:** não afirmar strings de UI; afirmar IDs e kinds.
- **Logs e suporte:** erros carregam código semântico; a mensagem é renderizada
  na borda.

### 11.2 Workflow

- **Vários estados do mesmo kind:** `Em rota` e `Em produção` são `active`.
- **Estado terminal reaberto:** transição explícita, permissão, motivo,
  auditoria; não apagar histórico.
- **Cancelamento após conclusão:** reabertura ou transição de correção; não
  sobrescrever o fato.
- **Estado removido em nova versão:** itens antigos preservados; migração
  explícita.
- **Estado desconhecido em cliente antigo:** somente leitura; não sobrescrever.
- **Loops:** permitidos, mas com guardas e histórico; evitar loop infinito.
- **Concorrência:** versão otimista e idempotência.
- **Automação/timer:** actor `system`, evento e auditoria; offline não dispara
  duas vezes.
- **Aprovação multiusuário:** quórum, rejeição, delegação; o perfil declara.
- **Cliente vê status simplificado:** mapa interno → externo.
- **Atraso:** flag calculado, não estado.
- **Em rota:** estado ou flag; decidir por necessidade de histórico/relatório.
- **Arquivamento:** flag ortogonal; não confundir com cancelamento.
- **Trabalho composto:** conclusão de filhos, dependências e roll-up.
- **Recorrência/manutenção:** instâncias futuras, não o mesmo work item.
- **Fuso horário:** timestamps em UTC, exibição local; prazos com timezone.
- **Migração de workflow:** versão, mapa de estados, rollback, dry-run.
- **Relatórios:** usar kind; não depender de nomes.
- **Integrações:** status externo mapeado, não texto.

### 11.3 Requisitos

- **Requisito condicional:** por tipo, valor, parte, estado ou país.
- **Evidência assíncrona:** aguardando pagamento/aprovação; UI mostra pending.
- **Waiver:** permissão, motivo, auditoria, expiração.
- **Requisito novo em item antigo:** não invalidar concluídos; aviso/migração.
- **Reabertura:** requisitos atuais vs da época.
- **Múltiplos anexos:** tipo, quantidade, tamanho, vírus, retenção.
- **Aprovação do cliente:** quem pode aprovar, quórum, delegação, silêncio.
- **Pagamento parcial/entrada:** política por perfil; não assumir “pago” binário.
- **Documento fiscal:** módulo de locale; não requisito universal.
- **Serviço em garantia/cortesia:** waiver/valor zero; não confundir com grátis.
- **Evidência apagada depois de concluída:** documento publicado é snapshot;
  anexo operacional pode ter retenção.
- **Bypass pelo cliente:** servidor sempre valida.
- **Mensagem de requisito:** chave + campo + ação, sem string hardcoded.
- **Testes:** requisito satisfeito, faltante, dispensado, condicional e
  concorrente.

### 11.4 Papéis e permissões

- **Rótulo ≠ permissão:** “prestador” e “artista” podem compartilhar preset.
- **Múltiplos papéis:** admin + worker, cliente + pagador, artista + gerente.
- **Organização:** funcionário pertence a empresa; subcontratado externo.
- **Escopo:** próprio, atribuído, participante, equipe, tenant, todos.
- **Campo sensível:** custo interno invisível ao cliente.
- **Transição sensível:** só responsável/admin pode concluir/cancelar.
- **Waiver:** capability separada; não dar a quem executa.
- **Delegação:** férias, ausência, transferência de responsabilidade.
- **Cliente corporativo:** vários usuários, aprovação por papel.
- **Menor privilégio:** admin não deve ser o padrão.
- **Auditoria:** toda mudança de papel/permissão e uso de override.
- **Migração de papel:** label pode mudar; capabilities exigem revisão.

### 11.5 Dados, migração e operação

- **Nenhuma renomeação de tabela no início:** adaptadores.
- **IDs antigos:** preservar; aliases.
- **Numeração:** separar ID interno, número público e prefixo do perfil.
- **Duplicidade:** regras de negócio por perfil; não no núcleo.
- **Backup/rollback:** antes de mudar workflow, requisitos ou numeração.
- **Testes de contrato:** engine × perfil × UI.
- **Performance:** cache de perfil, índices em kind/estado, não varrer JSON.
- **Segurança de perfil:** limites de tamanho, estados e campos; sem código
  arbitrário; revisão de administradores.
- **Compatibilidade de API:** versão, depreciação, aliases.
- **Documentação:** glossário e changelog de perfil.
- **Multi-tenant:** isolamento de perfis e dados.
- **Observabilidade:** métricas por kind, erros por requisito, tempo em estado.

## 12. Plano de migração (sem implementar agora)

### Fase 0 — Vocabulário e decisão (este documento)

- registrar o glossário e os limites Workaholic/Officina/flavor;
- criar ADR;
- não alterar código, banco, rotas ou telas.

### Fase 1 — Camada semântica invisível

- introduzir `work_item`/`state_kind` em novos adaptadores e testes;
- mapear estados AUTOSEG atuais para kinds;
- manter 100% do comportamento visível;
- nenhuma mudança de banco ou URL;
- testes de paridade.

### Fase 2 — Léxico somente leitura

- carregar um perfil de léxico para AUTOSEG;
- resolver rótulos de `work_item` nas telas novas ou em um piloto;
- manter literais antigos onde ainda não houver cobertura;
- testes de chaves ausentes e plural;
- feature flag para rollback.

### Fase 3 — Campos e seções orientados a perfil

- extrair grupos de campos do AUTOSEG (diagnóstico, execução, testes, mídias,
  documentos) para dados de perfil;
- renderizar uma tela piloto a partir do perfil;
- comparar com a tela atual;
- preservar nomes técnicos e dados existentes.

### Fase 4 — Requisitos de conclusão declarativos

- mover validações de conclusão do portal/GTK para requisitos de perfil;
- manter validação no servidor;
- implementar checklist e mensagens inline;
- migrar “não precisa de nota fiscal” e forma de pagamento;
- testes de autorização/requisito.

### Fase 5 — Workflow configurável

- extrair estados/transições do AUTOSEG para perfil;
- validar invariantes e migração de itens;
- suportar reabertura/cancelamento no perfil;
- manter aliases e status legados;
- testes de fluxo e concorrência.

### Fase 6 — Segundo flavor de prova

- criar perfil de **comissão de arte** apenas com configuração;
- usar o mesmo engine e a mesma UI genérica;
- demonstrar que nenhuma condição `if arts` foi necessária;
- medir esforço de configuração e lacunas.

### Fase 7 — Convergência opcional com Workaholic

- migrar persistência de work items para o modelo genérico do Workaholic;
- só depois de protocolo, requisitos e workflow estabilizados;
- manter adaptadores e dados legados até paridade total.

### Critérios de avanço por fase

- testes verdes e paridade visual/funcional;
- perfil validado por schema e por revisão humana;
- migração reversível, backup e rollback;
- documentação do perfil e do changelog;
- nenhuma regra de negócio dependente de rótulo;
- nenhuma quebra de links/API existentes;
- revisão de segurança em permissões/waivers.

### O que não fazer

- não renomear `ordens_servico` no banco;
- não trocar `/os` por `/work-items` sem aliases;
- não reescrever PDFs;
- não permitir workflow arbitrário por usuário no primeiro ciclo;
- não criar uma DSL Turing-complete;
- não migrar tudo de uma vez;
- não duplicar a regra no GTK e no site.

## 13. Riscos e anti-patterns

1. **DSL vira linguagem de programação.** Quanto mais expressivo, mais difícil
   validar, versionar e revisar. Começar com tipos fechados de requisito e
   condições declarativas.
2. **Generalização prematura.** Criar campos para todos os domínios antes de
   dois perfis reais gera um schema inútil. Validar com AUTOSEG e artes.
3. **Lógica baseada em rótulo.** `if status == "Concluída"` continua sendo
   acoplamento; usar `state_kind`.
4. **Rótulo no banco como identidade.** Texto muda; IDs não.
5. **Duas fontes de verdade.** Workaholic, Officina e flavor não podem manter
   cópias divergentes do mesmo perfil.
6. **Permissão só na UI.** O servidor precisa validar capability, requisito,
   estado e concorrência.
7. **Migração de fluxo sem mapa.** Itens podem ficar presos ou perder
   histórico.
8. **Perfis sem limite.** Um admin não deve poder criar 10 mil estados ou
   expressões perigosas.
9. **PDF reescrito.** Documento emitido é snapshot; reemissão é uma ação
   explícita.
10. **Perda de compatibilidade.** Links antigos, API antiga e números antigos
    precisam de aliases e prazo de depreciação.
11. **Testes frágeis.** Testar textos em vez de IDs/kinds quebra a cada
    renomeação.
12. **Workflow universal.** Tentar impor um fluxo único para arte, elétrica e
    TI contradiz o objetivo.
13. **Termos personalizados por usuário cedo demais.** Aumenta suporte e
    inconsistência; começar por workspace.
14. **Misturar estado com flag.** Atraso, urgência, pago e arquivado não são
    etapas.
15. **Ignorar o offline/local-first.** Perfil e dados precisam funcionar sem
    servidor, com versão e conflito explícitos.

## 14. Decisões humanas pendentes

Estas questões não devem ser resolvidas por IA sozinha:

1. O conjunto mínimo de `state_kind` deve incluir `waiting` e `draft` desde o
   início, ou começar com `open/active/done/cancelled`?
2. Renomeação de termos será apenas por workspace/admin ou também por usuário?
3. Perfis ficam em arquivos versionados, no banco por tenant, ou ambos?
4. Requisitos terão uma linguagem de expressão declarativa ou apenas tipos
   fechados + composições (`all_of`, `any_of`, `not`)?
5. O Workaholic ganhará um `WorkItem` tipado ou continuará genérico baseado em
   `fields` com adaptadores?
6. O estado externo do cliente será um mapa por perfil ou uma projeção
   automática por `state_kind`?
7. O número público e o prefixo pertencem ao perfil ou ao workspace?
8. Documentos devem guardar o snapshot completo do léxico ou apenas a versão?
9. Haverá hierarquia de work items (pai/filho) no primeiro protocolo?
10. Qual biblioteca de mensagens será adotada para plural/gênero (gettext,
    ICU MessageFormat, Fluent)?
11. O workflow será por tipo de trabalho, por workspace ou por serviço?
12. Qual o nível de override permitido para um flavor sobre outro?
13. Como autorizar mudanças de perfil em produção (revisão humana, quatro
    olhos, assinatura)?
14. Qual o prazo de retenção de evidências, waivers e snapshots?

## 15. Critérios de aceitação do protocolo futuro

O protocolo só pode ser considerado pronto quando:

- dois perfis contrastantes (AUTOSEG eletricista e comissão de arte) rodarem
  sobre o mesmo engine sem condicionais de flavor no núcleo;
- todos os rótulos visíveis vierem do léxico;
- o mesmo work item puder mudar de nome sem migração de dados;
- fluxos diferentes funcionarem por configuração validada;
- requisitos de conclusão forem declarativos e aplicados no servidor;
- papéis/capabilities forem independentes de rótulos;
- links, APIs, números e PDFs antigos continuarem válidos;
- houver testes de contrato, migração, concorrência, autorização e rollback;
- um perfil novo puder ser criado sem alterar Workaholic, Officina ou clientes;
- a documentação explicar como criar, versionar e revisar um perfil.

## 16. Esboço técnico de implementação futura

Este é um mapa conceitual, não uma API congelada. A implementação real deve
começar pela fase 1 e só avançar com testes de paridade.

### 16.1 Workaholic — primitivas sem vocabulário de produto

Possíveis módulos futuros:

```text
workaholic/src/workaholic/
  domain/
    work.py          # WorkItem, PartyRole, Assignment
    workflow.py      # State, StateKind, Transition, WorkflowDefinition
    requirements.py  # RequirementSpec, RequirementResult, composição all_of/any_of
    events.py        # eventos semânticos e auditoria
  application/
    work_service.py  # criar, transicionar, validar versão, consultar permitidos
  infrastructure/
    repositories.py  # persistência genérica
```

O núcleo não recebe “OS”, “comissão”, “prestador” ou “nota fiscal”. Ele recebe
IDs, kinds, requisitos e configuração validada. A responsabilidade de executar
PDF, e-mail, financeiro ou estoque **não** é do Workaholic puro.

### 16.2 Officina — protocolo e orquestração

Possíveis módulos futuros:

```text
officina/
  protocol/
    profile.py       # WorkProfile, composição e validação
    lexicon.py       # Term, resolução de locale e fallback
    fields.py        # FieldGroup, seções, visibilidade
    requirements.py  # avaliadores de aplicação + registro de kinds
    permissions.py   # capabilities, role presets e escopos
  application/
    work_service.py  # casos de uso, efeitos, transações e eventos
  presentation/
    view_model.py    # modelo pronto para GTK/web/CLI, sem regra de negócio
```

A Officina combina:

- o schema genérico do Workaholic;
- o perfil do flavor;
- o locale do usuário;
- os adaptadores de financeiro, documentos, estoque e notificações;
- as capabilities do ator.

### 16.3 Flavor — dados, não branches

Exemplo de árvore futura para o AUTOSEG:

```text
flavors/autoseg/
  profiles/
    service_order.yaml
  lexicon/
    pt-BR.yaml
    en.yaml
  fields/
    service_details.yaml
    fiscal_br.yaml
  workflows/
    service_order.yaml
  documents/
    service_report.yaml
  permissions/
    roles.yaml
```

Um flavor de artes teria os mesmos tipos de arquivo, com outros valores:

```text
flavors/arts/
  profiles/
    commission.yaml
  lexicon/
    pt-BR.yaml
  fields/
    art_spec.yaml
    usage_rights.yaml
  workflows/
    commission.yaml
```

Nenhum desses arquivos altera o código do Workaholic ou da Officina.

### 16.4 Fluxo de uma transição

```text
1. cliente solicita transição
2. Officina autentica o ator e verifica capability
3. Workaholic carrega o work item e valida versão/estado
4. Workaholic verifica se a transição existe no workflow
5. Officina avalia requisitos e evidências
6. se faltar requisito: retorna 409/422 com lista estruturada
7. se permitido: transação local + evento + efeitos enfileirados
8. resposta inclui novo estado, estado_kind, allowed_transitions e pendências
9. cliente renderiza o novo estado usando o léxico resolvido
```

### 16.5 Contrato conceitual de resposta

```json
{
  "work_item_id": "01J...",
  "state": "concluida",
  "state_kind": "done",
  "allowed_transitions": ["reabrir"],
  "missing_requirements": [],
  "labels": {
    "state": "Concluída",
    "work_item": "ordem de serviço"
  },
  "version": 8
}
```

`labels` é opcional e resolvido por locale; o cliente não deve persistir esses
textos como identidade. Em uma API pública, é preferível devolver chaves e
permitir que o cliente resolva o léxico com o perfil em cache.

### 16.6 Camadas de teste

- **Workaholic:** grafo válido, transições proibidas, concorrência, versão,
  requisitos primitivos, eventos.
- **Officina:** carregamento/validação de perfil, fallback de locale, composição
  de campos, capabilities e avaliadores.
- **Flavor:** golden tests de paridade AUTOSEG, migração de estados, documentos
  e requisitos.
- **Cliente:** renderização, acessibilidade, preservação de formulário e erros
  inline.
- **Contrato:** um perfil de artes e um de eletricista usando o mesmo engine sem
  branches de flavor.

## 17. Referências

- [`docs/PRODUCT_VISION.md`](../PRODUCT_VISION.md)
- [`docs/WORKAHOLIC_INTEGRACAO.md`](../WORKAHOLIC_INTEGRACAO.md)
- [`docs/ROADMAP.md`](../ROADMAP.md)
- [`workaholic/docs/ARCHITECTURE.md`](../../workaholic/docs/ARCHITECTURE.md)
- [`workaholic/docs/DECISIONS.md`](../../workaholic/docs/DECISIONS.md)
- [`workaholic/docs/adr/0002-semantic-work-protocol.md`](../../workaholic/docs/adr/0002-semantic-work-protocol.md)
- [`docs/PERMISSIONS_AND_APPROVALS.md`](../PERMISSIONS_AND_APPROVALS.md)
- [`docs/COMPLETUDE.md`](../COMPLETUDE.md) — comportamento atual do AUTOSEG
- [`docs/NAMING_AND_CLI.md`](../NAMING_AND_CLI.md) — nomes de produto e CLI
