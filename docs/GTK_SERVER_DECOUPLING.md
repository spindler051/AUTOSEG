# GTK × servidor: separação e modos de conexão

**Status:** desenho de arquitetura e plano incremental. Não autoriza um
big-bang; cada fase deve preservar o comportamento atual e ser reversível.

**Objetivo:** permitir que o app GTK rode **totalmente local, sem servidor
web**; que ele possa **subir um servidor web quando o operador quiser**; e que
o mesmo GTK consiga ser cliente de um **servidor headless rodando em outro
Linux** (por exemplo, um celular com Nura/Alpine).

---

## 1. Situação atual

- `gtk_app.py` ainda abre o SQLite local diretamente para OS, PJ, financeiro e
  estoque, mas a primeira fatia de clientes, painel e Portal do Cliente já usa
  `AppService`/`LocalService`.
- O `WebAccessManager` inicia e para os dois portais. O padrão continua com o
  acesso web ligado; `--no-web`/`AUTOSEG_WEB_ACCESS=0` abre o modo local-only
  sem importar os portais.
- O Portal do Cliente tem botão “Ligar/Desligar servidor”; o Portal do
  Prestador ainda não tem controle visual próprio.
- O banco é global (`banco.BANCO`), definido no import.
- Existe uma API JSON read-only de financeiro (`api_financeiro.py`,
  `/api/v1`) com bearer token, paginação, auditoria e OpenAPI. Ela é um bom
  precedente de contrato, mas cobre só leitura financeira.
- O `HttpService` já implementa `health`, mas ainda não lista/salva clientes.
- O gerenciador de túneis Cloudflare (`tuneis`/`links_publicos`) já é separado
  do domínio.

O acoplamento principal não é o HTTP em si; é o GTK conhecer **SQL, banco e
módulos de negócio diretamente**. A primeira fatia reduziu esse acoplamento em
clientes/painel/portal; OS, PJ, financeiro e estoque ainda precisam de fatias
próprias.

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

### Fase 0 — Tirar o servidor do caminho local (implementada)

- `--no-web` e `AUTOSEG_WEB_ACCESS=0` abrem o GTK sem subir os portais e sem
  importar `portal_prestador`/`servidor_web` no início.
- `INICIAR_AUTOSEG_SEM_WEB.command` é o atalho local-only.
- `web_access.py` agora concentra o ciclo de vida dos dois portais. O GTK não
  importa as classes dos portais nem chama `iniciar`/`parar` diretamente.
- O padrão continua “ligado” durante a transição; o botão “Ligar servidor”
  cria o servidor do cliente sob demanda.
- Ainda falta uma preferência visual “Ativar acesso web” e o controle do
  portal do prestador na tela de configurações.

**Resultado:** GTK abre e funciona sem porta 8765/8766 e sem Cloudflare.

### Fase 1 — `AppService` + `LocalService` (primeira fatia implementada)

- `application/contracts.py` define o contrato de casos de uso, DTOs e erros
  estáveis.
- `application/local_service.py` implementa saúde, resumo do início, listar,
  obter e salvar clientes, além do resumo e da lista de solicitações do Portal
  do Cliente.
- O GTK usa o serviço em clientes, painel, Portal do Cliente, financeiro,
  histórico, PJ e lista de OS ativas. `gtk_app.py` está sem SQL direto.
- `gtk_dialogos.py` ainda concentra a leitura/gravação da OS, materiais e
  anexos; é a última fatia grande do desktop.
- `application/connection.py` guarda modo local/remoto; o modo remoto ainda só
  tem `health` (`HttpService`). Não há fallback silencioso para o banco local.
- Testes: `test_application_service.py` e `test_web_access.py`.

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
- `docs/AUTH_AND_CONNECTION_UX.md`: fluxo de login local/remoto e conta admin.

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
  Medições e limites na seção 10.

---

## 9. Recomendação

Começar pela **Fase 0** (servidor fora do caminho local) e pela **Fase 1**
(clientes no `AppService`). São pequenas, reversíveis e provam o desenho sem
reescrever o app. A separação completa só deve avançar com testes de contrato
e um servidor remoto real (Mac → celular) antes de migrar OS/financeiro.

---

## 10. Servidor no celular com 2 GB — medições e limites

Cenário: Galaxy J6 (Exynos 7870, 2 GB de RAM) com Nura/Alpine, rodando **somente o Portal do Prestador** em modo headless.
O port do J6 no Nura é experimental/testing; valide boot, rede, sono e
temperatura antes de confiar nele.

### 10.1 Números medidos no código atual

| Cenário | Resultado |
|---|---|
| Servidor headless (portais + SQLite, sem GTK) | **~48 MB RSS** |
| PDF com 10 fotos 3000×2000 | **~173 MB de pico**, ~4,4 s, PDF de ~3,7 MB (Mac) |
| PDF no J6 (estimativa) | 15–40 s, memória parecida; A53 é mais lenta |
| 2 PDFs simultâneos | ~350 MB de pico + CPU disputada |
| ffmpeg | **não é usado hoje** |
| cloudflared | processo separado, rede/criptografia; pouca CPU |

O gargalo não é o número de usuários navegando. É **PDF com muitas fotos**.

### 10.2 Três usuários, dois simultâneos

- 2 pessoas navegando/editando OS: tranquilo.
- 2 pessoas enviando fotos: ok, com pico moderado.
- 2 pessoas gerando PDF ao mesmo tempo: funciona, mas **serialize**; um PDF
  por vez reduz memória e evita disputa de CPU/GIL.
- 2 pessoas + interface gráfica pesada do Nura + navegador no próprio celular:
  aperta. Prefira acessar de outro dispositivo.

### 10.3 Configuração recomendada

- rodar **provider-only**, sem portal do cliente e sem GTK;
- PDF em fila, **1 por vez**, com limite de 10–15 fotos por relatório;
- cliente redimensiona/comprime antes do upload: ~1600 px, JPEG ~80;
- `zram`/swap de 1–2 GB;
- monitorar `free -m` e RSS; se passar de ~1,2 GB, reduzir fotos ou mover o PDF
  para outro computador;
- manter na tomada e com ventilação; é desenvolvimento/teste, não produção.

---

## 11. Rust, GPU e ffmpeg

### 11.1 Rust

Rust pode reduzir o baseline e melhorar CPU/concorrência, mas **não resolve
sozinho** o pico de memória: o custo dominante é decodificar/redimensionar
imagens e montar o PDF. Um rewrite completo do PDF é caro e arriscado
(ReportLab já resolve layout, tabelas, fontes e quebra de página).

Ordem recomendada:

1. otimizar a pipeline de imagem (Pillow `draft()`, `libvips`, limite de fotos);
2. colocar PDF em fila, um por vez;
3. só depois avaliar um worker Rust para imagem/HTTP;
4. manter Rust para núcleo/protocolo quando o contrato estiver estável.

### 11.2 GPU

O J6 tem Mali-T830 e o driver mainline pode estar aceitável, mas o servidor
atual **não usa GPU**: ReportLab/Pillow são CPU-bound. A GPU ajuda na interface
e no preview/redimensionamento do **cliente**, não na geração de PDF do
servidor.

### 11.3 ffmpeg

ffmpeg não faz parte do servidor atual. Se entrar vídeo no futuro, ele vira uma
nova carga pesada e precisa de fila, limites e, se possível, encode/decode por
hardware (V4L2) — mas isso é outro projeto.

### 11.4 O que mover para o cliente

- **Sim:** resize/compressão de fotos, thumbnail, preview, cache local.
- **Não:** regras de negócio, permissões, financeiro e PDF final com e-mail.
- **Talvez:** PDF no desktop controlado; nunca como única opção para web/mobile.
