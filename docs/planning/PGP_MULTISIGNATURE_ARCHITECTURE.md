# PGP, multiassinatura e integridade criptográfica

**Status:** planejamento apenas. Nada implementado, nenhum código ou banco alterado.  
**Escopo:** Workaholic core, Officina, flavor AUTOSEG e, no futuro, Meu Auto
Financeiro como produto separado.  
**Documentos relacionados:**
[`ANTI_TAMPERING_FINANCIAL_LEDGER.md`](ANTI_TAMPERING_FINANCIAL_LEDGER.md),
[`SIGNED_OS_TWO_PARTY_AND_VERSIONING.md`](SIGNED_OS_TWO_PARTY_AND_VERSIONING.md)
e ADR [`0003-signed-event-ledger.md`](../../workaholic/docs/adr/0003-signed-event-ledger.md).

## 1. O que este documento decide

Este é o documento de arquitetura de alto nível. Ele separa o que é genérico do
que é produto, o que é assinatura criptográfica do que é política de negócio e o
que é evidência técnica do que é validade jurídica.

Decisões centrais:

1. Workaholic fornece o **mecanismo genérico** de ledger assinado, registro de
   chaves, verificação e avaliação de política.
2. Officina fornece o **fluxo de aprovação**, papéis, UI e notificações.
3. O flavor AUTOSEG define os **tipos de evento, políticas e rótulos** do
   AUTOSEG: OS, financeiro, prestadores e PDFs.
4. Regras brasileiras de assinatura digital (ICP-Brasil/PAdES), fiscais e
   jurídicas ficam no **locale/flavor AUTOSEG**, nunca no core.
5. Meu Auto Financeiro é um **produto separado**; pode reutilizar o mecanismo
   genérico, mas não importa regras do AUTOSEG.
6. O padrão inicial de aprovação de OS é **2-de-3 assinaturas independentes de
   administradores**, com política versionada.
7. Alterações de valor de um prestador exigem, além do quórum de admins, a
   assinatura da **chave do prestador afetado** (ou fallback custodiado
   explícito).
8. Chave privada **não fica no servidor em texto puro**. O padrão recomendado é
   dispositivo do administrador/hardware. Armazenar chave privada criptografada
   no banco é um perfil de menor garantia, nunca o padrão silencioso. O modo de
   conveniência que usa a senha de login como fator de desbloqueio é o perfil de
   menor garantia; exige opt-in explícito, aviso na UI e política de senha.
9. Assinaturas são **independentes + verificação de quórum**; não se presume
   threshold cryptography nativa no OpenPGP.
10. O histórico local é **tamper-evident**, não imutável por si só. Checkpoints
    externos e verificador independente são obrigatórios para detectar rollback
    e reescrita.

## 2. Mapa de camadas

| Camada | Responsabilidade | Não pode |
|---|---|---|
| **Workaholic core** | Envelope canônico, hash chain, evento assinado, registro de chaves públicas, avaliação de política M-de-N, verificador offline, versionamento de schema | Conhecer AUTOSEG, OS, prestador, ICP-Brasil, PAdES, fiscal, rótulos de produto |
| **Officina** | Fluxo de proposta/aprovação, papéis, UI, notificações, perfis de política, integração com auth | Implementar criptografia própria ou regra fiscal brasileira |
| **Flavor AUTOSEG** | Tipos de evento (`os.*`, `finance.*`), política 2-de-3, isolamento de prestador, evidências em PDF, decisão PAdES/OpenPGP, ICP-Brasil | Exigir que o core conheça "prestador" ou "OS" |
| **Locale BR** | ICP-Brasil, PAdES, requisitos legais/fiscais, retenção legal | Ser importado pelo core |
| **Meu Auto Financeiro** | Produto separado, banco/chaves/políticas próprias; pode usar o core | Importar regras do AUTOSEG ou compartilhar chaves/banco |

O teste de fronteira: um músico, eletricista ou artista deve conseguir usar o
core sem ouvir falar de "OS", "prestador", "PIX" ou "ICP-Brasil". O AUTOSEG
fornece esses conceitos como dados de perfil/política.

## 3. Identidade criptográfica

Cada administrador tem um par OpenPGP próprio:

- **Pública:** registrada no banco/registro de chaves, com fingerprint, papéis,
  validade e revogação. Serve para verificar assinaturas.
- **Privada:** pertence ao administrador. Não é compartilhada, não fica em texto
  puro, não é exportada pelo servidor padrão.

Recomendação padrão:

1. Gerar/importar a chave no dispositivo do administrador.
2. Proteger com senha de desbloqueio **separada** da senha de login.
3. Preferir OpenPGP card/YubiKey ou keychain do sistema.
4. Registrar a pública por um evento assinado, com prova de posse (desafio
   assinado) e conferência de identidade por outro canal.
5. Assinar localmente; enviar ao servidor apenas payload canônico + assinatura +
   fingerprint.

### 3.1 Chave privada criptografada no banco (fallback)

O texto original permite manter a chave privada vinculada à conta desde que
criptografada. Isso é possível, mas **reduz a garantia**: um servidor
comprometido que capture a senha de desbloqueio ou o processo de assinatura pode
assinar em nome do admin.

Se esse perfil for aceito, ele deve ser explícito e separado. Este é o perfil
recomendado quando a chave fica no banco; a seção 3.2 abre uma exceção
consciente para quem aceitar usar a senha de login como desbloqueio:

- Argon2id com salt individual e parâmetros calibrados;
- AES-256-GCM com nonce único e AAD vinculando `admin_id`, `key_fingerprint` e
  versão do envelope;
- senha de desbloqueio separada da senha de autenticação;
- chave descriptografada só em memória, pelo menor tempo possível;
- nunca logar chave, senha, nonce ou plaintext;
- rate limit e auditoria de tentativas;
- aviso claro na UI: "chave no servidor = menor garantia de não repúdio";
- possibilidade de migrar para hardware depois.

Não aplicar hash irreversível à chave privada: ela precisa ser recuperável para
assinar. Hash é para senha de autenticação, não para a chave em si.

### 3.2 Modo conveniência: senha de login como fator de desbloqueio

O modo de conveniência existe para o usuário não precisar decorar uma passphrase
longa. Ele é **opt-in, de menor garantia e nunca o padrão silencioso**.

Desenho:

1. A chave privada OpenPGP é protegida por uma passphrase aleatória de alta
   entropia (ou por uma DEK aleatória). O usuário não precisa memorizá-la.
2. Uma **KEK** é derivada da senha de login com **Argon2id**, salt individual,
   parâmetros versionados e contexto de domínio
   (`autoseg.signing-key.v1`). Não reutilizar o hash de login armazenado como
   chave.
3. A passphrase/DEK é envolvida com **AES-256-GCM** ou ChaCha20-Poly1305. O
   envelope guarda ciphertext, nonce, salt, parâmetros, fingerprint da chave e
   AAD vinculando conta/fingerprint/versão.
4. No login, o cliente (GTK/nativo) deriva a KEK, desembrulha a passphrase, abre
   a chave PGP e mantém a chave privada **somente em memória**.
5. Ao sair, bloquear a tela, expirar a sessão ou após um timeout curto, o cache
   é descartado. Assinaturas de alto risco podem exigir reautenticação.
6. No desbloqueio da chave, o servidor não recebe a KEK, a passphrase ou a
   chave privada em claro; a derivação e o desbloqueio acontecem no cliente. Se
   o envelope for armazenado no banco, ele contém apenas material cifrado. A
   senha de login ainda pode ser exposta na autenticação; ver o risco crítico
   abaixo.

**Consequência central:** neste modo, a senha de login passa a ser uma entrada
para a capacidade de assinatura. Uma senha fraca, reutilizada ou vazada reduz a
garantia da assinatura; um envelope vazado pode ser atacado offline.

**Risco crítico do fluxo atual:** hoje a senha de login é enviada ao servidor
para autenticação. Um servidor comprometido pode capturá-la e, se também tiver
o envelope da chave, desbloquear a chave e assinar. Isso quebra a premissa de
que o servidor não consegue assinar em nome do usuário. Portanto, o modo de
conveniência com a senha de login só é aceitável se:

- a autenticação não expuser a senha crua ao servidor (ex.: PAKE/OPAQUE ou
  derivação/verificador separado no cliente), **ou**
- o risco for aceito explicitamente e o envelope não estiver no servidor, **ou**
- houver uma camada adicional (hardware/biometria/segundo fator) que o servidor
  não consiga contornar.

Caso contrário, a recomendação é Keychain/OS, hardware ou uma senha de
desbloqueio separada que nunca sai do dispositivo.

O sistema não controla a escolha da senha do usuário, mas controla as proteções
ao redor:

- exigir comprimento/entropia mínimos e bloquear senhas comuns/comprometidas;
- Argon2id calibrado, salt por usuário e parâmetros versionados;
- rate limit e auditoria de tentativas de desbloqueio;
- aviso explícito na UI: “sua senha de login também protege sua chave de
  assinatura; use uma senha longa e única”;
- reautenticação/biometria para assinaturas de alto valor;
- opção de migrar para Keychain/OS, hardware ou passphrase separada;
- nunca ativar o modo de conveniência sem consentimento informado.

**Responsabilidades:** o usuário escolhe e protege a senha; o sistema recomenda,
impõe mínimos e informa o risco. Não é aceitável esconder que a senha virou
fator de assinatura nem tratar esse modo como equivalente ao hardware.

| Modo | Onde a chave privada fica | Fator de desbloqueio | Garantia |
|---|---|---|---|
| Manual | Dispositivo, protegida por passphrase | Passphrase digitada | Alta com passphrase forte; menor conveniência |
| Keychain/OS | Keychain do sistema | Login/biometria do SO | Alta; depende do dispositivo |
| Hardware | YubiKey/OpenPGP card/TPM/Secure Enclave | PIN/biometria | Mais alta; requer hardware |
| Conveniência | Envelope cifrado no banco/dispositivo | Senha de login (KEK) | Menor; aceitável só com opt-in, Argon2id e aviso |

### 3.3 Revogação, rotação e recuperação

- Revogação é um evento assinado; vale a partir de `revoked_at`.
- Assinaturas antigas continuam válidas para o passado; não contam para eventos
  futuros.
- Rotação: nova chave assinada pela antiga + quórum.
- Perda de chave: quórum de recuperação (ex.: 3-de-5 chaves offline) autoriza
  revogação e novo cadastro.
- **Não existe chave mestra universal** capaz de falsificar assinaturas
  individuais. Recuperação autoriza troca/revogação; não assina no lugar.
- Se o quórum ficar insuficiente, o sistema entra em modo somente leitura e
  exige cerimônia de recuperação; não inventa aprovação.

### 3.4 Como eliminar o risco do servidor comprometido

O risco aparece quando se combinam três elos: a senha de login vai ao servidor,
o envelope da chave privada fica no servidor e a mesma senha abre o envelope.
A regra é **quebrar ao menos um elo**. As opções abaixo não são exclusivas; o
desenho pode combinar mais de uma.

#### 3.4.1 Chave privada fora do servidor (recomendado)

- Chave no Keychain do sistema, Secure Enclave, TPM, YubiKey/OpenPGP card ou
  outro hardware.
- O servidor guarda somente a chave pública, as assinaturas e a política.
- Desbloqueio por login do SO, biometria, PIN do hardware ou toque no token.
- Mesmo que o servidor capture a senha de login, não há chave privada lá para
  abrir.

Vantagens: melhor combinação de conveniência e garantia; não exige decorar
passphrase longa. Limites: perda/roubo do dispositivo exige revogação e
recuperação; hardware tem custo; no navegador é preciso um helper nativo ou
token, não a chave crua em JavaScript.

#### 3.4.2 Segredo de desbloqueio separado

- A chave é cifrada com uma passphrase/PIN que **nunca** é enviada ao servidor.
- O envelope pode ficar no servidor; a senha de login, capturada, não abre a
  chave.
- O segredo pode ser guardado no Keychain para não ser digitado sempre, ou
  solicitado por sessão/assinatura.
- PIN curto exige Argon2id, rate limit e bloqueio; hardware/biometria é melhor
  que PIN curto.

Vantagem: simples e eficaz contra captura da senha de login. Limite: volta a
exigir um segredo que o usuário precisa lembrar ou guardar; se guardado no
Keychain, equivale parcialmente à opção 3.4.1.

#### 3.4.3 PAKE/OPAQUE

- O servidor armazena um verificador/registro PAKE, não a senha.
- O cliente e o servidor executam um protocolo em que o servidor não aprende a
  senha; a KEK é derivada no cliente.
- Um servidor comprometido não consegue derivar a KEK sozinho a partir do
  registro.

Vantagem: permite manter o envelope no servidor e usar a senha de login como
fator de desbloqueio sem entregar a senha. Limites: complexidade de protocolo,
necessidade de biblioteca revisada, cliente nativo confiável, proteção contra
phishing/online guessing e atualização assinada do cliente. Não é um projeto
para criptografia caseira.

#### 3.4.4 Verificador derivado no cliente, com domínios separados

- O cliente deriva dois valores da senha: um verificador de login e uma KEK de
  assinatura, com salts/contextos diferentes.
- O servidor vê apenas o verificador; não consegue derivar a KEK.
- Se o verificador vazar, há risco de pass-the-hash/replay; use TLS, channel
  binding e, de preferência, PAKE.

Vantagem: mais simples que PAKE. Limite: não é equivalente a PAKE; no navegador,
XSS/código malicioso pode capturar a senha antes da derivação. É aceitável como
transição, não como garantia máxima.

#### 3.4.5 Multiassinatura como defesa em profundidade

- 2-de-3 (ou 3-de-5) assinaturas independentes, de chaves distintas.
- Comprometer uma senha/chave não valida uma OS sozinho.
- Para valores altos, hardware para os admins e assinatura do prestador
  afetado.

Não substitui a proteção da chave; reduz o impacto de um comprometimento
individual. O atacante precisa comprometer o quórum, não uma pessoa.

#### 3.4.6 HSM ou serviço de assinatura dedicado

- A chave privada fica num HSM/KMS/serviço de assinatura com política e
  auditoria; o servidor da aplicação não tem a chave.
- O serviço exige autorização forte (hardware/PIN/política) e registra cada uso.
- Protege contra vazamento do banco/servidor da aplicação, mas o próprio serviço
  de assinatura vira um alvo; compromise/política bypass continuam possíveis.

É uma opção empresarial; não elimina a necessidade de quórum, auditoria e
recuperação.

| Solução | Servidor vê a senha? | Chave privada no servidor? | Conveniência | Garantia |
|---|---|---|---|---|
| Keychain/OS | Pode ver a senha de login | Não | Alta (biometria/login) | Alta; depende do dispositivo |
| Hardware | Pode ver a senha de login | Não | Alta (toque/PIN) | Mais alta; requer token |
| Segredo separado | Não (não é enviado) | Envelope cifrado, sim | Média | Alta se o segredo for forte |
| PAKE/OPAQUE | Não aprende a senha | Envelope cifrado, sim | Alta | Alta, com protocolo correto |
| Verificador no cliente | Vê só o verificador | Envelope cifrado, sim | Alta | Média; risco de replay/XSS |
| HSM/serviço | Pode ver a senha de login | Não (no HSM) | Média/Alta | Alta, com política/auditoria |
| Conveniência atual | Sim, na autenticação | Envelope cifrado, sim | Alta | Menor; só com opt-in e risco aceito |

**Recomendação para o AUTOSEG:**

1. Padrão: chave no Keychain/OS ou hardware; assinatura com biometria/PIN/toque;
   nenhuma chave privada no servidor.
2. Se houver backup/multidispositivo com envelope no servidor: usar segredo de
   desbloqueio separado ou PAKE/OPAQUE; nunca a senha de login no fluxo atual.
3. Manter 2-de-3 assinaturas independentes e hardware para alto valor.
4. No web, usar helper nativo/hardware; não colocar a chave privada no
   JavaScript.
5. Tratar comprometimento do servidor como realista: presença do usuário
   (hardware/biometria), atualizações assinadas, auditoria e revogação são
   barreiras; nenhuma promessa de “o servidor nunca consegue” deve ser absoluta.

## 4. M-de-N: assinaturas independentes + política

OpenPGP não implementa threshold cryptography nativa. O desenho usa:

- N assinaturas independentes sobre o mesmo envelope canônico;
- uma política versionada que exige M assinaturas de papéis/chaves elegíveis;
- verificação de que os signatários são distintos;
- verificação de que a chave estava válida na data relevante;
- verificação de que a política aplicável era aquela no momento do evento.

### 4.1 Configuração inicial

- 3 administradores (A, B, C), cada um com chave própria.
- OS validada com **2-de-3** assinaturas de admins distintos.
- Combinações aceitas: A+B, A+C, B+C.
- Uma assinatura isolada não valida a OS.
- A política é um registro imutável/versionado; não é um booleano no código.

### 4.2 Dimensão do prestador afetado

Para eventos que alteram valor financeiro de um prestador:

- 2 de 3 admins **e**
- assinatura da chave do `provider_id` afetado.

Ser admin não substitui a chave do prestador. Se o próprio prestador for admin,
a política ainda exige outro admin distinto; autoaprovação sozinha não vale.

Fallback quando o prestador não tem chave:

- 3-de-5 admins + evento `custodial=true` + justificativa;
- alerta vermelho permanente;
- prazo para cadastrar a chave e sair do fallback.

### 4.3 Política versionada

- `policy_id`, `policy_version`, `required_roles`, `min_signatures`,
  `distinct_signers`, `provider_must_sign`, `max_amount_centavos`,
  `break_glass`.
- Mudar a política exige governança própria; um admin não pode reduzir 2-de-3
  para 1-de-3 sozinho.
- A política aplicada a um evento é a que estava vigente quando ele foi
  proposto; mudanças posteriores não reescrevem o passado.

## 5. Fluxo de assinatura da OS

### 5.1 Snapshot canônico

A OS é um documento versionado, não uma linha mutável. O snapshot contém:

- `os_id` estável, `schema_version`, `canonicalization`;
- `numero_os` como rótulo (renumeração não reescreve snapshot antigo);
- cliente, descrição, relatório técnico, materiais;
- valores em centavos, itens, fórmula (`id`, `version`, inputs, resultado);
- hashes dos anexos;
- estado operacional;
- `policy_id`/`policy_version`;
- contexto/finalidade da assinatura;
- autor, timestamps.

### 5.2 Serialização e hash

- JSON canônico determinístico (RFC 8785/JCS ou equivalente versionado).
- Hash SHA-256 do payload canônico.
- Guardar os **bytes canônicos assinados**, não apenas o objeto reinterpretado.
- Nunca re-serializar um payload antigo com código novo.

### 5.3 Assinaturas

1. Admin A revisa o diff e assina o hash/envelope com a chave privada.
2. Registra admin, fingerprint, assinatura, versão e timestamp.
3. Estado: aguardando segunda assinatura.
4. Admin B revisa a mesma versão e assina.
5. O sistema verifica:
   - assinaturas válidas;
   - duas identidades distintas;
   - mesmo payload/hash;
   - signatários elegíveis pela política;
   - quórum 2-de-3;
   - chaves válidas/não revogadas na data;
   - nenhuma restrição adicional.
6. Quórum atingido: estado **Validada criptograficamente — 2/3**.
7. O comprovante de validação contém hash, versão, política e assinaturas.

A validação não pode ser só um booleano. Deve ser recalculável a partir do
payload, assinaturas, chaves e política.

### 5.4 Estados de aprovação criptográfica

Separados do estado operacional da OS:

- `nao_submetida`
- `aguardando_assinaturas`
- `parcialmente_assinada`
- `validada`
- `integridade_comprometida`
- `substituida_por_nova_versao`
- `custodial` (fallback de prestador sem chave)
- `break_glass`

Mudança em OS validada gera **nova versão**; a anterior e suas assinaturas são
preservadas. A nova versão precisa de nova aprovação.

## 6. Transações financeiras

O mesmo mecanismo serve para:

- confirmação de recebimentos;
- ajustes;
- estornos;
- cancelamentos;
- transferências internas;
- alterações de rateio/repasse;
- alteração de valor de OS/prestador.

Cada transação tem ID único, versão/snapshot imutável, valor em centavos,
contexto, participantes, política e assinaturas.

Políticas configuráveis por risco:

- operação comum: 1-de-3;
- OS concluída: 2-de-3;
- ajuste financeiro sensível: 2-de-3;
- risco elevado: 3-de-3;
- valor de prestador: 2 admins + prestador afetado.

A aprovação criptográfica **não é liquidação bancária**. São estados separados.

## 7. Auditoria e encadeamento

Cada evento do ledger contém:

- evento único, tipo, referência à operação;
- autor/propositor;
- hash do payload;
- hash do evento anterior;
- assinaturas;
- timestamp verificável quando disponível;
- política aplicada.

O encadeamento dificulta alteração silenciosa, mas **não é imutável sozinho**.
Um root/servidor comprometido pode reescrever o banco. Por isso:

- checkpoints periódicos com raiz de Merkle;
- assinatura do checkpoint por quórum;
- publicação externa do checkpoint (Git privado, e-mail assinado, segundo
  servidor, timestamp público);
- backups verificáveis;
- verificador independente;
- comparação do head local com a âncora externa.

Sem âncora externa, não há como provar que o histórico não foi reescrito.

## 8. Verificação independente

O verificador recebe:

1. bytes canônicos da OS/transação;
2. assinaturas;
3. chaves públicas;
4. política aplicável e versão;
5. dados de revogação/validade das chaves no momento relevante.

Ele verifica:

- conteúdo intacto;
- assinaturas válidas;
- identidades/fingerprints;
- quórum e papéis;
- chaves válidas e não revogadas;
- política correta para aquela versão/data;
- cadeia/checkpoint.

A UI do AUTOSEG não é autoridade final. O verificador deve rodar offline/CLI e
ser capaz de produzir um relatório legível e um resultado exit code. Para o site,
planejar agente local ou fluxo de download/verificação; PGP no navegador não é
prático.

## 9. Código-fonte e implantação

Os admins podem ter acesso ao código. Isso não pode equivaler a autorização para
assinar em nome de outro. Prever:

- commits assinados;
- branches principais protegidas;
- revisão obrigatória de mudanças sensíveis (cripto, política, auth, dinheiro);
- builds reproduzíveis e artefatos assinados;
- verificação de integridade da versão distribuída;
- processo controlado de deploy;
- auditoria de mudanças no mecanismo de validação;
- separação entre permissão administrativa e posse de chave privada.

Reconhecer: cliente/servidor comprometido pode mostrar UI falsa, capturar
segredos no desbloqueio ou contornar validações internas. Por isso hardware,
verificação independente e âncora externa são necessários para garantia maior.

## 10. Integração com o projeto atual

- SQLite: tabelas aditivas; estado atual continua como projeção; evento + estado
  na mesma transação.
- Auth atual: sessão não é assinatura; chave privada separada.
- Desktop GTK: assinatura via agente local/hardware.
- Portal do Prestador: proposta/assinatura quando o prestador tiver chave;
  fallback custodiado quando não tiver.
- Portal do Cliente: leitura do estado de validação e evidências; não assina por
  outro.
- PDFs: evidências e decisão PAdES/OpenPGP no flavor AUTOSEG/locale.
- Histórico: OS antigas não recebem assinatura retroativa; genesis checkpoint.
- Financeiro: eventos `finance.*`; isolamento por prestador.
- Meu Auto Financeiro: produto separado; pode usar o core; banco/chaves/políticas
  próprias; sem importar regras AUTOSEG.

## 11. PDFs e assinatura legal

- O PDF pode exibir: estado, quantidade de assinaturas, signatários,
  fingerprints, versão, hash, política.
- Opções: OpenPGP destacada sobre dados canônicos; PAdES no PDF; ambas.
- QR code, imagem de assinatura ou hash impresso **não** são assinatura digital
  válida.
- ICP-Brasil/PAdES e requisitos legais ficam no **locale/flavor AUTOSEG**, não no
  Workaholic core.
- Avaliar com advogado: validade legal, não repúdio, retenção, certificados.
- O snapshot semântico pode ser a verdade técnica; o PDF pode ser o documento
  legal. Definir qual é qual.

## 12. Requisitos e testes

Testes mínimos:

- payload alterado em 1 byte → assinatura inválida;
- assinatura duplicada do mesmo admin → não conta como quórum;
- assinatura de admin não autorizado → rejeitada;
- quórum insuficiente → não aplica;
- quórum atingido → aplica e comprova;
- chave revogada antes/depois do evento;
- rotação/substituição de chave;
- replay de evento;
- concorrência entre duas versões (expected head);
- rollback do banco vs checkpoint;
- canonicalização/golden vectors;
- migração de schema sem reescrever assinatura antiga;
- verificação offline;
- PDF/evidência;
- logs sem segredos/chaves;
- performance com volume.

## 13. Fases

### Fase 0 — decisões

Fechar o mínimo: perfil de custódia de chave, quem assina o quê, política
2-de-3 de OS, tratamento de prestador sem chave, âncora externa, break-glass,
PDF/legal. Registrar ADRs.

### Fase 1 — core em modo sombra

Ledger genérico, canonicalização, hash chain, registro de chaves, verificador
CLI. Registrar eventos sem bloquear escrita. Genesis checkpoint. Sem mudança de
comportamento.

### Fase 2 — OS 2-de-3 em DEV

Aplicar a política 2-de-3 em uma fatia de OS, atrás de flag. UI de proposta,
assinatura, estados, comprovante. Testes de adulteração/quórum/concorrência.

### Fase 3 — financeiro

Eventos financeiros, isolamento de prestador, rateios/repasses/pagamentos.
Checkpoints externos e verificação independente.

### Fase 4 — PDF/legal/hardware

PAdES/ICP-Brasil no AUTOSEG/locale, hardware keys, agente de assinatura,
revisão jurídica, recuperação de quórum.

### Fase 5 — fechar caminhos antigos

Escritas financeiras diretas passam a exigir evento assinado. `portal_auditoria`
deixa de ser fonte de verdade financeira. Relatórios mostram evidência.

Cada fase: backup, migração aditiva, validação, rollback, testes e revisão
externa N3/N4. Sem big-bang.

## 14. Limitações e riscos

- Chave privada comprometida pode assinar como o dono; hardware/limiar/revogação
  reduzem, não eliminam.
- Se M chaves forem comprometidas, a política não protege.
- Root/servidor comprometido pode apagar/mentir; detecção exige âncora externa.
- Cliente comprometido pode capturar a senha de desbloqueio; hardware ajuda.
- PGP é difícil para usuários comuns; UX e suporte são parte do projeto.
- Assinatura PGP não é automaticamente assinatura jurídica brasileira.
- Aprovação criptográfica ≠ liquidação financeira ≠ validade fiscal.
- Não descrever hash chain local como "imutável" sem âncora.
- Não assinar retroativamente registros históricos; usar genesis checkpoint.
- Não usar chave mestra universal; recuperação é quórum, não backdoor.

## 15. Decisões abertas

1. Chave privada: hardware por padrão ou criptografada no banco como opção?
2. Quórum de OS: 2-de-3 fixo ou varia por valor/tipo?
3. Quem são os três admins iniciais e como novos entram/saem?
4. Prestador tem chave própria ou custódia? Qual fallback?
5. Política de alteração de quórum: qual governança impede redução unilateral?
6. Recuperação: 3-de-5 offline? Onde ficam as chaves?
7. Âncora externa: Git privado, e-mail, segundo servidor ou timestamp público?
8. Break-glass: quem, prazo, reversão.
9. PDF: OpenPGP, PAdES ou ambos? ICP-Brasil é requisito?
10. Meu Auto Financeiro usa o core? Com quais políticas e chaves?
11. Quais eventos financeiros exigem assinatura do prestador afetado?
12. Retenção/privacidade dos metadados e evidências.

Estas decisões devem ser respondidas com use case e registradas em ADR; a Fase 1
não depende de todas.

## 16. Referências

- [`ANTI_TAMPERING_FINANCIAL_LEDGER.md`](ANTI_TAMPERING_FINANCIAL_LEDGER.md)
- [`SIGNED_OS_TWO_PARTY_AND_VERSIONING.md`](SIGNED_OS_TWO_PARTY_AND_VERSIONING.md)
- [`../PERMISSIONS_AND_APPROVALS.md`](../PERMISSIONS_AND_APPROVALS.md)
- [`../REVIEW_WITHOUT_DEVELOPER.md`](../REVIEW_WITHOUT_DEVELOPER.md)
- [`../../workaholic/docs/adr/0003-signed-event-ledger.md`](../../workaholic/docs/adr/0003-signed-event-ledger.md)
