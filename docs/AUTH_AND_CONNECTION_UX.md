# Login, conta local e conexão com servidor

**Status:** proposta de UX e segurança. **Não implementado.** Autenticação e
permissões são N3/N4 em `docs/REVIEW_WITHOUT_DEVELOPER.md`; qualquer mudança
nessa área exige revisão humana externa ou fica em DEV atrás de flag.

**Ideia:** ao abrir o app GTK, oferecer dois caminhos claros:

1. **Rodar localmente** — banco SQLite próprio, sem servidor e sem internet.
2. **Conectar a um servidor** — login remoto, dados do servidor.

O modo híbrido (local + sync) é uma fase posterior.

---

## 1. Tela de entrada

> Implementação parcial em `9.6.0-dev.47`: o GTK já tem a página **Conexão**
> com modo local, URL do servidor, teste de `/api/v1/health` e salvamento em
> `connection.json`. Login/senha e troca real de modo ainda não.

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
5. O banco local é criado/aberto em `AUTOSEG_BASE`.
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
   - `http://192.168.0.10:8766` — servidor na LAN;
   - `https://algo.trycloudflare.com` — túnel Cloudflare.
3. O app testa `GET /api/v1/health`.
4. Mostra versão, modo e capacidades do servidor.
5. Pede e-mail/usuário e senha.
6. Recebe um token de sessão; guarda no Keychain/libsecret.
7. O app usa os dados do servidor, não o SQLite local.

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
  API /api/v1 + SQLite + anexos
  sem HTML, sem GUI

officina-server --web
  API + Officina Web
  Portal do Prestador + Portal do Cliente

officina-server --all
  API + Officina Web + jobs (futuro)
```

O GTK local não sobe nada. O GTK remoto só consome a API. O container roda
`officina-server`, nunca o GTK.

---

## 9. Segurança mínima antes de implementar

- Hash de senha com salt e parâmetros atuais.
- Rate limit de login.
- Bloqueio temporário após falhas repetidas.
- Sessão com expiração e revogação.
- Token de dispositivo revogável.
- CSRF no site; bearer token na API.
- Logs sem senha, token, CPF/CNPJ ou conteúdo de formulário.
- Backup/restore do banco local antes de migração.
- Testes de permissão por papel.
- Revisão humana externa antes de MAIN (N3/N4).

---

## 10. Fases

### Fase A — documentação e protótipo local

- tela de escolha local/servidor;
- primeira conta local admin;
- login local;
- “lembrar este dispositivo” atrás de flag;
- usuários locais e papéis;
- testes de hash, bloqueio, sessão e permissões.

### Fase B — conexão remota

- URL + health;
- login no servidor;
- token no Keychain;
- `HttpService` para clientes/OS;
- sem fallback silencioso.

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
- `docs/VISAO_MULTICLIENTE_LOCAL_FIRST.md` — solo local, servidor central, híbrido.
- `docs/PLANO_MODO_LOCAL_SYNC.md` — sync por mudanças, outbox e conflitos.
- `docs/CONDO_SHARING_AND_TENANCY.md` — usuários, organizações, papéis e grants.
- `docs/REVIEW_WITHOUT_DEVELOPER.md` — N3/N4 e revisão humana.
- `docs/NAMING_AND_CLI.md` — `officina-web`, `officina-gtk`, `officina-cli`.
