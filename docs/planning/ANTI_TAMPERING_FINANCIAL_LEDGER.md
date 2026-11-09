# Anti-tampering financeiro com assinaturas PGP

**Status:** planejamento apenas. Nada implementado.  
**Escopo:** mudanças financeiras da empresa e dos prestadores no AUTOSEG/Officina.  
**Não é:** blockchain, consenso distribuído, mineração ou promessa de imutabilidade
absoluta contra root/servidor comprometido.

## 1. Resumo para decisão

A recomendação é um **log de eventos append-only, assinado e encadeado por hash**,
parecido com uma mistura de Git com um log de transparência:

- cada mudança financeira vira um **evento** com payload canônico;
- o evento é assinado com a **chave privada** de cada aprovador;
- as assinaturas são verificadas com as chaves públicas do registro de chaves;
- cada evento contém o hash do evento anterior, formando uma corrente;
- checkpoints periódicos com raiz de Merkle são assinados e publicados fora do
  servidor (âncora externa), para detectar rollback e apagamento;
- políticas definem **quantas** e **quais** assinaturas são necessárias por tipo
  de mudança e por valor;
- o servidor atualiza o estado atual somente depois que a política é satisfeita.

Isso é mais próximo de **Git assinado + log de transparência** do que de uma
blockchain. Não há mineração nem consenso: há uma ordem única, assinaturas e
provas verificáveis.

## 2. O que PGP faz e o que não faz

PGP/OpenPGP fornece:

- autenticidade: a assinatura prova posse da chave privada correspondente;
- integridade: qualquer alteração no payload invalida a assinatura;
- não repúdio técnico: o dono da chave não pode negar facilmente que assinou
  aquele payload (mas pode alegar comprometimento da chave);
- verificação offline com a chave pública.

PGP **não** fornece:

- ordem dos eventos;
- proteção contra replay;
- proteção contra apagamento/rollback do banco inteiro;
- identidade humana: a assinatura aponta para uma chave, não para uma pessoa;
- proteção se a chave privada foi roubada;
- assinatura legal automática no Brasil (ICP-Brasil é um tema separado).

Por isso o desenho combina PGP com **hash chain**, **sequência monotônica**,
**checkpoints** e **âncoras externas**.

### Correção importante de vocabulário

Chaves públicas **verificam** assinaturas; chaves privadas **assinam**. Não se
"assina com a chave pública". O fluxo correto é:

1. cada administrador assina o mesmo envelope canônico com sua chave privada;
2. o envelope carrega várias assinaturas destacadas;
3. qualquer pessoa verifica cada assinatura com a chave pública correspondente.

"Multi-signature" aqui significa **várias assinaturas independentes sobre o mesmo
payload**, não uma chave PGP com vários UIDs e nem "todos os admins assinam tudo".

## 3. Modelo de ameaças

| Ameaça | O que o desenho faz | Risco residual |
|---|---|---|
| Sessão de admin roubada | Sem a chave privada, o invasor só propõe; não aprova | Se a chave estiver no navegador/servidor, o ataque vira assinatura |
| Chave privada roubada | Limiar de assinaturas, PIN/biometria, hardware token, revogação | Se o limiar inteiro for roubado, não há como impedir |
| Admin mal-intencionado | Separação de funções, limiar, assinatura do prestador afetado | Dois admins coligados podem aprovar se a política permitir |
| Prestador tentando mudar valor de outro | Política exige a chave do prestador afetado; ser admin não basta | Se a chave do prestador for custodial, a garantia é mais fraca |
| Alteração direta no SQLite | Hash chain e assinaturas detectam | Root pode reescrever tudo; checkpoint externo detecta |
| Apagar/rollback do banco | Checkpoint externo e comparação do head | Sem âncora externa, não há como provar rollback |
| Replay de evento antigo | `seq`, `prev_hash`, `event_id` e nonce; rejeição de duplicata | Servidor comprometido pode tentar esconder |
| Relógio do servidor adulterado | Ordem por sequência, não por relógio; timestamp externo no checkpoint | Timestamp local não é prova sozinho |
| Perda de chave | Quórum de recuperação, revogação, novo cadastro | Perder o quórum pode bloquear mudanças |
| Key ID exposto | Fingerprint é público; metadados vazam | Privacidade de quem assinou e quando |

**Não é objetivo** impedir que root/servidor apague o banco ou negue serviço.
Isso é detectável com âncora externa, não prevenível por assinatura local.

## 4. Arquitetura escolhida: log assinado, não blockchain

### 4.1 Por que não blockchain

Blockchain resolve consenso entre partes que não confiam umas nas outras. Aqui
temos um servidor da empresa, um banco SQLite e administradores conhecidos. Não
há necessidade de mineração, prova de trabalho ou consenso distribuído.

### 4.2 Por que não apenas Git

Git assinado é uma boa inspiração: commits assinados, conteúdo endereçado por
hash e histórico verificável. Mas Git permite `force-push` e reescrita de
histórico; para dinheiro isso não basta. Precisamos de:

- trilha append-only com proteção contra UPDATE/DELETE;
- sequência única e política de aprovação;
- checkpoint externo que detecte reescrita;
- estado financeiro atual derivado/validado pelo log.

### 4.3 Modelo

```text
Evento N-1 ──hash──► Evento N ──hash──► Evento N+1 ──► checkpoint Merkle
     ▲                    ▲
 assinaturas         assinaturas
```

- Um único escritor/sequenciador por tenant/instalação.
- `event_hash` cobre `seq`, `prev_hash`, tipo, agregado, hash do payload,
  política e timestamp.
- Assinaturas cobrem um **envelope de proposta canônico** (payload + tipo +
  agregado + política + nonce + autor + criado_em). A ordem final é protegida
  pela corrente; o checkpoint cobre a história.
- Correções não alteram o evento antigo: criam um novo evento de ajuste/
  estorno que referencia o original.

Se no futuro houver várias instalações independentes trocando verdade
financeira, aí sim se avalia um log permissionado/consenso. Para o AUTOSEG
atual, uma corrente linear por instalação é suficiente e muito mais simples.

## 5. Conceitos

- **Evento:** unidade imutável de mudança.
- **Payload:** dados da mudança (antes/depois, valores em centavos, motivo).
- **Envelope:** payload + metadados que serão assinados.
- **Assinatura:** assinatura PGP destacada de uma chave privada.
- **Política:** regra que diz quais papéis/chaves e quantas assinaturas são
  necessárias para um tipo de evento.
- **Chave:** par público/privado de um admin, prestador ou recuperação.
- **Key registry:** cadastro assinado e encadeado de chaves, papéis, validade e
  revogação.
- **Checkpoint:** raiz de Merkle de um intervalo de eventos, assinada por um
  quórum e publicada fora do servidor.
- **Âncora externa:** local fora do banco (Git privado, e-mail assinado, outro
  servidor, timestamp público) que guarda o checkpoint.
- **Head:** último `seq`/hash conhecido.
- **Break-glass:** mudança emergencial de um admin, marcada em vermelho, com
  assinatura retroativa obrigatória em prazo curto.

## 6. Modelo de dados proposto

Nomes em inglês; valores e textos podem ser em português.

```sql
ledger_events (
  id              INTEGER PRIMARY KEY,
  tenant_id       TEXT NOT NULL,
  seq             INTEGER NOT NULL,
  event_id        TEXT NOT NULL UNIQUE,     -- UUID/ULID do envelope
  event_type      TEXT NOT NULL,             -- finance.entry.update, ...
  aggregate_type  TEXT NOT NULL,             -- financeiro, rateio, repasse, os
  aggregate_id    TEXT NOT NULL,
  payload_json    TEXT NOT NULL,             -- JSON canônico
  payload_hash    TEXT NOT NULL,             -- SHA-256 do payload canônico
  prev_hash       TEXT NOT NULL,
  event_hash      TEXT NOT NULL,
  policy_id       TEXT NOT NULL,
  proposer_id     TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  status          TEXT NOT NULL,             -- proposed, approved, applied, ...
  UNIQUE(tenant_id, seq)
);

ledger_signatures (
  event_id        TEXT NOT NULL,
  key_fingerprint TEXT NOT NULL,
  role            TEXT NOT NULL,             -- admin, provider, finance, recovery
  signature_armor TEXT NOT NULL,             -- assinatura PGP destacada
  signed_at       TEXT NOT NULL,
  PRIMARY KEY(event_id, key_fingerprint)
);

ledger_keys (
  fingerprint     TEXT PRIMARY KEY,
  public_key      TEXT NOT NULL,             -- ASCII armored
  owner_type      TEXT NOT NULL,             -- admin, provider, recovery
  owner_id        TEXT NOT NULL,
  roles_json      TEXT NOT NULL,
  valid_from      TEXT NOT NULL,
  valid_to        TEXT,
  revoked_at      TEXT,
  revocation_event TEXT,
  created_event   TEXT NOT NULL
);

ledger_policies (
  id              TEXT PRIMARY KEY,
  event_type      TEXT NOT NULL,
  min_signatures  INTEGER NOT NULL,
  required_roles  TEXT NOT NULL,
  provider_must_sign INTEGER NOT NULL DEFAULT 0,
  max_amount_centavos INTEGER,
  distinct_signers INTEGER NOT NULL DEFAULT 1,
  break_glass     INTEGER NOT NULL DEFAULT 0,
  version         INTEGER NOT NULL
);

ledger_checkpoints (
  seq             INTEGER PRIMARY KEY,
  merkle_root     TEXT NOT NULL,
  head_hash       TEXT NOT NULL,
  created_at      TEXT NOT NULL,
  signatures_json TEXT NOT NULL,
  anchor_ref      TEXT                      -- Git/e-mail/timestamp/outro
);

ledger_meta (
  chave           TEXT PRIMARY KEY,
  valor           TEXT NOT NULL
);
```

Regras:

- `ledger_events`, `ledger_signatures` e `ledger_checkpoints` são append-only.
  Triggers `BEFORE UPDATE/DELETE` devem abortar. Isso é defesa em profundidade;
  root pode remover triggers, por isso o checkpoint externo é obrigatório.
- O estado atual (`financeiro`, `ordens_servico`, `produtividade_rateios`,
  `produtividade_repasses`, etc.) continua existindo como projeção. Toda escrita
  financeira passa pelo serviço do ledger e grava evento + estado na mesma
  transação SQLite (`BEGIN IMMEDIATE`).
- O log não substitui backup; ele fica no mesmo banco ou em um `ledger.db`
  anexado. Para maior resistência, exportar NDJSON + assinaturas periodicamente.
- Valores monetários sempre em centavos inteiros; datas ISO; JSON canônico
  (RFC 8785/JCS ou serialização determinística equivalente); UTF-8.

## 7. Assinaturas e políticas

### 7.1 O que é o quórum

Não usar "todos assinam". Isso é frágil: uma chave perdida bloqueia tudo, o custo
cresce com o número de admins e qualquer admin comprometido pode travar a
operação. Usar **M-de-N** por risco:

| Evento | Assinaturas | Observações |
|---|---|---|
| `finance.entry.create` até R$ 500 | 1 admin | Baixo risco |
| `finance.entry.create` acima de R$ 500 | 2-de-3 admins distintos | Valor alto |
| `finance.entry.update` | 2-de-3 admins distintos | Nunca o mesmo proponente sozinho |
| `finance.payment.confirm` | 1 finance + 1 admin | Ou 2-de-3 |
| `finance.rateio.update` | 1 admin + técnico afetado, se tiver chave | Evita rateio unilateral |
| `finance.provider_value.update` | 2 admins + **chave do prestador afetado** | Núcleo do isolamento |
| `finance.repasse.confirm` | 1 admin + 1 finance | Valor e destinatário |
| `ledger.key.register` / `revoke` | 3-de-5 admins | Chaves são infraestrutura |
| `ledger.policy.change` | 3-de-5 admins | Não permitir auto-alteração fácil |
| `break_glass` | 1 admin | Expira em 24 h; exige 2 assinaturas depois |

Os números são proposta; o dono do produto decide. O importante é:
**distintos**, **por papel**, **por valor** e **com o afetado assinando quando for
o caso**.

### 7.2 Isolamento entre prestadores

O caso "ambos são admins" não pode ser resolvido só por "é admin". A política do
evento `finance.provider_value.update` deve exigir:

1. pelo menos 2 assinaturas de admins distintos; e
2. uma assinatura da chave vinculada ao `provider_id` afetado.

Assim, um admin que não é o prestador afetado não consegue, sozinho, mudar o
valor do outro. Se o próprio prestador afetado for admin, a política ainda exige
outro admin distinto; autoaprovação sozinha é rejeitada.

Se o prestador ainda não tiver chave, o fallback precisa ser explícito:

- 3-de-5 admins + evento marcado `custodial=true` + justificativa obrigatória;
- aparece em vermelho no painel e no relatório;
- prazo para o prestador cadastrar a chave e assumir o controle.

Nunca fazer fallback silencioso.

### 7.3 Separação de funções

- Quem propõe não conta como aprovação única em evento de alto risco.
- Financeiro não altera valor técnico de OS; admin técnico não confirma pagamento
  sozinho.
- O proponente pode assinar, mas a política exige outros papéis/chaves.
- Em caso de conflito de interesse (prestador afetado), a assinatura dele é
  obrigatória e a do admin que se beneficia não substitui.

### 7.4 Break-glass

Uma mudança emergencial pode ser aplicada com 1 admin, mas:

- fica marcada `break_glass`;
- notifica todos os admins imediatamente;
- exige 2 assinaturas em até 24 h;
- se não completar, o evento é marcado `unauthorized` e a mudança é revertida
  por um evento de compensação;
- todo o histórico fica visível.

Break-glass não pode ser silencioso nem virar rotina.

## 8. Chaves e identidades

### 8.1 Geração e custódia

- Chave privada **nunca** no banco, no servidor, no Git ou em backup do servidor.
- Preferir OpenPGP card/YubiKey ou chave em keychain do sistema com PIN.
- Para o site web, PGP no navegador é ruim. Planejar um **agente local de
  assinatura** (app desktop/CLI) ou WebAuthn/passkeys como alternativa futura.
- A chave pública é registrada no `ledger_keys` por um evento assinado pelo
  próprio dono + quórum existente.
- O cadastro prova posse: desafio assinado com a chave privada; o admin confere
  identidade e fingerprint por um segundo canal.

### 8.2 Papéis e identidades

- `admin_id` e `provider_id` são identidades; a chave é separada.
- Uma pessoa pode ter mais de uma chave; uma chave pode ter mais de um papel,
  mas a política conta fingerprints distintos.
- O login por senha/sessão não é a assinatura. Sessão comprometida não deve
  permitir assinar.
- O registro de chaves mapeia fingerprint → dono → papéis → validade/revogação.

### 8.3 Rotação e revogação

- Nova chave é registrada com assinatura da chave antiga + quórum.
- Revogação é um evento assinado; vale a partir do `revoked_at`.
- Assinaturas antigas continuam válidas (feitas antes da revogação), mas não
  contam para eventos posteriores.
- Chave perdida: quórum de recuperação (ex.: 3-de-5 chaves offline) autoriza a
  revogação e o novo cadastro.
- Testar o procedimento de perda/roubo antes de production.

## 9. Fluxo de uma mudança

1. **Propor:** admin abre "Alterar valor da OS", vê o diff, o valor antigo/novo,
   o prestador afetado, o motivo obrigatório.
2. **Montar envelope:** o serviço canonicaliza o payload e mostra o hash
   (fingerprint) que será assinado.
3. **Assinar:** o proponente assina localmente (hardware/PIN). A assinatura vai
   para `ledger_signatures` com status `proposed`.
4. **Coletar:** a política calcula o que falta: 2 admins, prestador afetado,
   financeiro etc. A UI mostra "2 de 3 assinaturas" e quem falta.
5. **Aplicar:** quando o quórum é satisfeito, o serviço valida tudo, aplica a
   mudança nas tabelas atuais e grava o evento na corrente, na mesma transação.
6. **Checkpoint:** periodicamente, um Merkle root é assinado e publicado fora.
7. **Verificar:** CLI e clientes recalculam hashes e assinaturas; a UI mostra
   "verificado" somente após a verificação.

Se o quórum não for atingido, o estado atual não muda. A proposta expira e é
marcada como rejeitada/expirada; o payload fica no log de propostas para
auditoria.

### 9.1 Concorrência

- Um sequenciador por tenant; `BEGIN IMMEDIATE`; `expected_head` obrigatório.
- Se o head mudou entre a proposta e a aplicação, a proposta é rejeitada e
  precisa ser refeita sobre o novo estado.
- Não usar `MAX(id)+1`; usar a sequência do ledger.

### 9.2 Replay e idempotência

- `event_id`/nonce único; rejeitar duplicata.
- `seq` monotônico; `prev_hash` obrigatório.
- Rejeitar evento cujo `prev_hash` não é o head atual.
- Checkpoint externo detecta rollback de head.

## 10. Verificação

### 10.1 CLI

Planejar um comando somente leitura:

```bash
./autoseg ledger verify --db <dados.db> --from 1 --to head
./autoseg ledger export --format ndjson --out ledger.ndjson
./autoseg ledger checkpoint --verify <checkpoint.json>
```

Ele deve:

- recalcular `payload_hash`, `event_hash` e a corrente;
- verificar cada assinatura PGP contra `ledger_keys` e a política;
- validar que os signatários são distintos e têm os papéis exigidos;
- comparar o head com o último checkpoint externo;
- reportar `OK`, `tampered`, `rollback`, `missing_signature`, `revoked_key`.

### 10.2 Verificação pelo cliente

O servidor não pode ser o único juiz. O cliente (GTK/CLI/web com agente local)
deve verificar o checkpoint e as assinaturas antes de mostrar "aprovado". Para o
site, planejar um agente local ou um fluxo de download/verificação; PGP no
navegador não é prático.

### 10.3 Âncora externa

- Checkpoint a cada N eventos ou diariamente.
- Publicar `checkpoint.json` + assinaturas em um local fora do banco:
  - repositório Git privado com branch/tag protegida;
  - e-mail assinado para todos os admins;
  - segundo servidor/cofre;
  - OpenTimestamps/timestamp público (prova de existência).
- O anchor guarda só a raiz/head, não os dados financeiros.
- Na inicialização/login, comparar o head local com o anchor mais recente; se
  divergir, alarme e modo somente leitura até investigação.

## 11. Interface e experiência

- Mostrar sempre: tipo de mudança, entidade, valor antigo/novo, prestador
  afetado, motivo, solicitante, assinaturas coletadas, faltantes e prazo.
- Botão "Assinar" deve abrir o agente/hardware; nunca pedir chave privada no
  formulário web.
- Exibir o hash do envelope de forma curta (ex.: 12 caracteres) e o fingerprint
  da chave; permitir copiar.
- "Verificado" só depois da verificação local; "servidor diz que está ok" não é
  suficiente.
- Notificações de proposta pendente, expiração, break-glass e divergência de
  checkpoint.
- Histórico legível por humanos e exportável em NDJSON/CSV para auditoria.
- Acessibilidade: não depender só de cor; break-glass com texto e ícone.

## 12. Operação e recuperação

- Backup do banco + ledger + chaves públicas + checkpoints; nunca da chave
  privada.
- Testar restauração e verificação após restauração.
- Key ceremony inicial: gerar chaves, registrar, testar assinatura/verificação,
  simular perda e revogação.
- Quórum de recuperação separado do quórum do dia a dia.
- Trocar chaves periodicamente e após qualquer suspeita.
- Plano de incidente: revogar chave, congelar escrita, comparar checkpoints,
  investigar, comunicar, restaurar.
- Retenção: definir por quanto tempo propostas rejeitadas, assinaturas e
  metadados ficam guardados; LGPD/privacidade.
- Relógio: não confiar no relógio local para ordem; usar `seq` e timestamp
  externo do checkpoint.

## 13. Migração e fases

### Fase 0 — decisão e desenho (este documento)

- Fechar limiares, papéis, custódia de chaves de prestador, âncora externa,
  break-glass e revisão legal.
- Nenhum código alterado.

### Fase 1 — ledger somente leitura

- Criar tabelas, canonicalização, hash chain, registro de chaves e CLI de
  verificação.
- Registrar eventos financeiros sem bloquear escrita (shadow mode).
- Criar um **genesis checkpoint** assinado com o hash do estado atual; não
  assinar retroativamente eventos históricos como se tivessem acontecido.
- Rodar em DEV com banco temporário; comparar estado atual com replay do ledger.
- Rollback: feature flag desligada; tabelas aditivas.

### Fase 2 — uma fatia com enforcement

- Escolher uma fatia pequena: `finance.provider_value.update` ou
  `finance.rateio.update`.
- Exigir assinatura no caminho de escrita; bloquear update direto.
- UI de proposta/assinatura; testes de autorização e concorrência.
- Ainda em DEV/flag; revisão externa N3/N4.

### Fase 3 — expandir para dinheiro

- `finance.entry.*`, `finance.payment.confirm`, `finance.repasse.*`.
- Checkpoints periódicos e âncora externa.
- Simular admin comprometido, chave perdida, rollback e restauração.

### Fase 4 — prestadores e hardware

- Chaves de prestadores; cadastro/verificação; custódia.
- OpenPGP card/YubiKey; agente de assinatura no desktop.
- Revisão legal de assinatura eletrônica e não repúdio.

### Fase 5 — remover caminhos antigos

- Fechar writes diretos nas tabelas financeiras.
- `portal_auditoria` deixa de ser a fonte de verdade financeira; vira log
  secundário ou é alimentado pelo ledger.
- Relatórios e PDFs mostram o ID do evento/checkpoint quando aplicável.

Cada fase: backup, migração idempotente, validação, rollback, testes e revisão
externa. Nada de big-bang.

## 14. Segurança, privacidade e legal

- Chave privada nunca no servidor. Se o servidor tiver a chave, o modelo de
  não repúdio cai.
- Fingerprints e metadados são públicos dentro da instalação; não são segredo.
- O ledger contém dados financeiros sensíveis; mesma proteção do banco
  (permissões 600/700, backup criptografado, retenção).
- Assinatura PGP não é automaticamente assinatura legal brasileira. Para
  validade jurídica/ICP-Brasil, avaliar com advogado; o ledger pode ser prova
  interna e auditoria, não necessariamente assinatura qualificada.
- Se a chave for comprometida, o dono pode alegar repúdio; custódia (hardware,
  PIN, testemunhas, key ceremony) e quórum reduzem esse risco.
- Ameaça de coerção/insider: nenhum sistema técnico resolve sozinho; política,
  segregação e auditoria externa complementam.

## 15. Riscos residuais e não objetivos

- Root/servidor comprometido pode apagar o banco e mentir na UI; checkpoint
  externo e verificação no cliente detectam, mas não impedem a negação de
  serviço.
- Se M chaves forem comprometidas, a política não protege; escolher M/N e
  hardware de acordo com o risco.
- PGP é difícil para usuários comuns; UX e suporte são parte do projeto.
- Volume alto de eventos com assinatura manual é inviável; usar limiares e
  agrupamento.
- Não prometer "blockchain" nem "imutável" sem âncora externa.
- Não assinar retroativamente o histórico; genesis checkpoint é o correto.
- Não usar um DAG sem regra de merge para dinheiro; uma corrente linear é mais
  simples e auditável.

## 16. Decisões pendentes (dono do produto)

Estas decisões são intencionais e devem ser respondidas com use case real, não
todas agora. O documento
[`SIGNED_OS_TWO_PARTY_AND_VERSIONING.md`](SIGNED_OS_TWO_PARTY_AND_VERSIONING.md)
propõe perfis A/B/C e um formato de ADR. A Fase 1 (ledger em modo sombra) não
depende de fechar todos os limiares.

1. Limiares: 2-de-3 ou 3-de-5? Por valor? Por tipo?
2. Prestador tem chave própria ou custódia da empresa? Se custódia, qual o
   fallback e como marcar?
3. Quem pode propor vs. aprovar? Financeiro assina pagamento?
4. Hardware (YubiKey/OpenPGP card) é obrigatório para admins?
5. Assinatura no site: agente local, desktop, WebAuthn ou download/upload?
6. Âncora externa: Git privado, e-mail assinado, segundo servidor ou timestamp
   público? Frequência?
7. Quórum de recuperação e cerimônia de chaves.
8. Break-glass: quem pode, prazo, o que reverte.
9. Retenção/privacidade dos metadados e do ledger.
10. Revisão legal/ICP-Brasil e política de não repúdio.
11. Escopo inicial: só empresa, ou já inclui valores de prestadores?
12. Multi-tenant: uma corrente por instalação ou por tenant?

## 17. Exemplo de evento

```json
{
  "event_id": "01J...",
  "tenant_id": "autoseg",
  "seq": 128,
  "event_type": "finance.provider_value.update",
  "aggregate_type": "financeiro",
  "aggregate_id": "18",
  "payload": {
    "provider_id": 4,
    "os_id": 12,
    "field": "valor",
    "old_centavos": 35000,
    "new_centavos": 30000,
    "reason": "Correção de valor cobrado a menor",
    "requested_by": "admin:1"
  },
  "payload_hash": "sha256:...",
  "prev_hash": "sha256:...",
  "policy_id": "finance.provider_value.update.v1",
  "proposer": "admin:1",
  "created_at": "2026-11-09T13:00:00",
  "signatures": [
    {"key": "FINGERPRINT_ADMIN_1", "role": "admin", "sig": "-----BEGIN PGP SIGNATURE-----..."},
    {"key": "FINGERPRINT_ADMIN_2", "role": "admin", "sig": "-----BEGIN PGP SIGNATURE-----..."},
    {"key": "FINGERPRINT_PROVIDER_4", "role": "provider", "sig": "-----BEGIN PGP SIGNATURE-----..."}
  ]
}
```

O evento acima só é aplicado se as três assinaturas forem válidas, se os admins
forem distintos e se a chave do prestador 4 estiver válida e vinculada a ele.

## 18. Referências internas

- [`PGP_MULTISIGNATURE_ARCHITECTURE.md`](PGP_MULTISIGNATURE_ARCHITECTURE.md) —
  arquitetura de alto nível, camadas Workaholic/Officina/AUTOSEG, 2-de-3,
  verificação independente e limites.
- [`SIGNED_OS_TWO_PARTY_AND_VERSIONING.md`](SIGNED_OS_TWO_PARTY_AND_VERSIONING.md)
  — OS assinada pelo prestador + empresa, versionamento, canonicalização e
  mudanças de fórmula.
- [`../../workaholic/docs/adr/0003-signed-event-ledger.md`](../../workaholic/docs/adr/0003-signed-event-ledger.md)
  — ADR da fronteira do ledger assinado.
- [`docs/features/API_FINANCEIRO.md`](../features/API_FINANCEIRO.md) — moeda em
  centavos, paginação, isolamento por prestador.
- [`docs/PERMISSIONS_AND_APPROVALS.md`](../PERMISSIONS_AND_APPROVALS.md) —
  papéis, aprovação em camadas e auditoria.
- [`docs/REVIEW_WITHOUT_DEVELOPER.md`](../REVIEW_WITHOUT_DEVELOPER.md) — revisão
  externa para mudanças N3/N4.
- [`workaholic/docs/ARCHITECTURE.md`](../../workaholic/docs/ARCHITECTURE.md) —
  fronteira do motor genérico.
- [`docs/operations/DATA_STORAGE.md`](../operations/DATA_STORAGE.md) — banco,
  backup e permissões.

## 19. Recomendação final

Sim, vale fazer; mas como **log assinado com limiares**, não como "todos assinam
tudo" e não como blockchain.

Ordem recomendada:

1. fechar as decisões da seção 16;
2. implementar ledger shadow + verificador CLI + genesis checkpoint;
3. impor assinatura em uma única fatia financeira no DEV;
4. só depois expandir para pagamentos, rateios, repasses e valores de
   prestadores;
5. com âncora externa, hardware keys e revisão legal antes de produção.

O que isso garante de verdade:

- mudanças financeiras passam a ter autor, payload e assinaturas verificáveis;
- alteração direta no banco é detectável;
- rollback/apagamento é detectável com âncora externa;
- um admin sozinho não muda valor de outro prestador;
- prestador não muda valor de outro prestador nem assina pelo outro;
- quem assinou é rastreável até a chave e o cadastro de identidade.

O que isso não garante:

- que uma pessoa específica assinou (garante que a chave dela assinou);
- que o servidor não vai apagar tudo (garante detecção, não prevenção);
- que duas ou mais chaves comprometidas não consigam aprovar;
- validade legal automática no Brasil.
