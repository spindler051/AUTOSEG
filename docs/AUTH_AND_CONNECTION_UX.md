# Login, conta local e conexão com servidor

**Status:** implementado no **DEV** em 2026-11-07: login local ou servidor,
identidade do prestador, logout e token revogável. Autenticação e permissões
continuam N3/N4 em `docs/REVIEW_WITHOUT_DEVELOPER.md`; a MAIN continua sem essa
mudança até revisão humana externa.

**Ideia:** ao abrir o app GTK, oferecer dois caminhos claros:

1. **Rodar localmente** — banco SQLite próprio, sem servidor e sem internet.
2. **Conectar a um servidor** — login remoto, dados do servidor.

O modo híbrido (local + sync) é uma fase posterior.

---

## 1. Tela de entrada

> Implementado no DEV: o GTK abre na tela de login quando não há sessão válida.
> A tela sempre oferece **Local** e **Servidor**. O DEV abre com **Servidor**
> selecionado por padrão, mas o usuário pode escolher Local; o banco local só é
> aberto/criado se essa opção for usada.

> A decomposição completa de modos, papéis, paridade web/GTK/Qt/nativo,
> descoberta de servidores e solicitação sem login está em
> `docs/APP_MODES_ROLES_AND_SERVERS.md`.

```text
┌─────────────────────────────────────────────┐
│  AUTOSEG / Officina                         │
│                                             │
│  [ Rodar localmente ]                       │
│  [ Conectar a um servidor ]                 │
│                                             │
│  Versão • ambiente • idioma                 │
└─────────────────────────────────────────────┘
```

Não misturar “servidor” na primeira tela do modo local. Quem trabalha sozinho
não deve precisar entender URL, túnel ou container.

---

## 2. Modo local — primeira execução

Fluxo:

1. O usuário escolhe **Rodar localmente**.
2. O app detecta que ainda não existe conta local.
3. Pede:
   - nome;
   - e-mail (opcional no modo solo, útil para identificação);
   - senha;
   - confirmação da senha.
4. Cria a primeira conta como **administrador local**.
5. O banco local é criado/aberto na pasta local do usuário: `~/Library/Application Support/AUTOSEG/local` (macOS) ou `~/.local/share/autoseg/local` (Linux); `AUTOSEG_BASE` pode sobrescrever.
6. O app entra direto, sem servidor.

Regras:

- A senha nunca é gravada em texto; usar hash forte (PBKDF2/Argon2 com salt).
- A conta local é dona do banco local.
- O administrador local pode criar outros usuários locais.
- Se o usuário trabalha sozinho, pode continuar usando só o admin.
- O e-mail é identidade de exibição; não é prova de identidade.
- Nada é enviado para servidor no modo local.

---

## 3. Usuários locais e papéis

Papéis iniciais sugeridos:

| Papel | Pode |
|---|---|
| **Admin local** | tudo no banco local, criar/desativar usuários, configurar conexão, backup |
| **Operador** | clientes, OS, materiais, relatórios; sem usuários/configuração |
| **Leitura** | consultar OS e relatórios; sem escrita |
| **Campo** | subconjunto: minhas OS, fotos, relatório, deslocamento |

Regras:

- Toda ação sensível gera auditoria local.
- Admin não pode apagar o último admin ativo.
- Desativar usuário preserva histórico.
- Não existe “login compartilhado” entre pessoas.
- O admin local não vira automaticamente admin do servidor.

---

## 4. “Não pedir senha toda vez”

Não armazenar a senha. O correto é **lembrar este dispositivo**:

- criar um token de dispositivo local, revogável;
- guardar no Keychain (macOS), libsecret (Linux) ou Keystore;
- permitir “esquecer este dispositivo”;
- opção de bloquear após inatividade;
- opção de pedir senha sempre;
- se o token for perdido, voltar ao login normal.

Isso é diferente de “salvar a senha”. Salvar senha em arquivo ou SQLite é
proibido.

---

## 5. Modo servidor

Fluxo:

1. O usuário escolhe **Conectar a um servidor**.
2. Informa a URL:
   - `http://127.0.0.1:8766` — servidor local;
   - `http://192.0.2.10:8766` — servidor na LAN;
   - `https://algo.trycloudflare.com` — túnel Cloudflare.
3. O app testa `GET /api/v1/health`.
4. Mostra versão, modo e capacidades do servidor.
5. Pede e-mail/usuário e senha.
6. Recebe um token de sessão revogável; guarda em arquivo privado ou apenas
   em memória, conforme “Lembrar este dispositivo”.
7. O app usa os dados do servidor, não o SQLite local.

Endpoints do servidor:

```text
POST /api/v1/desktop/login   {email, senha, lembrar}
GET  /api/v1/desktop/me      Authorization: Bearer <token>
POST /api/v1/desktop/logout  Authorization: Bearer <token>
```

Todas as demais rotas `/api/v1/desktop/*` exigem o token. Health e login são as
únicas rotas públicas.

Regras:

- Falha de conexão **não** cai silenciosamente para o banco local.
- URL sem `https` só é aceita em localhost/LAN, com aviso.
- Cloudflare Tunnel não é autenticação; é transporte. O login continua
  obrigatório.
- Token não vai para URL, log, telemetria ou arquivo de configuração em texto.
- “Esquecer servidor” apaga token e configuração, não o banco local.
- O servidor é a autoridade de usuários/permissões no modo remoto.

---

## 6. Conta local × conta do servidor

Decisão importante:

- A conta local é **do dispositivo/banco local**.
- A conta do servidor é **do servidor**.
- Não assumir que são a mesma pessoa automaticamente.

Evolução possível:

1. modo local: conta local;
2. modo remoto: conta do servidor;
3. modo híbrido: vincular conta local a uma conta do servidor com convite ou
   código de pareamento;
4. sync usa IDs estáveis, não e-mail como chave primária.

Enquanto isso não estiver resolvido, não prometer “a mesma conta funciona em
tudo”.

---

## 7. URL do servidor: localhost e Cloudflare

| URL | Uso | Cuidado |
|---|---|---|
| `http://127.0.0.1:8766` | servidor no mesmo computador | sem TLS; aceitável em loopback |
| `http://192.168.x.x:8766` | servidor na LAN | só em rede confiável; firewall |
| `https://....trycloudflare.com` | túnel de teste | não usar dados reais sem login/permissões |
| `https://app.exemplo.com` | produção | TLS + proxy + autenticação |

O teste de conexão deve ser somente leitura (`/api/v1/health`) e mostrar:

- versão;
- modo (`local`, `server`, `headless`);
- se a API está disponível;
- se o site está disponível;
- tempo de resposta;
- erro claro quando não conectar.

---

## 8. O que o servidor precisa ter

Separação interna:

```text
officina-server --api
  servidor de dados: /api/v1 + SQLite + anexos
  sem HTML, sem GUI

officina-web
  GUI do site: Portal do Prestador + Portal do Cliente
  hoje ainda compartilha o processo com a API; separação futura
```

O GTK local não sobe nada. O GTK remoto só consome a API. O container roda
`officina-server`, nunca o GTK.

---

## 9. Segurança: implementado e pendente

Implementado no DEV:

- hash de senha existente (PBKDF2 com salt);
- rate limit em memória por origem/e-mail e bloqueio após 10 falhas;
- sessão com expiração e revogação;
- token de dispositivo revogável;
- bearer token na API desktop;
- logs sem senha ou token;
- testes de login, token, logout e arquivo de sessão.

Pendente antes da MAIN:

- revisão humana externa (N3/N4);
- migrar o token do arquivo para Keychain/libsecret;
- política de inatividade e bloqueio de tela;
- rate limit durável e auditoria de login no banco;
- permissões por papel no servidor (AUT-001 a AUT-021);
- CSRF já coberto no site, mas revisar com o novo login.

---

## 10. Fases

### Fase A — login local (DEV)

- [x] tela de login com modo local e servidor;
- [x] primeira conta local admin;
- [x] login local;
- [x] “lembrar este dispositivo” no servidor;
- [ ] usuários locais e papéis completos;
- [x] testes de hash, bloqueio, sessão e logout.

### Fase B — conexão remota (DEV)

- [x] URL + health;
- [x] login no servidor;
- [x] token revogável em arquivo privado;
- [x] `HttpService` para clientes/OS;
- [x] sem fallback silencioso;
- [ ] token no Keychain/libsecret.

### Fase C — híbrido

- conta local vinculada à conta do servidor;
- outbox/change log;
- sync por registro, não por arquivo SQLite;
- conflitos visíveis;
- servidor como autoridade de numeração/financeiro/estoque.

---

## 11. O que não fazer

- salvar senha em texto ou SQLite;
- login local que “vira” login remoto sem vínculo explícito;
- deixar o GTK abrir o banco local quando a conexão remota falhar;
- usar Cloudflare Tunnel como se fosse autenticação;
- criar usuários sem papel/auditoria;
- apagar o último admin;
- sincronizar `dados.db` por Syncthing/Dropbox;
- implementar auth sem revisão humana.

---

## 12. Relação com os outros documentos

- `docs/GTK_SERVER_DECOUPLING.md` — modos local/remoto, `AppService`, `HttpService`.
- `docs/PERMISSIONS_P0.md` — papéis, matriz e testes de autorização.
- `docs/PERMISSIONS_AND_APPROVALS.md` — permissões configuráveis e aprovações.
- `docs/planning/VISAO_MULTICLIENTE_LOCAL_FIRST.md` — solo local, servidor central, híbrido.
- `docs/planning/PLANO_MODO_LOCAL_SYNC.md` — sync por mudanças, outbox e conflitos.
- `docs/planning/CONDO_SHARING_AND_TENANCY.md` — usuários, organizações, papéis e grants.
- `docs/REVIEW_WITHOUT_DEVELOPER.md` — N3/N4 e revisão humana.
- `docs/NAMING_AND_CLI.md` — `officina-web`, `officina-gtk`, `officina-cli`.
