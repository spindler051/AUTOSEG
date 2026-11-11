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
- o banco relacional não passa por Syncthing/Dropbox/torrent.

Isso já está alinhado com `PLANO_MODO_LOCAL_SYNC.md`; a análise reforça que
Syncthing só serve como transporte de journal/blobs, não como merge de SQLite.

## 2. Modos como presets de um motor

Em vez de portais/modos separados, a recomendação é um motor com três eixos:

- **storage:** local ou remoto (thin client);
- **transports:** nenhum, LAN, hub, relay, arquivos/Syncthing;
- **authority:** o próprio dispositivo, um servidor, um dispositivo designado
  ou nenhuma autoridade (com política de conflito).

| Modo | Storage | Transportes | Autoridade |
|---|---|---|---|
| Local | local | nenhum | próprio dispositivo |
| Local + Sync | local | hub e/ou LAN | servidor se existir; senão dispositivo designado |
| Sync serverless | local | LAN, relay, Syncthing opcional | dispositivo designado ou política por entidade |
| Server (thin client) | remoto | HTTP | servidor |

`connection.json` pode guardar `{storage, transports[], authority}` e a UI
oferece presets. O servidor é um peer com papéis extras: hub, autoridade e
relay.

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
3. **Syncthing journal transport** — cada device escreve só seu journal;
4. **relay/WAN** — Tailscale/WireGuard primeiro; relay mínimo que só armazena e
   encaminha mudanças cifradas;
5. **P2P nativo** — Iroh, Hypercore/Hyperswarm, libp2p, p2panda ou feeds
   estilo Scuttlebutt, somente depois de avaliar maturidade, licença e suporte
   a Python/Rust.

BitTorrent/torrent é adequado para blobs imutáveis e snapshots de bootstrap,
não para estado relacional mutável. O problema difícil de WAN P2P é NAT
traversal, não o log.

## 8. Syncthing

- Rodar como processo externo; não vendorizar (MPL-2.0 vs 0BSD).
- Cada dispositivo escreve apenas seu próprio journal; assim o Syncthing não
  vê conflito de arquivo.
- Blobs imutáveis por SHA-256 podem ser sincronizados.
- `.stignore` deve excluir banco, WAL, segredos e arquivos temporários.
- REST API para status/pareamento no GTK; versionamento de arquivos como
  segurança.
- LGPD: journal e blobs contêm dados de clientes; criptografia de disco e
  retenção continuam necessárias.

Syncthing é um atalho de transporte para o início, não substitui assinatura,
version vector, autorização nem resolução de conflito.

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
- Tratar Syncthing como transporte de journal/blobs, não como banco.
- Registrar Rust como direção de núcleo/protocolo e manter o contrato
  language-neutral.

## 11. Decisões pendentes

1. Qual autoridade por entidade em cada modo?
2. Financeiro/estoque aceitam escrita offline? Com qual reconciliação?
3. Número provisório pode ser permanente no mesh? Quem atribui o canônico?
4. E2E: servidor vê conteúdo ou não?
5. Mobile: PWA ou app nativo?
6. Syncthing só para journal/blobs ou nem isso?
7. Qual o escopo inicial: local + servidor, ou LAN também?
8. Quando o Rust entra: núcleo, protocolo, CLI ou módulo? Qual o contrato de
   conformidade?

## 12. Ordem prática

1. change recorder + triggers + device ID + version vectors;
2. transporte hub (HTTP) e aplicação idempotente;
3. autoridade por entidade;
4. LAN/mDNS + pareamento assinado;
5. Syncthing journal transport;
6. relay/WAN;
7. avaliar P2P nativo e Rust com contrato/testes.

## 13. Referências

- [`PLANO_MODO_LOCAL_SYNC.md`](PLANO_MODO_LOCAL_SYNC.md)
- [`VISAO_MULTICLIENTE_LOCAL_FIRST.md`](VISAO_MULTICLIENTE_LOCAL_FIRST.md)
- Ink & Switch — Local-first software
- CRDT.tech
- Syncthing — Understanding Synchronization
- SQLite — SQLite Over a Network
- p2panda — <https://github.com/p2panda/p2panda> (avaliar, não adotar agora)
