# Condomínios, compartilhamento de OS e multiempresa

**Status:** visão de futuro. **Não é compromisso, prazo ou decisão de
arquitetura.** Registra um caminho possível para o Officina/AUTOSEG em
condomínios, com consentimento e isolamento de dados.

> **Vocabulário:** neste documento, “organização” geralmente significa
> **organização cliente** (condomínio/empresa). A **prestadora** é a empresa que
> executa o serviço e é dona dos dados operacionais (tenant); o AUTOSEG é a
> primeira prestadora. Não usar “loja”. Ver
> `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md`.

## 1. A ideia

Hoje o AUTOSEG é usado pela prestadora. O condomínio é o cliente do serviço.
No futuro, o condomínio pode ter uma conta própria no Officina para:

- acompanhar as OS que a AUTOSEG executa;
- receber relatórios, fotos e status;
- autorizar acesso de síndico, zelador e portaria com papéis diferentes;
- futuramente, gerenciar também serviços de terceiros (elétrica, pintura,
  manutenção geral).

A AUTOSEG continua sendo a prestadora. O condomínio não vira “dono” das OS da
AUTOSEG; ele recebe **acesso autorizado** a uma parte dos dados.

## 2. Três níveis de compartilhamento

| Nível | O que é | Complexidade | Quando |
|---|---|---|---|
| **1. Exportação** | PDF/ZIP/CSV de uma OS ou período, gerado pela prestadora | baixa | primeiro passo |
| **2. Portal do condomínio** | link/login read-only com status, fotos e relatório; papéis e consentimento | média | depois do portal atual estabilizar |
| **3. Workspace do condomínio** | o condomínio usa o Officina para as próprias OS e serviços | alta | futuro distante |
| **4. Rede multiempresa** | vários prestadores, vários condomínios, reputação, cobrança | muito alta | não agora |

O nível 1 é o mais seguro: não exige conta, sincronização ou banco novo. O
nível 2 já exige autenticação, permissões, consentimento e auditoria. O nível 3
é outro produto.

## 3. Consentimento e papéis

Compartilhar não pode ser automático. O fluxo precisa ser explícito:

1. a prestadora seleciona a OS/período e o escopo;
2. o responsável do condomínio recebe um convite/link;
3. o responsável aceita o escopo e indica os usuários;
4. o acesso tem prazo e pode ser revogado;
5. tudo fica registrado em auditoria.

Papéis sugeridos:

| Papel | Vê | Não vê |
|---|---|---|
| **Síndico** | OS, status, relatórios, fotos, valores do contrato | dados de outros condomínios |
| **Zelador** | OS, status, fotos, relatório técnico, comentários | financeiro interno da prestadora |
| **Porteiro** | status, previsão, acesso/autorização | valores, relatório completo, dados pessoais |
| **Morador** | apenas as próprias solicitações | OS de terceiros |

O princípio é **minimização**: cada papel vê o necessário para sua função.

## 4. O que é compartilhado

Por OS, com escopo configurável:

- número, cliente/condomínio, descrição e status;
- data prevista, responsável técnico e situação;
- fotos autorizadas e relatório técnico;
- valores do contrato ou da OS (opcional, por papel);
- PDF publicado;
- comentários/ciência do condomínio;
- histórico de acesso.

Não compartilhar por padrão:

- financeiro interno, custos, margem e repasses;
- dados de outros clientes;
- anotações internas;
- notas fiscais sem autorização;
- telefone/e-mail de pessoas fora do escopo.

## 5. Modelo de dados e arquitetura

Conceitos que o Workaholic/Officina precisariam ter:

```text
Organização/Tenant      condomínio, prestadora, administradora
Usuário                 pessoa com papel na organização
Vínculo                 usuário ↔ organização ↔ papel
Recurso compartilhado   OS, relatório, foto, contrato
Grant                   quem, o quê, escopo, validade, revogação
ShareLink               token de uso único/curto para acesso externo
AuditEvent              quem viu/baixou/alterou o quê e quando
```

A API poderia expor algo como:

```text
POST /api/v1/shares                 cria um compartilhamento com escopo
GET  /api/v1/shares/{id}            status/escopo
POST /api/v1/shares/{id}/revoke     revoga
GET  /api/v1/condos/{id}/os         lista autorizada
GET  /api/v1/shared/{token}         acesso externo de curta duração
```

O token de compartilhamento não é login permanente. Para o nível 2, o
condomínio tem conta e sessão próprias; para o nível 1, o link é temporário e
expira.

### Local-first

- O condomínio pode ter uma instância local do Officina no futuro;
- a prestadora pode compartilhar por exportação assinada ou por API;
- sync entre prestadora e condomínio é a fase mais complexa (conflitos,
  permissões, dinheiro, anexos);
- não começar por P2P entre condomínio e prestadora.

## 6. Modelos de implantação e open source

O mesmo código pode rodar em modelos diferentes. A escolha não é só técnica:
define quem responde por backup, atualização, segurança e suporte.

| Modelo | Quem opera | Onde ficam os dados | Responsabilidade | Quando faz sentido |
|---|---|---|---|---|
| **Local desktop** | condomínio/zelador | máquina local | usuário faz backup; sem acesso remoto | teste, condomínio pequeno, operação offline |
| **Servidor local** | condomínio | servidor/NAS na rede do condomínio | condomínio atualiza, faz backup e protege a rede | portaria/zelador com infraestrutura |
| **Auto-hospedado** | condomínio ou administradora | VPS/nuvem contratada por eles | eles cuidam de TLS, backup, patch e disponibilidade | condomínio com TI/administradora |
| **Hospedado por nós** | AUTOSEG ou parceiro | infraestrutura nossa | SLA, backup, atualização, suporte e incidente | condomínio sem TI e que quer delegar |
| **Híbrido/federado** | ambos | cada lado mantém o seu | consentimento, exportação/API e resolução de conflito | quando prestadora e condomínio trocam OS |

Detalhe importante: “local” pode ser o app GTK no notebook do zelador ou um
servidor headless na rede do condomínio. São operações diferentes; o modo
`--no-web` já cobre o primeiro, e o portal web cobre o segundo. O que falta é
empacotamento, instalador, atualização, backup e identidade.

### Open source muda a discussão

- A licença 0BSD permite usar, modificar e redistribuir, inclusive
  comercialmente, sem garantia.
- A marca, o suporte e a hospedagem são serviços separados do código. O projeto
  não controla forks.
- Receita provável: hospedagem gerenciada, implantação, suporte, SLA, treinamento
  e integração — não licença.
- Qualquer condomínio pode rodar sozinho. Isso é uma feature, não um problema;
  exige documentação de instalação, backup e atualização.
- O suporte precisa de matriz de versões: não dá para manter todas as versões e
  forks.
- Atualização de segurança precisa de canal e prazo; auto-hospedado sem patch
  vira risco.
- Formato de exportação e backup precisam ser abertos o suficiente para não
  prender o condomínio.
- Se nós hospedamos, viramos operadores de dados pessoais; é preciso
  contrato/DPA, retenção, exclusão e resposta a incidente. Se o condomínio
  hospeda, ele é o controlador e nós somos, no máximo, fornecedores.
- Multi-tenant só depois de identidade, permissão e isolamento testados. No
  início, uma instância por condomínio é mais simples e mais segura que um banco
  compartilhado.
- “Open source” não significa “suporte ilimitado de graça”. O escopo de suporte
  precisa estar escrito.

### Responsabilidades por modelo

| Atividade | Condomínio local/auto-hospedado | Hospedado por nós |
|---|---|---|
| Instalação | condomínio | nós |
| Atualização | condomínio (com aviso nosso) | nós |
| Backup/restore | condomínio | nós |
| TLS/domínio | condomínio | nós |
| Monitoramento | condomínio | nós |
| Suporte de uso | condomínio/contrato | incluído no contrato |
| Incidente de dados | condomínio lidera | nós lideramos |
| Exportação/portabilidade | condomínio | condomínio, com nosso apoio |

### O que não prometer

- que todo condomínio vai conseguir operar sozinho sem suporte;
- que um fork antigo continuará compatível;
- que hospedagem gerenciada é só “ligar o servidor”;
- que open source elimina custo operacional;
- que a mesma instância atende vários condomínios sem isolamento;
- que o condomínio pode editar OS da prestadora só porque tem uma instância.

### Sequência recomendada

1. exportação com consentimento (não depende de hospedagem);
2. portal read-only hospedado por nós, uma instância por condomínio se possível;
3. documentar instalação local/auto-hospedada e backup;
4. oferecer hospedagem gerenciada como serviço separado;
5. só depois workspace/federação.

Isso preserva a possibilidade de o condomínio ser independente sem obrigar a
AUTOSEG a virar provedora de infraestrutura para todos.

## 7. Escala

O que escala bem:

- separar **organização/tenant** de **usuário**;
- permissões por recurso, não por “tela”;
- exportação/portal read-only antes de workspace completo;
- auditoria e consentimento desde o início;
- banco local por instalação, servidor opcional.

O que não escala:

- um único `dados.db` compartilhado por vários condomínios e prestadoras;
- login compartilhado entre prestadora e condomínio;
- link público sem expiração/escopo;
- colocar valores, custos e repasses no portal do porteiro;
- tentar virar marketplace de serviços antes de resolver permissões e
  identidade.

## 8. Riscos e detalhes provavelmente inviáveis

- **Exportar sem consentimento** — viola expectativa de privacidade e LGPD.
- **Um link público permanente** — vaza dados e não tem revogação.
- **Porteiro ver financeiro** — desnecessário e perigoso.
- **Condomínio editar OS da prestadora** — outra empresa, outro contrato;
  exigiria fluxo de disputa e auditoria.
- **Multiempresa em um banco só sem `tenant_id`** — risco de vazamento.
- **Marketplace com reputação, cobrança e disputa** — produto separado, muito
  maior que “compartilhar OS”.
- **Sync bidirecional de OS/financeiro entre condomínio e prestadora** — conflito
  de autoridade; só depois de um contrato de dados e permissões.
- **Achar que “exportar PDF” é integração** — é o nível 1, não o produto
  completo.

## 9. Fases possíveis

### Fase A — Exportação com consentimento

- PDF/ZIP de uma OS ou período;
- carimbo de geração, escopo e validade;
- registro de quem exportou e para quem;
- sem conta no condomínio.

### Fase B — Portal read-only do condomínio

- conta do condomínio;
- convite do síndico;
- papéis síndico/zelador/porteiro;
- acesso por OS ou contrato;
- auditoria e revogação;
- sem edição de OS.

### Fase C — Workspace do condomínio

- condomínio cria solicitações próprias;
- prestadores autorizados recebem;
- OS de elétrica, pintura, manutenção etc.;
- o AUTOSEG é um prestador, não o dono do workspace;
- multiempresa de verdade.

### Fase D — Rede

- vários prestadores e condomínios;
- reputação, cobrança, disputas, SLAs;
- só com equipe, operação e suporte compatíveis.

## 10. Decisões abertas

- O condomínio é **tenant** ou apenas um **contato** da prestadora?
- Quem é o controlador dos dados da OS: prestadora, condomínio ou ambos?
- O consentimento é por OS, por contrato ou por condomínio?
- O condomínio pode comentar/aceitar, ou só visualizar?
- Quanto tempo o link/exportação fica válido?
- O condomínio pode baixar fotos/PDFs? Com qual marca d'água?
- Como revogar acesso e apagar dados mediante LGPD?
- Quem paga a conta do workspace do condomínio?
- O condomínio pode convidar outros prestadores? Com qual contrato?
- Como evitar que o condomínio veja dados de outros clientes da prestadora?
- Quem hospeda por padrão: condomínio, AUTOSEG ou um parceiro?
- Qual é o SLA e o que acontece quando o serviço cai?
- Quem paga a hospedagem e o que acontece se o condomínio parar de pagar?
- Como migrar de auto-hospedado para gerenciado — e o contrário — sem perder dados?
- Qual é a política de versões, forks e suporte?
- Quanto tempo os dados ficam retidos após o fim do contrato?

## 11. Recomendação

Começar pelo **nível 1/2** quando o portal atual e o `AppService` estiverem
estáveis:

1. exportação com consentimento e auditoria;
2. portal read-only com papéis e revogação;
3. documentação de instalação local/auto-hospedada e backup;
4. hospedagem gerenciada como serviço separado;
5. só depois pensar em workspace/marketplace.

Nada disso deve entrar antes de permissões, identidade, auditoria e LGPD
estarem resolvidas. É uma direção promissora, mas **sem compromisso de prazo**
e sem prometer que o condomínio vai gerenciar as OS da AUTOSEG.

## 12. Relação com os outros documentos

- `docs/planning/VISAO_MULTICLIENTE_LOCAL_FIRST.md`
- `docs/GTK_SERVER_DECOUPLING.md`
- `docs/planning/MULTI_PLATFORM_GUI_GUIDELINE.md`
- `docs/PRODUCT_VISION.md`
- `docs/HUMAN_CENTERED_DECISIONS.md`
