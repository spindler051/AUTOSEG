# Peça 6.2 — Papéis do cliente e permissões por objeto

**Uso:** colar no ChatGPT. Trabalha sobre uma cópia do repositório, **não faz
commit**, devolve ZIP.

**Base:** `e9973b8` (main com a peça 6.1 integrada).
**Dependências:** 6.1 (shell, login de cliente e home do cliente).
**Entrega:** ZIP com arquivos completos, patch, testes e notas.

## 1. Missão

Dar ao cliente papéis reais e fazer a permissão por objeto valer no serviço,
não só na tela. Nesta peça entram:

- papéis de cliente **customer**, **porteiro**, **zelador** e **síndico**;
- escopo por organização cliente para síndico/zelador;
- matriz inicial de permissões, configurável em `policy.yaml`;
- atribuição de papel pelo admin da prestadora;
- enforcement nas rotas de OS/documentos do cliente;
- enforcement nas rotas principais de OS do prestador, corrigindo o acesso
  amplo atual (“qualquer prestador abre qualquer OS”).

A matriz é **provisória**: o produto ainda vai testar os papéis. Ela deve ficar
em dados/configuração, com testes claros, para ser ajustada sem reescrever o
portal.

## 2. Modelo de papel

### 2.1 Um papel de cliente por conta, nesta fase

- O papel fica em `account_links.client_role` (`customer`, `porteiro`,
  `zelador`, `síndico` em minúsculas: `customer`, `porteiro`, `zelador`,
  `sindico`).
- `account_links.role` continua `customer` para clientes, preservando o
  contrato atual; o papel específico é `client_role`.
- Para prestadores, `client_role` é ignorado.
- O vínculo organizacional continua vindo das tabelas existentes:
  - síndico: `v9_responsaveis` (`papel` “Síndico”/“Gestor”) para as
    organizações;
  - zelador: `v9_vinculos` aprovado com `papel='Zelador'`;
  - porteiro: sem escopo organizacional amplo; vê apenas os próprios pedidos;
  - customer: vê apenas as próprias OS/solicitações.
- Não crie uma tabela nova de papéis nesta peça. Use
  `account_links.client_role` + as tabelas existentes.

### 2.2 Matriz inicial (provisória)

| Ação | customer | porteiro | zelador | síndico |
|---|---|---|---|---|
| ver própria OS/solicitação | sim | sim | sim | sim |
| ver OS da organização | não | não | sim | sim |
| criar solicitação | sim | sim | sim | sim |
| baixar documento da própria OS | sim | sim | sim | sim |
| baixar documento da organização | não | não | sim | sim |
| ver contato do solicitante | próprio | próprio | organização | organização |
| editar/concluir/cancelar OS | não | não | não | não |
| ver financeiro/repasses | não | não | não | não |
| gerenciar usuários/papéis | não | não | não | não |

- Síndico e zelador têm leitura organizacional; **não** editam OS nesta fase.
- Financeiro do cliente fica fora; não crie tela nem permissão de financeiro.
- A matriz deve existir em `officina/application/policy.py` (`PADRAO`) e poder
  ser sobrescrita por `policy.yaml`.
- Não esconda permissão apenas no HTML; o serviço precisa negar.

## 3. Interfaces e mudanças de dados

### 3.1 `accounts.py`

Adicionar, de forma idempotente:

```python
CLIENT_ROLES = ("customer", "porteiro", "zelador", "sindico")

def set_client_role(banco, account_id: int, role: str) -> AccountLink
def list_client_accounts(banco) -> tuple[AccountLinkView, ...]
```

- `install` adiciona `client_role TEXT NOT NULL DEFAULT 'customer'` com
  `CHECK (client_role IN ('customer','porteiro','zelador','sindico'))` se a
  coluna não existir. Não recrie a tabela.
- `AccountLink` ganha `client_role: str = "customer"` no fim.
- `set_client_role` valida o papel, exige link de cliente ativo, atualiza e
  devolve o link; não altera `prestadores`/`v9_usuarios`.
- `list_client_accounts` devolve dados mínimos para a tela de admin
  (account_id, display_name, client_role, active, client_user_id), sem senha
  nem hash.
- `membership_for_account` para cliente usa `link.client_role` como papel.
- `identity_for_account`/`identity.load_identity` continuam iguais.

### 3.2 `identity.py`

- `Membership` ganha `client_org_ids: frozenset[int] = frozenset()`.
- `Principal` ganha `client_org_ids: frozenset[int] = frozenset()`.
- `to_principal` aceita para cliente:
  `customer`, `porteiro`, `zelador`, `sindico`; para prestador continua
  `admin`/`employee`.
- Para cliente, valida `provider_id is None` e `client_id` igual ao da
  identidade; `client_org_ids` só é permitido para cliente.
- `accounts.membership_for_account` calcula `client_org_ids`:
  - `sindico`: organizações em `v9_responsaveis` do usuário, não mescladas;
  - `zelador`: organizações com `v9_vinculos` aprovado e papel “Zelador”;
  - `porteiro`/`customer`: vazio.
- Não coloque PII em `Membership`/`Principal`.

### 3.3 `policy.py`

Adicionar `organization` aos escopos/relacionamentos e as roles:

```python
PADRAO["roles"]["customer"] = ...
PADRAO["roles"]["porteiro"] = ...
PADRAO["roles"]["zelador"] = ...
PADRAO["roles"]["sindico"] = ...
```

Permissões mínimas:

- `customer`: as atuais de cliente (`work_item.create.request`,
  `work_item.view.own`, `report.view.own`, `document.view.own`,
  `customer.view.own`, campos próprios).
- `porteiro`: `work_item.create.request`, `work_item.view.own`,
  `document.view.own`, `customer.view.own`.
- `zelador`: `work_item.create.request`, `work_item.view.organization`,
  `document.view.organization`, `report.view.organization`,
  `customer.contact.view.organization`.
- `sindico`: `work_item.create.request`, `work_item.view.organization`,
  `document.view.organization`, `report.view.organization`,
  `customer.view.organization`, `customer.contact.view.organization`.
- Nenhuma role de cliente recebe `finance.*`, `work_item.edit.*`,
  `work_item.delete.*`, `work_item.assign.*`, `work_item.conclude.*` ou
  `stock.*`.

### 3.4 `object_policy.py`

- `Principal`/`Resource` ganham `client_org_ids`/`client_org_id`.
- `relationship`:
  - prestador admin → `all`;
  - prestador dono/participante → `own`/`involved`;
  - cliente cujo `client_org_id` está em `principal.client_org_ids` e cujo
    papel é `sindico`/`zelador` → `organization`;
  - cliente dono (`resource.client_id == principal.client_id`) → `own`;
  - caso contrário, `other`.
- `can` deve considerar `work_item.view.organization`,
  `document.view.organization`, etc.
- Um recurso de outra organização/prestadora continua negado.
- Teste que `customer` não ganha `organization` só por ter `client_id`.

### 3.5 Serviço de OS/documentos

Criar/expandir `officina/application/work_item_access.py` (ou equivalente)
com:

```python
def resource_for_work_item(banco, work_id: int) -> Resource
def require_work_item(banco, principal, work_id: int, action: str) -> Decision
def require_document(banco, principal, work_id: int, document_id: int,
                     action: str = "download") -> Decision
```

- O serviço lê o vínculo real da OS (cliente, organização, responsável,
  participantes) e chama `ObjectPolicy.require`.
- Não confie em IDs vindos do formulário.
- Use esse serviço em `client_service` (6.1) e nas rotas principais de OS do
  prestador:
  - GET detalhe/PDF/YAML de OS;
  - POST salvar/atribuir/concluir/cancelar quando a rota já existe.
- Se a integração com o portal do prestador exigir reescrever o fluxo inteiro,
  **pare** e registre o bloqueio em `NOTES.md`; não faça um bypass, não
  duplique a regra e não declare a peça concluída.

### 3.6 Administração de papel

Adicionar no portal do prestador, somente para admin:

- `GET /contas` — lista simples de contas de cliente com papel atual.
- `POST /contas/<account_id>/papel` — valida CSRF, chama
  `accounts.set_client_role`, registra auditoria (`neg.audit` ou equivalente)
  e redireciona para `/contas`.
- Rejeitar conta de prestador, papel inválido, conta inativa e acesso de
  employee.
- Não criar editor de permissões granular nesta peça; é só o papel do cliente.
- A tela pode ser uma tabela simples com o layout existente; sem novo CSS.

## 4. O que não fazer

- Não implementar OS anônima, rate limit por IP/fingerprint ou captcha.
- Não criar financeiro do cliente.
- Não mexer no GTK nem na sessão durável.
- Não criar tabela nova de papéis/organizações; use as existentes.
- Não permitir que síndico/zelador editem, concluam, cancelem ou vejam
  financeiro.
- Não colocar SQL/regra de permissão no handler.
- Não usar `if admin` novo fora da política; o admin passa pelo
  `ObjectPolicy`.
- Não logar PII, senha, hash, token ou conteúdo de documento.
- Não alterar dinheiro, status de OS, PDFs ou e-mails.
- Não “consertar” teste enfraquecendo a asserção; se a regra não fecha, pare.

## 5. Testes obrigatórios

Criar/expandir `tests/test_client_roles.py`, `tests/test_object_permissions.py`
e `tests/test_client_web.py`. Cobrir, no mínimo:

1. `accounts.set_client_role` aceita os quatro papéis e rejeita inválido,
   conta de prestador e conta inativa.
2. `membership_for_account` devolve o papel e `client_org_ids` corretos para
   síndico, zelador, porteiro e customer.
3. síndico vê OS/documentos de todas as organizações sob sua responsabilidade;
4. zelador vê OS/documentos das organizações em que é zelador aprovado;
5. porteiro vê somente os próprios pedidos;
6. customer vê somente as próprias OS;
7. nenhum papel de cliente vê OS/documentos de outra organização/cliente;
8. nenhum papel de cliente vê financeiro, clientes, estoque, prestadores ou
   administração;
9. prestador employee vê/edita apenas OS própria ou em que participa;
10. prestador employee não vê/edita OS de outro employee;
11. admin da prestadora vê/edita conforme a política;
12. cliente não acessa rota de prestador e prestador não acessa rota de
    cliente;
13. `POST /contas/<id>/papel` exige admin + CSRF e registra auditoria;
14. `policy.yaml` com matriz alterada muda a decisão sem alterar código;
15. acesso negado não vaza nome, CPF, descrição, documento ou existência do
    recurso;
16. as suítes de 6.1 e do portal continuam passando.

Rodar:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_client_roles tests.test_object_permissions \
  tests.test_client_web tests.test_officina_web tests.test_login_web \
  tests.test_web_session tests.test_web_cookie tests.test_auth \
  tests.test_accounts tests.test_identity tests.test_object_policy -v
```

Regressão:

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_rev12_correcoes tests.test_admin_parity tests.test_portal_v4 -v
```

Se não houver `.venv`, registrar o erro exato; não declarar aprovação.

## 6. ZIP

```text
officina-client-roles/
├── changed-files/
│   ├── officina/application/policy.py
│   ├── officina/application/object_policy.py
│   ├── officina/application/work_item_access.py
│   ├── flavors/autoseg/modules/accounts.py
│   ├── flavors/autoseg/modules/identity.py
│   ├── flavors/autoseg/modules/client_service.py
│   ├── flavors/autoseg/modules/client_web.py
│   ├── flavors/autoseg/modules/portal_prestador.py
│   └── tests/...
├── officina-client-roles.patch
├── CHANGED_FILES.txt
├── TEST_RESULTS.txt
└── NOTES.md
```

Sem `.git`, banco, anexos, PDFs, logs, tokens ou PII.

## 7. Critérios de aceite

- Quatro papéis de cliente com matriz inicial configurável.
- Escopo organizacional de síndico/zelador usando as tabelas existentes.
- Serviço nega acesso cruzado; UI não é a autoridade.
- Admin consegue atribuir papel de cliente com CSRF e auditoria.
- Rotas principais de OS do prestador deixam de aceitar “qualquer prestador”.
- Nenhuma permissão de financeiro/edição para cliente nesta fase.
- Testes negativos provam cada negativa.
- Se a integração do portal do prestador não fechar sem reescrita, o bloqueio
  está documentado e a peça **não** foi declarada concluída.
- Diff limitado aos arquivos permitidos.
