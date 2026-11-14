# Modos local, sync e serverless — análise externa

**Status:** análise de planejamento; **não implementado**.
**Fonte:** conversa compartilhada do ChatGPT em 2026-11-11:
<https://chatgpt.com/share/6af4ff2b-2db0-83e9-8a56-ee2764eee167>
**Relação com o plano vigente:**
[`PLANO_MODO_LOCAL_SYNC.md`](PLANO_MODO_LOCAL_SYNC.md) continua sendo o plano
base; este documento registra a análise externa, as correções de arquitetura e
o contexto de longo prazo.

> **Cuidado:** a outra IA declarou que **não leu o código**, apenas README e
> documentação. Nomes de módulos, comportamento atual e detalhes de
> `LocalService`, `HttpService`, `ConnectionMode`, `runtime_config` e do plano
> de sync podem estar desatualizados. Confirme tudo no checkout antes de
> implementar. A conversa também **não sabia** da direção futura de uma
> reescrita ampla do núcleo/protocolo em Rust.

## 1. Ideia central

Não sincronizar o arquivo SQLite. Cada dispositivo mantém seu banco privado e
troca um **log de mudanças** append-only; anexos e PDFs são blobs imutáveis
endereçados por hash.

```text
<local_data_dir>/
  dados.db                         # privado, nunca compartilhado
  sync/
    journal/<device_id>/000123.jsonl
    blobs/<sha256>
```

- cada dispositivo escreve somente o próprio journal;
- segmentos são selados/rotacionados, nunca reescritos;
- o receptor aplica mudanças de forma idempotente;
- o banco relacional não passa por transporte de arquivos/torrent.

Isso já está alinhado com `PLANO_MODO_LOCAL_SYNC.md`; a análise reforça que
O transporte de arquivos pode levar journal/blobs, mas não faz merge de SQLite.

## 2. Modos como presets de um motor

Em vez de portais/modos separados, a recomendação é um motor com três eixos:

- **storage:** local ou remoto (thin client);
- **transports:** nenhum, LAN, hub, relay, transporte de arquivos;
- **authority:** o próprio dispositivo, um servidor, um dispositivo designado
  ou nenhuma autoridade (com política de conflito).

| Modo | Storage | Transportes | Autoridade |
|---|---|---|---|
| Local | local | nenhum | próprio dispositivo |
| Local + Sync | local | hub e/ou LAN | servidor se existir; senão dispositivo designado |
| Sync serverless | local | LAN, relay, transporte de arquivos opcional | dispositivo designado ou política por entidade |
| Server (thin client) | remoto | HTTP | servidor |

`connection.json` pode guardar `{storage, transports[], authority}` e a UI
oferece presets. O servidor é um peer com papéis extras: hub, autoridade e
relay.

### 2.1 Seis modos de UX

O número depende do recorte. A arquitetura tem **quatro presets**; o produto
se desdobra em **seis modos de UX** quando separamos prestador/cliente e
LAN/WAN:

| # | Modo de UX | Storage | Transporte | Autoridade | Offline |
|---|---|---|---|---|---|
| 1 | Local prestador | local | nenhum | próprio dispositivo | sim |
| 2 | Local cliente | local + fila | nenhum/exportação | próprio dispositivo; envio posterior ao prestador | sim |
| 3 | Local + Sync (hub) | local | HTTP hub quando houver rede | servidor; senão dispositivo designado | sim |
| 4 | Servidor (thin client) | remoto | HTTP | servidor | não |
| 5 | Sync LAN | local | mDNS/HTTPS entre peers | dispositivo designado ou política por entidade | sim |
| 6 | Sync WAN/P2P | local | relay/Tailscale/WAN P2P | dispositivo designado ou política por entidade | sim |

“Híbrido” não é um sétimo modo: é o modo 3 com peers LAN/WAN opcionais. Se o
produto não oferecer o modo 2 no primeiro corte, ele continua existindo como
taxonomia futura; a implementação pode começar com 1, 3 e 4.

O importante é não transformar a taxonomia de UX em seis implementações
diferentes: por baixo são os mesmos eixos `storage`, `transports` e
`authority`.

## 3. Autoridade por entidade

O plano base tratava o servidor como autoridade de numeração, financeiro e
estoque. Isso não vale nos modos sem servidor. Cada entidade precisa declarar
uma política explícita:

- **merge:** campos simples, LWW por campo/HLC com histórico;
- **append-only:** eventos, pagamentos, movimentos de estoque, auditoria;
- **authority-required:** numeração canônica, fechamento financeiro, fiscal;
- **manual:** conflito de status, CPF/CNPJ duplicado, divergência de saldo.

Sem autoridade disponível, a entidade cai para append-only + reconciliação
sinalizada; não se inventa um “servidor invisível”. O número provisório
`OS-<device>-<seq>` pode ser permanente e válido no modo mesh; renumeração
canônica só existe quando há autoridade.

## 4. Captura de mudanças

- Preferir o **serviço de aplicação** para registrar a intenção.
- Complementar com **triggers SQLite** nas tabelas legadas para não perder
  escritas que burlarem o serviço.
- Usar um marcador “aplicando mudança remota” para os triggers não reemitirem
  o que veio de outro peer.
- A escrita de domínio + change record + outbox deve ser atômica.
- Aplicação remota é idempotente, em transação, e não reemite a mudança.

## 5. Identidade, confiança e assinaturas

Em serverless, cada peer precisa verificar autorização e integridade:

- cada dispositivo tem chave Ed25519;
- pareamento por QR/código com expiração;
- log assinado de membros/papéis/revogações;
- mudanças assinadas; peers rejeitam mudanças fora do escopo;
- dispositivo comprometido continua um risco dentro do seu escopo — limitar
  permissões e permitir revogação;
- não confiar na LAN por si só; TLS mútuo ou payload assinado.

## 6. Version vectors, não apenas “versão + 1”

O plano base usa `base_version` e cursor por peer, o que funciona no hub. Em
mesh, onde peers relayam mudanças, isso não basta:

- cada mudança tem `(origin_device, seq)` e `change_id` global;
- cada peer mantém um **version vector** por dispositivo;
- mudanças concorrentes são detectadas por causalidade (parents/version
  vector), não por relógio ou `versão + 1`;
- cursores por peer continuam úteis para transporte, mas não são a verdade da
  causalidade.

## 7. Transportes

Ordem recomendada:

1. **HTTP hub** — protocolo push/pull/ack já previsto;
2. **LAN** — mDNS + pareamento + TLS mútuo/assinaturas;
3. **transporte de arquivos (journal)** — cada device escreve só seu journal;
4. **relay/WAN** — Tailscale/WireGuard primeiro; relay mínimo que só armazena e
   encaminha mudanças cifradas;
5. **P2P nativo** — Iroh, Hypercore/Hyperswarm, libp2p, p2panda ou feeds
   estilo Scuttlebutt, somente depois de avaliar maturidade, licença e suporte
   a Python/Rust.

BitTorrent/torrent é adequado para blobs imutáveis e snapshots de bootstrap,
não para estado relacional mutável. O problema difícil de WAN P2P é NAT
traversal, não o log.

## 8. Relay / auxiliary node modes (opt-in)

A client PC can be an **auxiliary relay**: it stores and forwards encrypted
changes and blobs for other AUTOSEG devices. It is a transport, not an
authority. The server remains authoritative for numbering, finance,
permissions and global state.

**Status:** future; no relay code exists. This section defines the product and
security contract.

Modes are per device and mutually exclusive:

| Mode | Scope | Payload | Default |
|---|---|---|---|
| **Off** | none | none | on |
| **Own orders** | the signed-in account's own OS | changes and own metadata; optional own blobs | off |
| **Company metadata** | the whole company | OS metadata and changes; **no PDFs, images or heavy media** | off |
| **Full** | the whole company | everything, including PDFs, photos and heavy media | off |

### Consent and toggles

- Off by default. Every mode is an explicit opt-in.
- **Own orders:** consent from the signed-in user.
- **Company metadata / Full:** consent from the account/company owner.
- **Full** shows a heavy-mode warning and requires storage/bandwidth limits.
- A visible badge says “this device is acting as a relay”.
- One-click revoke; remote revoke and wipe; cached data has a TTL.
- No hidden or background relay. The device owner can see activity and bytes.

### Why opt-in is mandatory

A relay forwards ciphertext it cannot decrypt. It therefore gets **no direct
product benefit** from the work it does: it only spends disk, bandwidth,
battery, heat and legal exposure so that other devices stay in sync or
recoverable. That asymmetry is precisely why relay mode must never be
implicit:

- no default-on relay and no "help the network" prompt during first run or
  onboarding;
- enabling requires an explicit confirmation naming the mode, its limits and
  the fact that the payload is unreadable to the relay;
- the device owner can always see bytes served, peers served and storage used;
- disabling takes effect immediately and drops cached payloads;
- the server records the consent and revocation, so a relay can be audited
  without inspecting the relayed content.

Example local settings screen:

```text
Relay on this device:        [ ] off (default)
Use this device as:          ( ) My orders only
                             ( ) Company relay — no PDFs/images/heavy media
                             ( ) Full relay — PDFs, images and heavy media
Only on Wi-Fi:               [x]
Only while charging:         [x]
Battery floor:               40%
Storage limit:               5 GB
Upload limit:                10 Mbps
[ ] I understand this device may serve other AUTOSEG devices.
    Revoke at any time; cached data expires.
```

Example config file:

```ini
[relay]
enabled = false
mode = own_orders          # own_orders | company_metadata | full
only_on_wifi = true
only_while_charging = true
battery_floor = 40
max_storage_gb = 5
max_upload_mbps = 10
consent_company = false
consent_full = false
```

### Security and resource rules

- Relay payloads are end-to-end encrypted; the relay cannot read PII or
  financial content it forwards.
- Minimize routing metadata; do not expose customer data to the relay.
- The relay never merges SQLite files and never becomes an authority.
- Pause on metered networks, low battery, thermal pressure or quota exhaustion.
- Relay activity is audited; revocation stops new work immediately.
- “Auxiliary endpoint” here means relay/fallback transport, not a second
  authority. True failover requires a secondary server with a promotion rule.

## 9. Rust e o longo prazo

A direção futura inclui uma **reescrita ampla do núcleo/protocolo em Rust**
(as UIs continuam nativas/web; ver
[`VISAO_MULTICLIENTE_LOCAL_FIRST.md`](VISAO_MULTICLIENTE_LOCAL_FIRST.md)
§6.3). A conversa externa não sabia disso.

Consequências para este plano:

- o **protocolo, o schema do journal, os IDs, as assinaturas e as políticas de
  autoridade** devem ser language-neutral e especificados antes do Rust;
- o Rust deve ser uma segunda implementação atrás do mesmo contrato, com testes
  de conformidade; não uma segunda verdade;
- `p2panda` é Rust e pode ser relevante para o transporte/mesh no futuro, mas
  precisa de avaliação de maturidade, licença, modelo de dados e integração;
  não é dependência atual;
- evitar acoplar o protocolo a detalhes de Python/GTK ou a um banco específico;
- não iniciar a reescrita em Rust antes de existir contrato testável e
  protocolo v0.

## 10. O que isso muda no plano atual

- `PLANO_MODO_LOCAL_SYNC.md` continua válido como base.
- Adicionar autoridade por entidade aos modos, em vez de assumir servidor
  sempre autoritativo.
- Para mesh, trocar a confiança em `base_version`/cursor por version vectors e
  causalidade.
- Reforçar assinatura de mudanças, log de membros e triggers de captura.
- Tratar relay/transporte de arquivos como journal/blobs, não como banco.
- Registrar Rust como direção de núcleo/protocolo e manter o contrato
  language-neutral.

## 11. Decisões pendentes

1. Qual autoridade por entidade em cada modo?
2. Financeiro/estoque aceitam escrita offline? Com qual reconciliação?
3. Número provisório pode ser permanente no mesh? Quem atribui o canônico?
4. E2E: servidor vê conteúdo ou não?
5. Mobile: PWA ou app nativo?
6. Relay: modos, consentimento, limites e default?
7. Qual o escopo inicial: local + servidor, ou LAN também?
8. Quando o Rust entra: núcleo, protocolo, CLI ou módulo? Qual o contrato de
   conformidade?

## 12. Ordem prática

1. change recorder + triggers + device ID + version vectors;
2. transporte hub (HTTP) e aplicação idempotente;
3. autoridade por entidade;
4. LAN/mDNS + pareamento assinado;
5. relay/transporte de arquivos (journal);
6. relay/WAN;
7. avaliar P2P nativo e Rust com contrato/testes.

## 13. Referências

- [`PLANO_MODO_LOCAL_SYNC.md`](PLANO_MODO_LOCAL_SYNC.md)
- [`VISAO_MULTICLIENTE_LOCAL_FIRST.md`](VISAO_MULTICLIENTE_LOCAL_FIRST.md)
- Ink & Switch — Local-first software
- CRDT.tech
- SQLite — SQLite Over a Network
- p2panda — <https://github.com/p2panda/p2panda> (avaliar, não adotar agora)
