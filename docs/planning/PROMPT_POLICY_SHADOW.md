# Prompt — Principal/ObjectPolicy em modo sombra (AUTOSEG)

**Uso:** colar este arquivo em outra IA implementadora. Não é uma spec de
produto; é um contrato de tarefa para uma primeira fatia reversível.

**Repositório:** `spindler051/AUTOSEG`
**Base:** `main` no commit `4eb4145` ou posterior.
**Branch de trabalho:** criar `feat/policy-shadow`. **Não fazer push na
`main`.** Entregar um PR ou um patch/diff para revisão.

---

## 1. Papel

Você é um engenheiro sênior Python/SQLite. Leia `AGENTS.md` antes de tocar no
código. Código, comentários, testes e documentação novos em inglês. Strings de
UI continuam em pt-BR.

## 2. Missão

Implementar a primeira fatia de autorização por objeto para **OS/work items**
em **modo sombra**:

```text
Principal + Resource -> ObjectPolicy.can() -> decisão da política
                                            -> comparação com o comportamento atual
                                            -> registro JSONL de divergência
                                            -> nunca bloqueia, nunca muda comportamento
```

O objetivo é medir a distância entre a autorização atual e a política-alvo.
**Não implementar bloqueio nesta tarefa.** A aplicação da política é uma fase
posterior, com revisão humana.

## 3. Leia antes de codar

1. `AGENTS.md` — change gates e regras duras.
2. `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` §2, §4 e §9.
3. `officina/application/object_policy.py`
4. `officina/application/policy.py`
5. `officina/application/contracts.py`
6. `officina/core/portal_negocios.py` (`os_salvar`)
7. `officina/core/produtividade_os.py` (`_os_ativa_responsavel`, `participou`,
   `financeiro_pessoal`)
8. `officina/core/prestadores_ext.py` (`responsavel_atual`, tabelas
   `os_prestadores`, `os_responsaveis`, `os_encerramentos`)
9. `flavors/autoseg/modules/portal_prestador.py` (`os_form`, `documentos`,
   `anexo`, rota de contato do cliente)
10. `flavors/autoseg/modules/api_desktop.py` (`_rota_os`, `_rota_os_id`)
11. `tests/test_object_policy.py`, `tests/test_produtividade_rev07.py`,
    `tests/test_rev12_correcoes.py`

## 4. Restrições não negociáveis

- **Não bloquear nada.** Nenhum `require()` em caminho de produção. Nenhuma
  rota muda de comportamento.
- **Não criar tabela, coluna, migração ou `provider_org_id`.**
- **Não inventar tenant/organização.** `organization_id` fica `None` nesta
  fase; marcar `tenant_unknown`.
- **Não refatorar** `portal_prestador.py`, GTK, HTML, CSS ou o contrato
  web/GTK.
- **Não adicionar `if admin`** fora da política/adaptador.
- **Não colocar SQL ou regra de negócio em rota/template.**
- **Não adicionar dependências.**
- **Não usar dados reais/PII** em testes ou logs.
- **Não alterar `AGENTS.md`.**
- Manter o diff pequeno. Se precisar de algo maior, parar e explicar.

## 5. Implementação

### 5.1 Corrigir o esqueleto da política

Editar apenas `officina/application/object_policy.py`:

- adicionar ao `ACTIONS`: `start`, `assume`, `archive`, `reopen`, `attach`,
  `download`, `publish`, `confirm`, `send`, `merge`, `impersonate`;
- adicionar `tenant_unknown: bool = False` ao `Decision`;
- fazer `deny` explícito vencer o bypass de admin;
- semântica de tenant:
  - se `principal.organization_id` e `resource.organization_id` estiverem
    ambos preenchidos e diferentes: negar com
    `"Recurso de outra organização."`;
  - se qualquer um for `None`: `tenant_unknown=True`; **não negar só por
    isso**; continuar avaliando papel/relação;
  - se ambos forem `None`, a decisão é medida, mas sempre marcada;
- manter `relationship()` para `own`/`involved`/`all`, sem fingir isolamento
  quando o tenant é desconhecido;
- atualizar `tests/test_object_policy.py` para a nova lista de ações, precedência
  de `deny` e `tenant_unknown`. Não enfraquecer testes existentes.

### 5.2 Criar o adaptador AUTOSEG (flavor, não core)

Criar `flavors/autoseg/modules/policy_shadow.py`. Ele lê tabelas do AUTOSEG, então
pertence ao flavor; `ObjectPolicy` continua genérico.

Funções públicas:

```python
def principal_provider(banco, provider_id: int) -> Principal
def principal_client(banco, user_id: int) -> Principal
def resource_work_item(banco, os_id: int) -> Resource
```

Mapeamento:

- **Provider:**
  - `account_id = provider_id`, `provider_id = provider_id`;
  - `active = prestadores.ativo == 1`;
  - `role = "admin"` se `v9_admin_prestadores` contém o id, senão
    `"employee"`;
  - `organization_id = None`.
  - Se `v9_admin_prestadores` não existir, tratar como não-admin; não quebrar.
- **Client:**
  - `account_id = user_id`, `role = "customer"`;
  - `client_id = v9_usuarios.cliente_pf_id` quando existir;
  - `active = v9_usuarios.ativo == 1`;
  - `organization_id = None`.
- **Work item:**
  - `kind = "work_item"`, `id = os_id`, `organization_id = None`;
  - `owner_id` = responsável atual em `os_responsaveis`;
  - `client_id` = `ordens_servico.cliente_id`;
  - `participant_ids` = `os_prestadores` com `ativo=1`;
  - `attributes` com `status`, `arquivada`, `finalizer_id` de
    `os_encerramentos` quando a tabela existir, e
    `legacy_participant_ids` (todas as linhas, inclusive inativas) para
    medir a diferença.
- Tabelas/colunas opcionais ausentes devem degradar sem exceção; o adaptador de
  sombra nunca pode derrubar uma requisição.

### 5.3 Criar o coletor de sombra

No mesmo `policy_shadow.py`:

```python
def evaluate(principal, action, resource, actual_allowed, source, extra=None):
    ...
```

Comportamento:

- chamar `ObjectPolicy.can(...)`;
- comparar `decision.allowed` com `actual_allowed`;
- gravar somente se `AUTOSEG_POLICY_SHADOW` estiver em
  `1/true/on/yes`;
- anexar uma linha JSON em
  `<AUTOSEG_BASE ou runtime_config.base_dir()>/logs/policy_shadow.jsonl`;
- criar `logs/` com `0700` e o arquivo com `0600`;
- usar `threading.Lock`; engolir `OSError` e nunca quebrar a requisição;
- **sem PII/segredos**: apenas IDs, papel, ação, tipo/id do recurso, decisão,
  motivo, relação, `actual_allowed`, `divergence`, `tenant_unknown`, `source`,
  `extra` allowlisted e timestamp;
- nunca logar nome, CPF/CNPJ, telefone, e-mail, endereço, conteúdo de anexo,
  token, cookie ou corpo de requisição.

Exemplo de linha:

```json
{"ts":"2026-11-10T18:00:00","source":"os_form","action":"view","resource":"work_item:40","principal":"provider:4","role":"employee","relationship":"other","policy":false,"actual":true,"divergence":true,"reason":"Sem vínculo com o recurso.","tenant_unknown":true}
```

### 5.4 Instrumentar os caminhos de OS (somente observar)

Adicionar `evaluate(...)` sem mudar condições, retornos ou escritas. Usar a
condição existente como `actual_allowed`.

- `portal_prestador.os_form`: `view`/`read` para OS existente;
  `actual_allowed=True` (hoje qualquer prestador autenticado abre).
- `portal_prestador.documentos`: `download` para PDF/preview, `read` para os
  demais; `actual_allowed=True`.
- `portal_prestador.anexo`: `download` em GET, `attach` em POST/upload;
  `actual_allowed=True`.
- Rota de contato do cliente: `view` na relação cliente/OS;
  `actual_allowed=True`.
- `neg.os_salvar`: `edit` com a condição existente
  (`responsavel_atual == pid or admin`); `conclude`/`cancel` quando
  `acao_status` for final, mesma condição; `assign` com `admin`.
- `api_desktop._rota_os` e `_rota_os_id`: `view` em GET, `edit` em save,
  `assign` em assign, `start` em start, `publish` em publish;
  `actual_allowed=True` (hoje não há check).
- Não instrumentar `_os_ativa_responsavel` se isso mudar o comportamento de
  exceção; instrumentar os chamadores.

Manter todos os checks atuais exatamente como estão. O adaptador de sombra é
uma segunda opinião, não um substituto.

## 6. Testes

Criar `tests/test_policy_shadow.py` e atualizar `tests/test_object_policy.py` se
necessário.

Cobrir:

1. Admin edita OS de outro provider: política permite; atual permite; sem
   divergência.
2. Responsável edita a própria OS: ambos permitem.
3. Participante ativo edita: política pode permitir `involved`; atual pode
   negar; divergência registrada.
4. Prestador sem vínculo abre `/os/<id>`: política nega; atual permite;
   divergência registrada (vazamento conhecido).
5. Prestador sem vínculo baixa `/pdf-preview`: mesma divergência.
6. Cliente dono vê a própria OS: política permite; outro cliente: política nega.
7. Prestador inativo: política nega.
8. `AUTOSEG_POLICY_SHADOW` desligado: nenhum arquivo de log é criado.
9. `AUTOSEG_POLICY_SHADOW` ligado: JSONL tem uma linha por decisão e não contém
   PII.
10. Caracterização: `os_form` continua 200 e `os_salvar` grava os mesmos
    valores; nada é bloqueado.

Rodar exatamente:

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_object_policy tests.test_policy_shadow -v
PYTHONPATH=. .venv/bin/python -m unittest tests.test_rev12_correcoes tests.test_produtividade_rev07 -v
python3 scripts/audit_comments.py --strict
```

Não rodar rede, e-mail, túneis ou dados de produção.

## 7. Documentação e evidências

- Atualizar `docs/PLATFORM_MIGRATION_LEDGER.md`: Identity/access de
  `not started` para algo como `adapter shadow`, somente se os testes passarem.
- Adicionar um bullet curto no `CHANGELOG.md`: política em modo sombra para work
  items, sem mudança de comportamento.
- **Não alterar `AGENTS.md`.**
- Na resposta, incluir:
  - arquivos alterados;
  - comandos de teste e resultados exatos;
  - 3–5 linhas JSONL sanitizadas;
  - tabela de divergências esperadas (view/download sem vínculo, edição de
    participante etc.);
  - a frase explícita: “Shadow only; no enforcement.”

## 8. Critérios de aceite

- Nenhuma mudança de comportamento; suítes existentes passam.
- Nenhum enforcement, nenhum `require()` em produção.
- Nenhuma mudança de schema/migração/dependência.
- Nenhuma PII/segredo nos logs.
- Vazamentos conhecidos aparecem como `divergence=true`.
- A política é genérica; o mapeamento de tabelas AUTOSEG fica no flavor.
- Nenhum `if admin` novo fora do adaptador; nenhum SQL novo em rota/template.
- Diff limitado aos arquivos listados.
- Se algo estiver ambíguo, parar e perguntar; não inventar tenant, papéis ou
  regras.

## 9. O que o revisor vai checar

1. Algo foi bloqueado ou mudou? (deve ser não)
2. `actual_allowed` reflete a condição existente, não uma invenção?
3. `owner_id`, `participant_ids` e `client_id` estão mapeados corretamente?
4. `deny` vence admin? `tenant_unknown` aparece?
5. Os vazamentos conhecidos estão registrados como divergência?
6. Há PII ou segredo nos logs?
7. Há acoplamento novo, SQL em rota ou `if admin`?
8. O diff é pequeno o suficiente para revisar de uma vez?

## 10. Condições de parada

Pare e peça decisão humana se:

- precisar mudar schema ou criar tenant;
- precisar bloquear uma rota para os testes passarem;
- descobrir que o comportamento atual não pode ser caracterizado sem refatorar
  o portal;
- precisar alterar um teste existente para aceitar um vazamento;
- o diff passar de ~15 arquivos ou ~800 linhas;
- houver dúvida sobre quem é o “dono” financeiro da OS.

Não “resolva” esses casos por conta própria.
