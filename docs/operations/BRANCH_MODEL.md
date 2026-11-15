# Modelo de branches: main e dev

**Atualizado:** 2026-11-12
**Produção:** `main` em `3892e7b`, intocada.
**Desenvolvimento:** `dev`, única branch de trabalho.

## Runtime

- A MAIN roda a partir do worktree `/Users/idkosx/AUTOSEG_MAIN_RUNTIME`, que
  fica fixo na branch `main`. Nunca iniciar a MAIN a partir do diretório da DEV.
- A DEV roda a partir de `/Users/idkosx/GestaoServicos_DEV`, na branch `dev`.
- O comando `./autoseg` recusa iniciar a MAIN quando o diretório atual não está
  na branch `main`, para evitar que código de desenvolvimento escreva no banco
  de produção.
- Worktree de runtime não é branch nova: é só um checkout de apoio.

## Regra

- `main` é produção. Só recebe merge da `dev`, depois de homologação e
  autorização explícita.
- `dev` é a única branch de desenvolvimento. Todo trabalho novo parte dela.
- Branch temporária só é criada com autorização, tem um objetivo único e é
  apagada depois do merge na `dev`. O padrão é não criar branch.
- Worktree temporário segue a mesma regra: um por tarefa, removido no fim.

## O que foi consolidado em 2026-11-12

Antes da consolidação existiam 21 branches locais e 24 remotas. As 18 branches
históricas de P0-AUTH, login, sessão, identidade, policy e portal eram etapas
intermediárias já contidas na branch de feedbacks. Nenhum commit delas foi
perdido.

A `dev` foi criada a partir da branch de feedbacks e recebeu:

- os quatro commits de documentação que estavam só na `main`;
- a limpeza do Meu Auto Financeiro embutido, mantendo o bridge de empréstimos;
- as correções dos feedbacks 143–156 da MAIN.

O commit de documentação do outbox ficou preservado nas tags de arquivo; ele
era um prompt histórico já superado pelo congelamento do P0-AUTH.

## Backups e rollback

Antes de apagar qualquer branch ou worktree:

- bundle completo do repositório:
  `~/Library/Application Support/AUTOSEG/backups/consolidation_20261112/repo-all-refs-20261112.bundle`;
- manifesto de branches e commits:
  `branch-manifest.txt` na mesma pasta;
- alterações não commitadas dos worktrees antigos: `worktrees/<nome>/`;
- banco DEV: `autoseg_teste_after_main_feedbacks_20261112.db`;
- banco DEV antes da cópia da foto 150:
  `autoseg_teste_before_anexo150_copy_20261112.db`.

Cada ponta de branch antiga também está numa tag `archive-20261112/*`. Para
recuperar qualquer estado, basta restaurar o bundle num clone novo ou conferir
a tag correspondente.

## Fluxo de release

1. Trabalhar e testar na `dev`.
2. Homologar no DEV com as flags ainda em `0`, salvo decisão explícita.
3. Com autorização, merge da `dev` na `main`.
4. Criar uma tag de release na `main`.
5. Voltar a `dev` para o próximo ciclo.

A `main` nunca é resetada para a `dev` nem recebe force-push. O histórico da
produção é preservado.
