# Modos do app, papéis e descoberta de servidores

**Status:** visão de produto e decomposição em problemas menores. **Nada aqui
está implementado.** O foco de produção continua sendo o AUTOSEG; federação,
diretório de servidores e sync híbrido são fases posteriores.

**Relação com os outros documentos:**

- `docs/AUTH_AND_CONNECTION_UX.md` — login local/remoto e primeira conta admin.
- `docs/PERMISSIONS_P0.md` — matriz de ações e testes de autorização.
- `docs/PERMISSIONS_AND_APPROVALS.md` — grupos, flags e aprovação tipo Git.
- `docs/GTK_SERVER_DECOUPLING.md` — modos local, servidor e híbrido.
- `docs/VISAO_MULTICLIENTE_LOCAL_FIRST.md` — visão multicliente.
- `docs/PLANO_MODO_LOCAL_SYNC.md` — sync por mudanças, outbox e conflitos.
- `docs/CONDO_SHARING_AND_TENANCY.md` — organizações, usuários, papéis e grants.
- `docs/MULTI_PLATFORM_GUI_GUIDELINE.md` — mesma hierarquia, controles nativos.
- `docs/REVIEW_WITHOUT_DEVELOPER.md` — auth e permissões são N3/N4.

---

## 1. Tela de entrada

```text
┌─────────────────────────────────────────────┐
│  Officina                                  │
│                                             │
│  [ Rodar localmente ]                       │
│  [ Conectar a um servidor ]                 │
└─────────────────────────────────────────────┘
```

### Rodar localmente

1. Escolher o perfil:
   - **Prestador** — gerencia clientes, OS, financeiro, estoque.
   - **Cliente** — solicita e acompanha serviços.
2. Criar a primeira conta local (admin, no caso do prestador).
3. Abrir o banco local.
4. Opcional, futuro: **subir um servidor de sincronização** para outros
   dispositivos da mesma instalação.

### Conectar a um servidor

1. Informar a URL ou escolher um servidor descoberto.
2. Testar `/api/v1/health`.
3. Fazer login.
4. O servidor devolve o papel: cliente, prestador, admin, financeiro etc.
5. O app mostra apenas as funções permitidas.

O modo local não deve exigir URL de servidor. O modo servidor não deve usar o
banco local para escrita.

---

## 2. Modos de operação

| Modo | Dados | Funciona offline | Uso |
|---|---|---|---|
| **Local prestador** | SQLite local | sim | AUTOSEG sozinho no desktop |
| **Local cliente** | SQLite local + fila | sim, para solicitar | cliente sem conta no servidor; sync futuro |
| **Servidor** | servidor | não; precisa de rede | vários dispositivos/usuários |
| **Híbrido** | local + servidor | sim, com sync | fase posterior |

### 2.1 Local cliente

É o caso mais delicado:

- o cliente pode criar uma solicitação local sem internet;
- a solicitação fica em uma fila local;
- quando houver conexão, ela é enviada ao servidor do prestador escolhido;
- o cliente recebe um protocolo local e depois o protocolo do servidor;
- sem conta, o vínculo é por telefone/e-mail/URL de acompanhamento;
- com conta, o histórico fica vinculado.

Não prometer sync bidirecional de OS/financeiro para cliente. O cliente
solicita e acompanha; não edita a OS do prestador.

---

## 3. Papéis e permissões

### 3.1 Separação fundamental

```text
Conta de plataforma  → quem entra no app
Vínculo              → pessoa ↔ organização ↔ papel
Organização/Tenant   → prestador, condomínio, administradora
```

Uma pessoa pode ter papéis diferentes em organizações diferentes.

### 3.2 Papéis iniciais

| Papel | Escopo | Pode |
|---|---|---|
| **Admin da organização** | um prestador/tenant | tudo na organização, criar usuários, ver todas as OS, inclusive de outros admins |
| **Admin de plataforma** | instalação/servidor | administração técnica, suporte, auditoria; não é o mesmo que admin de cliente |
| **Prestador/técnico** | próprios serviços | ver/editar apenas OS em que participa ou é responsável |
| **Despachante** | organização | atribuir OS, ver fila, sem financeiro sensível |
| **Financeiro** | organização | contas a receber/pagar, repasses; sem editar OS técnica |
| **Campo** | próprios serviços | minhas OS, fotos, relatório, deslocamento |
| **Leitura** | organização | consultar OS/relatórios, sem escrita |
| **Cliente** | própria conta/OS | solicitar, acompanhar, aprovar, baixar documentos |

Regras:

- Admin da organização pode editar OS de qualquer pessoa, inclusive de outro
  admin. Todos os admins da mesma organização têm o mesmo nível.
- Prestador não-admin só edita OS em que é responsável/participante.
- Prestador não-admin vê CPF/CNPJ/e-mail somente de clientes envolvidos em uma
  OS dele; não lista a base inteira nem busca por documento.
- Permissão é validada no servidor/serviço, não só na tela.
- Toda ação sensível gera auditoria.
- Não é possível remover o último admin ativo.
- Desativar usuário preserva histórico; não apagar fisicamente.
- Isolamento por tenant: uma organização nunca vê dados de outra.

### 3.3 Matriz de capacidades

| Capacidade | Admin org | Prestador | Despachante | Financeiro | Campo | Leitura | Cliente |
|---|---:|---:|---:|---:|---:|---:|---:|
| Criar/editar cliente | sim | parcial | sim | não | não | não | próprio |
| Criar OS | sim | sim | sim | não | sim | não | solicitar |
| Editar OS de outro | sim | não | não | não | não | não | não |
| Encerrar OS | sim | própria | não | não | própria | não | não |
| Ver financeiro da org | sim | próprio | não | sim | não | não | próprio |
| Criar usuário | sim | não | não | não | não | não | não |
| Configurar servidor | sim | não | não | não | não | não | não |
| Ver auditoria | sim | não | não | parcial | não | não | própria |

A matriz é uma proposta; os nomes e limites precisam de decisão do dono.

---

## 4. Paridade entre web, GTK, Qt e nativos

Regra: **mesmas capacidades de produto, filtradas por permissão e contexto**.

- O site, o GTK, o Qt e os apps nativos usam o mesmo `AppService`.
- A UI não contém regra de negócio; ela pede ao serviço.
- O servidor decide o que o papel pode fazer.
- A aparência segue a plataforma; a hierarquia e os conceitos são os mesmos.

Exceções aceitáveis:

- administração pesada pode ser desktop-first;
- campo/mobile expõe subconjunto;
- cliente tem workflow próprio, mais simples que o prestador.

Não significa “colocar todas as telas em todos os clientes”. Significa que a
capacidade existe no contrato e pode ser exposta onde fizer sentido.

---

## 5. Servidores e descoberta

### 5.1 Hoje

- Um servidor: AUTOSEG.
- O cliente informa URL manualmente:
  - `http://127.0.0.1:8766`;
  - `http://192.168.x.x:8766`;
  - `https://....trycloudflare.com`.
- O site é direto: entra no site da AUTOSEG e já está no prestador.
- O app é mais descentralizado: escolhe servidor, login e papel.

### 5.2 Futuro — diretório de servidores

UX parecida com “escolher instância”, mas **não** é o protocolo Mastodon:

- lista de servidores/prestadores;
- cartão com nome, cidade, especialidades, versão e status;
- busca por nome/cidade/serviço;
- QR code para pareamento;
- servidor favorito;
- “AUTOSEG” como entrada padrão.

Não começar por federação ActivityPub. Primeiro um **diretório simples**
(JSON/HTML) com servidores conhecidos; depois, se houver demanda, um protocolo.

Riscos:

- descoberta não é confiança;
- servidor falso/phishing;
- dados de cliente em servidor errado;
- reputação e moderação viram produto separado.

---

## 6. Solicitação sem login

Regra por prestador, não global:

- AUTOSEG aceita solicitação sem login e assume o risco de OS troll;
- outros prestadores podem exigir conta, telefone verificado ou aprovação;
- o prestador configura a política;
- o site e o app mostram o que é exigido antes de enviar.

Controles de abuso recomendados:

- rate limit por IP/dispositivo;
- campo de contato obrigatório ou opcional;
- fila de moderação;
- limite de solicitações por hora;
- bloqueio de anexos antes da verificação;
- CAPTCHA só se o abuso justificar;
- registro de origem para auditoria;
- possibilidade de o prestador recusar sem criar OS.

Não usar telefone/e-mail como prova de identidade. São contato, não identidade.

---

## 7. Decomposição dos problemas

| Problema grande | Pedaços menores | Fase |
|---|---|---|
| Login local/remoto | conta local, hash, sessão, token de dispositivo, recuperação | A |
| Papéis e permissões | papéis, vínculos, matriz, auditoria, último admin | A |
| Paridade de features | contrato, DTOs, matriz por papel, tela por tela | A/B |
| Cliente no app | solicitar, acompanhar, aprovar, documentos, conta opcional | B |
| Conexão com servidor | URL, health, login, token, erros, sem fallback | B |
| Descoberta de servidores | lista manual, diretório, QR, favoritos | C |
| Multi-prestador | organização/tenant, isolamento, convites | C |
| Sync híbrido | outbox, change log, cursores, conflitos | D |
| Federação | protocolo, identidade, confiança, moderação | E (talvez nunca) |

Cada pedaço precisa de teste e rollback. Não juntar auth + sync + federação no
mesmo PR.

---

## 8. Ordem de produção (AUTOSEG primeiro)

### P0 — produção AUTOSEG

- login local do prestador/admin;
- papéis admin × prestador;
- prestador só edita as próprias OS;
- admin edita todas, inclusive de outros admins;
- auditoria;
- solicitação web sem login, com risco aceito e limites;
- paridade das funções essenciais no GTK.

### P1 — cliente e servidor

- modo cliente no app;
- conexão com servidor;
- login remoto e token;
- usuários locais/remotos;
- cliente acompanha solicitações.

### P2 — descoberta

- diretório simples de servidores;
- QR/pareamento;
- multi-prestador;
- isolamento por tenant.

### P3 — híbrido

- sync por mudanças;
- conflitos;
- autoridade do servidor para numeração/financeiro/estoque.

### P4 — federação

- só se houver demanda real, equipe e operação;
- não é pré-requisito para o AUTOSEG funcionar.

---

## 9. O que não fazer agora

- Federação estilo Mastodon.
- Marketplace/reputação/cobrança entre prestadores.
- Sync bidirecional de dinheiro/estoque sem contrato de conflito.
- Login obrigatório para solicitar serviço na AUTOSEG.
- Admin de plataforma confundido com admin de cliente.
- Uma tela com “local + servidor + sync + descoberta” ao mesmo tempo.
- Implementar auth/permissões sem revisão humana (N3/N4).

---

## 10. Decisões abertas

- Cliente local sem conta: guardar solicitação por quanto tempo?
- Cliente com conta: e-mail, telefone ou CPF?
- O diretório de servidores é operado por quem?
- Um servidor pode hospedar vários prestadores? Com qual isolamento?
- Admin de organização pode criar outro admin? Sim, com auditoria?
- Financeiro pode ver OS técnica? Só leitura?
- Prestador pode ver OS de outro prestador na mesma organização?
- Solicitação anônima aceita anexos? Com qual limite?
- Como revogar dispositivo/token?
- Qual o plano de backup/restore no modo local?

---

## 11. Próximo passo recomendado

Não implementar tudo. A próxima peça é **P0**:

1. definir a matriz de permissões com o dono;
2. escrever testes de autorização;
3. implementar login local e papéis atrás de flag;
4. revisar com humano externo;
5. só depois expor no GTK.

Sem esse passo, “admin edita tudo” e “prestador só edita as próprias OS” fica
apenas em documentação.
