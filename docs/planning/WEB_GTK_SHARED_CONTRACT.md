# Contrato compartilhado entre site e GTK

**Status:** proposta de arquitetura de apresentação. **Não implementado.**
Nenhuma reescrita, nenhum framework de UI e nenhum código novo nesta fase.

**Última atualização:** 2026-11-10

---

## 1. Por que isso existe

Hoje o site e o GTK implementam a mesma tela duas vezes:

- a lista de OS tem colunas, filtros e ações em dois lugares;
- o formulário de OS tem campos, validações e textos em dois lugares;
- o financeiro tem KPIs, abas e regras de exibição em dois lugares;
- uma mudança no site não aparece automaticamente no GTK, e vice-versa.

Isso não é apenas duplicação de HTML/widgets. É duplicação de **comportamento
de produto**: o que a tela mostra, o que pode ser feito, qual texto aparece,
qual erro é exibido e qual permissão é exigida.

A abstração proposta compartilha **o contrato da tela**, não a aparência. O site
continua HTML/CSS; o GTK continua GTK4/libadwaita. Os dois consomem a mesma
descrição de tela, o mesmo view model e os mesmos casos de uso.

---

## 2. O que compartilhar e o que manter nativo

| Compartilhado (contrato) | Nativo (adaptador) |
|---|---|
| ID da tela e título | janela, sidebar, tabs, stack |
| Seções, ordem e hierarquia | widgets e layout |
| Campos, rótulos, ajuda e ordem | entrada de texto, select, data, checkbox |
| Validação e mensagens de erro | como o erro é mostrado (inline/toast/dialog) |
| Ações disponíveis e prioridade | botão, menu, atalho, ícone |
| Permissão exigida por ação | como a ação é escondida/desabilitada |
| Confirmações destrutivas | `Adw.AlertDialog`, `<dialog>`, etc. |
| Estados vazios, carregando, erro, offline | componente visual de cada plataforma |
| View model / DTO | renderização |
| Comandos e queries do `AppService` | transporte local ou HTTP |
| Terminologia e i18n | formatação nativa de datas/números |

**Regra:** o contrato diz **o quê**; o adaptador diz **como**. O contrato não
contém HTML, CSS, widgets GTK, SQL ou regra de negócio.

---

## 3. Arquitetura

```text
                 AppService (casos de uso)
                 /                      \
        Presentation Contract      Design tokens / i18n
           /            \
     Web adapter      GTK adapter
     (HTML/CSS)       (GTK4/Adw)
```

O `AppService` continua sendo a fronteira de negócio e permissão. O contrato de
apresentação apenas descreve a tela e aponta para os casos de uso. A UI não
decide permissão; ela consulta a política para esconder/desabilitar, mas o
serviço continua sendo a autoridade.

### 3.1 Formato inicial (conceitual)

Sem framework, sem DSL nova. Dataclasses Python simples, versionadas no
repositório:

```python
@dataclass(frozen=True)
class Screen:
    id: str
    title: str
    sections: tuple[Section, ...]
    actions: tuple[Action, ...]

@dataclass(frozen=True)
class Section:
    id: str
    title: str
    fields: tuple[Field, ...]

@dataclass(frozen=True)
class Field:
    id: str
    label: str
    kind: str          # text, money, date, select, checkbox, textarea
    required: bool
    help: str = ''
    permission: str | None = None

@dataclass(frozen=True)
class Action:
    id: str
    label: str
    command: str       # nome do caso de uso no AppService
    permission: str
    style: str         # primary, secondary, danger
    confirmation: str | None = None
```

O exemplo é ilustrativo. O importante é que o contrato seja **dados**, não uma
segunda implementação da regra de negócio.

### 3.2 Exemplo: lista de OS

```text
Screen: work_item.list
Query: AppService.listar_os_ativas(filtro)
Columns: número, cliente, status, responsável, total, atualizado_em
Actions:
  - abrir (work_item.view.involved)
  - nova (work_item.create)
Empty state: "Nenhuma OS ativa."
```

- Web renderiza uma tabela HTML.
- GTK renderiza uma `Adw` list/column view.
- Os dois usam o mesmo DTO, os mesmos rótulos e a mesma regra de permissão.

### 3.3 Exemplo: formulário de OS

```text
Screen: work_item.edit
Sections: identificação, materiais, situação, composição, rateio, mídias
Commands: salvar_os, iniciar_os, concluir_os, cancelar_os
Validation: compartilhada no AppService
Auto-save: contrato de evento, não um botão "Salvar"
```

- Web usa inputs HTML; GTK usa `Adw.EntryRow`, `Gtk.TextView`, etc.
- A validação e a mensagem vêm do serviço/contrato, não de cada tela.
- A confirmação de cancelamento é nativa em cada plataforma, com o mesmo texto
  e a mesma exigência de motivo.

---

## 4. Testes de contrato

O contrato só é confiável se os dois adaptadores forem testados contra ele:

- **teste de contrato**: a tela declara os campos/ações esperados; o adaptador
  web e o adaptador GTK expõem todos eles;
- **teste de permissão**: uma ação proibida não aparece e, se chamada direto no
  serviço, falha;
- **teste de validação**: o mesmo erro é retornado pelo serviço e exibido pelos
  dois adaptadores;
- **teste de view model**: o DTO não vaza `sqlite3.Row`, HTML ou objeto GTK;
- **teste de regressão visual**: manual/smoke por plataforma, não pixel a pixel.

Não é necessário testar HTML no GTK nem widgets GTK no navegador. O contrato é
o denominador comum.

---

## 5. Adoção incremental

### Fase 0 — documentação e inventário (agora)

- este documento;
- lista das telas duplicadas e dos campos/ações que precisam de contrato;
- nenhuma mudança de comportamento.

### Fase 1 — leitura

- escolher uma tela de leitura: **lista de OS** ou **lista de clientes**;
- definir o contrato e o view model;
- fazer o adaptador web e o GTK consumirem o mesmo contrato;
- manter o visual atual;
- testes de contrato e de permissão.

### Fase 2 — formulário

- escolher um formulário: cliente ou OS;
- mover validação/mensagens para o serviço;
- contrato de campos e ações;
- auto-save com eventos compartilhados;
- web e GTK renderizam nativamente.

### Fase 3 — financeiro e telas administrativas

- KPIs, abas, filtros e ações;
- permissões por papel;
- mesmos textos e estados.

### Fase 4 — tokens e i18n

- consolidar os tokens já documentados em
  `docs/planning/MULTI_PLATFORM_GUI_GUIDELINE.md`;
- chaves de tradução compartilhadas;
- formatos nativos de data/moeda.

Cada fase é um PR pequeno, com flag e rollback. Nenhuma fase reescreve o portal
inteiro.

---

## 6. O que não fazer

- não criar um framework de UI genérico;
- não criar uma DSL de telas que vire uma segunda linguagem de programação;
- não colocar HTML dentro do GTK nem widgets GTK no navegador;
- não duplicar regra de negócio no contrato: ele aponta para o `AppService`;
- não usar o contrato para “esconder” permissão; o serviço continua validando;
- não buscar paridade pixel a pixel;
- não migrar todas as telas de uma vez;
- não bloquear a consolidação de OS/financeiro por causa dessa abstração.

---

## 7. Relação com o audit de engenharia

O audit está correto ao priorizar:

1. autorização no serviço;
2. consolidação de ordens de serviço;
3. representação financeira;
4. remoção de SQL/regra de negócio dos portais;
5. adiamento da expansão do Workaholic.

O contrato web/GTK **não compete** com essa ordem. Ele é uma ferramenta para
executar os itens 2 e 4 com menos duplicação: uma vez que a lista/formulário de
OS tenha um contrato, o site e o GTK deixam de implementar a mesma regra duas
vezes.

Ele também não é a mesma coisa que Workaholic:

- **Workaholic** é um motor genérico de domínio, ainda protótipo;
- **contrato web/GTK** é uma camada de apresentação do produto atual, com
  consumidores reais e benefício imediato.

Por isso, o contrato pode avançar antes do Workaholic, desde que fique restrito
ao que o AUTOSEG já usa.

---

## 8. Critério para dizer que funcionou

- uma mudança de campo/label/validação em uma tela aparece nos dois adaptadores
  sem editar os dois;
- a mesma ação tem o mesmo nome, a mesma permissão e o mesmo resultado no site
  e no GTK;
- o site e o GTK continuam visualmente nativos;
- o serviço continua sendo a única autoridade de permissão;
- os testes de contrato quebram quando um adaptador esquece um campo/ação;
- nenhuma tela foi reescrita de uma vez.

---

## 9. Relação com os documentos existentes

- `docs/planning/MULTI_PLATFORM_GUI_GUIDELINE.md` — princípios visuais e
  tokens; este documento é o contrato funcional entre web e GTK.
- `docs/SURFACE_PARITY.md` — paridade de capacidades; o contrato é a fonte.
- `docs/GTK_SERVER_DECOUPLING.md` — `AppService`, `LocalService` e
  `HttpService`.
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md` — migração em fatias.
- `docs/PLATFORM_MIGRATION_LEDGER.md` — estado das fatias.
- `docs/HUMAN_CENTERED_DECISIONS.md` — decisões de produto.
- `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` — autorização por
  objeto e site único.
