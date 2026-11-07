# Permissões configuráveis e aprovação de mudanças

**Status:** desenho de produto e segurança. **Não implementado.** Permissões e
autenticação são N3/N4; a implementação precisa de revisão humana externa ou
fica em DEV atrás de flag.

**Ideia central:** a Officina não deve ter só três papéis fixos. Cada
organização deve poder criar grupos, papéis e flags, com escopo de dados e
política de aprovação. O AUTOSEG é a primeira distribuição e define os padrões;
outros prestadores podem configurar os seus.

---

## 1. Modelo em uma frase

```text
Grupo        quem é a pessoa na organização
Papel        conjunto nomeado de permissões
Permissão    ação atômica + escopo de dados
Política     quando a ação é direta ou precisa de aprovação
```

Não é uma escada rígida `admin > employee > customer`. É um sistema de
permissões com escopo:

- **Admin** — escopo `tenant`/`all`, inclusive editar e apagar qualquer OS.
- **Employee** — escopo `own`/`involved`, sem finanças da empresa, sem lista
  completa de colegas, com aprovação para ações sensíveis.
- **Customer** — escopo `own`, somente as próprias solicitações e documentos.

Os nomes são padrões do AUTOSEG; a organização pode criar outros.

---

## 2. Catálogo de permissões

Formato sugerido:

```text
recurso.acao.escopo
```

Exemplos:

```text
work_item.view.own
work_item.view.involved
work_item.view.all
work_item.create
work_item.edit.own
work_item.edit.involved
work_item.edit.all
work_item.delete
work_item.approve
work_item.assign
work_item.close.own
work_item.close.all

finance.view.own
finance.view.team
finance.view.all
finance.manage
finance.approve

people.view.names
people.view.all
people.manage
roles.manage

report.publish.own
report.publish.all
stock.view
stock.manage
settings.manage
audit.view
```

`work_item` é o nome genérico do núcleo; o AUTOSEG mapeia para **OS**. Assim a
mesma engine serve encanador, eletricista, músico ou condomínio.

Regras:

- permissão atômica, sem “permissão de tela”;
- escopo explícito (`own`, `involved`, `team`, `tenant`, `all`);
- negação por padrão;
- o servidor calcula a permissão efetiva; a UI só esconde o que não pode;
- não usar nome de campo como permissão;
- não criar permissão sem um caso de uso real.

---

## 3. Grupos, papéis e flags

```text
Organização
  ├── Grupo Admin
  │     └── Papel: root do tenant
  ├── Grupo Funcionários
  │     ├── Papel: employee
  │     ├── Papel: field
  │     └── Papel: finance
  ├── Grupo Clientes
  │     └── Papel: customer
  └── Grupos customizados
        └── Papéis com flags escolhidas
```

- Um usuário pode ter mais de um papel.
- Permissões efetivas = união dos papéis, limitada ao tenant.
- Admin pode criar papéis e flags por tenant.
- Flags customizadas não podem ultrapassar o escopo do tenant.
- Alteração de papel/permissão é auditada.
- O último admin ativo não pode ser removido.
- Admin pode criar outro admin? Sim, com auditoria e confirmação; decisão
  registrada.

---

## 4. Padrões do AUTOSEG

### 4.1 Admin / root do tenant

Permissões:

```text
*  (todas as permissões do tenant)
```

Inclui:

- editar qualquer OS, inclusive de outro admin;
- apagar/arquivar OS;
- ver financeiro completo;
- ver e gerenciar pessoas, papéis e configurações;
- aprovar ou recusar mudanças;
- exportar dados.

Cuidados:

- root do tenant **não** é root da plataforma;
- toda ação sensível é auditada;
- não pode remover o último admin;
- apagar OS deve preferir arquivamento/tombstone, não exclusão física;
- admin não aprova a própria mudança quando a política exigir segundo aprovador
  (fase futura).

### 4.2 Employee

Permissões iniciais:

```text
work_item.view.own
work_item.view.involved
work_item.create            (sujeito a aprovação)
work_item.edit.own          (sujeito a aprovação)
work_item.edit.involved     (sujeito a aprovação)
work_item.close.own         (sujeito a aprovação)
report.publish.own
finance.view.own
stock.view
```

Não pode:

- ver o financeiro completo da empresa;
- ver quanto os colegas recebem;
- ver a lista completa de funcionários ou a quantidade de funcionários;
- ver OS de colegas sem participação;
- apagar OS;
- alterar papéis, configurações ou dados bancários da empresa;
- aprovar as próprias mudanças.

Pode ver:

- suas próprias OS e as OS em que participa;
- os dados do cliente necessários para executar o serviço;
- seu próprio financeiro/repasses;
- nomes de colegas atribuídos à mesma OS (necessário para o trabalho), mas não
  o diretório completo de funcionários.

### 4.3 Customer

Permissões iniciais:

```text
work_item.create.request
work_item.view.own
report.view.own
document.view.own
approval.respond.own
```

Não pode:

- ver OS de outros clientes;
- ver custos, margem, rateio ou financeiro interno;
- editar a OS do prestador;
- ver a lista de funcionários;
- aprovar mudanças internas.

Pode:

- solicitar serviço;
- acompanhar status;
- aprovar orçamento ou conclusão quando o fluxo exigir;
- baixar relatórios e documentos liberados.

---

## 5. Fluxo de aprovação tipo Git

### 5.1 Criar OS como employee

1. Employee preenche a OS.
2. Sistema salva como **rascunho/aprovação pendente**.
3. Admin recebe na fila **Aprovações**.
4. Admin vê o conteúdo, o autor e o contexto.
5. Admin aprova → a OS vira uma OS real e entra na operação.
6. Admin recusa → o rascunho fica com o motivo; o employee pode corrigir e
   reenviar.

A OS pendente:

- não entra no financeiro;
- não movimenta estoque;
- não gera PDF publicado;
- não aparece para outros employees;
- aparece para o autor e para admins.

### 5.2 Editar OS existente

1. Employee abre uma OS em que participa.
2. Edita os campos permitidos.
3. Clica em **Enviar para aprovação**.
4. O sistema grava uma **ChangeRequest** com:
   - autor;
   - OS base e versão;
   - campos alterados;
   - valores antes/depois;
   - justificativa/comentário.
5. Admin vê o diff e aprova ou recusa.
6. Aprovar aplica a mudança de forma atômica na versão correta.
7. Recusar mantém a OS original e registra o motivo.
8. Se a OS mudou desde o envio, a solicitação fica **stale** e precisa ser
   atualizada antes de aprovar.

### 5.3 Modelo de dados

```text
change_requests
  id
  tenant_id
  entity_type        work_item | customer | finance ...
  entity_id          null quando é criação
  operation          create | update | delete
  base_version       versão conhecida
  proposed_patch     JSON canônico
  status             draft | submitted | approved | rejected | stale | cancelled
  author_id
  reviewer_id
  reason
  created_at, updated_at, decided_at
  applied_version
```

Eventos:

```text
change_request.created
change_request.submitted
change_request.approved
change_request.rejected
change_request.stale
change_request.applied
```

Auditoria:

- quem pediu;
- quem aprovou/recusou;
- o diff;
- a versão aplicada;
- o motivo.

### 5.4 Regras de integridade

- Aprovação aplica o patch na versão base; se mudou, não aplica.
- Não permitir aprovar a própria mudança quando a política exigir outro
  aprovador.
- Mudanças financeiras acima de um limite podem exigir financeiro + admin
  (fase futura).
- Exclusão de OS nunca é hard delete; usar arquivamento/tombstone.
- Toda aprovação/recusa gera notificação ao autor.
- O admin pode comentar antes de decidir.

---

## 6. Política de aprovação configurável

Por tenant e por ação:

| Política | Efeito |
|---|---|
| `auto` | aplica direto |
| `require_admin` | fica pendente para admin |
| `require_role:<papel>` | fica pendente para um papel específico |
| `require_two_roles` | exige dois aprovadores (fase futura) |
| `amount_threshold` | acima de valor X exige aprovação financeira (fase futura) |

Padrões AUTOSEG sugeridos:

| Ação | Admin | Employee | Customer |
|---|---|---|---|
| Criar OS | auto | require_admin | cria solicitação |
| Editar descrição/contato | auto | require_admin | não |
| Adicionar material | auto | require_admin | não |
| Alterar valor | auto | require_admin | não |
| Relatório/fotos da própria OS | auto | auto (configurável) | não |
| Encerrar OS | auto | require_admin | não |
| Confirmar recebimento | auto | próprio, auto | não |
| Apagar/arquivar OS | auto | não | não |
| Criar usuário/papel | auto | não | não |

O dono pode mudar esses padrões por organização.

---

## 7. O que é genérico e o que é AUTOSEG

Núcleo Officina/Workaholic:

- catálogo de permissões;
- grupos, papéis e flags;
- escopos;
- change requests;
- auditoria;
- políticas de aprovação.

AUTOSEG (flavor):

- mapeia `work_item` para OS;
- define os papéis padrão Admin/Employee/Customer;
- define quais campos são financeiros;
- define PDF, fiscal, estoque e repasses;
- define os textos e telas.

Outro prestador pode usar os mesmos mecanismos com outros nomes e políticas.

---

## 8. Segurança

- Negar por padrão.
- Validar no `AppService`, não na UI.
- Filtrar por tenant em toda consulta.
- Não confiar em `tenant_id`/`role` enviado pelo cliente.
- Sessão/token revogável.
- Rate limit e auditoria de negação.
- Hash de senha forte.
- Não logar senha, token, CPF/CNPJ ou conteúdo de formulário.
- Admin não pode remover o último admin.
- Flags customizadas não podem criar acesso cross-tenant.
- Revisão humana externa antes de MAIN.

---

## 9. Fases

### Fase 0 — política pura

- catálogo de permissões;
- grupos/papéis padrão;
- funções `can_*` sem banco;
- testes unitários.

### Fase 1 — enforcement no serviço

- `AppService` recebe ator/sessão;
- filtra OS por escopo;
- bloqueia edição não autorizada;
- auditoria de negação;
- testes `AUT-001` a `AUT-015`.

### Fase 2 — change requests

- modelo e migrations;
- criar/editar OS via submissão;
- fila de aprovação;
- diff e decisão;
- stale/versionamento.

### Fase 3 — UI

- tela de aprovações;
- diff;
- comentários;
- notificações;
- estados de rascunho/pendente/recusado.

### Fase 4 — login e grupos

- conta local admin;
- usuários e grupos;
- editor de papéis/flags;
- “lembrar dispositivo”.

### Fase 5 — revisão e produção

- revisão humana externa;
- teste com cópia de dados reais;
- promoção para MAIN.

---

## 10. Decisões abertas

- Admin pode aprovar a própria mudança? (recomendação: sim para root do
  tenant, não quando a política exigir segundo aprovador)
- Employee pode ver nomes de colegas na mesma OS? (recomendação: sim, somente
  os participantes)
- Employee pode ver o cliente completo ou só o necessário?
- Qual o limite de valor que exige aprovação financeira?
- Excluir OS é arquivar ou apagar? (recomendação: arquivar)
- Papéis customizados são por tenant ou globais?
- Um usuário pode ter papéis em mais de um tenant?
- Como notificar aprovações? (portal, e-mail, app)
- Qual o prazo de retenção de change requests e auditoria?
- Quem aprova mudanças de papéis e permissões?

---

## 11. Relação com os outros documentos

- `docs/PERMISSIONS_P0.md` — matriz inicial e testes AUT.
- `docs/APP_MODES_ROLES_AND_SERVERS.md` — modos e papéis.
- `docs/AUTH_AND_CONNECTION_UX.md` — login local/remoto.
- `docs/CONDO_SHARING_AND_TENANCY.md` — tenant, usuários e grants.
- `docs/PLANO_MODO_LOCAL_SYNC.md` — sync e conflitos.
- `docs/REVIEW_WITHOUT_DEVELOPER.md` — N3/N4.
