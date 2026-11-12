## P0-AUTH-CLOSE-GATE-HARDENING — DEV freeze (2026-11-12)

Branch `feat/p0-auth-close-gate`, commit `fafcd8e`; base do hardening
`2ba7d46`. Suíte completa: **724 OK · 1 skip**. O reenvio manual tem um único
caminho, dependente da outbox; sem outbox ele falha antes de enviar. O
dispatcher exige `recipient_refs`; o rollback recusa projeções com referências
simbólicas; o cleanup do PDF é limitado ao worker que ainda tem o lease.
`AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0`. MAIN em `3892e7b`, intocada.

Ainda há três caminhos antigos fora do contrato do reenvio manual: o campo
`emails_adicionais` no formulário de conclusão, o envio automático no branch
`not use_outbox` e chamadas diretas aos serviços sem `connection`. Antes da
MAIN, falta homologar a branch no DEV 8866 com a outbox instalada, ensaiar
migração/rollback e autorizar a outbox em produção. Estado detalhado em
[`operations/P0_AUTH_DEV_FREEZE.md`](operations/P0_AUTH_DEV_FREEZE.md).

## P0-AUTH-CLOSE-GATE-FIXES — validação DEV (2026-11-12)

O fechamento adicional corrige `publico` em OS encerrada, faz a verificação de
status e confirmação de PDF na mesma `BEGIN IMMEDIATE`, preserva e-mails
válidos na projeção de rollback e permite restauração operacional explícita da
quarentena com idade zero. `AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0` permanece;
não foi feita integração com MAIN ou aprovação de implantação.



## P0-AUTH-CLOSE-GATE — DEV handoff

The close-gate review extends transaction-guarded attachment/invoice commands
with staged rotation, recoverable quarantine and a DEV-only worker. Manual
email retry requires a fresh operation ID plus duplicate acknowledgment;
recipient identities remain references and are resolved at dispatch. PDF
publication validates hashes before adopting an orphan. The original
`AUTOSEG_OBJECT_POLICY_ENFORCEMENT=0` default remains unchanged. Deploy only
after reviewing the attached test report and any residual issues; MAIN is
not part of this change.

### P0-AUTH-FINAL — outbox DEV, ativação pendente (2026-11-11)

Migração **aditiva exclusiva de DEV** `os_effect_outbox` com backup, lease,
reconciliação e publicação pós-commit. Revalidações e transações compartilhadas
foram ampliadas em escritores de OS. Não é certificação de TOCTOU totalmente
fechado: os caminhos HTTP de anexos/nota já usam guarda e efeitos
recuperáveis, porém efeitos de filesystem e consumidores legados diretos
precisam de homologação e reconciliação operacional antes da ativação. `AUTOSEG_OBJECT_POLICY_ENFORCEMENT`
permanece `0`. Consultar `docs/operations/OBJECT_POLICY_ROLLOUT.md` e o
`NOTES.md` desta entrega; não habilitar na MAIN.

# Handoff — estado atual

**Atualizado:** 2026-11-12
**Versão:** `9.6.0-dev.73`
**Branch de trabalho:** `feat/p0-auth-close-gate` (`fafcd8e`); MAIN em `3892e7b`.
**Produção:** MAIN intocada; 8765/8766 continuam no código antigo.

Este é o ponto de retomada. O índice completo fica em
[`docs/README.md`](README.md); o histórico de mudanças no
[`CHANGELOG.md`](../CHANGELOG.md); o plano no [`ROADMAP.md`](ROADMAP.md).

> **Direção registrada em 2026-11-10:** o AUTOSEG é a primeira **prestadora de
> serviço** do ecossistema Officina — não uma loja. O alvo é um site, um link e
> um login, com conta/vínculo/contexto e política por objeto. O site e o GTK
> atuais são as sementes do Officina Web/GTK. As peças 5.1–5.5 e 6.1–6.4 estão
> integradas atrás de flags; a rota final é `/login`; a ativação de produção
> segue pendente. Ver
> [`planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md`](planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md)
> e [`planning/OFFICINA_WEB_AND_GTK.md`](planning/OFFICINA_WEB_AND_GTK.md).

## P0-AUTH — implementação parcial em revisão

- Reabertura de OS `Pendente`: permissão `work_item.reopen` exige admin
  mesmo com a flag de enforcement desligada; rechecagem dentro de
  `BEGIN IMMEDIATE` para o comando `abrir`.
- Guardas adicionais de vínculo/status foram inseridas nos writers de
  atribuição, assunção, arquivamento, rota, cancelamento e fotos.
- **Gate não concluído:** outros writers ainda fazem escritas em transações
  independentes. A flag deve permanecer `0`; conferir `BLOCKED.md` da peça.

## O que está funcionando

- App desktop GTK4/libadwaita em macOS e Linux.
- Site único do Officina Web para prestador e cliente; sem segundo processo web.
- Banco SQLite fora do repositório; API headless e GUI do site em comandos separados.
- Cadastros, OS, materiais, fotos, relatórios, PDF, financeiro, estoque,
  orçamento, notas fiscais e e-mails em rascunho.
- Permissões e aprovações documentadas; `policy.yaml` carregado em runtime.
- Numeração configurável de OS, com aliases para números antigos.
- DEV abre em modo servidor por padrão; se o usuário escolher Local no login, usa o banco local em `~/Library/Application Support/AUTOSEG/local` (macOS) ou `~/.local/share/autoseg/local` (Linux).
- Login único em `/login`: prestador e cliente no site, com a flag ligada;
  `/entrar` foi removida e responde `404`. Com a flag desligada, `/login` serve
  o formulário antigo do prestador.
- A tela de login do site reutiliza o split-screen do AUTOSEG; o GTK continua
  provider-only.
- GTK com login local ou de servidor, identidade e logout real: o botão/menu
  **Sair** revoga o token, limpa a sessão e volta ao login.
- Sessão de servidor com token revogável; local não persiste senha.
- Paridade de prestador: GTK tem notas/e-mails; site tem prestadores,
  estoque, caixa e composição para admin.
- Sem servidor, as listas ficam vazias e a janela mostra aviso de indisponível.
- O app verifica o servidor a cada 5 s e avisa quando ele cai ou volta.
- Workaholic integrado apenas na fatia de clientes; o restante continua no
  código legado.
- Feedbacks abertos da DEV corrigidos: OS rápida em uma tela com cliente
  opcional, aviso de duplicidade, cancelamento só com motivo, Pendente sem
  e-mail, retorno de Iniciada para Pendente, fotos com salvamento automático,
  ordem das abas, tema claro/escuro com sete acentos, composição estruturada e
  ordens recentes no Início do GTK. O campo Material pesquisa e autocompleta o
  estoque, sem o segundo botão “Adicionar do estoque”. A situação da OS agora
  é escolhida em popup, e o responsável é transferido pelo select de admin na
  Identificação. A aba Mídias concentra fotos, Fechamento, nota fiscal e
  confirmação; tema e acento ficam em Configurações, salvos na conta.
- Ciclo de feedbacks 57–60 e 62: busca/criação de cliente na OS, lista com
  **Dados incompletos**, conclusão sem destinatário, forma de pagamento
  obrigatória e erros de login/formulários em toast/inline sem perder campos.

## Estado da numeração

- A DEV de teste já foi migrada para `YYMMDDNNN` (somente dígitos).
- A MAIN continua com 23 OS em `OS-00xx`.
- Números antigos viram aliases; PDFs, e-mails e documentos já emitidos não são
  reescritos.
- A migração da MAIN exige ensaio em cópia, backup, janela e smoke.

## Onde ficam os dados

- Servidor de produção: `/var/lib/autoseg` no Linux e
  `/Library/Application Support/AUTOSEG` no macOS.
- Servidor DEV: `<dados do usuário>/server-dev`; banco em
  `dados_teste/autoseg_teste.db`.
- GTK local: `<dados do usuário>/local`.
- `./autoseg paths` imprime os caminhos efetivos, inclusive overrides.
- Detalhes, permissões e backup em
  [`operations/DATA_STORAGE.md`](operations/DATA_STORAGE.md).
- A MAIN antiga em `~/gestaoservicos_MAIN` não é lida automaticamente; a
  cópia para o modo local é uma janela separada, documentada no arquivo acima.

## Testes

- Integração 6.4 + login único: **256 testes focados OK**.
- Regressão do portal: **65 OK, 1 skip**.
- Portal antigo do cliente: **3 OK**.
- `audit_comments.py --strict`: **0 achado(s) alto(s), 0 baixo(s)**.
- GTK: smoke de inicialização e logout real validados; o token antigo foi
  rejeitado pela API após o logout.
- Comandos e critérios em [`TESTES.md`](../TESTES.md).
- Scripts `test_v9.py`, `test_v91.py`, `test_v92.py` e `test_v94_correcoes.py`
  são legado da arquitetura anterior e não indicam regressão.

## Pendências principais

1. **MAIN:** ensaiar e executar a migração de numeração com backup e janela.
2. **Login/auth:** 5.1–5.5 integradas; `/login` é a rota única e o GTK tem
   logout real. Faltam ativação de produção, Keychain/libsecret, inatividade,
   auditoria durável de login e revisão humana externa.
3. **Permissões:** 6.2 está no código atrás de
   `AUTOSEG_OBJECT_POLICY_ENFORCEMENT`; falta corrigir ou aceitar o TOCTOU,
   rodar os testes negativos de isolamento e decidir a ativação em produção.
4. **API remota:** clientes, OS, prestadores, financeiro, PJ, catálogo,
   estoque, composição e PDF já passam pelo servidor no fluxo do prestador;
   faltam os endpoints client-safe e a sincronização.
5. **Login de cliente no GTK:** planejado como peça 6.5, remote-only, depois do
   gate P0 de autorização. Faltam login desktop de cliente, sessão genérica,
   API client-safe, navegação reduzida, testes negativos e rollout. Ver
   [`planning/GTK_CLIENT_MODE.md`](planning/GTK_CLIENT_MODE.md).
6. **Qualidade:** triar exceções amplas silenciosas e rodar o primeiro ciclo de
   revisão externa em dinheiro/OS/PDF.
7. **CI:** workflows continuam modificados e não publicados por falta de token
   GitHub com escopo `workflow`.

## Bloqueios e riscos

- Não há desenvolvedor humano dedicado. Mudanças N3/N4 exigem revisor humano
  externo ou permanecem em DEV/flag.
- A ativação de produção do enforcement por objeto está bloqueada pelo TOCTOU
  entre autorização e writer.
- Cliente no GTK depende desse gate; a 6.5 é remote-only e não pode duplicar
  regra de OS/permissão no widget.
- Modo remoto de dados ainda é incompleto; não prometer GTK contra celular.
- Não sincronizar `dados.db` como arquivo (Syncthing/Dropbox).
- A migração de numeração não pode usar `MAX+1` nem adivinhar datas.

## Próximas três ações

1. Fechar o TOCTOU e decidir a ativação de
   `AUTOSEG_OBJECT_POLICY_ENFORCEMENT` em produção, com testes negativos de
   isolamento.
2. Implementar a peça 6.5 (cliente no GTK remote-only) depois desse gate:
   login, `/me`, home com as próprias OS, logout e bloqueio das rotas de
   prestador.
3. Rodar o ensaio da migração de numeração em cópia da MAIN e trazer o
   relatório antes/depois; depois migrar com backup, janela e smoke.

## Comandos úteis

```bash
./autoseg dev        # app DEV
./autoseg app-local  # local-only, sem portas
./autoseg server     # servidor de dados DEV (8766)
./autoseg site       # GUI do site DEV (8866)
./autoseg api        # servidor headless de produção
./autoseg paths      # onde ficam banco e dados
```

```bash
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```
