# Handoff — estado atual

**Atualizado:** 2026-11-09
**Versão:** `9.6.0-dev.73`
**Branch de trabalho:** `develop`
**Produção:** MAIN intocada; servidor e túneis parados.

Este é o ponto de retomada. O índice completo fica em
[`docs/README.md`](README.md); o histórico de mudanças no
[`CHANGELOG.md`](../CHANGELOG.md); o plano no [`ROADMAP.md`](ROADMAP.md).

> **Direção registrada em 2026-11-10:** o AUTOSEG é a primeira **prestadora de
> serviço** do ecossistema Officina — não uma loja. O alvo é um site, um link e
> um login, com conta/vínculo/contexto e política por objeto. O site e o GTK
> atuais são as sementes do Officina Web/GTK. Nenhuma mudança de código foi
> feita nesta fase. Ver
> [`planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md`](planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md)
> e [`planning/OFFICINA_WEB_AND_GTK.md`](planning/OFFICINA_WEB_AND_GTK.md).

## O que está funcionando

- App desktop GTK4/libadwaita em macOS e Linux.
- Portal do prestador e portal do cliente em processos separados.
- Banco SQLite fora do repositório; API headless e GUI do site em comandos separados.
- Cadastros, OS, materiais, fotos, relatórios, PDF, financeiro, estoque,
  orçamento, notas fiscais e e-mails em rascunho.
- Permissões e aprovações documentadas; `policy.yaml` carregado em runtime.
- Numeração configurável de OS, com aliases para números antigos.
- DEV abre em modo servidor por padrão; se o usuário escolher Local no login, usa o banco local em `~/Library/Application Support/AUTOSEG/local` (macOS) ou `~/.local/share/autoseg/local` (Linux).
- Login obrigatório de prestador, local ou servidor, com identidade e logout.
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

- Suíte não visual: **343 testes, 0 falhas, 1 skip**.
- Scripts de aceitação atualizados e passando: `tests/test_portal_v4.py`,
  `tests/test_fluxo_v5.py`, `tests/test_fluxo_v6.py`, `tests/test_fluxo_v7.py`,
  `tests/test_fluxo_cliente_v94.py` e `tests/test_rev09_fluxo_os.py`.
- Comandos e critérios em [`TESTES.md`](../TESTES.md).
- Scripts `test_v9.py`, `test_v91.py`, `test_v92.py` e `test_v94_correcoes.py`
  são legado da arquitetura anterior e não indicam regressão.

## Pendências principais

1. **MAIN:** ensaiar e executar a migração de numeração com backup e janela.
2. **Login/auth:** básico implementado (local/servidor, identidade, logout e
   token). Faltam Keychain/libsecret, inatividade, auditoria durável de login e
   revisão humana externa.
3. **Permissões:** ligar a política pura ao `AppService` e aplicar no servidor;
   o login identifica o prestador, mas ainda não aplica AUT-001 a AUT-021.
4. **API remota:** clientes, OS, prestadores, financeiro, PJ, catálogo,
   estoque, composição e PDF já passam pelo servidor; falta sync.
5. **Login de cliente no GTK:** adiado por ser nicho; primeiro aplicar
   permissões de admin × funcionário no serviço.
6. **Qualidade:** triar exceções amplas silenciosas e rodar o primeiro ciclo de
   revisão externa em dinheiro/OS/PDF.
7. **CI:** workflows continuam modificados e não publicados por falta de token
   GitHub com escopo `workflow`.

## Bloqueios e riscos

- Não há desenvolvedor humano dedicado. Mudanças N3/N4 exigem revisor humano
  externo ou permanecem em DEV/flag.
- MAIN não recebeu os commits N3 da `develop`.
- Modo remoto de dados ainda é incompleto; não prometer GTK contra celular.
- Não sincronizar `dados.db` como arquivo (Syncthing/Dropbox).
- A migração de numeração não pode usar `MAX+1` nem adivinhar datas.

## Próximas três ações

1. Rodar o ensaio da migração de numeração em cópia da MAIN e trazer o relatório
   antes/depois.
2. Depois de aprovado, migrar a MAIN com backup, janela e smoke.
3. Implementar a política de permissões ligada ao `AppService`, começando pelos
   casos AUT-001 a AUT-021.

## Comandos úteis

```bash
./autoseg dev        # app DEV
./autoseg app-local  # local-only, sem portas
./autoseg server     # servidor de dados DEV (8766)
./autoseg site       # GUI do site DEV (8865/8866)
./autoseg api        # servidor headless de produção
./autoseg paths      # onde ficam banco e dados
```

```bash
./.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```
