# Redesenho da numeração de OS e migração

**Status:** RFC de arquitetura e migração. **Nada implementado, nada migrado.**
Esta mudança é N3/N4: mexe em identidade pública, schema, links, PDFs, e-mails e
dados históricos. Exige backup, ensaio em cópia, validação e revisão humana
externa antes da MAIN.

**Regra desta mudança:** nada de atalho, regex salvando o dia, `MAX+1`,
número duplicado em tela ou reescrever documento histórico. O desenho vem
primeiro; a migração vem depois, com rollback.

---

## 1. O que existe hoje

Análise da `~/gestaoservicos_MAIN/dados.db` em 2026-11-07:

| Item | Situação |
|---|---|
| OS existentes | **23** |
| IDs internos | 10–37, com lacunas 13, 14, 26, 33, 35 |
| Formato do número | **todas** `OS-00xx` |
| `numero_os` | `TEXT UNIQUE` |
| `criado_em` | ISO consistente em todas |
| `data_abertura` | mistura `YYYY-MM-DD HH:MM:SS` e `DD/MM/YYYY HH:MM` |
| Maior volume diário | 12 OS em 2026-11-03 |
| Tabelas filhas | usam `os_id`, não o número; isso ajuda a migração |
| Documentos/PDFs | `os_documentos` referencia `os_id`; nomes de arquivo incluem número e id |
| E-mails | assunto/corpo usam `numero_os`; alguns fallbacks usam `#id` |
| Links do site | rotas usam `/os/{id}`, enquanto a tela mostra `numero_os` |
| Bugs visíveis | link e número diferentes; linha PJ mostra `OS {os_id}`; PDF `OS_<numero>_<id>.pdf` |

O número não é a identidade interna. O `id` é. Isso é bom: a migração não
precisa reescrever chaves estrangeiras nem anexos. O que precisa mudar é a
**identidade pública** e todos os lugares que a exibem.

---

## 2. Formato desejado

Padrão inicial do AUTOSEG:

```text
YYMMDD + sequência diária de 3 dígitos
2026-11-07 → 261107001, 261107002, ...
```

- `261107000` é o “dia”, não uma OS.
- Primeira OS do dia = `001`.
- Limite diário = **999**; aceitamos essa limitação.
- Data de referência = data de criação da OS.
- Não reutilizar número; se o dia acabar, falhar de forma clara.
- Número é único por organização/tenant.

Exemplo de migração dos dados atuais:

| id | antigo | novo | dia |
|---:|---|---|---|
| 10 | OS-0010 | 261030001 | 2026-10-30 |
| 11 | OS-0011 | 261030002 | 2026-10-30 |
| 12 | OS-0012 | 261030003 | 2026-10-30 |
| 15 | OS-0013 | 261102001 | 2026-11-02 |
| 16 | OS-0014 | 261103001 | 2026-11-03 |
| … | … | … | … |
| 28 | OS-0026 | 261103012 | 2026-11-03 |
| 29 | OS-0027 | 261104001 | 2026-11-04 |
| 34 | OS-0032 | 261105001 | 2026-11-05 |
| 36 | OS-0033 | 261106001 | 2026-11-06 |
| 37 | OS-0034 | 261106002 | 2026-11-06 |

A ordem usa `criado_em` e, em empate, `id`. `data_abertura` não é confiável
porque tem formatos misturados e pode ter sido editada.

---

## 3. Numeração configurável da Officina

A numeração não pode ser `YYMMDD` hardcoded. O núcleo deve ter uma política
declarativa, por instalação e, no futuro, por tenant.

```yaml
versao: 1
modo: date_sequence        # date_sequence | sequential | uuid | custom
fuso: America/Sao_Paulo
prefixo: ""
sufixo: ""
separador: ""
data:
  formato: "%y%m%d"
sequencia:
  estilo: numeric          # numeric | letters
  largura: 3
  maximo_por_dia: 999
custom:
  template: "{data}{sequencia}"
```

Modos:

| Modo | Exemplo | Uso |
|---|---|---|
| `date_sequence` | `261107001` | padrão AUTOSEG |
| `sequential` | `OS-0001` | instalações simples |
| `letters` | `261107AAA` | quando o cliente quer letras |
| `uuid`/`ulid` | `01J...` | integrações e idempotência |
| `custom` | `AUT-2026-0001` | marca/tenant |

Regras:

- a política é dado, não código;
- mudar a política afeta **novas** OS, não renumera as antigas;
- a política é versionada e auditada;
- o admin vê uma prévia antes de salvar;
- não pode haver dois números iguais no mesmo tenant;
- o servidor valida no backend, não na UI;
- o formato público precisa ser URL-safe.

---

## 4. Identidade: três conceitos separados

```text
id interno       INTEGER/UUID imutável, usado por FKs e auditoria
número público   texto único, exibido ao usuário, configurável
alias            número antigo/legado que resolve para o id
```

Não usar `id` como número público. Não usar `numero_os` como chave estrangeira.
Não exibir dois números diferentes para a mesma OS.

### 4.1 Tabelas novas

```text
numbering_policies
  id, tenant_id, version, mode, config_json, active, created_at, created_by

numbering_sequences
  tenant_id, scope, period, next_value, updated_at
  PRIMARY KEY (tenant_id, scope, period)

numbering_aliases
  alias, tenant_id, os_id, source, created_at
  PRIMARY KEY (tenant_id, alias)

ordens_servico
  numero_os              número público atual
  numero_os_legado       número antigo (auditoria)
  numero_os_emitido_em   data/hora da emissão
  numero_policy_id       versão da política usada
```

`numbering_sequences` evita `MAX+1` e permite concorrência correta.
`numbering_aliases` permite que links, e-mails e PDFs antigos continuem
resolvendo.

---

## 5. Geração concorrente

Fluxo de criação:

1. abrir transação;
2. ler a política ativa;
3. calcular o período (`YYMMDD` ou outro);
4. atualizar `numbering_sequences` com lock de escrita;
5. se `next_value > max`, falhar com erro claro;
6. formatar o número;
7. inserir a OS;
8. atualizar a sequência;
9. commit.

Nada de `SELECT MAX(numero_os)+1`. Nada de gerar número fora da transação.
Duas requisições simultâneas não podem receber o mesmo número.

---

## 6. Links, site, PDF e e-mail

O problema atual não é só o formato; é a exposição inconsistente.

### 6.1 Uma única função

```text
format_os_number(policy, date, sequence) -> str
resolve_os_token(token, tenant_id) -> os_id | None
```

Todo lugar usa essas funções:

- site: listas, detalhe, formulários, cancelamento, financeiro;
- API: `os.numero`;
- GTK: tabela, diálogo, título;
- PDF: cabeçalho, título, nome do arquivo;
- e-mail: assunto, corpo, anexo;
- busca: número, alias e id apenas quando necessário.

### 6.2 URLs

Decisão recomendada: **número público na URL**, com resolução por alias.

```text
/os/261107001          número novo
/os/OS-0034            alias antigo
/os/37                 id legado (redireciona para o número)
```

Cuidados:

- definir prioridade de resolução (alias/número antes de id);
- validar colisão entre número público e id numérico;
- redirecionar 301/302 do id para o número canônico;
- links antigos em e-mails/PDFs continuam funcionando via alias;
- nunca quebrar link já enviado.

Se a colisão numérica for inaceitável, usar um namespace explícito
(`/os/n/<numero>`) ou UUID público. Isso é decisão de produto, não detalhe.

### 6.3 PDFs e e-mails antigos

- PDFs já gerados não são reescritos.
- E-mails já enviados não são reenviados.
- O alias explica o número antigo.
- Novos PDFs usam só o número canônico no nome:
  `261107001.pdf` ou `OS-261107001.pdf`.
- O PDF não deve exibir “número + id” como se fossem dois números.

---

## 7. Migração dos 23 registros

### Fase 0 — preparação

- backup consistente do `dados.db` e anexos;
- copiar para uma base de ensaio;
- congelar escrita durante a migração;
- rodar mapeamento somente leitura;
- revisar a tabela de mapeamento;
- definir fuso e política.

### Fase 1 — schema aditivo

- criar `numbering_*`;
- adicionar `numero_os_legado`, `numero_os_emitido_em`, `numero_policy_id`;
- não alterar `numero_os` ainda.

### Fase 2 — ensaio

- rodar migração na cópia;
- validar contagens, unicidade, FKs, aliases, links, PDFs e e-mails;
- testar rollback;
- comparar totais financeiros e estoque antes/depois.

### Fase 3 — migração real

Uma transação:

1. para cada OS por `criado_em, id`;
2. agrupa por dia no fuso configurado;
3. atribui `YYMMDD001...`;
4. grava `numero_os_legado`;
5. insere alias antigo → id;
6. atualiza `numero_os`;
7. grava `numbering_sequences` com o próximo valor;
8. valida unicidade e contagem;
9. commit.

Se qualquer etapa falhar: rollback e restaurar backup.

### Fase 4 — superfícies

- trocar site/GTK/PDF/e-mail/API para a função canônica;
- corrigir `/os/{id}` e `OS {os_id}`;
- adicionar redirecionamento de links antigos;
- rodar smoke completo.

### Fase 5 — MAIN

- revisão humana externa;
- backup;
- janela de manutenção;
- migração;
- smoke;
- monitorar logs;
- rollback documentado.

---

## 8. Testes obrigatórios

- geração sequencial no mesmo dia;
- virada de dia/fuso;
- 999º e 1000º número;
- concorrência com duas criação simultâneas;
- letras (`A`, `Z`, `AA`);
- UUID/ULID;
- política inválida;
- mudança de política não renumera antigas;
- migração idempotente;
- migração com `criado_em` inválido;
- migração com mais de 999/dia;
- aliases antigos;
- links `/os/<numero>`, `/os/<alias>`, `/os/<id>`;
- PDF, e-mail e API com o mesmo número;
- rollback restaura o banco anterior.

---

## 9. O que não fazer

- `MAX(CAST(SUBSTR(numero_os...)))+1`;
- regex para “adivinhar” data;
- renumerar sem backup;
- reescrever PDFs/e-mails históricos;
- exibir número antigo e novo ao mesmo tempo na operação normal;
- manter dois geradores de número;
- mudar o número no link sem alias;
- usar o `id` como número público;
- migrar schema e comportamento no mesmo commit;
- ir para MAIN sem ensaio em cópia e revisão.

---

## 10. Decisões abertas

1. Data base: `criado_em` (recomendado) ou `data_abertura`?
2. Fuso: `America/Sao_Paulo` ou fuso do servidor?
3. URL pública: número, alias, `/os/n/<numero>` ou UUID?
4. Prefixo visual: nenhum (`261107001`) ou `OS-` (`OS-261107001`)?
5. Limite 999: erro, fila para o próximo dia ou bloqueio administrativo?
6. Numeração por instalação ou por tenant?
7. Letras: base 26 (`A..Z, AA..`) ou outro alfabeto?
8. UUID/ULID: quando usar e como exibir?
9. Quem pode mudar a política? Admin da organização ou só plataforma?
10. O que fazer com PDFs antigos que já foram enviados?

---

## 11. Próximo passo

Não implementar a migração ainda. O próximo passo correto é:

1. decidir os 10 pontos acima;
2. escrever os testes de caracterização da numeração atual;
3. implementar a política e o gerador em `develop`, sem trocar a produção;
4. rodar a migração em cópia e revisar o mapeamento;
5. só então planejar a janela da MAIN.

Enquanto isso, a MAIN continua com `OS-00xx`; a `develop` pode receber a
fundação sem tocar nos dados reais.
