# GTK × servidor: separação e modos de conexão

**Status:** desenho de arquitetura e plano incremental. Não autoriza um
big-bang; cada fase deve preservar o comportamento atual e ser reversível.

**Objetivo:** permitir que o app GTK rode **totalmente local, sem servidor
web**; que ele possa **subir um servidor web quando o operador quiser**; e que
o mesmo GTK consiga ser cliente de um **servidor headless rodando em outro
Linux** (por exemplo, um celular com Nura/Alpine).

---

## 1. Situação atual

- `gtk_app.py` abre o banco SQLite local diretamente e chama módulos de domínio.
- No `__init__`, o GTK **inicia automaticamente** o `PortalPrestador` e o
  `ServidorPortal`, mesmo quando ninguém vai usar o navegador.
- O Portal do Cliente já tem botão “Ligar/Desligar servidor”; o Portal do
  Prestador ainda não tem esse controle.
- O banco é global (`banco.BANCO`), definido no import.
- Existe uma API JSON read-only de financeiro (`api_financeiro.py`,
  `/api/v1`) com bearer token, paginação, auditoria e OpenAPI. Ela é um bom
  precedente de contrato, mas cobre só leitura financeira.
- O gerenciador de túneis Cloudflare (`tuneis`/`links_publicos`) já é separado
  do domínio.

O acoplamento principal não é o HTTP em si; é o GTK conhecer **SQL, banco e
módulos de negócio diretamente**. Para rodar remoto, ele precisa falar com um
contrato estável, não com o SQLite do celular.

---

## 2. Modos de operação

| Modo | Onde fica o banco | Servidor web | Túnel | Uso |
|---|---|---|---|---|
| **Local-only** | Mac, SQLite local | nenhum | nenhum | GTK sozinho, offline |
| **Local + acesso web** | Mac, SQLite local | portal no Mac | opcional | GTK + navegador/telefone na mesma máquina |
| **Remoto** | celular/servidor Linux | portal no celular | gerenciado pelo servidor | GTK no Mac, dados no celular |
| **Remoto + cache local** | servidor + cache | portal no servidor | servidor | evolução futura, sync |

Nesta primeira etapa, **um modo usa um banco só**. Não tentar sincronizar o
banco local com o remoto; isso é a fase de sync/local-first, separada.

---

## 3. Arquitetura-alvo

```text
GTK   Qt   CLI   Web   iOS/Android
  \    |     |     |       /
       AppService (contrato de aplicação)
         /                     \
  LocalService              HttpService
  (in-process)              (HTTPS/JSON)
       |                         |
  SQLite local              Servidor headless
                                 |
                            SQLite remoto
```

### 3.1 Contrato `AppService`

O contrato deve ser **de casos de uso**, não de tabelas. Exemplo:

```python
class AppService(Protocol):
    def health(self) -> Health: ...
    def login(self, email: str, senha: str) -> Session: ...
    def listar_clientes(self, filtro: ClienteFiltro) -> Pagina[Cliente]: ...
    def obter_cliente(self, cliente_id: int) -> Cliente: ...
    def salvar_cliente(self, cliente_id: int | None, dados: ClienteInput) -> Cliente: ...
    def listar_os(self, filtro: OSFiltro) -> Pagina[OSResumo]: ...
    def obter_os(self, os_id: int) -> OSDetalhe: ...
    def salvar_os(self, os_id: int | None, dados: OSInput) -> OSDetalhe: ...
    # financeiro, catálogo, estoque, anexos, relatórios...
```

Regras:

- DTOs explícitos; nada de `sqlite3.Row` saindo do contrato.
- Dinheiro em centavos; datas ISO; IDs opacos para o cliente.
- Erros com código estável (`validacao`, `permissao`, `conflito`, `nao_encontrado`).
- Toda operação tem versão/`If-Match` quando há concorrência.
- O contrato não sabe se está local ou remoto.

### 3.2 `LocalService`

Implementação in-process que chama os módulos atuais (ou os novos serviços
extraídos). O GTK usa `LocalService` no modo local; **nenhuma porta HTTP é
aberta**.

### 3.3 `HttpService`

Cliente do servidor remoto. Mesmo contrato, transporte HTTPS/JSON. Guarda
token no Keychain, renova sessão, faz retry idempotente e trata offline.

### 3.4 Servidor headless

`servidor_backend.py` passa a ser um adaptador fino:

```text
HTTP /api/v1  →  AppService  →  domínio/repositórios  →  SQLite
```

O servidor não deve conter HTML de portal nem regra de negócio nova. Os
portais HTML atuais podem continuar como um adaptador separado, usando os
mesmos serviços.

---

## 4. Setup inteligente no GTK

Na primeira abertura (ou em Configurações → Conexão), mostrar três escolhas:

1. **Neste Mac — local**
   - Abre o SQLite local.
   - Não abre porta nenhuma.
   - Botão opcional: “Ativar acesso web neste Mac”.

2. **Este Mac — servidor**
   - Abre o SQLite local.
   - Sobe o Portal do Prestador (e opcionalmente o do Cliente).
   - Botão opcional: “Publicar com Cloudflare”.
   - Mostra URL local, URL de rede e URL pública.

3. **Conectar a um servidor**
   - Campo URL + login (ou QR code de pareamento).
   - Testa `/api/v1/health` e mostra versão/modo.
   - Guarda token no Keychain; não cria banco local.
   - Se cair, mostra offline e permite tentar de novo; sem fallback silencioso
     para o banco local.

Configuração sugerida:

```json
{
  "mode": "local",
  "server_url": "",
  "web_access": false,
  "tunnel": false,
  "last_user": "..."
}
```

Arquivo: `~/.config/autoseg/connection.json` (ou `AUTOSEG_BASE`), sem token.
Token no Keychain/libsecret/Keystore.

### 4.1 Regras de ouro

- O modo local **não** importa `portal_prestador` nem `servidor_web` no início.
- O modo remoto **não** abre o SQLite local para escrita.
- Um servidor web só sobe por ação explícita (ou preferência salva).
- Cloudflare é gerenciado pelo **dono do servidor**:
  - local: GTK gerencia o túnel;
  - remoto: o servidor gerencia e devolve a URL pública no health/status;
  - nunca dois túneis para o mesmo banco.
- Trocar de modo não move dados automaticamente; exportar/importar ou backup.

---

## 5. API do servidor

Reaproveitar o padrão de `api_financeiro.py`:

- prefixo `/api/v1`;
- JSON, centavos, ISO-8601, cursores opacos;
- bearer token com hash no banco e escopos;
- rate limit e auditoria;
- OpenAPI;
- `GET /api/v1/health` com versão, modo, capabilities e `public_url`;
- `POST /api/v1/auth/login` (ou pareamento) para obter token;
- endpoints por caso de uso, não por tabela;
- upload/download de anexos com limites e content-type;
- idempotency key em operações de escrita;
- erros estáveis.

Primeira fatia da API: **health + login + clientes (listar/obter)**. Depois OS
(listar/obter), financeiro e anexos.

---

## 6. O que fazer no código, em ordem

### Fase 0 — Tirar o servidor do caminho local (base implementada)

- `--no-web` e `AUTOSEG_WEB_ACCESS=0` já abrem o GTK sem subir os portais e sem
  importar `portal_prestador`/`servidor_web` no início.
- `INICIAR_AUTOSEG_SEM_WEB.command` é o atalho local-only.
- Ainda falta transformar o start em um `WebAccessManager` com botão para
  subir/parar os portais sob demanda.
- Criar `WebAccessManager` no GTK para iniciar/parar os portais.
- Mover o start de `PortalPrestador`/`ServidorPortal` do `__init__` para o
  manager.
- Adicionar preferência “Ativar acesso web” e variável
  `AUTOSEG_WEB_ACCESS=0` para modo local-only.
- O padrão pode continuar “ligado” durante a transição; o importante é existir
  o caminho sem servidor.
- O botão “Ligar servidor” deve criar o servidor sob demanda, não falhar.

**Resultado:** GTK abre e funciona sem porta 8765/8766 e sem Cloudflare.

### Fase 1 — `AppService` + `LocalService`

- Criar `application/` (ou `core/services/`) com o contrato e DTOs.
- Implementar `LocalService` para uma fatia pequena: **clientes**.
- Fazer o GTK usar `LocalService` nessa fatia.
- Testes de contrato e caracterização; comportamento/HTML inalterados.

### Fase 2 — `HttpService` + primeira API

- Expor `health`, `login` e clientes no `/api/v1`.
- Implementar `HttpService` com o mesmo contrato.
- Tela de conexão local/remota no GTK.
- Testar Mac → celular na LAN e via túnel.
- Nenhuma regra no cliente; só DTOs e chamadas.

### Fase 3 — OS, financeiro e arquivos

- Migrar OS (listar/obter/salvar), financeiro e anexos.
- Upload de fotos já redimensionadas no cliente.
- PDFs continuam no servidor, com fila.
- Contrato de eventos/histórico.

### Fase 4 — Servidor no celular

- `servidor_backend.py --only-provider` (sem portal do cliente, sem GTK).
- Serviço OpenRC/systemd; bind localhost/LAN; Cloudflare opcional.
- Health, backup, logs e limites de memória.
- 2 GB: um PDF por vez, fotos otimizadas.

### Fase 5 — Cache/offline e sync

- Só depois do contrato estável.
- Cache local de leitura, outbox de escrita e resolução de conflitos.
- É a fase local-first/P2P já documentada; não misturar com a Fase 1.

---

## 7. Arquivos e módulos sugeridos

```text
application/
  contracts.py        AppService, DTOs, erros
  local_service.py    implementação in-process
  http_service.py     cliente HTTP
  connection.py       modos, settings, health, token
interfaces/
  gtk/                UI atual, sem SQL
  http/               /api/v1 e portais HTML
repositorios/         consultas por agregado (já iniciado)
```

- `gtk_app.py`: importa `connection`/`AppService`; não importa
  `PortalPrestador` no topo.
- `portal_prestador.py`: adaptador HTML + `/api/v1`, usando serviços.
- `servidor_backend.py`: opção `--only-provider` e health.
- `runtime_config.py`: modo, URL, `web_access`, portas.
- `docs/FUNDAMENTAL_STRUCTURAL_PROBLEMS.md`: item #1 continua por fatias.

---

## 8. Riscos e decisões abertas

- **Protocolo:** REST/JSON (recomendado para começar) ou JSON-RPC?
- **Auth remota:** bearer token de longa duração + login, ou pareamento por QR
  com token curto? (Recomendação: login + token no Keychain; QR só pareamento.)
- **Offline:** falhar explicitamente ou cache somente leitura? (Fase 5.)
- **Túnel:** servidor dono do túnel no modo remoto; GTK dono no modo local.
- **Migração de dados:** trocar de modo não move banco; exportar/importar.
- **PDF:** servidor (fila) versus cliente; para e-mail/automação, servidor.
- **Rust:** núcleo/protocolo no futuro, não a UI; não começar por Rust.
- **2 GB/celular:** 3 usuários e 2 simultâneos são viáveis; serializar PDFs.

---

## 9. Recomendação

Começar pela **Fase 0** (servidor fora do caminho local) e pela **Fase 1**
(clientes no `AppService`). São pequenas, reversíveis e provam o desenho sem
reescrever o app. A separação completa só deve avançar com testes de contrato
e um servidor remoto real (Mac → celular) antes de migrar OS/financeiro.
