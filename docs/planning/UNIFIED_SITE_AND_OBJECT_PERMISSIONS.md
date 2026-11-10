# Site único, identidade e permissões por objeto

**Status:** arquitetura-alvo e auditoria do estado atual. **Nenhuma mudança de
código nesta fase.** Autenticação, permissões e migração de dados são N3/N4:
precisam de revisão humana e implantação gradual, preferencialmente atrás de
flag.

**Última atualização:** 2026-11-10

**Decisão de produto:** o AUTOSEG deixa de ser dois portais separados e passa a
ter **um link, um site e um login**. Depois do login, o sistema identifica a
conta e os vínculos da pessoa:

- cliente;
- prestador/funcionário;
- administrador da prestadora;
- mais de um vínculo na mesma conta, quando for o caso.

A mesma pessoa pode entrar como cliente e como prestador (proposta; ver §10). A
escolha do contexto é explícita quando houver mais de um vínculo.

**Correção de vocabulário:** o AUTOSEG **não é uma loja**. O AUTOSEG é uma
**prestadora de serviço** dentro do ecossistema Officina. “Loja” não é o termo
correto para o tenant, para a empresa ou para o produto. Neste documento:

- **Officina** é o ecossistema/plataforma;
- **AUTOSEG** é a primeira prestadora de serviço e a primeira distribuição real;
- **Officina Web** é o produto web genérico que nascerá do site atual;
- **Officina GTK** é o produto desktop genérico que nascerá do app GTK atual;
- **prestadora/organização prestadora** é o limite operacional e de dados
  (tenant), não uma loja.

---

## 0. Resumo executivo

O estado atual não é “dois portais com o mesmo login”. São **dois produtos
separados no mesmo processo**, com identidades, cookies, sessões, senhas,
permissões e rotas diferentes:

| Hoje | Cliente | Prestador |
|---|---|---|
| Porta | 8765 | 8766 |
| Identidade | `v9_usuarios` (CPF) | `prestadores` (e-mail) |
| Cookie | `autosseg_pj` | `autosseg_session` |
| Sessão | `portal_v9.SESSOES` em memória | `portal_prestador.SESSOES` em memória |
| Login | `/entrar-pf` | `/login` |
| Admin | papéis da organização cliente (`v9_responsaveis`) | flag global `v9_admin_prestadores` |
| Legado | `cliente_acessos` + `autosseg_legado` | `desktop_sessoes` e `api_tokens` |

A intenção de unificar já existe em documentos antigos, mas o código nunca
chegou lá. O roteador híbrido de `portal_v9.py` é praticamente inalcançável
porque o portal do prestador intercepta `/pj`, `/chamados` e `/organizacoes`.
O resultado é um histórico de tentativas parciais, não uma base de login único.

O problema maior não é estético. A auditoria encontrou:

- qualquer prestador autenticado consegue abrir **qualquer OS** e baixar
  **prévia de PDF não publicada**, YAML e contato do cliente;
- a API desktop autentica o prestador, mas não aplica permissão em várias
  rotas de OS, PJ e financeiro;
- o admin é **global na instalação**, não scoped à prestadora;
- não existe `tenant_id`/`provider_org_id` nas tabelas operacionais;
- o cliente tem isolamento razoável por `cliente_pf_id`/`v9_responsaveis`, mas
  o prestador não tem isolamento por objeto;
- existem 15 consultas inline a `v9_admin_prestadores`, cerca de 34 usos de
  `responsavel_atual`, 30 usos de `s.get('admin')` e 40 `PermissionError` só em
  `portal_prestador.py`.

### 0.1 O que muda no alvo

- **Um link, um site, um login** — cliente e prestador na mesma origem.
- **Conta + vínculos** — a mesma pessoa pode ser cliente e prestador; o
  contexto é explícito.
- **Prestadora/tenant** — o AUTOSEG é a primeira prestadora; todo dado
  operacional pertence a ela.
- **Política por objeto** — view/edit/assign/finance/rateio/documento com
  escopo `own`/`involved`/`provider_org` e campos de PII.
- **OS anônima** — permitida pela política da prestadora, com protocolo, link,
  triagem e limites.
- **Officina Web/GTK** — extração posterior do shell, auth e contratos; o
  AUTOSEG continua sendo o flavor/prestadora.
- **Auditoria** — toda decisão sensível registra ator, contexto, recurso,
  decisão e motivo.

**Conclusão:** unificar o login sem antes criar a camada de identidade e a
política por objeto apenas esconderia o problema. A ordem correta é:

1. identidade única e vínculos;
2. prestadora/tenant explícito;
3. política por objeto no serviço;
4. site único e login único atrás de flag;
5. OS anônima e acompanhamento;
6. retirada dos portais antigos.

---

## 1. Contexto: Officina, AUTOSEG e o primeiro site

### 1.1 Camadas

```text
Workaholic
  motor genérico: registros, schemas, validação, versionamento, armazenamento

Officina
  ecossistema/plataforma: contratos de aplicação, política, capacidades,
  vocabulário genérico e futuros produtos Officina Web / Officina GTK

AUTOSEG
  primeira prestadora de serviço e primeira distribuição real do ecossistema;
  vocabulário, fluxo de OS, relatórios, branding, fiscal e integrações

Officina Web / Officina GTK
  produtos genéricos que serão extraídos do site e do GTK atuais
```

O AUTOSEG é o **primeiro cliente real** do ecossistema, não o ecossistema
inteiro. O site e o GTK atuais são provas de uso que devem originar os produtos
genéricos. Essa extração é planejamento; a prioridade continua sendo o AUTOSEG
funcionando bem.

### 1.2 O que é genérico e o que é AUTOSEG

| Área | Deve ir para Officina | Fica no AUTOSEG |
|---|---|---|
| Conta, login, sessão, vínculos | sim | branding e textos |
| Política por objeto, papéis, campos | sim | presets e nomes de papéis |
| OS/work item, cliente, financeiro genérico | sim, por contratos | regras de negócio específicas |
| Prestadora/tenant e isolamento | sim | configuração da prestadora |
| PDF, e-mail, NFS-e, PIX, CPF/CNPJ | contrato genérico | implementação brasileira/AUTOSEG |
| GTK shell, navegação, componentes | sim | telas e fluxos AUTOSEG |
| Web shell, login, layout | sim | telas e fluxos AUTOSEG |

**Regra:** o core/Officina não importa AUTOSEG. O AUTOSEG pode depender do
Officina. A extração é incremental; não é um fork nem uma reescrita big-bang.

### 1.3 Por que “loja” está errado

“Loja” sugere varejo, catálogo e checkout. O AUTOSEG presta serviço técnico,
abre OS, executa atendimento, emite relatório e cobra. O limite correto é
**prestadora/organização prestadora** (tenant). Uma futura instalação Officina
pode hospedar várias prestadoras; o AUTOSEG é a primeira delas.

---

## 2. Estado atual auditado

Esta seção é factual. As referências são a funções, rotas e tabelas; números de
linha mudam com frequência e não são contrato.

### 2.1 Dois servidores, dois logins

`flavors/autoseg/modules/servidor_backend.py` inicia dois servidores HTTP no
mesmo processo:

- `ServidorPortal` em 8765 (cliente);
- `PortalPrestador` em 8766 (prestador).

Não há proxy reverso nem dispatcher por caminho. A escolha do “portal” é feita
pela porta. Os cookies não têm `Domain`, então o navegador envia todos para os
dois portos; cada servidor ignora o cookie que não conhece.

### 2.2 Identidades e sessões

| Contexto | Identidade | Credencial | Sessão | Admin |
|---|---|---|---|---|
| Cliente CPF | `v9_usuarios.cpf` | `senha_hash` | `autosseg_pj`, memória | `v9_responsaveis` por organização cliente |
| Cliente legado | `cliente_acessos.cliente_id` | `senha_hash` | `autosseg_legado`, memória | nenhum; somente leitura |
| Prestador web | `prestadores.email` | `senha_hash` | `autosseg_session`, memória | `v9_admin_prestadores`, global |
| Prestador desktop | `prestadores.id` | token `autoseg_desk_` | `desktop_sessoes`, banco | `v9_admin_prestadores`, global |
| API financeira | `prestadores.id` | token `autoseg_fin_` | `api_tokens`, banco | escopo `financeiro:read` |
| MAF (dormente) | `meu_auto_financeiro.usuarios` | senha própria | `maf_session`, memória | admin da família |

Não existe tabela `accounts`, `account_links`, `memberships` ou equivalente.
Uma pessoa que é cliente e prestador precisa de duas contas e dois logins.

### 2.3 Onde a permissão é decidida hoje

A autorização está espalhada em três camadas informais:

1. **Wrapper HTTP**: `if not s.get('admin'): raise PermissionError` em algumas
   rotas.
2. **Função de domínio**: `if admin`/`responsavel_atual` em outras.
3. **Nenhuma**: rotas e funções que confiam no chamador.

O mesmo tipo de decisão aparece em lugares diferentes:

| Decisão | Implementação A | Implementação B | Implementação C |
|---|---|---|---|
| Editar OS | `neg.os_salvar` exige responsável ou admin | `prod._os_ativa_responsavel` repete a regra | `os_write.salvar_os` não verifica nada |
| Ver OS | `os_form` não verifica vínculo | `prod.participou` libera PDF/NF para participante | lista de OS mostra todas as OS ativas a qualquer prestador |
| Gerenciar PJ | wrapper web verifica admin | `portal_v9.post` não verifica | API desktop não verifica |
| Atribuir OS | wrapper web verifica admin | `ext.atribuir` não verifica | API desktop não verifica |
| Confirmar recebimento | wrapper web verifica finalizador/admin | `neg.financeiro_receber` não verifica | API/local não verifica |
| Publicar relatório | rota web não verifica | `fluxo.publicar_relatorio` não verifica | API desktop não verifica |

Os números do grep atual:

- **15** consultas inline a `v9_admin_prestadores`;
- **~34** usos de `responsavel_atual(...)`;
- **30** usos de `s.get('admin')`, sendo 21 no formato “nega se não for admin”;
- **40** `raise PermissionError` em `portal_prestador.py`;
- **15** em `prestadores_ext.py`;
- **9** em `produtividade_os.py`.

Isso não é uma camada de permissão. É uma convenção social repetida em cada
rota, fácil de esquecer e impossível de auditar de forma central.

### 2.4 Falhas concretas

#### P0 — antes de qualquer exposição maior

1. **API desktop é praticamente root para qualquer token de prestador.**
   `api_desktop._rota_os` não recebe o ator e chama `LocalService.salvar_os`,
   que não verifica responsável, status ou arquivamento. Qualquer prestador
   autenticado pode editar, atribuir, iniciar, publicar e baixar PDF de
   qualquer OS. `_rota_pj` não verifica admin. `GET /financeiro` devolve o
   financeiro global.

2. **Qualquer prestador lê qualquer OS e PII.**
   `GET /os/<id>` (`os_form`) não verifica vínculo. A rota devolve cliente,
   contato, valores, materiais, eventos, fotos e relatório interno. O mesmo
   vale para `/os/<id>/relatorio.yaml`, `/os/<id>/pdf-preview` e
   `/clientes/<id>/contato`.

3. **Não existe fronteira de prestadora/tenant.**
   `prestadores`, `clientes`, `ordens_servico`, `financeiro`,
   `produtividade_rateios`, `estoque_*` e `empresa_movimentos` não têm
   `provider_org_id`/`tenant_id`. `v9_admin_prestadores` tem apenas
   `prestador_id`; o admin é global. Um banco = uma instalação inteira.

4. **Qualquer prestador lista e busca a base inteira de clientes.**
   `clientes_core.listar_paginado` devolve documento, telefone e e-mail;
   `clientes_lista` mostra tudo sem mascaramento; a busca rápida aceita
   documento. Isso contradiz a própria matriz P0, que reserva PII para
   clientes envolvidos em OS do prestador.

5. **Funções de domínio administrativas não têm segunda linha de defesa.**
   `ext.cadastrar`, `ext.alternar_ativo`, `ext.arquivar_prestador`,
   `ext.redefinir_senha_prestador_desktop`, `cad.definir_admin`,
   `cad.atribuir_responsavel`, `cad.mesclar_*`, `fluxo.publicar_relatorio`,
   `ext.remover_nota_fiscal`, `neg.financeiro_receber` e outras não recebem
   ator nem verificam permissão. A proteção existe só em alguns wrappers.

#### P1 — alto

6. **Participação é permanente.** `os_prestadores.ativo` existe, mas nenhum
   código o coloca em 0. `prod.participou` ignora `ativo`. Quem foi atribuído
   uma vez, ou apenas gerou um evento, mantém acesso a PDF, fotos, NF e e-mail.

7. **Não há proteção do último admin nem auditoria de mudança de admin.**
   `cad.definir_admin` insere/remove direto. O web permite alternar o próprio
   admin. Nenhuma das duas ações grava evento.

8. **Financeiro/rateio têm dono frágil.** OS encerrada pelo desktop grava
   `os_encerramentos.prestador_id = NULL`; ninguém vê o recebível em
   `financeiro_pessoal` e o repasse não fecha. `neg.financeiro_receber` não
   verifica ator. `definir_rateio_manual` permite admin atribuir parcela a si
   mesmo quando não é o finalizador. `financeiro_cancelar` apaga rateios de
   todos os técnicos.

9. **Admin de PJ só é barrado em um wrapper.** `portal_prestador` verifica
   admin no POST; `portal_v9.post` e `api_desktop._rota_pj` não. O GET
   `/organizacoes/responsaveis` lista organizações e CPF parcial para qualquer
   prestador.

10. **Publicação e prévia não têm autorização.** `POST /os/<id>/publicar` e
    `fluxo.publicar_relatorio` não verificam quem publica. A prévia é pior:
    expõe dados ainda não publicados.

#### P2 — médio

11. **GTK/local é UI-only.** O menu sempre mostra Prestadores, Estoque,
    Composição e Financeiro; `LocalService` não recebe ator. Um prestador
    comum pode executar ações de admin no app local.

12. **Permissões de catálogo/configuração são arbitrárias.** Qualquer
    prestador altera serviços e preços; estoque, caixa, composição e
    prestadores são admin-only. Não há política que explique a diferença.

13. **O esqueleto de política está morto e tem falhas de desenho.**
    `ObjectPolicy` não é importado por produção. A checagem de organização
    falha aberta quando os IDs são `None`; o admin passa antes de um `deny`
    explícito; as ações não incluem `start`, `assume`, `archive`, `reopen`,
    `attach`, `download`, `confirm`, `send`, `merge` e `impersonate`.

14. **Regras de PDF do cliente divergem.** `pdf_chamado` não inclui `Gestor`;
    `pdf_pj` inclui `Gestor` para Empresa; o legado rejeita PJ inteiro.

### 2.5 O que já está razoavelmente correto

- O cliente PF é isolado por `v9_usuarios.cliente_pf_id` + `clientes.id`
  (`obter_os_pf`, `listar_os_pf`, `pdf_pf`).
- O cliente PJ é isolado por `v9_organizacoes` + `v9_responsaveis`
  (`listar_os_organizacao`, `autorizar_pdf_os_organizacao`).
- O chamado é isolado por `v9_chamados.usuario_id`.
- O portal do prestador verifica sessão em todas as rotas não públicas e
  revalida senha/ativo a cada request.
- O login do prestador tem rate limit e mensagem genérica.
- O cliente não vê custo, margem, rateio, repasse ou dados bancários do
  prestador no HTML.
- A API financeira tem token com escopo e rate limit.

Essas partes boas devem ser preservadas e migradas para a camada única, não
jogadas fora.

### 2.6 Conclusão da auditoria

O sistema atual tem **duas ilhas de isolamento parcial**:

1. admin × prestador comum no portal web;
2. cliente × cliente no portal do cliente.

Fora dessas ilhas, a autorização é opcional. O desktop API, o GTK local, a
prévia de PDF, o YAML, o contato do cliente e a publicação de relatório
derrubam até essas duas ilhas. Antes de adicionar papéis novos, multi-prestadora
ou login único, o serviço precisa receber um ator e uma política única.

---

## 3. Modelo-alvo

### 3.1 Princípios

1. **Uma identidade, vários vínculos.** A conta não é cliente nem prestador;
   ela tem vínculos.
2. **A prestadora é o limite operacional.** Todo dado operacional pertence a
   uma prestadora/organização prestadora.
3. **Papel é preset de capacidade, não escada rígida.** Admin, prestador,
   financeiro, despachante, campo, leitura e cliente são presets iniciais.
4. **A política decide; a UI só reflete.** Esconder um botão não é segurança.
5. **Negar por padrão.** Sem vínculo ou permissão, a resposta é não.
6. **Anônimo é política, não bypass.** A OS anônima é permitida se a política
   da prestadora permitir, com limites e auditoria.
7. **Toda decisão sensível é auditada.** Quem, quando, em qual recurso, qual
   decisão e por quê.

### 3.2 Identidade

```text
accounts
  id, email, cpf, telefone, senha_hash, ativo, email_verificado,
  telefone_verificado, criado_em, atualizado_em

account_links / memberships
  id, account_id, provider_org_id, tipo (provider|client),
  provider_id | client_id | client_org_id,
  papel, status, criado_em, atualizado_em
```

Regras:

- a conta guarda credenciais e identificadores de login;
- o perfil de cliente e o perfil de prestador continuam separados;
- a mesma conta pode ter vínculo de cliente e de prestador;
- a mesma pessoa pode ter vínculos em mais de uma prestadora no futuro;
- desativar conta/vínculo não apaga histórico;
- e-mail e CPF são atributos únicos **por prestadora** quando a instalação
  hospedar várias prestadoras; na primeira fase, com uma prestadora, podem ser
  únicos na instalação;
- o login aceita e-mail ou CPF (proposta; ver §10).

### 3.3 Prestadora/organização prestadora

```text
provider_orgs
  id, slug, nome, nome_fantasia, cnpj, status, flavor_id,
  branding_json, policy_id, anonymous_os_policy_id, criado_em
```

- AUTOSEG é a primeira `provider_org`.
- Uma instalação pode começar com uma prestadora e evoluir para várias.
- O servidor deriva a prestadora da sessão/vínculo, nunca do corpo da request.
- Admin de prestadora é scoped a `provider_org_id`; admin de plataforma é outro
  papel, separado.
- Dados operacionais recebem `provider_org_id` (ou vivem em banco separado por
  prestadora; ver §6.5).
- Unicidade de e-mail, CPF, CNPJ e número de OS passa a ser por prestadora.

### 3.4 Cliente e organização cliente

- `clientes` continua sendo o perfil de cliente (PF ou PJ).
- `v9_organizacoes` é uma **organização cliente** (condomínio/empresa), não a
  prestadora. Para evitar colisão, o documento usa “organização cliente” e
  “prestadora”.
- `v9_vinculos` e `v9_responsaveis` continuam sendo papéis dentro da
  organização cliente; eles não concedem poderes de prestadora.
- O cliente pode solicitar OS, acompanhar, baixar documento e responder; não
  edita a OS técnica.

### 3.5 Papéis iniciais

| Papel | Escopo | Resumo |
|---|---|---|
| Admin da plataforma | instalação | suporte técnico, auditoria, gestão de prestadoras; não é admin de cliente |
| Admin da prestadora | `provider_org` | tudo na prestadora, inclusive OS de outros admins; gerencia papéis |
| Prestador/técnico | próprios/involved | vê/edita OS em que é responsável ou participante ativo |
| Despachante | `provider_org` | atribui/transfere OS; não edita conteúdo técnico nem financeiro |
| Financeiro | `provider_org` | recebíveis, repasses, pagamentos; não edita relatório técnico |
| Campo | próprios/involved | subconjunto mobile: OS, fotos, relatório, deslocamento |
| Leitura | `provider_org` | consulta; sem escrita |
| Cliente | próprios | solicita, acompanha, aprova, baixa documentos |
| Responsável de organização cliente | organização cliente | vê OS da organização cliente; não é admin da prestadora |
| Anônimo | política da prestadora | abre solicitação/OS conforme limites; acompanha por protocolo |

Os nomes são presets do AUTOSEG. A prestadora pode criar papéis derivados, mas
não pode conceder além do próprio escopo.

### 3.6 Contexto de login

```text
login → account → links/memberships → contexto ativo → permissões efetivas
```

- Se houver um único vínculo, entra direto.
- Se houver mais de um, mostra um seletor: “como cliente”, “como prestador”,
  “como admin da prestadora X”.
- O contexto ativo fica na sessão; trocar de contexto não cria outra conta.
- O padrão é o vínculo de maior permissão, mas a troca é explícita.
- O servidor valida o contexto em cada request; não confia no contexto enviado
  pelo navegador.

---

## 4. Permissões por objeto

### 4.1 Formato

```text
recurso.acao.escopo
```

Exemplos:

```text
work_item.view.own
work_item.view.involved
work_item.edit.involved
work_item.assign.provider_org
finance.view.own
finance.view.provider_org
client.pii.read.involved
rateio.edit.involved
settings.manage.provider_org
```

Escopos:

| Escopo | Significado |
|---|---|
| `own` | o recurso pertence ao próprio usuário/cliente |
| `involved` | o usuário participa do recurso (responsável, técnico ativo ou cliente vinculado) |
| `team` | mesma equipe/setor |
| `provider_org` | toda a prestadora |
| `all` | toda a instalação (reservado a admin de plataforma) |

### 4.2 Corpo de permissão do recurso

```yaml
resource: work_item
owner: current_responsible_provider_id
participants: active_provider_ids
client: client_id
provider_org: provider_org_id
permissions:
  view:
    - owner
    - involved
    - provider_org:admin
    - client:owner
  read:
    - owner
    - involved
    - provider_org:admin
    - client:owner
  create:
    - client
    - provider
    - provider_org:admin
    - anonymous:policy
  edit:
    - owner
    - involved
    - provider_org:admin
  assign:
    - provider_org:admin
    - dispatcher
  conclude:
    - owner
    - provider_org:admin
  cancel:
    - owner
    - provider_org:admin
  export:
    - provider_org:admin
fields:
  finance:
    read: [provider_org:admin, finance]
    edit: [provider_org:admin, finance]
  cost:
    read: [provider_org:admin, finance]
  pii:
    read: [owner, involved, client:owner, provider_org:admin]
    edit: [client:owner, provider_org:admin]
```

O corpo fica em configuração versionada por prestadora. Não fica espalhado em
`if` no código.

### 4.3 Resolução

```text
1. negar por padrão
2. validar conta ativa e contexto ativo
3. validar isolamento de prestadora
4. aplicar o papel (preset)
5. aplicar grants/denies explícitos
6. aplicar o vínculo com o objeto (own/involved/client/provider_org)
7. aplicar permissões de campo (PII, custo, margem, financeiro)
8. registrar a decisão e o motivo na auditoria
```

Regras:

- `deny` vence `grant`;
- admin de prestadora tem `*` dentro da prestadora, mas não fora dela;
- admin de prestadora continua sujeito a bloqueios legais/operacionais
  (último admin, repasse já confirmado, OS arquivada etc.);
- prestador comum recebe por padrão `own` e `involved`;
- cliente recebe `own`, `create.request` e leitura dos próprios documentos;
- permissão de campo é separada da permissão de objeto;
- toda negação e toda alteração de permissão entram na auditoria;
- o servidor é a fronteira; a UI só consulta a política para exibir/esconder.

### 4.4 Campos e PII

Campos que precisam de política própria:

- `client.documento`, `client.telefone`, `client.email`, `client.endereco`;
- `work_item.total`, `work_item.cost`, `work_item.margin`;
- `finance.*`, `rateio.*`, `repasse.*`;
- `provider.documento`, `provider.banco`, `provider.pix`;
- anexos, fotos, relatório interno, nota fiscal.

Regra inicial do AUTOSEG:

- admin da prestadora: todos os campos da prestadora;
- prestador comum: PII do cliente somente quando envolvido em OS dele; sem
  listar a base inteira, sem buscar por CPF/CNPJ, sem exportar;
- financeiro: valores e repasses da prestadora, sem editar OS técnica;
- cliente: apenas os próprios dados e os dados da OS que é dele;
- anônimo: apenas o mínimo para abrir e acompanhar a solicitação.

### 4.5 Contrato de código

O serviço deve receber um `Principal` e um `Resource` e chamar uma única
política:

```python
decision = policy.can(principal, "work_item.edit", resource)
policy.require(principal, "work_item.edit", resource)  # levanta PermissionDenied
```

A rota declara a ação; o serviço valida; o repositório filtra por prestadora.
A UI usa `policy.can(...)` apenas para exibir/esconder.

Regras de implementação:

- nenhuma regra `if admin` nova em serviço, rota ou template;
- nenhuma decisão de permissão em template;
- o repositório nunca devolve linha de outra prestadora;
- o serviço não confia em `provider_org_id`, `provider_id` ou papel vindos do
  corpo da request;
- o desktop/local também recebe ator; “modo local” não é desculpa para pular
  permissão;
- decisões negadas são auditadas;
- o código existente com `if admin` é migrado aos poucos, com teste de
  caracterização antes e depois.

### 4.6 Correções necessárias no esqueleto atual

`officina/application/object_policy.py` é um começo, mas não está pronto:

- não é importado por produção;
- a checagem de organização falha aberta quando `organization_id` é `None`;
- o admin passa antes de um `deny` explícito;
- as ações não cobrem `start`, `assume`, `archive`, `reopen`, `attach`,
  `download`, `confirm`, `send`, `merge`, `impersonate`;
- não há adaptador que construa `Principal`/`Resource` a partir das tabelas
  atuais;
- `policy.yaml` é global, não por prestadora;
- os testes são sintéticos, não caracterizam o comportamento real.

Essas correções são pré-requisito para a fase 1 (política em modo sombra).

---

## 5. OS anônima e acompanhamento

### 5.1 Política por prestadora

Cada prestadora configura:

```yaml
anonymous_os:
  habilitado: true
  alvo: prestadora | organizacao_cliente
  exige_nome: true
  exige_telefone: true
  exige_email: false
  exige_endereco: true
  permite_fotos: false
  limiar_por_hora: 10
  moderacao: manual | automatica
  retencao_dias: 90
  acompanhamento: protocolo | link | ambos
  vinculo_posterior: codigo | email | telefone | nenhum
```

### 5.2 Padrão AUTOSEG

- Permitido, conforme a política da prestadora AUTOSEG.
- A pessoa informa contato, endereço, descrição e urgência.
- Recebe um **protocolo** e um **link de acompanhamento**.
- A solicitação entra numa fila de triagem; não vira OS técnica automaticamente
  sem revisão, salvo se a política permitir.
- Fotos são opcionais e só entram quando a política permitir.
- O link de acompanhamento é um token aleatório, com expiração e sem PII no
  caminho.
- O anônimo não vê valores internos, custo, margem, rateio ou dados de outros
  clientes.

### 5.3 Vínculo posterior

1. A pessoa cria conta ou entra.
2. Informa o protocolo/código.
3. O sistema pede confirmação por e-mail ou telefone.
4. A solicitação é vinculada à conta.
5. O histórico anterior passa a aparecer no painel.

Sem confirmação, o protocolo continua funcionando como acompanhamento público,
mas não é vinculado a uma conta.

### 5.4 Controles de abuso

- rate limit por IP e por contato;
- honeypot;
- verificação de e-mail/telefone quando a política exigir;
- limite de anexos e tamanho;
- moderação/triagem;
- expiração do protocolo;
- retenção e exclusão documentadas;
- auditoria de criação, vínculo e acesso;
- bloqueio de conteúdo malicioso/arquivos;
- sem promessa de atendimento automático.

---

## 6. Modelo de dados

### 6.1 Novas tabelas

```text
accounts
  id, email, cpf, telefone, senha_hash, ativo,
  email_verificado, telefone_verificado, criado_em, atualizado_em

account_links
  id, account_id, provider_org_id, tipo, provider_id,
  client_id, client_org_id, papel, status, criado_em, atualizado_em

provider_orgs
  id, slug, nome, nome_fantasia, cnpj, status, flavor_id,
  branding_json, policy_id, anonymous_os_policy_id, criado_em

roles
  id, provider_org_id, nome, sistema, criado_em

role_permissions
  role_id, permissao

user_roles
  account_id, role_id, provider_org_id, criado_em

permission_grants
  account_id, permissao, efeito (grant|deny), provider_org_id,
  criado_por, criado_em, expira_em

resource_acl
  provider_org_id, recurso, recurso_id, account_id,
  permissao, efeito, criado_por, criado_em

anonymous_requests
  id, provider_org_id, protocolo, token_hash, nome, telefone,
  email, endereco, descricao, urgencia, status, os_id,
  criado_em, expira_em, vinculado_account_id

audit_events
  id, provider_org_id, account_id, acao, recurso, recurso_id,
  decisao, motivo, ip_hash, criado_em
```

### 6.2 Colunas nas tabelas existentes

Adicionar `provider_org_id` (ou `tenant_id`) em:

- `clientes`;
- `ordens_servico`;
- `financeiro`;
- `produtividade_rateios`;
- `produtividade_repasses`;
- `estoque_produtos` / `estoque_movimentos`;
- `catalogo_servicos`;
- `empresa_movimentos`;
- `os_eventos`, `os_anexos`, `os_notas_fiscais` (ou herdar via OS);
- `prestadores` (vínculo com a prestadora; um prestador pode ter mais de um
  vínculo no futuro).

Na primeira fase, com uma prestadora, a migração atribui o ID da AUTOSEG a
todas as linhas existentes. O campo já nasce no schema para evitar uma segunda
migração quando o Officina Web hospedar várias prestadoras.

### 6.3 Unicidade por prestadora

Trocar as restrições globais por compostas:

| Hoje | Alvo |
|---|---|
| `prestadores.email UNIQUE` | `(provider_org_id, email)` |
| `v9_usuarios.cpf UNIQUE` | `(provider_org_id, cpf)` |
| `v9_organizacoes.cnpj UNIQUE` | `(provider_org_id, cnpj)` |
| `ordens_servico.numero_os UNIQUE` | `(provider_org_id, numero_os)` |
| `clientes.documento` (checagem global) | `(provider_org_id, documento)` |

### 6.4 Migração dos dados atuais

| Hoje | Alvo | Cuidado |
|---|---|---|
| `prestadores` | `accounts` + `account_links(tipo=provider)` + perfil | não duplicar senha; migrar hash |
| `v9_usuarios` | `accounts` + `account_links(tipo=client)` + perfil PF | CPF vira atributo da conta; e-mail opcional |
| `v9_admin_prestadores` | `user_roles`/`account_links.papel=admin` | admin vira scoped à prestadora |
| `v9_responsaveis` | papel dentro da organização cliente | não confundir com admin da prestadora |
| `cliente_acessos` | vínculo legado/conta migrada | manter login legado durante transição |
| `desktop_sessoes` | sessão única/token unificado | revogar no reset de senha |
| `api_tokens` | token de API com escopo | manter `financeiro:read` |
| `v9_organizacoes` | `client_orgs`/organização cliente | não renomear sem migração testada |

A migração deve ser idempotente, com backup, validação e rollback. Nenhum
histórico financeiro/fiscal é reescrito silenciosamente.

### 6.5 Isolamento: banco compartilhado ou banco por prestadora

| Forma | Vantagens | Riscos | Quando usar |
|---|---|---|---|
| Banco compartilhado + `provider_org_id` | login único simples, relatórios cruzados, uma operação | toda query precisa filtrar; risco de vazamento; unicidade composta | primeira fase AUTOSEG e poucas prestadoras |
| Um banco por prestadora | isolamento forte, backup/exportação por prestadora | login único precisa de control plane; relatórios cruzados difíceis | muitas prestadoras ou exigência de isolamento |
| Híbrido: control plane + banco por prestadora | contas/vínculos globais + dados isolados | duas transações, sincronização, mais complexidade | Officina Web multi-prestadora |

**Recomendação para a primeira fase:** uma prestadora (AUTOSEG) e um banco, mas
com `provider_org_id` no schema e filtro obrigatório no repositório. Para o
Officina Web multi-prestadora, decidir entre banco compartilhado e híbrido com
base em isolamento, operação e custo. Não iniciar multi-prestadora antes de a
política e os testes de isolamento existirem.

---

## 7. Rotas e experiência

### 7.1 Uma origem, um shell

```text
https://autoseg.exemplo/
├── /                         início público + abrir OS
├── /acompanhar/<token>       acompanhamento anônimo
├── /entrar                   login único
├── /cadastro                 criar conta cliente
├── /conta                    conta, segurança, vínculos
├── /contexto                 trocar cliente/prestador/admin
├── /app                      shell autenticado
│   ├── /app/os
│   ├── /app/clientes
│   ├── /app/financeiro
│   ├── /app/relatorios
│   └── /app/configuracoes
└── /api/v1                   API única
```

- O mesmo shell renderiza conforme o contexto e as permissões.
- Não há mais 8765/8766 na experiência do usuário.
- O servidor pode continuar com dois processos atrás de um proxy durante a
  transição; o usuário vê uma origem.
- O cookie único é `autosseg_session` (ou `officina_session` no futuro), com
  `HttpOnly`, `SameSite=Lax/Strict`, `Secure` em HTTPS e rotação no login.
- CSRF único, validado em todo POST autenticado.
- Logout único encerra a sessão e o contexto.

### 7.2 Login e contexto

- Login aceita e-mail ou CPF (proposta).
- Conta com um vínculo entra direto.
- Conta com vários vínculos mostra o seletor.
- Conta sem vínculo de prestadora não vê menus de prestadora.
- Conta sem vínculo de cliente não vê o painel de cliente.
- Admin de plataforma vê a administração de prestadoras, não o painel de
  cliente por padrão.
- A troca de contexto é auditada.

### 7.3 Compatibilidade e redirecionamentos

Manter durante a migração:

- `/cliente/*` e `/pj/*` → novas rotas;
- `/legado` → login legado ou aviso de migração;
- `/portal-cliente` → `/entrar`;
- `/os/<numero>` → `/app/os/<numero>` quando autenticado; acompanhamento
  público quando anônimo e permitido;
- links antigos de PDF/relatório continuam válidos até a retirada.

Nenhuma URL histórica deve quebrar sem aviso e redirecionamento.

### 7.4 API

- Uma API `/api/v1` com autenticação unificada.
- Tokens de API têm escopo e prestadora.
- Tokens de desktop são revogados no logout/reset de senha.
- A API financeira mantém `financeiro:read` e rate limit.
- Rotas de escrita exigem o mesmo `ObjectPolicy` do site.
- O modo local usa o mesmo contrato de serviço, com ator.

---

## 8. Migração em fatias

### Fase 0 — documentação e caracterização (esta fase)

- este documento;
- auditoria do estado atual;
- `officina/application/object_policy.py` continua esqueleto, sem integração;
- testes de caracterização do comportamento atual;
- nenhuma mudança de comportamento no site.

### Fase 1 — política em modo sombra

- construir `Principal`/`Resource` a partir das tabelas atuais;
- calcular a decisão para as rotas existentes;
- comparar com o comportamento atual;
- registrar divergências, sem bloquear;
- corrigir a matriz antes de aplicar;
- corrigir as falhas do esqueleto (organização, deny, ações).

### Fase 2 — identidade única atrás de flag

- criar `accounts`/`account_links`/`provider_orgs`;
- migrar prestadores e clientes existentes;
- login único e seletor de contexto;
- manter os logins antigos funcionando como fallback;
- rollback: desligar a flag e voltar aos cookies antigos.

### Fase 3 — shell único e rotas

- uma origem e um shell;
- redirects dos portais antigos;
- navegação por contexto/permissão;
- mesmo cookie/CSRF;
- testes de rota e de sessão.

### Fase 4 — leitura e PII

- aplicar `view/read` por objeto;
- mascarar PII e valores financeiros por campo;
- corrigir `/os/<id>`, `/pdf-preview`, `/relatorio.yaml`, `/clientes/<id>`;
- inverter os testes que hoje codificam vazamento.

### Fase 5 — escrita

- aplicar `edit`, `assign`, `conclude`, `cancel`, `publish`, `attach`,
  `download`, `confirm`;
- migrar `os_salvar`, `produtividade_os`, `portal_negocios`, `fluxo_os`,
  `prestadores_ext`, `api_desktop` e `local_service`;
- remover os `if admin` migrados;
- manter auditoria e testes de regressão.

### Fase 6 — OS anônima e acompanhamento

- política por prestadora;
- protocolo e link;
- triagem/moderação;
- vínculo posterior à conta;
- rate limits e retenção;
- testes de abuso.

### Fase 7 — Officina Web/GTK e multi-prestadora

- extrair shell, auth, política e contratos para Officina;
- manter AUTOSEG como flavor/prestadora;
- decidir banco compartilhado vs banco por prestadora;
- só então permitir múltiplas prestadoras na mesma instalação;
- retirar os portais antigos quando houver paridade e testes.

Cada fase tem flag, rollback e critério de aceite. Nenhuma fase começa com
“reescrever tudo”.

---

## 9. Testes e critérios de aceite

### 9.1 Caracterização

Antes de mudar comportamento, congelar:

- login/logout/sessão dos dois portais;
- criação de OS, status, valores, materiais e PDF;
- financeiro, rateio e repasses;
- PDF do cliente e do prestador;
- permissões atuais (inclusive as falhas conhecidas).

### 9.2 Matriz de autorização

Cobrir, no serviço e na rota:

- admin da prestadora edita OS de outro admin;
- prestador comum edita OS própria/involved;
- prestador comum não edita OS de outro;
- prestador removido perde acesso a PDF/fotos/NF;
- cliente vê apenas a própria OS/organização;
- cliente não vê PII de outro cliente;
- admin de prestadora A não vê prestadora B;
- último admin não pode ser removido;
- usuário desativado não entra;
- token revogado não chama API;
- desktop/local respeita as mesmas regras do web;
- publicação/prévia exigem responsável ou admin;
- financeiro/rateio exigem finalizador/admin;
- catálogo/configuração exigem admin.

### 9.3 Testes que precisam ser invertidos

Alguns testes atuais **codificam o vazamento** e precisam mudar junto com a
política:

- `tests/test_portal_v4.py` afirma que qualquer prestador abre `/os/1`,
  `/os/3` e `/clientes/1`;
- `tests/test_rev12_correcoes.py` afirma que um prestador não participante
  recebe `200 application/pdf` em `/pdf-preview` de outro.

Esses testes são úteis como caracterização do estado atual, mas não podem
sobreviver à fase 4.

### 9.4 Critérios de aceite da unificação

- um link e um login;
- cliente e prestador na mesma conta quando a pessoa tiver os dois vínculos;
- contexto explícito quando houver mais de um;
- nenhuma rota autenticada sem política;
- nenhum dado de outra prestadora em resposta;
- nenhuma PII fora do vínculo;
- OS anônima com protocolo, limite e triagem;
- logs/auditoria de decisão;
- rollback por flag;
- paridade de comportamento AUTOSEG antes da retirada dos portais.

---

## 10. Decisões abertas (produto)

Estas decisões ainda precisam do dono do produto. As propostas abaixo são
defaults para destravar a documentação e os testes, não decisões finais.

| # | Decisão | Proposta inicial | Por que importa |
|---|---|---|---|
| 1 | Login por e-mail, CPF ou ambos? | aceitar e-mail ou CPF; conta guarda os dois | cliente hoje usa CPF; prestador usa e-mail |
| 2 | A mesma conta pode ser cliente e prestador? | sim, com vínculos separados e seletor de contexto | é o pedido central da unificação |
| 3 | A mesma conta pode ter vínculos em várias prestadoras? | sim no modelo; começar com uma prestadora | evita segunda migração no Officina Web |
| 4 | O AUTOSEG é a única prestadora na primeira fase? | sim; multi-prestadora só depois da política | “AUTOSEG em primeiro lugar” |
| 5 | OS anônima: alvo, provas, fotos, triagem, retenção? | permitir, com protocolo/link, contato obrigatório, fotos desativadas na primeira fase, triagem manual | risco de spam e dado falso |
| 6 | Quais papéis existem no lançamento? | admin, prestador, financeiro, leitura, cliente; despachante/campo depois | não criar complexidade sem uso |
| 7 | Prestador comum vê a base inteira de clientes? | não; só clientes envolvidos em OS dele | PII/LGPD e a própria matriz P0 |
| 8 | Cliente pode aprovar orçamento/encerrar OS? | apenas responder/aprovar; não editar OS técnica | limite de responsabilidade |
| 9 | Quem pode alterar permissões? | admin da prestadora; admin de plataforma audita | evitar autoaprovação |
| 10 | Último admin: bloqueio rígido? | sim, não pode ser removido/desativado | evitar travamento da prestadora |
| 11 | Retenção/exportação da auditoria? | definir antes da produção | LGPD e suporte |
| 12 | Branding/CNPJ/fiscal por prestadora? | sim no modelo; AUTOSEG como default | Officina Web multi-prestadora |

Enquanto não houver decisão, valem os defaults acima **apenas em documentação e
testes**, nunca em produção sem revisão.

---

## 11. Relação com os documentos existentes

- `docs/PRODUCT_VISION.md` — camadas Workaholic/Officina/AUTOSEG e princípios.
- `docs/planning/OFFICINA_WEB_AND_GTK.md` — como o site/GTK atuais originam o
  Officina Web/GTK e o que fica no AUTOSEG.
- `docs/PERMISSIONS_AND_APPROVALS.md` — catálogo e aprovação de mudanças;
  este documento corrige o estado real e a prioridade.
- `docs/PERMISSIONS_P0.md` — matriz P0 e testes AUT; continua válido como
  alvo, mas não descreve o código atual.
- `docs/APP_MODES_ROLES_AND_SERVERS.md` — modos, papéis e servidores.
- `docs/AUTH_AND_CONNECTION_UX.md` — login local/remoto e primeira conta.
- `docs/SURFACE_PARITY.md` — paridade entre GTK, site e papéis.
- `docs/planning/CONDO_SHARING_AND_TENANCY.md` — organizações e grants.
- `docs/HUMAN_CENTERED_DECISIONS.md` — decisões que precisam de contexto
  humano; as decisões abertas deste documento entram lá.
- `docs/PLATFORM_MIGRATION_LEDGER.md` — o que é genérico, legado ou flavor.

---

## 12. Glossário

| Termo | Significado |
|---|---|
| **Officina** | ecossistema/plataforma genérica; não é a prestadora nem o produto final |
| **AUTOSEG** | primeira prestadora de serviço e primeira distribuição real do ecossistema |
| **Officina Web** | produto web genérico que nascerá do site atual |
| **Officina GTK** | produto desktop genérico que nascerá do GTK atual |
| **Prestadora** | organização que executa o serviço e é dona dos dados operacionais (tenant) |
| **Organização cliente** | condomínio/empresa atendida pela prestadora; tem papéis próprios |
| **Conta** | identidade de login; não é cliente nem prestador por si só |
| **Vínculo/membership** | ligação da conta com uma prestadora e um perfil (cliente/prestador) |
| **Contexto** | vínculo ativo na sessão (cliente, prestador, admin da prestadora) |
| **Principal** | ator que executa a ação (conta + contexto + papéis) |
| **Recurso** | objeto sobre o qual se age (OS, cliente, financeiro, documento) |
| **Escopo** | alcance da permissão (`own`, `involved`, `provider_org`, `all`) |
| **OS anônima** | solicitação criada sem login, conforme política da prestadora |
| **Protocolo/token** | identificador público de acompanhamento, sem PII no caminho |

---

## 13. O que não muda nesta fase

- nenhum código de produção é alterado;
- nenhuma tabela é criada ou migrada;
- os dois portais continuam funcionando;
- a política continua esqueleto e não bloqueia nada;
- a prioridade de entrega continua sendo o AUTOSEG funcionando;
- a extração para Officina Web/GTK é planejamento, não autorização de
  reescrita.

A próxima ação segura é caracterizar o comportamento atual e corrigir o
esqueleto de política, ainda sem bloquear o site. A unificação visível só
começa depois que a identidade e a política tiverem testes.
