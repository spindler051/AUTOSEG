# Plano de evolução arquitetural — AUTOSEG

**Status:** planejamento, sem mudanças de código nesta etapa.  
**Base:** branch `feature/gtk4-libadwaita`, versão `9.6.0-dev.4` (REV10).  
**Objetivo:** documentar melhorias futuras para reduzir acoplamento, permitir
deploy em servidor/container e manter o desktop nativo, sem copiar a
complexidade do Immich.

---

## Resumo executivo

- Adotar **monolito modular**, não microserviços.
- Congelar `app.py` (Tkinter) e evoluir apenas o GTK/backend.
- Separar UI, casos de uso, repositórios e infraestrutura.
- Centralizar configuração, caminhos e portas.
- Criar migrações versionadas antes de pensar em Postgres.
- Manter SQLite local com um único escritor; nunca em SSHFS/SMB/NFS.
- Containerizar somente o servidor; desktop continua nativo/AppImage.
- Criar API HTTP apenas quando o GTK precisar acessar dados remotos ao vivo.
- Fila SQLite/worker antes de Redis; Postgres/Redis só com gatilho real.
- Primeiro backlog: config, migrações, repositórios, split do GTK e pytest.

---

## 1. Princípios

1. **Monolito primeiro, modular depois.** O sistema ainda é pequeno; não
   começar com microserviços, Kubernetes ou vários bancos. O Immich separa
   serviços porque processa mídia em escala; o AUTOSEG faz CRUD, PDFs e
   e-mails. O custo de microserviços não se justifica agora.
2. **Monolito modular.** Separar por domínio e por camada dentro do mesmo
   processo, com fronteiras explícitas. Um módulo deve poder virar serviço
   depois, se necessário.
3. **Strangler Fig.** O `app.py` Tkinter não será reescrito de uma vez. O GTK é
   o novo frontend; novas funções entram nele. O Tkinter fica congelado até
   paridade e testes, e depois é removido.
4. **SQLite é arquivo local, não servidor.** Não apontar para SSHFS, SMB ou NFS
   com escrita concorrente (ver referência oficial no fim). Um único processo
   escreve; leitores remotos usam API ou snapshot.
5. **Doze fatores onde fizer sentido.** Configuração em ambiente, logs como
   evento, processos descartáveis, build/release/run separados.
6. **Cada etapa é reversível.** Backup antes de migração; feature atrás de
   flag/entrada separada; testes antes de remover o legado.
7. **Não criar abstração sem dor real.** Repositório, fila e API só quando
   houver um ponto de extensão concreto.

---

## 2. Inventário atual

Contagens aproximadas (`wc -l`, outubro/novembro de 2026):

| Área | Arquivo | Linhas | Papel atual |
|---|---|---:|---|
| Desktop legado | `app.py` | 4.245 | Tkinter + regras + consultas SQL + PDF + portais |
| Desktop GTK | `gtk_app.py` | 1.965 | janela, páginas, SQL, portais, túneis, arquivos |
| Diálogos GTK | `gtk_dialogos.py` | 1.414 | cliente, OS, material, prestador, serviço, estoque |
| Widgets GTK | `gtk_comum.py` | 458 | tabelas, cartões, formulários, diálogos |
| Domínio PJ/PF | `cadastros_v9.py` | 863 | clientes, usuários, organizações, chamados, validação |
| Prestadores/arquivos | `prestadores_ext.py` | 616 | schema, senha, anexos, PDF, e-mail, configuração |
| Portal prestador | `portal_prestador.py` | 1.152 | HTTP + HTML + rotas + regras |
| Portal cliente legado | `portal_cliente_v94.py` | 571 | HTTP + HTML |
| Portal V9 | `portal_v9.py` | 407 | HTTP + HTML + chamados |
| Servidor do cliente | `servidor_web.py` | 490 | HTTP + HTML + arquivos |
| Casos de uso web | `portal_negocios.py` | 296 | clientes, OS e financeiro |
| Fluxo OS | `fluxo_os.py` | 253 | encerramento, PDF, credenciais |
| Estoque | `estoque_materiais.py` | 241 | schema, saldo e movimentos |
| Catálogo | `catalogo_servicos.py` | 192 | preços e orçamento |
| Frontend web | `web/styles.css` | 1.073 | estilo |
| Frontend web | `web/app.js` | 538 | comportamento |
| Bootstrap | `banco.py` | 220 | conexão e schema base |
| Testes | `test_*.py` | 33 arquivos | scripts de cenário, sem pytest |

Já existem bons sinais de modularidade:

- `portal_negocios.py` concentra casos de uso web;
- `fluxo_os.py` separa encerramento/PDF;
- `cadastros_v9.py` centraliza CPF/CNPJ, organizações e chamados;
- `servidor_backend.py` permite rodar os portais sem GUI;
- `AUTOSEG_BASE` e `GESTAO_BANCO` já separam dados de código;
- o GTK compartilha o mesmo backend, sem fork.

---

## 3. Blocos monolíticos e acoplamentos

### 3.1 `app.py` — Tkinter monolítico

**Sintoma:** 4.245 linhas, mistura UI, SQL direto, PDF, portais, túneis,
threads, arquivos e mensagens.

**Risco:** qualquer mudança de regra exige tocar duas interfaces; o Tkinter
continua divergindo do GTK.

**Direção:** congelar novas funcionalidades; corrigir apenas bugs críticos.
Remover quando o GTK tiver paridade e testes de aceitação. Não portar tela por
tela para depois portar de novo.

### 3.2 `gtk_app.py` e `gtk_dialogos.py` — UI grande

**Sintoma:** a janela conhece SQL, regras, portais, túneis e arquivos; todos os
diálogos ficam num arquivo só.

**Risco:** UI difícil de testar; banco muda e quebra tela; diálogo de cliente e
de estoque compartilham importações e helpers.

**Direção:** separar em fatias verticais:

```text
interfaces/gtk/
  janela.py
  paginas/clientes.py
  paginas/ordens.py
  paginas/financeiro.py
  paginas/estoque.py
  dialogos/cliente.py
  dialogos/os.py
  dialogos/prestador.py
  widgets.py
```

A UI chama serviços/casos de uso; não executa SQL.

### 3.3 `cadastros_v9.py` e `prestadores_ext.py` — domínio + infraestrutura

**Sintoma:** `cadastros_v9.py` mistura validação de documento, pessoas,
organizações, chamados, notificações, histórico e formatação. `prestadores_ext.py`
mistura schema, hash de senha, sessão, eventos, anexos, PDF, e-mail, rascunho
fiscal e configuração.

**Risco:** qualquer teste de CPF carrega dependências de PDF/armazenamento;
migrar para servidor fica difícil.

**Direção:** separar sem criar framework:

```text
dominio/documentos.py        CPF/CNPJ, normalização, duplicidade
dominio/pessoas.py           usuários, clientes PF
dominio/organizacoes.py      PJ, vínculos
dominio/chamados.py          análise, confirmação, notificações
infra/seguranca.py           hash, sessão, tokens
infra/arquivos.py            anexos e validação de imagem
infra/pdf.py                 geração e publicação
infra/email.py               rascunho e envio
infra/config_prestador.py    dados bancários/e-mail
```

### 3.4 Schema espalhado

**Sintoma:** `CREATE TABLE`/`ALTER TABLE` aparecem em `cadastros_v9.py` (24),
`prestadores_ext.py` (20), `produtividade_os.py` (8), `banco.py` (8),
`fluxo_os.py` (5), `estoque_materiais.py` (5), além de outros módulos.

**Risco:** não há versão de schema, ordem de migração nem rollback. Um banco
antigo pode falhar de forma diferente de um novo.

**Direção:** runner de migrações com tabela `schema_version` e arquivos
numerados. O `CREATE TABLE IF NOT EXISTS` atual vira baseline; migrações novas
são explícitas e idempotentes. Sempre backup `.backup` antes.

### 3.5 Dois servidores HTTP e templates no Python

**Sintoma:** `servidor_web.py`, `portal_prestador.py`, `portal_cliente_v94.py`
e `portal_v9.py` repetem sessão, cookies, CSRF, HTML, formulários e rotas.

**Risco:** correções de segurança precisam ser feitas em quatro lugares;
comportamento divergente entre portais; difícil testar.

**Direção:** um pacote `interfaces/web/` com:

- um servidor HTTP (ou ASGI) e um roteador;
- autenticação/sessão/CSRF compartilhados;
- templates fora do Python;
- um módulo de arquivos estáticos;
- rotas por domínio (`clientes`, `ordens`, `financeiro`, `pj`).

Não é necessário migrar tudo de uma vez: começar por uma rota ou pelo portal
administrativo.

### 3.6 SQL direto na UI

**Sintoma:** `gtk_app.py` tem 19 chamadas de banco; `gtk_dialogos.py` tem 9;
`app.py` tem 30. Consultas e regras aparecem na tela.

**Risco:** mudar o schema quebra a UI; não há como trocar SQLite por API/Postgres
sem tocar em todas as telas.

**Direção:** repositórios por agregado:

```text
repositorios/clientes.py
repositorios/ordens.py
repositorios/financeiro.py
repositorios/catalogo.py
repositorios/estoque.py
repositorios/pj.py
```

A interface pode começar simples (`listar`, `obter`, `salvar`, `buscar`), sem
ORM e sem abstração genérica. `conectar_banco()` e `ext.db()` continuam como
infraestrutura até a migração terminar.

### 3.7 Configuração e caminhos

**Sintoma:** `AUTOSEG_BASE`, `GESTAO_BANCO`, portas, binds, `PRESTADOR_HTTPS`,
`GMAIL`, `AUTOSEG_DEV` e caminhos são lidos em vários módulos, com defaults
diferentes (`8765/8766` vs `8865/8866`).

**Risco:** container, AppImage, macOS e Linux divergem; erro de porta em
produção.

**Direção:** um `core/config.py` com um objeto `Settings` imutável, validação de
tipos e defaults documentados. Variáveis continuam em ambiente; nada de
segredo no repositório.

### 3.8 Trabalho em segundo plano

**Sintoma:** PDF, e-mail, túneis e eventos usam `threading.Thread` e `after`
espalhados; sem fila persistente, retry ou idempotência.

**Risco:** fechar o app perde tarefa; duas execuções geram PDF duplicado; não
escala para worker.

**Direção:** começar com uma fila SQLite (`jobs`) e um executor local; depois
extrair um worker. Só usar Redis/BullMQ/RQ se houver múltiplos workers,
retentativas e volume. Jobs atuais: publicar PDF, e-mail, importação, backup,
limpeza.

### 3.9 Arquivos e armazenamento

**Sintoma:** PDFs, anexos, rascunhos e banco vivem no mesmo diretório local;
não há interface de storage.

**Risco:** container sem volume perde dados; múltiplas máquinas não
compartilham; backup manual.

**Direção:** `Storage` local agora, S3/MinIO depois. Caminhos relativos ao
`AUTOSEG_BASE`, nunca ao código instalado. Nunca usar SQLite no storage
compartilhado.

### 3.10 Testes e CI

**Sintoma:** 33 scripts, muitos monolíticos, sem pytest padronizado; alguns
sobem portas fixas e disputam recursos.

**Risco:** refatorar sem rede de segurança; regressões em CPF/CNPJ, PDF,
portal e migrations.

**Direção:** pasta `tests/`, fixtures de banco temporário, pytest, HTTP client,
testes de GUI via cage/Xvfb quando necessário. CI sem banco de produção.

---

## 4. Arquitetura-alvo (monolito modular)

```text
autoseg/
  core/
    config.py
    db.py
    migrations.py
    logging.py
    security.py
    validation.py
  dominio/
    clientes/
    ordens/
    financeiro/
    catalogo/
    estoque/
    pj/
    prestadores/
  infraestrutura/
    sqlite/
    arquivos/
    pdf/
    email/
    jobs/
    api_remota/
  interfaces/
    gtk/
    web/
    cli/
  migrations/
  tests/
```

Regras:

- `dominio` não importa GTK, HTTP, SQLite ou `os.environ`.
- `infraestrutura` implementa interfaces do domínio.
- `interfaces` apenas traduz entrada/saída.
- `core` é pequeno: configuração, banco, migração, logs, validação.
- Um módulo pode começar dentro de outro e ser extraído quando estabilizar.
- Não usar “camadas” vazias: cada pasta precisa de um caso de uso real.

### Fronteiras que já existem

Bons pontos de corte:

- `banco.BANCO` / `conectar_banco()` / `ext.db()`;
- `AUTOSEG_BASE` / `GESTAO_BANCO`;
- `ServidorPortal` / `PortalPrestador`;
- `fluxo.publicar_relatorio()`;
- `ext.registrar_imagem_transacao()`;
- `cadastros_v9` (CPF/CNPJ e PJ);
- `portal_negocios` (casos de uso web);
- `servidor_backend.py` (processo sem GUI).

---

## 5. Deploy: do Mac bare metal ao servidor

### Fase 0 — atual

- Mac bare metal, venv, SQLite, dois portais, túneis de teste.
- Linux: GTK nativo + snapshot/portais remotos.
- Bom para desenvolvimento; não é reproduzível nem isolado.

### Fase 1 — reprodutível

- versões exatas de dependências (`requirements.lock` ou equivalente);
- `.env.example` com todas as variáveis;
- `AUTOSEG_BASE` e `GESTAO_BANCO` explícitos;
- migrações + backup automático antes de atualizar;
- testes e CI.

**Aceite:** uma máquina nova sobe o backend com um comando documentado, sem
copiar arquivos manualmente.

### Fase 2 — backend em container

Separar **desktop** de **servidor**:

- **desktop:** macOS/Windows/Linux nativo, AppImage; não containerizar GTK;
- **servidor:** portais + backend agora; API e worker nas fases 3 e 4.

Preferência:

- **Podman rootless** em Linux/VPS (ou Docker Compose compatível);
- imagem Python 3.13 slim;
- usuário não-root;
- volume persistente para `dados.db`, anexos, PDFs e logs;
- `127.0.0.1` por padrão; proxy reverso para TLS;
- healthcheck;
- limites de CPU/memória;
- backup e restore testados.

**Alpine:** pode ser usado, mas validar `reportlab`, Pillow, wheels e fontes.
Se houver atrito, usar Debian slim; o ganho de alguns MB não paga uma imagem
quebrada. O backend não precisa de GTK/PyGObject.

**Aceite:** `podman compose up` (ou `docker compose up`) sobe os portais e o
volume; derrubar e recriar o container preserva dados.

### Fase 3 — API para desktop remoto

Hoje o GTK abre SQLite local. Para usar o banco do Mac ao vivo, não montar o
SQLite por rede: criar API HTTP.

- `api` com FastAPI (ou Flask/Starlette) e OpenAPI;
- DTOs/Pydantic;
- endpoints de leitura primeiro: clientes, OS, financeiro, catálogo, estoque;
- depois escrita;
- SSE ou polling para eventos dos portais;
- autenticação por token/sessão;
- `AUTOSEG_API_URL` no cliente GTK;
- adaptador local (SQLite) e remoto (HTTP) atrás da mesma interface.

**Quando migrar para Postgres?** Só quando houver mais de um escritor, várias
instâncias do servidor, clientes remotos concorrentes ou necessidade real de
operação multi-máquina. Para um único servidor com volume local, SQLite em WAL
continua suficiente.

### Fase 4 — fila/worker

- interface `JobQueue` + tabela SQLite `jobs`;
- worker separado (`worker.py`) para PDF, e-mail, importações e backup;
- retries/idempotência;
- Redis/BullMQ/RQ só se houver vários workers ou volume que justifique.

### Fase 5 — storage e observabilidade

- storage local → S3/MinIO se houver múltiplos servidores ou volume grande;
- logs estruturados com request ID;
- `/healthz`, `/readyz`, métricas;
- alerta de disco/backup;
- retenção de logs.

---

## 6. Immich: o que copiar e o que não copiar

| Ideia do Immich | Aplicar agora? | Observação |
|---|---|---|
| Cliente/servidor via REST | Depois | necessário para GTK remoto, não para o desktop local |
| Controllers/services/repositories | Sim, de forma leve | separar UI, caso de uso e SQL |
| OpenAPI/DTOs | Depois | junto com a API |
| Fila de jobs (Redis/BullMQ) | Depois | começar com fila SQLite/worker |
| Postgres | Depois, se necessário | SQLite single-writer atende o volume atual |
| Redis | Não | sem necessidade de fila distribuída agora |
| Serviço de ML separado | Não | não há ML no AUTOSEG |
| Microserviços/Kubernetes | Não | monolito modular primeiro |
| Containers para servidor | Sim, fase 2 | desktop continua nativo |
| Reverse proxy/TLS | Sim, antes de publicar | Caddy/Traefik/Nginx + Cloudflare Access |

O Immich acerta ao separar responsabilidades e ao ter jobs/observabilidade. O
erro para o AUTOSEG seria copiar a infraestrutura de mídia sem ter o problema
de mídia.

---

## 7. Segurança e operação

- Segredos somente em ambiente/`podman secret`; nunca no Git.
- Portal público somente atrás de TLS e proxy; Cloudflare Access para equipe.
- Banco e portais em `127.0.0.1`; acesso remoto por túnel SSH ou VPN.
- Cookies `Secure`, `HttpOnly`, `SameSite`; CSRF onde houver formulário.
- Rate limit e logs de autenticação.
- Backup diário com `sqlite3 .backup`, cópia offsite e teste de restore.
- Permissões `600` para banco e backups; quarentena separada.
- Separação produção/teste já documentada em `docs/BANCO_TESTE_PRODUCAO.md`.
- Dados pessoais: LGPD, retenção, acesso mínimo, auditoria.
- Não usar Cloudflare Quick Tunnel com dados reais.

---

## 8. Backlog sugerido (uma peça por vez)

### P0 — preparar o terreno

| # | Entrega | Aceite |
|---|---|---|
| 1 | Congelar `app.py` para novas features | novo código só no GTK/backend |
| 2 | `core/config.py` | nenhuma leitura de env espalhada nas novas telas |
| 3 | Runner de migrações + baseline | banco novo e antigo convergem; backup antes |
| 4 | Repositórios de clientes/OS | UI sem SQL nessas telas |
| 5 | Dividir `gtk_app.py`/`gtk_dialogos.py` por feature | imports claros; testes de GUI |
| 6 | Dividir `cadastros_v9`/`prestadores_ext` | domínio testável sem PDF/GTK |
| 7 | pytest + fixtures de banco temporário | CI verde, sem portas fixas |
| 8 | Dockerfile/Compose do backend | volume preserva dados; healthcheck |

### P1 — servidor e API

| # | Entrega | Aceite |
|---|---|---|
| 9 | Unificar servidores/templates web | uma sessão/CSRF; uma base de rotas |
| 10 | API read-only + `AUTOSEG_API_URL` | GTK lê dados remotos sem SQLite de rede |
| 11 | Fila SQLite + worker de PDF/e-mail | tarefa sobrevive a restart; idempotente |
| 12 | Logs estruturados + `/healthz` | operação básica observável |

### P2 — produção

| # | Entrega | Aceite |
|---|---|---|
| 13 | Deploy em VPS/VM com Podman rootless | sobe, reinicia, backup/restore |
| 14 | Proxy TLS + Cloudflare Access | portais não expostos diretamente |
| 15 | Postgres (somente se necessário) | repositórios trocados sem UI |
| 16 | Storage S3/MinIO (se necessário) | anexos/PDF fora do container |
| 17 | CI de AppImage/macOS | artefato reproduzível |

### Não fazer agora

- microserviços, Kubernetes, service mesh;
- Redis/BullMQ sem worker concorrente;
- Postgres por moda;
- S3 sem volume que justifique;
- OAuth/SSO multi-tenant antes da API;
- SQLite em SSHFS/SMB/NFS;
- reescrever o backend em Node/TypeScript só porque o Immich usa.

---

## 9. ADRs sugeridos (próximos documentos)

- **ADR-001:** adotar monolito modular; microsserviços somente com gatilho
  operacional.
- **ADR-002:** SQLite single-writer até existir API/multi-escritor; proibir
  SQLite em filesystem de rede.
- **ADR-003:** desktop nativo (macOS/AppImage); servidor em container.
- **ADR-004:** jobs atrás de interface; SQLite primeiro, Redis depois.
- **ADR-005:** API HTTP antes de qualquer cliente GTK remoto.

---

## 10. Referências

- Immich — arquitetura: <https://docs.immich.app/developer/architecture/>
- Immich — jobs e workers: <https://docs.immich.app/administration/jobs-workers/>
- Martin Fowler — Monolith First:
  <https://martinfowler.com/bliki/MonolithFirst.html>
- Martin Fowler — Strangler Fig:
  <https://martinfowler.com/bliki/StranglerFigApplication.html>
- The Twelve-Factor App: <https://12factor.net/>
- SQLite over a network:
  <https://www.sqlite.org/useovernet.html>
- Podman (rootless/containers): <https://docs.podman.io/en/latest/>
