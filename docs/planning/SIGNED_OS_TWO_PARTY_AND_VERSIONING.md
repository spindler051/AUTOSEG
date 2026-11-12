# OS assinada em duas partes e versionamento de formato

**Status:** planejamento apenas. Nada implementado.  
**Complementa:** [`ANTI_TAMPERING_FINANCIAL_LEDGER.md`](ANTI_TAMPERING_FINANCIAL_LEDGER.md).  
**Tema:** como o prestador e a empresa assinam a mesma OS, o que acontece
quando alguém tenta mudar depois, e como evoluir o formato sem quebrar
assinaturas antigas.

## 1. Modelo mental correto: documento versionado, não linha mutável

A OS não deve ser pensada como uma linha de `ordens_servico` que sofre `UPDATE`.
Ela deve ser pensada como um **documento versionado**:

```text
OS (id estável)
 ├── versão 1 — snapshot assinado pelo prestador + empresa
 ├── versão 2 — snapshot novo, assinaturas novas, referência à v1
 └── versão 3 — ...
```

- Cada versão é imutável.
- Uma mudança cria uma **nova versão**, não reescreve a antiga.
- A assinatura da empresa na versão 1 **não valida** a versão 2.
- A versão 2 só é considerada aprovada quando cumprir a política de assinaturas
  dela.
- O histórico mostra exatamente o que mudou entre v1 e v2.

Isso é o que o exemplo do prestador assinando a própria OS + a empresa
contra-assinando quer dizer. Está correto, desde que a assinatura seja sobre um
snapshot canônico e que a mudança seja um novo snapshot.

## 2. Duas assinaturas: prestador + empresa

### 2.1 O fluxo

1. O prestador cria/aceita a OS. O app monta o snapshot canônico.
2. O prestador assina com a chave privada dele.
3. O snapshot + assinatura ficam no ledger como `proposed`.
4. A empresa (um admin, um quórum ou uma chave corporativa governada) confere o
   diff e assina o **mesmo snapshot**.
5. As duas assinaturas válidas aplicam a versão.
6. Qualquer mudança posterior gera uma nova versão; as duas partes (ou o
   subconjunto exigido pela política) assinam de novo.

### 2.2 O que cada assinatura significa

- **Prestador:** "esta é a minha OS, estes são os meus valores/itens/condições
  nesta versão".
- **Empresa:** "a empresa conferiu e aceita esta versão".
- A empresa não assina "a OS em geral"; assina **aquele snapshot**.
- O prestador não assina "qualquer mudança futura"; assina **aquele snapshot**.

### 2.3 Cenários

| Cenário | Resultado |
|---|---|
| Prestador assina v1, empresa assina v1 | v1 válida e aplicada |
| Prestador altera valor e assina v2; empresa ainda não assinou | v2 pendente; v1 continua válida e imutável |
| Empresa altera valor e assina v2; prestador ainda não assinou | v2 pendente; v1 continua válida |
| Prestador tenta sobrescrever v1 com v2 assinada só por ele | v1 permanece; v2 não cumpre a política; a diferença é detectável |
| Empresa tenta sobrescrever v1 com v2 assinada só por ela | v1 permanece; v2 pendente do prestador |
| Alguém altera bytes de v1 no banco | assinatura de v1 falha na verificação |
| Alguém apaga v1 e deixa v2 | checkpoint/hash chain detectam a ausência |

O ponto central: **a assinatura antiga não "quebra" quando a OS muda.** Ela
continua válida para o snapshot antigo. O que quebra é a tentativa de usar a
assinatura antiga para validar o snapshot novo. A UI deve mostrar isso como
"versão nova aguardando assinatura", não como corrupção.

## 3. O que exatamente é assinado

Assinar a linha do SQLite ou o HTML da tela é frágil. O snapshot canônico deve
conter apenas dados semânticos estáveis:

```json
{
  "schema": "autoseg.os.snapshot",
  "schema_version": 1,
  "canonicalization": "RFC8785",
  "os_id": 12,
  "provider_id": 4,
  "client_id": 18,
  "numero_os": "261103009",
  "status": "Aberta",
  "values": {
    "currency": "BRL",
    "labor_centavos": 25000,
    "materials_centavos": 10000,
    "total_centavos": 35000
  },
  "items": [],
  "formula": {
    "id": "os.total",
    "version": 3,
    "inputs_hash": "sha256:...",
    "result_centavos": 35000
  },
  "dates": {
    "opened_at": "2026-11-03",
    "due_at": null
  },
  "attachments": [
    {"id": 7, "sha256": "..."}
  ],
  "author_id": "admin:1",
  "created_at": "2026-11-09T13:00:00"
}
```

Regras:

- **IDs estáveis:** `os_id`, `provider_id`, `client_id` são a identidade. O
  `numero_os` é um rótulo; se ele mudar por renumeração, o `os_id` continua o
  mesmo. Se o número for juridicamente relevante, ele entra no snapshot, mas
  snapshots antigos **não** são reescritos.
- **Dinheiro em centavos inteiros.** Nunca float.
- **Datas ISO.** Fuso explícito quando importar.
- **Fórmula versionada:** guardar `formula.id`, `formula.version`, entradas e
  resultado. Assim uma mudança futura na fórmula não reescreve o passado.
- **Anexos por hash:** o snapshot referencia o SHA-256 do arquivo; o arquivo
  original fica imutável no storage.
- **Não assinar HTML, CSS, template de PDF ou nome de coluna.** Renderização
  pode mudar sem invalidar o snapshot semântico.
- Se for assinar o PDF, assinar o **hash dos bytes do PDF** e guardar o PDF
  imutável; mudar o template gera um PDF novo, não reescreve o antigo.

## 4. Versionamento e mudanças fundamentais de formato

O problema levantado é real: se o formato canônico mudar, uma verificação que
tenta re-serializar o passado com o código novo pode falhar. A regra de ouro é:

> **Nunca re-serializar um payload já assinado. Guarde os bytes canônicos
> assinados e verifique exatamente esses bytes.**

### 4.1 Envelope versionado

Todo evento deve declarar:

- `schema` e `schema_version`;
- `canonicalization` (ex.: `RFC8785-v1`);
- `hash_algorithm` (ex.: `sha256-v1`);
- `signature_algorithm` (ex.: `openpgp-rfc4880-v1`);
- `policy_id` e `policy_version`.

A assinatura cobre o envelope canônico. Um verificador novo reconhece versões
antigas e usa o canonicalizador antigo. Um verificador antigo não precisa
entender o formato novo; ele só precisa continuar verificando o que já existia.

### 4.2 Guardar os bytes assinados

- Persistir `payload_canonical` (bytes exatos) junto com o hash e as assinaturas.
- O JSON parseado é conveniência para consulta; a verdade criptográfica é o
  byte exato.
- Se o payload for grande, guardar em blob endereçado por hash; o evento
  referencia o hash e o blob imutável.
- Testes com **golden vectors**: payloads assinados de exemplo, hashes e
  assinaturas conhecidas, verificados em CI para sempre.

### 4.3 Mudanças de schema

- Novo campo ou mudança de significado → **nova `schema_version`**.
- Não renomear campo, não mudar unidade de centavos para reais, não mudar
  `null` por `0` silenciosamente.
- Migração de dados não toca no snapshot antigo. Cria um **evento de migração**
  que referencia o hash antigo e o hash novo, assinado pelo quórum.
- O evento de migração é uma atestação: "a versão antiga X foi convertida na
  versão nova Y; os dois snapshots são estes". A assinatura antiga continua
  válida para X; a nova cobre Y.
- Se não for possível converter sem perda, o snapshot antigo permanece como
  está e o novo é uma nova versão.

### 4.4 Mudanças de fórmula

- A fórmula é dado versionado, não código implícito.
- O snapshot guarda `formula_version`, entradas e resultado.
- Verificar a assinatura **não** reexecuta a fórmula. A assinatura prova que
  aquele resultado foi assinado.
- Para auditoria de cálculo, guardar as entradas e manter a versão antiga da
  fórmula disponível; ou aceitar o resultado assinado como snapshot histórico.
- Mudar a fórmula não invalida snapshots antigos; só muda o cálculo de snapshots
  novos.

### 4.5 Mudanças de apresentação

- Template de PDF, CSS, ordem de campos na tela, nome de rótulo: não entram no
  snapshot semântico. Podem mudar sem quebrar assinatura.
- Se o PDF for o documento legal, assinar o PDF; nesse caso, mudanças de
  template geram um PDF novo, não reescrevem o antigo.
- Relatórios e exports derivados devem indicar a versão/hash do snapshot de
  origem.

### 4.6 Renumeração de OS

- O `os_id` é a identidade; `numero_os` é rótulo.
- Snapshots antigos mantêm o número antigo; snapshots novos usam o novo.
- Um evento de renumeração registra o mapeamento e é assinado.
- Não reescrever o snapshot antigo para "corrigir" o número. A verificação
  antiga continua válida; a UI mostra o número atual com indicação de "número
  na época: ...".

## 5. Semântica de verificação

Ao abrir uma OS/versão, o verificador deve produzir um estado claro:

| Estado | Significado | Ação |
|---|---|---|
| `valid` | assinaturas obrigatórias válidas e payload intacto | mostrar aprovada |
| `pending_provider` | falta assinatura do prestador | notificar prestador |
| `pending_company` | falta assinatura da empresa/quórum | notificar empresa |
| `changed` | bytes não batem com o hash/assinatura | bloquear, alarmar, investigar |
| `unknown_schema` | verificador não conhece a versão | usar verificador antigo/atualizar; não declarar inválido sem tentar |
| `revoked_key` | chave foi revogada depois da assinatura | assinatura histórica ainda vale; novos eventos não |
| `rollback` | head local atrás do checkpoint externo | modo somente leitura e investigação |
| `custodial` | prestador sem chave; fallback explícito | mostrar alerta vermelho permanente |

O sistema nunca deve mostrar "aprovado" só porque o servidor disse. A verificação
é local/CLI e o checkpoint é comparado com a âncora externa.

## 6. Perfis de política para começar

As decisões não precisam ser todas agora. Começar com perfis e evoluir com uso
real:

### Perfil A — simples (piloto)

- Criação/aceite da OS: prestador assina; empresa assina.
- Mudança de valor: prestador + empresa.
- Observação interna: 1 admin.
- Chave da empresa: uma chave corporativa em HSM/YubiKey, usada com aprovação
  de 1 admin.
- Sem âncora externa obrigatória; checkpoint diário local.

### Perfil B — padrão

- Criação/aceite: prestador + 1 admin.
- Mudança de valor: prestador + 2-de-3 admins distintos.
- Conclusão: prestador + 1 admin/financeiro.
- Cancelamento: prestador + 2-de-3.
- Chave da empresa: quórum 2-de-3; hardware para admins.
- Checkpoint diário + âncora externa semanal.

### Perfil C — alta garantia

- Prestador com quórum próprio (se PJ com sócios) + 3-de-5 admins da empresa.
- Mudança de valor/cancelamento/conclusão: os dois lados com quórum.
- Hardware obrigatório; âncora externa diária; revisão legal.
- Break-glass só com recuperação 3-de-5 e prazo curto.

O perfil A permite aprender o fluxo sem travar a operação. O C é para valores
altos ou exigência jurídica.

## 7. Decisões guiadas por use case

As perguntas da seção 16 do documento principal são intencionais. Elas devem
ser respondidas aos poucos, com uso real, e registradas como ADR/decisão:

- Quem assina a criação? O prestador que executa ou o admin que cadastrou?
- Quem assina a conclusão? Prestador, admin, financeiro ou os dois?
- Anexos entram no snapshot ou só o hash?
- Mudança de valor exige as duas partes sempre ou só acima de um limite?
- Prestador sem chave: custódia, bloqueio ou fallback 3-de-5?
- Chave da empresa: uma chave HSM ou quórum de admins?
- O PDF é o documento legal ou o snapshot semântico é a verdade?
- Qual o prazo de break-glass e o quórum de recuperação?
- Como a chave é desbloqueada no dia a dia: passphrase manual, Keychain/OS,
  hardware ou a senha de login no modo de conveniência? O modo de conveniência
  é opt-in, de menor garantia, e a senha passa a ser um fator de assinatura;
  ver [`PGP_MULTISIGNATURE_ARCHITECTURE.md`](PGP_MULTISIGNATURE_ARCHITECTURE.md)
  §3.2 e §3.4.

Formato de registro sugerido:

```text
ADR-XXXX — [decisão]
Contexto:
Opções:
Decisão:
Consequências:
Data:
Revisão:
```

Não é necessário decidir tudo antes da Fase 1 (ledger em modo sombra). As
decisões de política podem evoluir; o que não pode evoluir sem versionamento é
o **formato canônico** e o **significado dos bytes assinados**.

## 8. O que quebra assinatura (e o que não quebra)

**Quebra:**

- alterar qualquer byte do payload assinado;
- re-serializar o payload com outro canonicalizador;
- mudar nome de campo, unidade, tipo, `null`/vazio;
- reescrever a linha do banco e tentar usar a assinatura antiga;
- apagar o snapshot antigo e manter só o novo;
- recalcular um valor com fórmula nova e comparar com assinatura antiga;
- trocar o número da OS dentro do snapshot antigo.

**Não quebra:**

- mudar CSS, HTML, template de PDF, texto de tela;
- adicionar campo em uma versão nova do schema;
- mudar a fórmula para snapshots futuros;
- adicionar anexo novo como um novo evento;
- renumerar a OS fora do snapshot antigo;
- atualizar o verificador desde que ele mantenha o suporte à versão antiga.

## 9. Recomendação

1. Tratar a OS como documento versionado; nunca sobrescrever versão assinada.
2. Assinar snapshots semânticos canônicos, não linhas de banco nem HTML.
3. Guardar os bytes canônicos assinados; não re-serializar o passado.
4. Versionar schema, canonicalização, algoritmo e política.
5. Prestador assina o próprio snapshot; empresa contra-assina (chave
   corporativa governada ou quórum).
6. Mudança posterior = nova versão pendente; a assinatura antiga continua
   válida para a versão antiga.
7. Fórmula e PDF são versionados separadamente; mudança de fórmula/template não
   reescreve o passado.
8. Começar com o Perfil A em DEV e evoluir com use case + ADR.

## 10. Referências

- [`ANTI_TAMPERING_FINANCIAL_LEDGER.md`](ANTI_TAMPERING_FINANCIAL_LEDGER.md) —
  modelo de ameaças, ledger, chaves, checkpoints e fases.
- [`../features/API_FINANCEIRO.md`](../features/API_FINANCEIRO.md) — valores em
  centavos e isolamento por prestador.
- [`../PERMISSIONS_AND_APPROVALS.md`](../PERMISSIONS_AND_APPROVALS.md) — papéis e
  aprovação em camadas.
