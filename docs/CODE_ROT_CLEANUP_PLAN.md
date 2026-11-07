# Plano de limpeza da podridão de código

**Status:** plano de engenharia. Não é um convite a big-bang nem a “limpar tudo
de uma vez”. Cada onda precisa de testes, backup e rollback.

**Contexto:** código gerado por IA pode acumular prompt em comentário, regra
duplicada, ramo circular, exceção silenciosa e abstração sem consumidor. O
comentário é só o sintoma mais visível; a limpeza precisa atacar comportamento,
dados e estrutura.

---

## 1. O que contamos hoje

Baseline em 2026-11-07, após a suíte de testes e a limpeza dos scripts:

| Indicador | Baseline | Observação |
|---|---:|---|
| Comentários com prompt/IA/revisão/shortcut | **0 alto, 0 baixo** | `scripts/audit_comments.py --strict` |
| `except Exception`/bare except | **152** | nem todos são ruins; 32 são silenciosos |
| Exceções amplas silenciosas | **32** | `pass`/`continue`/`return None` engolindo erro |
| Funções com 60+ linhas | **56** | algumas são handlers aninhados; mede complexidade |
| Classes com 400+ linhas | **5** | `PortalPrestador`, `Handler`, `Janela`, `DialogoOS` e afins |
| SQL direto em UI/HTTP | **43 linhas** | restante no site; shell GTK em zero |
| TODO/FIXME sem issue | **0** | após o ajuste do auditor |
| Arquivos grandes | `portal_prestador.py` ~3.4k, `gtk_app.py` ~2.3k, `gtk_dialogos.py` ~2.2k | monólitos conhecidos |

Os números são **triagem**, não sentença. `except Exception` numa borda de UI
que mostra erro e registra log pode ser aceitável; `except Exception: pass` em
dinheiro, PDF ou status de OS não é.

---

## 2. Categorias de podridão

1. **Prompt rot** — comentário/docstring com pedido, IA, `REVxx`, “shortcut”.
2. **Logic rot** — regra duplicada, ramo circular, validação redundante,
   condição que nunca ocorre.
3. **Error rot** — exceção ampla silenciosa, erro virando “sucesso”, mensagem
   genérica sem contexto.
4. **Data rot** — schema espalhado, migração sem versão, SQL direto na UI,
   escrita concorrente sem transação.
5. **Structure rot** — arquivo monólito, UI/HTTP com regra de negócio, camadas
   sem contrato, abstração sem consumidor.
6. **Test rot** — teste que espelha implementação, cenário frágil, pouca
   caracterização dos fluxos críticos, suíte lenta/sem isolamento.
7. **Dependency rot** — import não usado, código morto, dependência pesada sem
   necessidade, versão fixa sem motivo.

---

## 3. Prioridade

Fórmula prática:

```text
prioridade = impacto × probabilidade × alcance / cobertura de teste
```

| Nível | Critério | Exemplos |
|---|---|---|
| **P0** | dinheiro, autenticação, perda de dados, status de OS, PDF/email fiscal | exceção silenciosa em rateio, financeiro, encerramento, estoque |
| **P1** | integridade de dados, duplicação de regra, schema/migração | duas regras de status, SQL divergente entre portal e GTK |
| **P2** | estrutura e testabilidade | SQL na UI, funções gigantes, handlers duplicados |
| **P3** | estilo, nomes, comentários, código morto | revisão de comentário, import não usado |

A ordem de execução **não** é a ordem do ranking: primeiro o que pode causar
dano real; depois o que reduz risco futuro.

---

## 4. Ondas de limpeza

### Onda 0 — Rede de segurança

- backup do banco e dos anexos antes de mexer em fluxo crítico;
- caracterização dos fluxos P0: encerrar OS, cancelar, rateio, financeiro,
  estoque, PDF, permissões;
- baseline dos auditores salvo em issue/PR;
- nenhuma mudança de comportamento nesta onda.

**Saída:** testes de caracterização verdes; rollback documentado.

### Onda 1 — Parar de piorar

- `audit_comments.py --strict` no pre-PR/CI;
- PR sem comentário de prompt, sem `REVxx`, sem `shortcut` sem issue;
- exceção ampla nova precisa de justificativa e log;
- diff pequeno; comportamento separado de estrutura;
- checklist “este código faz sentido sem o prompt?”.

**Saída:** nenhum achado alto novo; revisão humana obrigatória.

### Onda 2 — Limpeza mecânica de baixo risco

- comentários/docstrings (já feito);
- imports não usados, constantes duplicadas, código morto;
- TODO/FIXME com issue ou remoção;
- nomes óbvios e mensagens repetidas;
- nenhuma mudança de comportamento.

**Saída:** auditores estáveis; sem regressão.

### Onda 3 — Erro e observabilidade

- triar os **32 broad excepts silenciosos**:
  - P0: dinheiro, OS, PDF, estoque, autenticação → corrigir primeiro;
  - substituir por exceções específicas;
  - logar contexto sem dados pessoais;
  - devolver erro ao usuário em vez de “sucesso”;
  - manter catch amplo apenas na borda da UI que já mostra erro e registra log.

**Saída:** nenhum `except Exception: pass` em fluxo P0; logs e mensagens
testados.

### Onda 4 — Regras e SQL fora da UI

- continuar o item #1: clientes e resumos de OS já saíram;
- próximos: detalhe de OS, financeiro, estoque, anexos/eventos;
- repositórios/services por agregado, com testes de caracterização;
- comparar portal, GTK e API usando o mesmo serviço.

**Saída:** nenhuma regra de negócio nova na UI; SQL restante mapeado.

### Onda 5 — Schema, migrações e jobs

- runner versionado de migrações;
- fila SQLite para PDF/e-mail/importação;
- idempotência e retry;
- backup/restore testado.

**Saída:** migração de banco antigo testada; jobs não duplicam.

### Onda 6 — Remover legado

- remover caminho antigo só quando o adaptador for o único escritor;
- atualizar `PLATFORM_MIGRATION_LEDGER`;
- remover código morto e interfaces sem consumidor;
- não renomear coluna de produção sem migração.

**Saída:** uma fonte de verdade por fatia; legado removido com rollback.

---

## 5. Backlog inicial

| ID | Item | Prioridade | Estado |
|---|---|---|---|
| CR-001 | Prompt/comments leakage | P3 | **Mitigado**: auditoria 0/0; manter no CI |
| CR-002 | 32 exceções amplas silenciosas | P0/P1 | **Aberto**: triar por fluxo |
| CR-003 | 149 `except Exception` | P1 | **Aberto**: separar borda aceitável de erro engolido |
| CR-004 | 126 linhas de SQL em UI/HTTP | P2 | **Parcial**: clientes, resumos de OS e portal extraídos |
| CR-005 | 52 funções / 4 classes longas | P2 | **Aberto**: quebrar por fatia, não por estética |
| CR-006 | Schema/migrações espalhados | P1 | **Aberto** |
| CR-007 | Sessão/CSRF/HTML duplicados nos portais | P1 | **Aberto** |
| CR-008 | Código morto/imports/dependências | P3 | **Aberto** |
| CR-009 | Testes monolíticos e cobertura P0 | P1 | **Aberto** |
| CR-010 | Jobs em thread sem fila | P1 | **Aberto** |

---

## 6. Ferramentas

```bash
python3 scripts/audit_comments.py --strict
python3 scripts/audit_code_rot.py
```

- `audit_comments.py` — prompt/IA/revisão/shortcut em comentários e docstrings.
- `audit_code_rot.py` — broad/silent exceptions, funções/classes longas,
  TODO sem issue, SQL em UI/HTTP.
- Opcional depois: `ruff`/`pyflakes` (imports), `vulture` (código morto),
  `radon` (complexidade), `jscpd` (duplicação), `coverage` (fluxos P0).
- Nenhuma ferramenta substitui teste de comportamento e revisão humana.

---

## 7. Regras do processo

- **Uma onda por vez.** Não misturar limpeza de comentário, refatoração e
  mudança de comportamento no mesmo PR.
- **Teste antes.** Fluxo P0 sem caracterização não entra em limpeza.
- **Não apagar código por intuição.** Código morto precisa de busca de uso,
  teste e rollback.
- **Não trocar tudo por Rust para “limpar”.** Linguagem não resolve design.
- **Não medir sucesso por linha removida.** Medir por risco reduzido,
  comportamento preservado e teste verde.
- **Revisão independente:** a IA pode propor, executar e revisar em outra
  sessão, mas não aprovar a própria mudança. N3/N4 exigem revisão humana
  externa; sem revisor, ficam em DEV/flag. Ver
  `docs/REVIEW_WITHOUT_DEVELOPER.md`.
- **Pequenos commits:** um por fatia/onda, com mensagem que diga o que foi
  limpo e o que foi preservado.

---

## 8. Métricas de saída

- comentários altos: **0** e sem regressão;
- exceções amplas silenciosas: **0 em fluxos P0**;
- SQL em UI: reduzir por fatia, com mapa do restante;
- funções/classes longas: reduzir por fatia, sem “quebrar por quebrar”;
- cobertura de caracterização dos fluxos P0: alvo acordado com o dono;
- PRs menores; menos retrabalho e menos regressão;
- tempo para explicar um módulo sem o prompt original.

---

## 9. Próximas três ações

1. Commitar este plano e o auditor de podridão.
2. Triar as **32 exceções silenciosas** e corrigir primeiro as de dinheiro, OS,
   PDF e estoque.
3. Escolher **uma** fatia P0 (por exemplo, encerramento de OS + rateio) para
   caracterização e limpeza de comportamento; não começar por comentário.

O comentário já está sob controle. Agora o alvo é o comportamento.
