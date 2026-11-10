# Officina Web e Officina GTK — evolução a partir do AUTOSEG

**Status:** planejamento. **Não autoriza implementação, reescrita ou migração.**
A prioridade continua sendo o AUTOSEG funcionando. Este documento registra
como o site e o GTK atuais podem originar produtos genéricos do ecossistema
Officina sem transformar o AUTOSEG em um fork.

**Última atualização:** 2026-11-10

**Correção de vocabulário:** o AUTOSEG **não é uma loja**. É uma **prestadora de
serviço** dentro do ecossistema Officina. “Loja” não descreve o produto, o
tenant nem o modelo de negócio.

---

## 1. Decisão de produto

O AUTOSEG é a primeira prestadora de serviço real do ecossistema Officina. O
site e o app GTK atuais são as primeiras implementações concretas:

```text
AUTOSEG hoje
  ├── site do prestador + portal do cliente   → semente do Officina Web
  ├── app GTK do prestador                    → semente do Officina GTK
  ├── API/desktop                             → semente do Officina API
  └── vocabulário, OS, PDF, fiscal, branding   → flavor AUTOSEG

Officina amanhã
  ├── Officina Web   (produto web genérico)
  ├── Officina GTK   (produto desktop genérico)
  ├── Officina API   (contratos e serviços)
  └── prestadoras    (AUTOSEG primeiro; outras depois)
```

O AUTOSEG não é o ecossistema inteiro. É o primeiro cliente real que prova as
decisões. O Officina Web/GTK só devem nascer de necessidades reais observadas
no AUTOSEG, não de uma reescrita preventiva.

---

## 2. O que significa “prestadora” aqui

Uma **prestadora** é a organização que executa o serviço, abre OS, mantém
clientes, recebe, paga e emite documentos. É o limite operacional e de dados
(tenant).

Uma **organização cliente** é o condomínio/empresa atendida. Ela tem papéis
próprios (morador, síndico, gestor, administrador), mas não é a prestadora.

Uma **conta** é a identidade de login. Ela pode ter:

- vínculo de cliente com uma prestadora;
- vínculo de prestador/funcionário com uma prestadora;
- vínculo de admin da prestadora;
- mais de um vínculo, inclusive cliente e prestador na mesma conta.

O AUTOSEG é a primeira prestadora. O Officina Web poderá hospedar várias
prestadoras; isso é planejamento, não escopo da primeira entrega.

---

## 3. O que é genérico e o que é AUTOSEG

| Área | Officina (genérico) | AUTOSEG (flavor/prestadora) |
|---|---|---|
| Conta, login, sessão, CSRF | sim | textos, branding, políticas padrão |
| Vínculos, papéis, permissões | sim | presets e nomes de papéis |
| Prestadora/tenant | sim | configuração da AUTOSEG |
| OS/work item | contrato genérico | fluxo, status, campos e regras AUTOSEG |
| Cliente e organização cliente | contrato genérico | condomínio, síndico, PJ, campos brasileiros |
| Financeiro/recebíveis/repasses | contrato genérico | rateio, repasse, PIX, regras AUTOSEG |
| Documentos/PDF | contrato genérico | templates, marca, textos e fiscal brasileiro |
| Estoque/materiais | contrato genérico | vocabulário e regras AUTOSEG |
| GTK shell/navegação | sim | telas e fluxos AUTOSEG |
| Web shell/navegação | sim | telas e fluxos AUTOSEG |
| Fiscal/NF-e/NFS-e | contrato de provedor | implementação brasileira |
| E-mail/pagamentos | contrato de integração | Gmail, PIX e regras AUTOSEG |

**Regra de dependência:** Officina não importa AUTOSEG. AUTOSEG pode importar
Officina. Um flavor adiciona configuração, vocabulário, telas e módulos; não
copia o produto inteiro.

---

## 4. Como o site atual vira Officina Web

### 4.1 O que já existe e deve ser preservado

- dois servidores no mesmo processo (`ServidorPortal` e `PortalPrestador`);
- portal do cliente com CPF/senha e isolamento por cliente/organização;
- portal do prestador com e-mail/senha, OS, clientes, financeiro, estoque,
  composição, feedback e administração;
- API financeira e API desktop;
- PDF, e-mail, anexos, notas fiscais;
- testes de fluxo e caracterização.

Nada disso deve ser jogado fora. A unificação é uma migração, não um novo
produto paralelo.

### 4.2 O que precisa ser extraído

1. **Identidade e sessão** — conta única, vínculos, contexto, cookie/CSRF.
2. **Política por objeto** — `Principal`, `Resource`, `can/require`, campos.
3. **Prestadora/tenant** — `provider_org_id`, filtro de repositório, admin
   scoped.
4. **Shell web** — layout, navegação, componentes, tratamento de erro.
5. **Contratos de aplicação** — OS, cliente, financeiro, documentos, estoque.
6. **Rotas e URLs** — uma origem, namespaces, redirects históricos.
7. **Auditoria** — decisão, ator, contexto, recurso e motivo.

### 4.3 O que continua no AUTOSEG

- vocabulário “OS”, “prestador”, “condomínio”, “síndico”;
- fluxo de status e regras de negócio;
- composição de valores e rateio;
- PDF, marca, CNPJ, WhatsApp e textos;
- integrações brasileiras (Gmail, PIX, NF-e/NFS-e quando existirem);
- telas específicas de segurança/automação;
- presets de papéis e políticas padrão.

### 4.4 Arquitetura de transição

```text
Navegador
   │
   ▼
Uma origem (proxy/roteador)
   ├── /app, /entrar, /conta, /acompanhar  → shell novo
   ├── /cliente/*, /pj/*                   → redirect/legado
   └── /api/v1                             → API única
        │
        ├── serviço de identidade (accounts/links)
        ├── serviço de política (ObjectPolicy)
        └── dados da prestadora (provider_org_id)
```

Durante a transição, os dois servidores atuais podem continuar atrás do
roteador. O usuário vê uma origem e um login; a complexidade interna diminui
por fatias.

---

## 5. Como o GTK atual vira Officina GTK

### 5.1 O que já existe

- app GTK4/libadwaita;
- login local/servidor;
- `AppService`/`LocalService`/`HttpService`;
- telas de clientes, OS, financeiro, histórico, PJ, catálogo, estoque, caixa,
  composição e PDF;
- `WebAccessManager` para os portais.

### 5.2 O que precisa ser extraído

1. **Shell GTK** — janela, navegação, sidebar, atalhos, temas, acessibilidade.
2. **Contratos de aplicação** — o GTK não pode falar SQL direto.
3. **Sessão e contexto** — conta única, vínculo ativo, troca de contexto.
4. **Política** — o GTK local também recebe ator e respeita permissão.
5. **Componentes reutilizáveis** — tabelas, formulários, diálogos, estados
   vazios, erros.
6. **Branding por flavor** — nome, logo, cores, textos.

### 5.3 O que continua no AUTOSEG

- telas e fluxos específicos;
- vocabulário e campos;
- relatórios e PDF;
- integrações;
- presets de permissão.

### 5.4 Regra de paridade

GTK, web e API devem ter as **mesmas capacidades de produto**, filtradas pelo
mesmo contexto e pela mesma política. Uma ação não pode ser permitida no GTK
local e negada no web (ou vice-versa). O modo local não é uma exceção de
segurança.

---

## 6. Roteiro incremental

### Etapa A — AUTOSEG primeiro (agora)

- manter o AUTOSEG funcionando;
- documentar identidade, prestadora e política;
- caracterizar o comportamento atual;
- corrigir o esqueleto de política sem bloquear o site;
- não iniciar multi-prestadora.

### Etapa B — identidade única atrás de flag

- `accounts`, `account_links`, `provider_orgs`;
- login único e contexto;
- portais antigos como fallback;
- testes de migração e rollback.

### Etapa C — shell web único

- uma origem, um shell, redirects;
- política de leitura/PII;
- depois escrita;
- OS anônima e acompanhamento.

### Etapa D — extração do Officina Web

- mover shell, auth, política e contratos para `officina/`;
- manter AUTOSEG como flavor/prestadora;
- criar o primeiro produto web genérico somente quando houver um segundo
  consumidor real ou necessidade concreta.

### Etapa E — extração do Officina GTK

- mover shell e componentes para o produto genérico;
- manter telas/fluxos AUTOSEG no flavor;
- garantir paridade com o web;
- não reescrever o GTK por estética.

### Etapa F — multi-prestadora

- decidir banco compartilhado vs banco por prestadora;
- isolamento testado;
- branding/fiscal/numeragem por prestadora;
- admin de plataforma separado de admin de prestadora;
- só então permitir outras prestadoras na mesma instalação.

---

## 7. Não objetivos

- não criar uma “loja” ou marketplace;
- não transformar o AUTOSEG em um fork do Officina;
- não reescrever o GTK ou o site antes de a identidade e a política estarem
  testadas;
- não permitir multi-prestadora sem isolamento e auditoria;
- não copiar código AUTOSEG para o core;
- não prometer sync/offline/mobile nesta fase;
- não mudar comportamento visível do AUTOSEG sem pedido explícito e testes.

---

## 8. Critérios para dizer que o Officina Web/GTK “nasceu”

- existe uma conta única com vínculos e contexto;
- a política por objeto é aplicada no serviço, não na UI;
- o isolamento por prestadora tem testes;
- o shell web/GTK é genérico e o AUTOSEG é um flavor;
- o AUTOSEG continua com paridade de comportamento;
- há um segundo consumidor real ou uma necessidade concreta que justifique a
  extração;
- documentação, testes e rollback estão prontos.

Até lá, “Officina Web” e “Officina GTK” são direção de produto, não promessa de
entrega.

---

## 9. Relação com os outros documentos

- `docs/PRODUCT_VISION.md` — camadas e princípios do produto.
- `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` — site único,
  identidade, prestadora, permissões e OS anônima.
- `docs/PERMISSIONS_AND_APPROVALS.md` — catálogo e aprovação de mudanças.
- `docs/PERMISSIONS_P0.md` — matriz P0.
- `docs/APP_MODES_ROLES_AND_SERVERS.md` — modos, papéis e servidores.
- `docs/GTK_SERVER_DECOUPLING.md` — separação GTK × servidor.
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md` — como migrar uma fatia.
- `docs/PLATFORM_MIGRATION_LEDGER.md` — o que já migrou.
- `docs/HUMAN_CENTERED_DECISIONS.md` — decisões que precisam de contexto
  humano.
