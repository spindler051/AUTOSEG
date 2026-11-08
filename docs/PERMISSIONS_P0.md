# Permissões P0 — matriz e testes de autorização

**Status:** política proposta. O **login de prestador** já existe no DEV, mas a
aplicação de AUT-001 a AUT-021 no serviço ainda não. Auth e permissões são
N3/N4; a implementação precisa de revisão humana externa ou fica em DEV atrás
de flag. Ver `docs/SURFACE_PARITY.md`.

**Objetivo:** definir quem pode fazer o quê antes de criar tela de login,
sessão ou usuários. A regra precisa ser validada no serviço, não apenas na UI.

---

## 1. Atores

| Ator | Escopo | Observação |
|---|---|---|
| **Admin da organização** | um prestador/tenant | administra a própria organização |
| **Admin da plataforma** | instalação/servidor | suporte técnico; não é admin de cliente |
| **Prestador/técnico** | próprios serviços | vê/edita apenas OS em que participa |
| **Despachante** | organização | distribui OS; não mexe em dinheiro |
| **Financeiro** | organização | recebíveis, repasses, pagamentos |
| **Campo** | próprios serviços | subconjunto mobile: OS, fotos, relatório |
| **Leitura** | organização | consulta; sem escrita |
| **Cliente** | própria conta/OS | solicita, acompanha, aprova, baixa documentos |

Uma pessoa pode ter papéis diferentes em organizações diferentes. O papel
nunca é global por acidente.

---

## 2. Regra central de OS

```text
Admin da organização: pode editar qualquer OS da organização,
incluindo OS de outro admin.

Prestador/técnico não-admin: pode editar somente OS em que é
responsável atual ou participante ativo.

Despachante: pode atribuir/transferir, mas não editar conteúdo técnico
nem financeiro.

Financeiro: pode ver/alterar receivable/pagamento, mas não editar a OS técnica.

Campo: pode editar relatório/fotos/deslocamento das próprias OS.

Leitura: somente leitura.

Cliente: somente as próprias solicitações; não edita OS do prestador.
```

“Participante ativo” significa vínculo em `os_prestadores`/`os_responsaveis`
com o usuário. Não usar nome digitado no campo `tecnico` como autorização.

---

## 3. Matriz de ações

| Ação | Admin org | Prestador | Despachante | Financeiro | Campo | Leitura | Cliente |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ver qualquer OS da org | sim | não | sim | sim | não | sim | não |
| Ver OS própria | sim | sim | sim | sim | sim | sim | própria |
| Ver cliente vinculado à própria OS | sim | sim | sim | sim | sim | sim | próprio |
| Ver CPF/CNPJ/e-mail de cliente vinculado | sim | sim, no detalhe | não | sim | não | não | próprio |
| Ver CPF/CNPJ/e-mail de qualquer cliente | sim | não | não | não | não | não | não |
| Listar todos os clientes | sim | não | nomes, sem PII | nomes, sem PII | não | não | não |
| Buscar cliente por CPF/CNPJ/e-mail | sim | não | não | sim | não | não | não |
| Exportar base de clientes | sim | não | não | não | não | não | não |
| Criar OS | sim | sim | sim | não | sim | não | solicitar |
| Editar OS própria | sim | sim | não | não | sim | não | não |
| Editar OS de outro | sim | não | não | não | não | não | não |
| Encerrar OS própria | sim | sim | não | não | sim | não | não |
| Cancelar OS | sim | própria | não | não | não | não | não |
| Adicionar material | sim | própria | não | não | própria | não | não |
| Ver financeiro da org | sim | próprio | não | sim | não | não | próprio |
| Confirmar recebimento | sim | próprio | não | sim | não | não | não |
| Criar/desativar usuário | sim | não | não | não | não | não | não |
| Alterar permissões | sim | não | não | não | não | não | não |
| Configurar servidor/conexão | sim | não | não | não | não | não | não |
| Ver auditoria | sim | não | não | parcial | não | não | própria |
| Exportar dados | sim | não | não | parcial | não | não | próprios |

“Próprio” significa vinculado ao usuário; “parcial” precisa ser detalhado antes
de implementar.

---

## 4. Isolamento por organização

- Toda consulta de OS, cliente, financeiro e estoque filtra por
  `organizacao_id`/`tenant_id`.
- O servidor nunca confia no `tenant_id` enviado pelo cliente; deriva da sessão.
- Admin de uma organização não vê outra.
- Compartilhamento entre organizações só com grant explícito, escopo, prazo e
  auditoria (`docs/planning/CONDO_SHARING_AND_TENANCY.md`).
- Cliente pode ter vínculo com mais de uma organização; o papel é por vínculo.

---

## 5. Testes de autorização obrigatórios

| ID | Cenário | Esperado |
|---|---|---|
| AUT-001 | Admin A edita OS do admin B | permitido |
| AUT-002 | Prestador A edita OS do prestador B | negado |
| AUT-003 | Prestador A edita OS em que é participante | permitido |
| AUT-004 | Despachante atribui OS | permitido |
| AUT-005 | Despachante edita valor da OS | negado |
| AUT-006 | Financeiro confirma recebimento | permitido |
| AUT-007 | Financeiro edita relatório técnico | negado |
| AUT-008 | Campo edita fotos da própria OS | permitido |
| AUT-009 | Campo edita OS de outro | negado |
| AUT-010 | Leitura tenta salvar OS | negado |
| AUT-011 | Cliente vê OS de outro cliente | negado |
| AUT-012 | Admin de tenant A vê OS do tenant B | negado |
| AUT-013 | Último admin tenta se desativar | negado |
| AUT-014 | Usuário desativado tenta login | negado |
| AUT-015 | Token revogado tenta API | negado |
| AUT-016 | Employee vê CPF/CNPJ/e-mail de cliente envolvido | permitido |
| AUT-017 | Employee vê PII de cliente sem vínculo | negado |
| AUT-018 | Employee busca cliente por CPF/CNPJ/e-mail | negado |
| AUT-019 | Employee exporta base de clientes | negado |
| AUT-020 | API de cliente omite PII para employee não envolvido | negado |
| AUT-021 | Customer vê PII de outro cliente | negado |

Esses testes devem rodar no serviço, não só na interface. Uma rota HTTP ou
chamada direta ao `AppService` precisa falhar mesmo se a UI esconder o botão.

---

## 6. Onde a regra deve viver

```text
UI (GTK/web/Qt/nativo)
    → esconde ações sem permissão
AppService
    → valida permissão em toda operação
Repositório
    → filtra por tenant/organização
Banco
    → constraints e auditoria
```

A UI não é fronteira de segurança. O serviço é.

---

## 7. Fases de implementação

### Fase 1 — política pura

- catálogo declarativo em `policy.yaml`;
- `application/policy.py` com `PolicyStore.reload()` atômico;
- funções sem banco: `can_edit_os`, `can_view_finance`, `can_manage_users`;
- testes unitários com atores/OS fictícios;
- teste de mudança de política em runtime;
- nenhuma tela ainda.

### Fase 2 — serviço

- `AppService` recebe o ator/sessão;
- valida permissão antes de salvar;
- testes de autorização no serviço;
- auditoria de negação.

### Fase 3 — login local

- primeira conta admin;
- usuários locais;
- sessão;
- “lembrar dispositivo” com token, não senha.

### Fase 4 — UI

- esconder/desabilitar ações;
- mensagens claras;
- testes de fluxo.

### Fase 5 — revisão

- revisão humana externa;
- teste com dados reais em cópia;
- só então MAIN.

---

## 8. Decisões abertas

- Admin de organização pode criar outro admin? Com aprovação de quem?
- Prestador pode ver OS de outro prestador na mesma equipe? Só leitura?
- Financeiro pode ver relatório técnico? Com quais campos?
- Despachante pode cancelar OS? Ou só admin?
- Cliente pode aprovar orçamento e encerrar? Ou só aceitar?
- O que acontece quando o responsável é desativado?
- Como revogar sessão/token de um dispositivo perdido?
- Qual o prazo de retenção de auditoria?

---

## 9. Relação com os outros documentos

- `docs/APP_MODES_ROLES_AND_SERVERS.md` — modos, papéis e fases.
- `docs/PERMISSIONS_AND_APPROVALS.md` — RBAC configurável e change requests.
- `docs/AUTH_AND_CONNECTION_UX.md` — login local/remoto.
- `docs/REVIEW_WITHOUT_DEVELOPER.md` — N3/N4.
- `docs/planning/CONDO_SHARING_AND_TENANCY.md` — organizações e grants.
- `docs/GTK_SERVER_DECOUPLING.md` — `AppService` e modos.
- `docs/planning/PLANO_MODO_LOCAL_SYNC.md` — sync e conflitos.
