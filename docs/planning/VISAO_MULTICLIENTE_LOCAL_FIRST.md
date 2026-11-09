# Visão multicliente, local-first e P2P

**Status:** documento de visão e planejamento. **Nenhuma implementação está
autorizada por este documento.** Ele registra direção, modos de operação,
custos e limites — não promete prazos nem decide arquitetura irreversível.

**Última atualização:** 2026-11-06  
**Público:** dono do produto, mantenedores e agentes de IA.  
**Documento detalhado de sincronização:** `docs/planning/PLANO_MODO_LOCAL_SYNC.md`.

---

## 0. Resumo em uma página

O objetivo de longo prazo é transformar o AUTOSEG em uma **distribuição** de uma
plataforma de trabalho local-first, com o **Workaholic** como núcleo/protocolo e
vários clientes:

- CLI;
- portais web (cliente, prestador e administração);
- app GTK atual;
- app Qt (avaliação futura);
- app nativo iOS com interface Apple;
- app nativo Android com Jetpack Compose.

O modo local é o padrão, não um fallback: o usuário deve conseguir trabalhar
sem servidor, sem conta e sem internet. Sincronização é opcional e entra em
camadas: primeiro um servidor central, depois grupo local (LAN) e só muito
depois P2P/WAN.

A ordem recomendada é deliberadamente conservadora:

```text
app atual + modo claro/escuro
  → paridade web/GTK + serviços de aplicação
  → CLI
  → protocolo Workaholic v0 (local)
  → sincronização com servidor central
  → grupo local (LAN)
  → mobile/PWA
  → apps nativos iOS/Android
  → P2P/WAN/relay/E2E, se ainda fizer sentido
```

P2P, apps nativos e reescrita em Rust são as partes mais caras. Elas **não**
devem ser o primeiro passo. O risco de tentar tudo de uma vez é criar um
produto frágil, difícil de testar e impossível de manter — o “Bitcoin/GitHub de
serviços” que você quer evitar.

---

## 1. A visão em uma frase

Uma plataforma de gestão de trabalho **local-first, modular e com GUI de alta
qualidade**, na qual o AUTOSEG é a primeira distribuição (segurança e
automação), o Workaholic é o núcleo/protocolo genérico e cada interface — CLI,
GTK, Qt, web, iOS, Android — é um cliente do mesmo contrato de aplicação.

## 2. O que “local-first” significa aqui

**É:**

- abrir o app e trabalhar sem internet e sem servidor;
- criar clientes, OS, materiais, fotos, relatórios e financeiro localmente;
- sincronizar quando houver rede, sem bloquear o trabalho;
- manter uma cópia local consistente em cada dispositivo;
- aceitar consistência eventual e conflitos visíveis;
- permitir backup, exportação e recuperação sem depender do desenvolvedor.

**Não é:**

- sincronizar o arquivo `dados.db` com Syncthing, Dropbox ou cópia de arquivo;
- dois processos escrevendo no mesmo SQLite pela rede;
- garantir que todos os dispositivos vejam a mesma informação no mesmo instante;
- escolher “o certo” automaticamente em conflito de dinheiro, estoque ou status;
- obrigar o usuário a entender servidor, peer, relay ou chave criptográfica.

O detalhamento de por que o SQLite não deve ser sincronizado como arquivo está
em `docs/planning/PLANO_MODO_LOCAL_SYNC.md`.

---

## 3. Modos de operação

| Modo | Quem guarda os dados | Funciona offline | Autoridade | Complexidade | Quando |
|---|---|---|---|---|---|
| **Solo local** | um único dispositivo | sim, total | o próprio dispositivo | baixa | agora / próximo |
| **Grupo local (LAN)** | cada dispositivo + peers da rede | sim | combinada ou um peer “dono” | alta | depois do servidor central |
| **Servidor central** | servidor + cópias locais | sim | servidor para número, financeiro e estoque | média | primeiro alvo de sync |
| **Híbrido** | servidor + dispositivos + LAN | sim | servidor para dados sensíveis; peers para o resto | alta | depois de servidor + LAN |
| **P2P/WAN** | só dispositivos + relay opcional | sim | definida por regra de negócio, não por consenso global | muito alta | último, se houver necessidade real |

### 3.1 Solo local

É o modo mais importante para uso individual. Deve ser completo: cadastros, OS,
materiais, fotos, PDFs, financeiro pessoal, backup e restauração. Não pode
depender de login remoto, porta aberta ou servidor.

### 3.2 Grupo local (estilo Syncthing, mas de registros)

Vários dispositivos na mesma rede trocam **mudanças de registro**, não o arquivo
do banco. Descoberta por mDNS, pareamento por QR/código, transporte autenticado.
Se a rede cair, cada um continua local. Um peer pode ser o “dono” temporário,
ou todos trocam mudanças e mostram conflitos.

### 3.3 Servidor central

O servidor é mais um participante/autoridade, não o único lugar onde dá para
trabalhar. Ele é útil para:

- numeração canônica de OS;
- fechamento financeiro e repasses;
- saldo de estoque consolidado;
- permissões, dispositivos e auditoria;
- backups e suporte.

### 3.4 P2P/WAN

Só faz sentido depois que o modo local, o servidor central e a LAN estiverem
estáveis. Exige NAT traversal, relay, criptografia, revogação de dispositivo e
uma política de conflito por domínio. **P2P não é um objetivo por si só**; é um
meio para grupos que não querem ou não podem operar um servidor.

### 3.5 O que não é um modo

- “Serviço público global de OS” com estranhos — não é o produto.
- DHT/torrent público para dados de clientes — nunca.
- Blockchain, token ou consenso global — não há necessidade e o custo é enorme.

---

## 4. Família de clientes

| Cliente | Papel principal | Estado | Offline | Estratégia |
|---|---|---|---|---|
| **Web do prestador** | operação, OS, financeiro, portal | atual | parcial | referência funcional; deve virar cliente fino |
| **Web do cliente** | solicitações, acompanhamento, documentos | atual | não | pode continuar online-first |
| **GTK** | desktop operacional | atual | sim, local | paridade operacional com o web |
| **CLI** | automação, importação, diagnóstico, scripts | protótipo Workaholic | sim | primeira classe, não substituta da GUI |
| **Qt** | desktop alternativo (ex.: Windows) | não iniciado | sim | só se houver demanda real |
| **iOS nativo** | campo, fotos, OS, notificações | não iniciado | sim, com limites | SwiftUI/UIKit; decisão futura |
| **Android nativo** | campo, fotos, OS, notificações | não iniciado | sim, com limites | Kotlin/Jetpack Compose; decisão futura |
| **PWA** | alternativa intermediária mobile | não iniciado | sim, com limites | pode vir antes dos apps nativos |

### 4.1 Paridade: o que “todas as funções do site no GTK” significa

“Todas as funções” não deve significar “todas as funções em todos os clientes,
para todos os papéis”. Isso multiplica o custo por seis e cria telas ruins.

O contrato recomendado é uma **matriz de capacidades por papel**:

- **Prestador/técnico:** tudo que faz no portal do prestador deve existir no GTK
  (OS, fotos, relatório, materiais, financeiro pessoal, documentos).
- **Administração:** funções de cadastro, permissão, auditoria e configuração
  podem ser desktop-first; não precisam estar no celular.
- **Cliente:** portal do cliente continua sendo a interface do cliente; não
  precisa ser replicado no GTK.
- **Campo (mobile):** subconjunto focado: minhas OS, fotos, relatório,
  assinatura, deslocamento, notificações. Financeiro administrativo e
  configuração ficam no desktop/web.

Uma matriz concreta (função × cliente × papel) deve ser feita **antes** de
prometer paridade total.

### 4.2 Regras de GUI

- Um sistema de design compartilhado (tokens de cor, espaçamento, tipografia,
  estados), não widgets compartilhados entre stacks diferentes.
- Claro/escuro em todos os clientes: preferência do sistema + opção manual.
- Acessibilidade, teclado, leitores de tela e contraste.
- Convenções nativas em iOS e Android; não “um site dentro de um app”.
- Indicadores visíveis de offline, sincronizando, pendente e conflito.
- Nenhuma regra de negócio na UI.
- Aparência muito similar entre plataformas (mesmo produto, mesma hierarquia,
  mesmos tokens), mas comportamento e controles nativos de cada uma. A regra
  completa está em `docs/planning/MULTI_PLATFORM_GUI_GUIDELINE.md`.

---

## 5. Desacoplamento: GTK, web e o núcleo

### 5.1 Situação atual

Hoje o GTK e os portais web compartilham o mesmo SQLite e importam módulos de
domínio diretamente. Isso funciona, mas:

- a UI conhece SQL e regras;
- o servidor web é ao mesmo tempo interface e backend;
- não existe um contrato estável para um cliente novo;
- um app mobile não consegue reutilizar o cérebro sem levar junto HTML, GTK ou
  detalhes de SQLite.

### 5.2 Direção-alvo

```text
CLI   GTK   Qt   Web   iOS   Android
  \    |    |     |     |      /
       contrato de aplicação
   (comandos, consultas, eventos, permissões)
                 |
          Workaholic core
     (schemas, registros, estados, validação)
                 |
        armazenamento local
     (SQLite, anexos, change log)
                 |
        sincronização opcional
     (servidor / LAN / P2P)
```

- A UI chama **serviços de aplicação**; nunca executa SQL.
- O servidor web passa a ser **um adaptador**, não o centro do sistema.
- O GTK deixa de ser “o app que contém o backend” e passa a ser um cliente.
- O CLI usa os mesmos serviços, com comandos explícitos e `--dry-run`.
- O protocolo é a fronteira estável; o transporte é detalhe.

### 5.3 O que não fazer

- Colocar HTML/HTTP dentro do núcleo.
- Colocar widgets GTK dentro do núcleo.
- Fazer o app mobile falar direto com o SQLite do desktop.
- Duplicar regras de negócio em cada cliente.
- Reimplementar tudo em Rust antes de existir um contrato testável.

---

## 6. O “protocolo Workaholic”

O nome ainda é uma decisão em aberto (`docs/NAMING_AND_CLI.md`). Neste
documento, “protocolo Workaholic” significa o **contrato de aplicação**, não
apenas uma biblioteca Python.

### 6.1 Dois protocolos distintos

1. **Protocolo de aplicação local**
   - criar, ler, atualizar, arquivar, transicionar;
   - consultas, filtros, paginação;
   - validação, permissões e erros;
   - funciona em processo, por IPC local ou por HTTP local;
   - é o que CLI, GTK, web e mobile usam.

2. **Protocolo de sincronização**
   - exchange de mudanças entre réplicas;
   - cursores, idempotência, versão de schema;
   - conflitos e tombstones;
   - é o que servidor, LAN e P2P usam.

Misturar os dois é um erro comum: o protocolo de sync não é “o CRUD pela
internet”.

### 6.2 Requisitos do contrato

- versionamento explícito;
- negociação de capacidades;
- modelo de erro estável;
- idempotência por `change_id`/chave de operação;
- concorrência otimista (`base_version`);
- versão de schema;
- auditoria e eventos;
- testes de conformidade;
- compatibilidade com clientes antigos.

### 6.3 Rust

Rust é uma opção real para o núcleo/protocolo, não para reescrever todas as UIs.
O caminho seguro:

1. estabilizar a especificação e os testes de conformidade;
2. manter uma implementação de referência (Python) durante a transição;
3. reimplementar o núcleo/protocolo em Rust atrás do mesmo contrato;
4. expor para Swift/Kotlin via FFI (por exemplo, UniFFI) ou daemon local;
5. expor para GTK via FFI/PyO3 ou IPC;
6. expor para web via HTTP local ou WASM, se fizer sentido.

Sem testes de conformidade, uma reescrita em Rust vira uma segunda verdade.
Mobile tem restrições adicionais de background e empacotamento; um daemon local
no iOS não é uma solução livre.

---

## 7. Por que isso é muito mais complexo do que parece

Os itens abaixo são os principais multiplicadores de custo. Nenhum é “só uma
telinha”.

1. **Identidade e dispositivos**
   - usuário, organização, grupo, dispositivo e convite são coisas diferentes;
   - chaves, revogação, perda de celular, troca de máquina;
   - recuperação de conta sem servidor é um problema difícil.

2. **Semântica de sincronização**
   - log de mudanças, ordenação, cursores, duplicação, replay;
   - clientes offline por dias/semanas;
   - schema antigo versus schema novo;
   - sincronização parcial e retomada após queda.

3. **Conflitos por domínio**
   - cliente: last-write-wins por campo pode ser aceitável;
   - status de OS: máquina de estados; transição concorrente vira revisão
     manual;
   - dinheiro, repasse e estoque: append-only e autoridade; nunca LWW cego;
   - fotos/PDFs: imutáveis por hash;
   - exclusão: tombstone, não `DELETE` imediato.

4. **Numeração e documentos offline**
   - `MAX+1` não é seguro offline;
   - número provisório, número canônico, nunca reutilizar;
   - PDF emitido com número provisório precisa ser rastreável;
   - documento fiscal offline depende de regra legal e provedor.

5. **Invariantes financeiros**
   - pagamento, recebimento, repasse, comissão, estorno e cancelamento;
   - duas réplicas não podem “ganhar” um conflito financeiro por sincronizar
     primeiro;
   - auditoria e conciliação são obrigatórias;
   - o servidor provavelmente precisa ser autoridade.

6. **Permissões e multiempresa**
   - uso individual, empresa e grupo têm modelos de acesso diferentes;
   - quem vê o quê, por quanto tempo, em qual dispositivo;
   - LGPD, retenção, exportação e exclusão;
   - compartilhar um cliente entre organizações é um caso real e delicado.

7. **Anexos e blobs**
   - fotos, PDFs e notas fiscais;
   - content-addressed storage, deduplicação, upload resumível;
   - criptografia em repouso e em trânsito;
   - coleta de lixo e integridade;
   - Syncthing pode servir para blobs imutáveis, não para o banco.

8. **Evolução de schema**
   - um dispositivo pode ficar meses offline;
   - migração precisa ser idempotente e reversível;
   - clientes antigos podem enviar campos que o novo não entende;
   - “só atualizar todo mundo” não funciona em campo.

9. **Segurança**
   - chaves por dispositivo, revogação, rotação;
   - TLS, assinatura de payload, replay protection;
   - relay não pode virar ponto de confiança cego;
   - E2E versus servidor que gera PDF/e-mail/documento fiscal;
   - keychain/keystore e perda de dispositivo.

10. **Rede**
    - NAT, relay, firewall, mDNS, VLAN, isolamento de cliente em Wi-Fi;
    - redes móveis instáveis e background limitado;
    - descoberta “zero-config” não funciona em todas as redes;
    - latência e reconexão precisam ser testadas.

11. **Paridade de clientes**
    - seis stacks de UI (web, GTK, Qt, iOS, Android, CLI);
    - cada plataforma tem convenções, acessibilidade e testes próprios;
    - design system compartilhado, mas não widgets compartilhados;
    - cada cliente multiplica a matriz de testes e o suporte.

12. **Distribuição**
    - App Store e Play Store: revisão, sandbox, privacidade, atualizações;
    - macOS: assinatura/notarização;
    - Linux: Flatpak/AppImage;
    - Windows: instalador, assinatura, atualização;
    - relatórios de crash e diagnóstico.

13. **Operação e suporte**
    - backup, restauração, migração e recuperação de desastre;
    - servidor self-hosted: quem instala, atualiza e dá suporte?
    - version skew entre dispositivos;
    - logs e diagnóstico sem vazar dados pessoais;
    - cada modo novo aumenta o custo de suporte.

14. **Testes**
    - 2–5 dispositivos simulados;
    - clock skew, push duplicado, fora de ordem, crash no meio;
    - conflito de status, dinheiro e estoque;
    - migração de banco antigo;
    - restauração de backup;
    - testes de UI em cada plataforma.

15. **Fatores humanos**
    - usuários não entendem “sync”; precisam de modos simples;
    - conflito precisa de tela compreensível, não de JSON;
    - indicadores de offline/pendente/conflito;
    - treinamento e suporte;
    - uma arquitetura tecnicamente elegante pode ser inutilizável.

16. **Legal e privacidade**
    - LGPD, consentimento, retenção, acesso e exclusão;
    - dados fiscais e financeiros têm regras próprias;
    - self-hosted não elimina obrigações;
    - App Store exige política de privacidade e transparência.

---

## 8. Coisas que provavelmente são inviáveis ou não valem a pena

Esta seção existe para evitar promessas impossíveis. “Inviável” aqui significa
“inviável no escopo atual, com este tamanho de equipe e este nível de risco”, não
“impossível em teoria”.

1. **Sincronizar o SQLite ativo com Syncthing/Dropbox.** O arquivo pode ser
   copiado no meio de uma transação; locks não funcionam em rede; conflito vira
   cópia de arquivo, não merge de registros.

2. **Multi-master automático para dinheiro, estoque, documento fiscal e status
   de OS.** Não existe regra automática segura. Esses domínios precisam de
   autoridade, trilha de auditoria e revisão humana.

3. **Consistência forte/real-time entre dispositivos offline.** É fisicamente
   impossível sem conexão. O produto precisa aceitar consistência eventual e
   mostrar o estado.

4. **P2P puro, sem infraestrutura, com entrega garantida e NAT traversal
   perfeito.** NAT, relay, firewall e redes móveis tornam isso caro e
   imperfeito. Um relay ou servidor opcional é quase sempre necessário.

5. **E2E completo e, ao mesmo tempo, servidor gerando PDF/e-mail/documento
   fiscal a partir do conteúdo em texto claro.** Ou o servidor vê o conteúdo,
   ou a geração/documento acontece no cliente, ou há compartilhamento de chave
   com o servidor. É um trade-off explícito, não um detalhe.

6. **Uma única base de UI com aparência nativa em todas as plataformas.** É
   possível compartilhar lógica e design tokens; não é realista compartilhar a
   mesma camada de widgets e obter o look nativo de Apple, Android, GNOME e Qt.

7. **GTK como UI principal de Android/iOS.** GTK não é a stack nativa dessas
   plataformas; empacotamento, background, lojas e acessibilidade ficam ruins.
   GTK é excelente no desktop; mobile precisa de cliente próprio ou PWA.

8. **Reescrever tudo em Rust de uma vez.** Sem contrato e testes, vira uma
   segunda implementação divergente. Rust primeiro no núcleo/protocolo, depois
   nos adaptadores, nunca em big-bang.

9. **Blockchain, token, consenso global ou “GitHub de serviços”.** Não há
   problema de consenso global a resolver. O custo é enorme e não ajuda o
   usuário a abrir uma OS.

10. **Paridade total de todas as funções em todos os clientes desde o dia 1.**
    Multiplica o custo por seis e produz telas ruins. A matriz de capacidades
    por papel é o caminho.

11. **Merge automático de clientes duplicados por CPF/CNPJ.** Precisa de revisão
    humana; fusão errada de cadastro pode misturar histórico financeiro.

12. **Emissão offline de documento fiscal legalmente válido sem o provedor.**
    Depende da regra municipal/estadual e do provedor; pode ser possível apenas
    com contingência específica, não como regra geral.

13. **Background sync contínuo e irrestrito no iOS.** O sistema operacional
    limita execução em background. O produto precisa de sync sob demanda, push
    e tolerância a atrasos.

14. **Descoberta LAN “zero-config” em qualquer rede.** Wi-Fi de visitante,
    VLAN, isolamento de cliente e firewall bloqueiam mDNS. Precisa de fallback
    manual/QR/servidor.

15. **Envio de e-mail offline.** O máximo realista é enfileirar e enviar quando
    houver rede; o servidor de e-mail é externo.

16. **Edição colaborativa em tempo real estilo Google Docs.** Não é necessária
    para OS e adiciona uma camada enorme de complexidade (CRDT/OT, presença,
    permissões por cursor).

17. **Servidor self-hosted com zero operação e zero suporte.** Alguém precisa
    instalar, atualizar, fazer backup e diagnosticar. Se o produto promete
    “local para sempre”, o suporte e a recuperação precisam ser reais.

18. **“Os dados nunca saem do dispositivo” com relatórios/e-mails gerados no
    servidor.** É contraditório. O produto precisa dizer claramente o que fica
    local, o que vai para o servidor e o que vai para terceiros.

---

## 9. O que é viável e valioso fazer primeiro

1. **Modo claro/escuro no web e no GTK.**
   - tema do sistema + opção manual;
   - tokens de cor, contraste e estados;
   - testar todas as páginas e componentes;
   - GTK já segue o sistema; falta um seletor explícito se o produto quiser.

2. **Matriz de paridade web × GTK por papel.**
   - listar funções do portal do prestador;
   - marcar o que já existe no GTK, o que falta e o que é web-only;
   - priorizar o fluxo operacional (OS, fotos, relatório, materiais,
     financeiro pessoal).

3. **Extrair serviços de aplicação do web/GTK.**
   - começar por uma fatia pequena (catálogo ou clientes);
   - testes de caracterização antes;
   - UI sem SQL; uma regra, um lugar.

4. **CLI de leitura primeiro.**
   - `status`, `list`, `show`, `export`, `doctor`;
   - depois comandos de escrita com `--dry-run` e confirmação;
   - mesma camada de serviços, sem regra duplicada.

5. **Modo local completo.**
   - backup/restauração testados;
   - exportar/importar snapshot;
   - inicialização sem rede;
   - nenhum telefone para casa obrigatório.

6. **Protocolo Workaholic v0 + testes de conformidade.**
   - contrato de aplicação local;
   - change log e versionamento;
   - sem rede ainda;
   - uma implementação de referência.

7. **Sincronização com servidor central.**
   - dois dispositivos + servidor;
   - conflitos visíveis;
   - autoridade para número, financeiro e estoque;
   - sem P2P.

8. **Grupo local (LAN).**
   - só depois que o servidor central estiver estável;
   - mDNS/pareamento/fallback;
   - mesma especificação de sync.

9. **Mobile.**
   - PWA local-first primeiro, ou **uma** plataforma nativa;
   - não começar com iOS e Android nativos ao mesmo tempo;
   - validar background, câmera, PDF, assinatura e offline real.

10. **Qt.**
    - só se houver demanda real (ex.: Windows) e paridade GTK estável;
    - caso contrário, GTK + web + mobile já cobrem o produto.

---

## 10. Roadmap incremental

Cada fase deve ter critério de saída, testes e rollback. Nenhuma fase autoriza
a seguinte automaticamente.

### Fase 0 — Fundação de UI e paridade (agora)

- modo claro/escuro no web e no GTK;
- matriz de funções web × GTK × papel;
- inventário de acoplamentos (SQL na UI, regras duplicadas);
- nenhuma migração de schema.

**Saída:** tema claro/escuro utilizável; matriz documentada; lista de lacunas.

### Fase 1 — Local-only completo + CLI

- backup/restauração e exportação;
- CLI de leitura e comandos seguros;
- fluxo principal offline no GTK;
- testes de reinício e restauração.

**Saída:** usuário individual trabalha uma semana offline sem perder dados.

### Fase 2 — Protocolo v0

- contrato de aplicação local;
- comandos/consultas/erros/versionamento;
- change log e concorrência otimista;
- testes de conformidade;
- nenhuma rede.

**Saída:** GTK, web e CLI usam a mesma camada; regras não duplicadas.

### Fase 3 — Sync com servidor central

- push/pull/ack;
- autenticação de dispositivo;
- outbox/inbox;
- conflitos visíveis;
- autoridade para número, financeiro e estoque.

**Saída:** dois dispositivos offline criam OS; ao voltar, ambos convergem sem
perda; conflitos aparecem para revisão.

### Fase 4 — Grupo local (LAN)

- mDNS, pareamento, TLS/assinatura;
- troca direta de mudanças;
- fallback para servidor;
- Syncthing opcional só para blobs.

**Saída:** dois PCs na mesma LAN sincronizam sem internet; servidor ausente não
bloqueia.

### Fase 5 — Mobile/PWA

- cliente local-first em telefone;
- mesma especificação de sync;
- limites de background documentados;
- câmera, fotos, PDF e assinatura.

**Saída:** técnico em campo trabalha offline e sincroniza depois.

### Fase 6 — Apps nativos iOS/Android

- só depois do protocolo estável e de evidência de uso;
- uma plataforma por vez;
- interface nativa, notificações, biometria, keychain/keystore;
- revisão de loja e privacidade.

**Saída:** beta em TestFlight/Play interno com paridade de sync.

### Fase 7 — P2P/WAN/relay/E2E

- Tailscale/WireGuard ou relay;
- NAT traversal;
- criptografia e revogação;
- auditoria de segurança;
- só se o custo for justificado por usuários reais.

**Saída:** grupo sem servidor central sincroniza com segurança e conflitos
visíveis.

### Fase 8 — Outros clientes (Qt etc.)

- somente com demanda comprovada;
- design system e protocolo já estáveis;
- sem duplicar regra de negócio.

---

## 11. Regras para não criar um “Bitcoin/GitHub de serviços”

1. **Uma fonte de verdade por domínio.** Não duplicar regra em cliente, servidor
   e sync.
2. **Protocolo antes de UI.** Especificação + testes de conformidade antes de
   multiplicar clientes.
3. **Nada de big-bang.** Strangler: uma fatia, testes, rollback.
4. **Consenso global só se houver requisito real.** Para OS, dinheiro e estoque,
   autoridade do servidor é mais simples e segura.
5. **P2P é meio, não fim.** O fim é o usuário trabalhar offline e compartilhar
   quando quiser.
6. **Todo recurso precisa funcionar local-first**, salvo os explicitamente
   online (e-mail, nota fiscal, pagamento).
7. **Política de conflito por domínio**, documentada e testável.
8. **Sem blockchain/token/DHT público** para dados de clientes.
9. **Portabilidade de dados sempre.** Exportar e restaurar sem o desenvolvedor.
10. **Segurança e privacidade antes de sync.** Chaves, LGPD, retenção e
    auditoria.
11. **Cada cliente multiplica testes e suporte.** Medir o custo antes de abrir
    uma nova frente.
12. **Decisão irreversível precisa de humano.** ADR, alternativas e rollback.
13. **Qualidade de GUI não é luxo.** Tokens, contraste, acessibilidade,
    teclado, estados vazios, offline e conflito.
14. **Preservar o comportamento do AUTOSEG** durante toda a transição.

---

## 12. Decisões que precisam do dono

Estas decisões não devem ser tomadas por IA sozinha; precisam de contexto de uso,
evidência e, em alguns casos, revisão técnica/legal.

1. **Cliente de referência:** GTK ou web define a paridade?
2. **Qt:** é realmente necessário (Windows?) ou GTK + web bastam?
3. **Mobile:** PWA primeiro, uma plataforma nativa, ou as duas?
4. **P2P:** é uma necessidade real de usuários ou uma ambição de arquitetura?
5. **Autoridade em grupo:** servidor, dispositivo “dono” ou consenso? (Consenso
   é o mais caro e provavelmente desnecessário.)
6. **E2E:** o que pode ser criptografado se o servidor precisa gerar PDF,
   e-mail e documento fiscal?
7. **Paridade mobile:** quais funções e papéis realmente precisam estar no
   celular?
8. **Self-hosted:** quem instala, atualiza, faz backup e dá suporte?
9. **Rust:** núcleo, protocolo, CLI ou apenas um módulo futuro?
10. **Nome:** Workaholic é motor, protocolo, CLI ou codinome? (Ver
    `docs/NAMING_AND_CLI.md`.)
11. **Tema:** somente sistema, somente manual, ou os dois? (Recomendação: os
    dois.)
12. **Documento fiscal offline:** o que é legalmente permitido no Brasil e no
    provedor usado?
13. **Retenção/LGPD:** quanto tempo guardar, onde e como excluir dados
    sincronizados?

Essas decisões devem ser registradas em `docs/HUMAN_CENTERED_DECISIONS.md`
quando houver evidência suficiente.

---

## 13. Documentos relacionados

- `docs/PRODUCT_VISION.md` — visão geral da plataforma e do Workaholic.
- `docs/planning/PLANO_MODO_LOCAL_SYNC.md` — detalhamento técnico de offline/sync.
- `docs/NAMING_AND_CLI.md` — nomes e contrato da CLI.
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md` — método de migração por fatias.
- `docs/PLATFORM_MIGRATION_LEDGER.md` — estado das fatias migradas.
- `docs/WORKAHOLIC_INTEGRACAO.md` — integração atual do Workaholic.
- `docs/HUMAN_CENTERED_DECISIONS.md` — decisões que precisam de humano.
- `docs/GTK4_LINUX_MACOS.md` — estado e limites do GTK atual.
- `docs/GTK_SERVER_DECOUPLING.md` — separação GTK × servidor e modos local/remoto.
- `docs/planning/MULTI_PLATFORM_GUI_GUIDELINE.md` — guideline visual e nativa por plataforma.
- `docs/planning/CONDO_SHARING_AND_TENANCY.md` — compartilhamento de OS e multiempresa em condomínios.
- `workaholic/docs/ARCHITECTURE.md` — arquitetura do protótipo Workaholic.
