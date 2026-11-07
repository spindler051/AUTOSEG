# Revisão sem desenvolvedor humano

**Status:** política de risco. Não substitui um desenvolvedor humano; define o
que é aceitável enquanto não existe um.

## 1. Premissa honesta

Sem um desenvolvedor humano revisando código, o risco **não é zero**. Testes,
auditores e uma segunda IA reduzem erro, mas não substituem julgamento humano
em dinheiro, permissões, migração de dados, segurança e obrigações fiscais.

A política é:

```text
Baixo risco: automação + segunda IA + aceite do dono.
Alto risco: revisão humana externa obrigatória.
Sem revisor: a mudança fica na DEV/flag; não vai para produção.
```

Não fingir que “IA revisou” é revisão humana.

---

## 2. Níveis de risco e revisão

| Nível | Exemplos | Verificação mínima | Pode ir para MAIN? |
|---|---|---|---|
| **N0 — cosmético** | comentário, texto, documentação, espaçamento sem comportamento | auditor + compilação | sim, com diff pequeno |
| **N1 — leitura/UI** | tela de listagem, read-only query, tema, navegação | testes automatizados + segunda IA + smoke do dono | sim, se não toca dados |
| **N2 — escrita comum** | cadastro de cliente, edição de OS sem dinheiro, anexo | caracterização + testes HTTP/GTK + segunda IA + smoke | com cautela; ideal revisão externa antes de produção |
| **N3 — crítico** | encerramento de OS, rateio, financeiro, estoque, PDF/email, permissões, schema/migração | testes P0 + revisão humana externa + backup + rollback | **somente com revisão externa** |
| **N4 — irreversível** | apagar/renomear coluna, migração em produção, exclusão de dados, mudança de autenticação | revisão externa + dono + plano de rollback + backup | **não sem revisão e aprovação explícita** |

O nível é definido pelo **pior efeito possível**, não pela quantidade de linhas.

---

## 3. O que a segunda IA faz

A IA que escreveu o código **não aprova** o próprio código. A revisão usa outra
sessão/agente, de preferência outro modelo.

Pacote entregue ao revisor:

1. pedido original em linguagem de produto;
2. diff completo;
3. testes adicionados/alterados e saída dos testes;
4. arquivos e dados tocados;
5. riscos, rollback e o que **não** foi alterado;
6. checklist do nível de risco.

Prompt do revisor:

> “Você é um revisor adversarial. Encontre falhas de comportamento, perda de
> dados, concorrência, segurança, regra duplicada, exceção engolida, teste
> fraco e regressão de UI. Não aprove sem evidência. Lista arquivo:linha,
> severidade e teste que reproduz.”

Regras:

- revisor não vê a “justificativa” do autor antes de analisar o diff;
- achado P0/P1 bloqueia;
- “parece ok” não é evidência;
- a revisão da IA é registrada como **AI review**, nunca como revisão humana.

---

## 4. Automação obrigatória

Antes de qualquer merge:

```bash
python3 -m py_compile <arquivos alterados>
python3 -m unittest <suítes relevantes>
python3 scripts/audit_comments.py --strict
python3 scripts/audit_code_rot.py
```

Para N2+:

- teste HTTP real com banco temporário;
- teste de interface (Playwright/GTK) quando houver UI;
- backup + restauração do banco;
- migração de banco antigo;
- golden PDF com extração de texto;
- teste de permissões (admin, prestador, cliente);
- concorrência/idempotência quando houver dinheiro ou estoque.

Ferramentas recomendadas quando o ambiente permitir:

- `ruff`/`pyflakes` — imports e erros estáticos;
- `mypy`/`pyright` — tipos;
- `bandit` — segurança;
- `pip-audit` — dependências;
- `coverage` — foco nos fluxos P0;
- `vulture` — código morto;
- `radon` — complexidade;
- `hypothesis` — propriedades de dinheiro/estado;
- `mutmut` — qualidade dos testes.

Nenhuma ferramenta sozinha prova ausência de podridão.

---

## 5. Papel do dono do produto

O dono não precisa revisar código. Precisa:

- definir o comportamento esperado em linguagem simples;
- testar o fluxo em um banco de teste;
- aprovar o que o usuário vê;
- autorizar mudanças de dados/dinheiro;
- decidir o que fica em DEV e o que vai para MAIN.

Roteiro de aceite:

1. abrir uma cópia de teste;
2. executar o fluxo como usuário;
3. comparar com o comportamento anterior;
4. registrar o que mudou;
5. aprovar ou rejeitar.

Isso é **aceite de produto**, não revisão de código.

---

## 6. Revisão humana externa

Para N3/N4, contratar algumas horas de um desenvolvedor externo é mais barato
que um incidente financeiro. O pacote de revisão acima reduz o custo.

Onde procurar:

- freelancer com experiência em Python/SQLite;
- ex-colega ou conhecido desenvolvedor;
- comunidade open-source/local;
- auditoria pontual antes de produção.

Escopo sugerido de 1–2 horas:

- revisar o diff e os testes;
- apontar riscos de dados/dinheiro;
- validar rollback;
- assinar um parecer curto.

Se não houver revisor disponível:

- a mudança fica em DEV, atrás de flag;
- não vai para MAIN;
- o risco residual é registrado no documento/issue.

---

## 7. Deploy seguro

- backup consistente antes de migração;
- banco de teste separado;
- feature flag/rollback;
- smoke test no MAIN antes de liberar;
- monitorar erros e logs;
- não publicar dados reais em Quick Tunnel;
- uma mudança crítica por vez.

Sem revisor, uma mudança N3/N4 **não é considerada pronta**, mesmo com testes
verdes.

---

## 8. O que não fazer

- dizer que “a IA revisou” e tratar como revisão humana;
- deixar o mesmo agente aprovar o próprio diff;
- pular teste porque não há dev;
- mandar N3/N4 direto para MAIN “porque passou nos testes”;
- esconder risco residual;
- usar Rust, reescrita ou “limpeza geral” como substituto de revisão.

## 9. Registro

Toda mudança N2+ deve registrar:

```text
Nível de risco:
Testes executados:
AI review (modelo/sessão):
Revisão humana externa: sim/não/quem
Backup:
Rollback:
Risco residual:
```

O documento `docs/CODE_ROT_CLEANUP_PLAN.md` usa esta política para decidir o que
pode avançar em cada onda.

## 10. Relação com os outros documentos

- `docs/CODE_ROT_CLEANUP_PLAN.md`
- `docs/CODE_COMMENT_POLICY.md`
- `AGENTS.md`
- `docs/HUMAN_CENTERED_DECISIONS.md`
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md`
- `docs/EXTERNAL_AI_REVIEW_ROUTINE.md`
