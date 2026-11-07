# Plano: modo local, offline-first e sincronização

**Status:** planejamento, sem implementação.  
**Objetivo:** permitir que cada PC/Mac/telefone crie e edite ordens de serviço
totalmente offline, sincronize na mesma rede local quando possível e envie as
mudanças para o servidor quando ele voltar.

> **Visão geral multicliente:** `docs/planning/VISAO_MULTICLIENTE_LOCAL_FIRST.md`.
> Este documento detalha o sync; a visão descreve os modos de operação, os
> clientes, os custos e os limites do produto.

---

## 1. Resumo executivo

A recomendação é **não sincronizar o arquivo `dados.db`** com Syncthing,
Dropbox, torrent ou similar. SQLite é um arquivo local com locking/WAL; copiar
o arquivo enquanto ele está aberto pode corromper o banco. Syncthing também
resolve conflitos de arquivo criando cópias `.sync-conflict`, não fazendo merge
de linhas.

O caminho recomendado é:

1. **Cada dispositivo tem seu próprio SQLite local.**
2. Toda escrita entra primeiro no banco local + um **log de mudanças**.
3. Um motor de sincronização troca **mudanças de registro** (não o arquivo).
4. O servidor é mais um participante/autoridade, não o único lugar onde dá
   para trabalhar.
5. Sincronização LAN direta primeiro; P2P/WAN por último.
6. Anexos e PDFs podem usar armazenamento por hash (e até Syncthing para
   blobs imutáveis), mas o banco relacional não.
7. Finanças, estoque e numeração de OS têm regras próprias; não usar
   “last write wins” cego.

A ordem de maturidade:

```text
offline local → sync com servidor → sync LAN entre dispositivos → P2P/WAN
```

Não começar pelo último.

---

## 2. O que “local-first” significa aqui

- O app abre e trabalha **sem internet e sem servidor**.
- Criar cliente, OS, material, foto e relatório funciona localmente.
- A sincronização é assíncrona e pode falhar; o trabalho não pode ser perdido.
- Cada dispositivo tem uma cópia local consistente.
- O sistema é **eventualmente consistente**, não fortemente consistente.
- Conflitos precisam ser detectados, registrados e resolvidos; alguns exigem
  decisão humana.

Não é:

- um banco distribuído com transações globais;
- dois processos escrevendo no mesmo arquivo SQLite pela rede;
- garantia de que todos veem a mesma OS no mesmo instante;
- autorização para editar o mesmo campo em dois dispositivos e achar que o
  sistema escolhe sozinho o “certo”.

---

## 3. Por que não sincronizar o SQLite como arquivo

Syncthing divide arquivos em blocos, compara hashes e propaga blocos. Quando o
mesmo arquivo muda em dois dispositivos, ele cria uma cópia de conflito; não
entende tabelas, linhas, chaves estrangeiras ou transações.

Problemas com `dados.db` compartilhado:

- WAL e arquivos `-shm`/`-wal` precisam ser consistentes juntos;
- locks de SQLite não funcionam de forma confiável em SSHFS/SMB/NFS;
- uma cópia de arquivo pode pegar o banco no meio de uma transação;
- duas cópias abertas podem sobrescrever mudanças uma da outra;
- o conflito vira “arquivo 1” e “arquivo 2”, não uma linha para revisar;
- anexos e PDFs podem ser sincronizados por arquivo, mas o banco não.

Syncthing pode ser usado para uma pasta de **blobs imutáveis** (fotos e PDFs
já publicados), com nomes por SHA-256. Nunca para o SQLite ativo.

---

## 4. Opções de arquitetura

| Opção | Offline | Complexidade | Recomendação |
|---|---:|---:|---|
| A. Só local, um dispositivo | sim | baixa | já é o modo atual |
| B. Local + sync com servidor | sim | média | **primeiro alvo** |
| C. Local + sync LAN direta + servidor | sim | alta | depois de B |
| D. P2P/WAN + relay + E2E | sim | muito alta | último |
| E. Syncthing no `dados.db` | não seguro | baixa | **não fazer** |

### A. Só local

Cada instalação tem seu banco. Funciona hoje, mas não compartilha nada.

### B. Hub-and-spoke offline-first (recomendado)

```text
PC/Mac/Telefone
  SQLite local + outbox
        │  HTTPS (quando houver rede)
        ▼
Servidor AUTOSEG
  SQLite/Postgres + inbox + autoridade
```

- O dispositivo sempre escreve local.
- O servidor recebe mudanças em lote e devolve as mudanças dos outros.
- O servidor pode ser autoridade para numeração, financeiro e estoque.
- Funciona com um servidor em VPS/VM ou no Mac.

### C. LAN peer-to-peer + servidor

```text
Dispositivo A  ◀── mDNS/HTTPS LAN ──▶  Dispositivo B
       │                                   │
       └──────── quando possível ──────────┘
                       │
                    Servidor
```

- Descoberta por mDNS (`_autoseg._tcp`) ou IP manual.
- Pareamento por QR/código; cada dispositivo tem chave.
- Troca o mesmo protocolo de mudanças do servidor.
- O servidor continua sendo autoridade para dados sensíveis.
- Se a LAN cair, cada um segue local.

### D. P2P/WAN

- Tailscale/WireGuard para rede privada; ou libp2p/iroh para NAT traversal.
- Relay quando não há conexão direta.
- Criptografia ponta a ponta.
- É a fase mais cara; só faz sentido depois de B/C estabilizados.

“Torrent” não é o modelo certo para banco mutável. BitTorrent distribui blobs
imutáveis. Para banco, usar log de mudanças; para anexos, content-addressed
blobs.

---

## 5. Modelo de dados para sincronização

Toda entidade sincronizável precisa de:

- `id` estável: UUIDv7/ULID, não autoincremento local;
- `device_id`/`origin_device`;
- `created_at`, `updated_at` (UTC);
- `deleted_at` (tombstone, não apagar fisicamente antes de todos verem);
- `version` ou `base_version`;
- `change_id` no log.

### Log de mudanças

```text
sync_changes
  change_id       UUID/ULID (único global)
  device_id       dispositivo que originou
  actor_id        usuário/dispositivo
  entity          clientes | ordens | financeiro | estoque | anexo ...
  entity_id       UUID do registro
  operation       create | update | delete | transition
  payload         JSON canônico
  base_version    versão conhecida (para detectar conflito)
  hlc             hybrid logical clock
  schema_version  versão do schema
  hash            integridade
  created_at
```

### Estado de sync

```text
sync_peers        id, tipo (server/lan), chave pública, último cursor
sync_cursor       último change_id aplicado por peer
sync_outbox       mudanças ainda não confirmadas
sync_inbox        mudanças recebidas/duplicadas
sync_conflicts    conflitos pendentes de revisão
sync_devices      dispositivo, nome, chave, revogado_em
```

### Anexos

```text
attachments
  sha256, tamanho, mime, nome_original, caminho_local
```

- Upload/download por hash.
- Imutável depois de publicado.
- PDF publicado é uma versão imutável; nunca sobrescrever.
- Syncthing pode sincronizar a pasta de blobs, se desejado, mas o banco não.

### IDs de OS

O `proximo_numero_os` atual usa `MAX+1`; isso não é seguro offline.

Plano:

- toda OS tem UUID;
- número humano provisório local: `OS-<device>-<sequência>`;
- ao sincronizar, o servidor atribui o número canônico `261107001`;
- a interface mostra “provisório” até o servidor confirmar;
- nunca reutilizar número;
- PDF de OS provisória, se emitido, carrega o UUID e o número provisório.

---

## 6. Conflitos por domínio

Não existe uma regra única. O sistema precisa de políticas explícitas.

| Dados | Política inicial |
|---|---|
| Eventos/auditoria | append-only; mesclar por `change_id` |
| Cliente (campos) | last-write-wins por campo com HLC + revisão de duplicidade |
| CPF/CNPJ duplicado | bloquear merge automático; mostrar os dois cadastros |
| OS (descrição/contato) | LWW por campo; histórico de alterações preservado |
| Status da OS | máquina de estados; transição conflitante vira conflito manual |
| Materiais | ledger append-only; não sobrescrever quantidade |
| Estoque | movimentos append-only; saldo derivado; revisão manual se divergir |
| Financeiro | append-only para pagamentos; servidor autoritativo; sem LWW |
| Fotos/PDFs | imutáveis por hash; versão nova, nunca editar o antigo |
| Exclusão | tombstone; retenção até todos os peers confirmarem |

O servidor pode ser autoridade para:

- numeração canônica de OS;
- fechamento financeiro;
- saldo de estoque consolidado;
- cadastros duplicados;
- permissões e dispositivos.

Dispositivos offline podem criar dados provisórios, mas não podem “ganhar” um
conflito financeiro ou de estoque só por terem sincronizado primeiro.

---

## 7. Protocolo de sincronização

Começar simples, com HTTP/HTTPS e JSON canônico:

```text
POST /sync/push
  {device_id, changes:[...], cursor}
POST /sync/pull
  {device_id, since_cursor}
POST /sync/ack
GET  /sync/status
```

Regras:

- cada mudança tem `change_id` idempotente;
- push repetido não duplica;
- pull retorna mudanças em ordem determinística;
- servidor devolve cursor;
- conflito é registrado, não silenciado;
- cliente tenta de novo com backoff;
- anexos usam upload resumível por hash;
- não enviar o banco inteiro.

LAN:

- mDNS/DNS-SD para descobrir `_autoseg._tcp`;
- pareamento por QR/código;
- TLS mútuo ou payload assinado com chave do dispositivo;
- mesma API de push/pull, apontando para o peer;
- se o peer não responder, tentar servidor; se nada, ficar local.

WAN/P2P:

- Tailscale/WireGuard primeiro (simples e seguro);
- relay/libp2p/iroh só se realmente precisar de NAT traversal;
- criptografia E2E opcional; decidir o trade-off: servidor não vê conteúdo,
  mas também não resolve conflito de conteúdo.

---

## 8. Segurança

### Dispositivos

- Cada dispositivo gera par de chaves (Ed25519).
- Servidor registra a chave pública no pareamento.
- Revogação de dispositivo invalida a chave.
- QR/código de pareamento expira.
- Não confiar apenas na rede local; LAN não é automaticamente confiável.

### Transporte

- TLS obrigatório no servidor.
- LAN direta com TLS mútuo ou mensagens assinadas.
- Replay protection: nonce/timestamp + `change_id`.
- Rate limit e auditoria de sync.

### Dados em repouso

- SQLCipher ou criptografia de disco do sistema.
- Chaves no Keychain (macOS), libsecret (Linux), Keystore (Android).
- Backup criptografado.
- Perda/roubo: revogar dispositivo, rotacionar chave de grupo, apagar dados
  locais se possível.

### Privacidade

- Dados de clientes são pessoais (LGPD): acesso mínimo, retenção, auditoria.
- Sync por P2P não significa público; cada peer precisa estar autorizado.
- Nunca usar DHT/torrent público para dados reais.

---

## 9. Telefones

O frontend desktop atual é GTK4; ele não roda em Android/iOS.

Opções, em ordem:

1. **PWA local-first** (recomendado para começar):
   - IndexedDB/OPFS ou SQLite WASM;
   - mesma API de sync;
   - funciona em Android/iOS com limitações de background;
   - uma base web separada, sem fork do backend.
2. **App nativo Flutter/React Native**:
   - melhor integração e background;
   - mais custo de manutenção e nova stack;
   - só depois do protocolo estabilizar.
3. **Portal web online**:
   - não é offline; serve como fallback imediato enquanto não há app local.

O protocolo de sync deve ser compartilhado entre desktop, PWA e servidor,
idealmente com uma especificação formal e testes de compatibilidade.

---

## 10. Fases de implementação

### Fase 0 — preparar o modelo (sem sync ainda)

- UUIDs/ULIDs nas entidades;
- `change_log`, tombstones, `updated_at` UTC;
- HLC ou contador lógico;
- migrations versionadas;
- testes de schema.

**Aceite:** o banco atual pode ser migrado sem perda; toda escrita nova gera
mudança registrada.

### Fase 1 — modo local completo

- criar/editar OS, clientes, materiais e fotos offline;
- numeração provisória;
- backup local;
- exportar/importar snapshot assinado (opcional).

**Aceite:** desligar a rede não impede o fluxo principal; reiniciar não perde
dados.

### Fase 2 — sync com servidor (hub-and-spoke)

- API push/pull/ack;
- autenticação de dispositivo;
- outbox/inbox;
- resolução de conflito inicial;
- servidor autoritativo para número/financeiro/estoque.

**Aceite:** dois dispositivos offline criam OS; ao voltar, ambas aparecem no
servidor e nos dois dispositivos; conflitos ficam visíveis.

### Fase 3 — LAN peer sync

- mDNS + pareamento;
- troca direta de changesets;
- fallback para servidor;
- Syncthing opcional só para blobs.

**Aceite:** dois PCs na mesma LAN sincronizam sem internet; servidor ausente
não bloqueia.

### Fase 4 — WAN/P2P

- Tailscale/WireGuard;
- relay;
- E2E;
- revogação/rotação de chave.

**Aceite:** dispositivo fora da LAN sincroniza com autorização e criptografia.

### Fase 5 — mobile/PWA

- cliente local-first em telefone;
- mesma especificação de sync;
- limites de background documentados.

### Fase 6 — conflitos e operação

- tela de conflitos;
- comparação campo a campo;
- trilha de auditoria;
- métricas de sync;
- backup/restore testados.

---

## 11. Testes necessários

- 2–5 dispositivos simulados, cada um com SQLite temporário;
- offline por horas/dias;
- relógios dessincronizados;
- push duplicado e fora de ordem;
- crash no meio do push/pull;
- arquivo grande/anexo interrompido;
- dispositivo revogado;
- conflito de status de OS;
- conflito de pagamento/estoque;
- migração de schema antigo;
- restauração de backup.

Sem esses testes, “sincronizou” não é garantia de nada.

---

## 12. Riscos e decisões pendentes

Riscos altos:

- complexidade de sistema distribuído;
- conflitos de negócio (status, dinheiro, estoque);
- numeração de OS offline;
- segurança de dispositivos e chaves;
- background limitado em iOS;
- duplicação de clientes/CPF;
- expectativa de “tempo real” quando o modelo é eventual.

Decisões que precisam ser tomadas antes de código:

1. O servidor é **autoridade** ou apenas mais um peer?
2. Financeiro/estoque aceitam escrita offline? Com qual revisão?
3. O número da OS pode ser provisório? Quem atribui o definitivo?
4. E2E: servidor vê conteúdo ou não?
5. Mobile: PWA ou app nativo?
6. Syncthing só para blobs ou nem isso?
7. Qual o escopo inicial: um PC + servidor, ou LAN também?

Recomendação: começar com **local + servidor**, servidor autoritativo para
dinheiro/estoque/numeração, e LAN/P2P depois.

---

## 13. Referências

- Ink & Switch — Local-first software:
  <https://www.inkandswitch.com/local-first/>
- CRDT.tech — Conflict-free Replicated Data Types: <https://crdt.tech/>
- Syncthing — Understanding Synchronization:
  <https://docs.syncthing.net/users/syncing.html>
- SQLite — SQLite Over a Network:
  <https://www.sqlite.org/useovernet.html>
- Martin Fowler — Strangler Fig:
  <https://martinfowler.com/bliki/StranglerFigApplication.html>
- The Twelve-Factor App: <https://12factor.net/>
