# Rotina de revisão externa com outras IAs

**Status:** processo de qualidade. Não é revisão humana e não autoriza
reescrita geral. Serve para usar ChatGPT/Gemini como **revisores externos
independentes**, com pesquisa de boas práticas, antes de ondas grandes de
features.

**Relação com a política de risco:** `docs/REVIEW_WITHOUT_DEVELOPER.md`.
IA externa é evidência complementar; N3/N4 continuam exigindo revisor humano
externo.

---

## 1. Quando rodar

- **Antes de uma onda grande de features** — 1 ou 2 arquivos críticos.
- **Mensalmente** — um arquivo por ciclo, sem pressa.
- **Depois de incidente** — o arquivo/fluxo envolvido.
- **Antes de migração de schema, mudança de dinheiro ou permissões** — sempre.
- **Depois de um diff grande** — revisão focada no diff, não no arquivo inteiro.

Não rodar em paralelo com uma refatoração grande. O arquivo precisa estar
estável para o revisor entender o comportamento.

---

## 2. Escolha do arquivo

Um arquivo por rodada. Prioridade:

| Prioridade | Arquivos | Motivo |
|---|---|---|
| P0 | `fluxo_os.py`, `produtividade_os.py`, `pdf_cliente_v9.py`, `composicao.py` | encerramento, dinheiro, rateio, PDF |
| P0/P1 | `prestadores_ext.py` | anexos, PDF, e-mail, schema |
| P1 | `portal_negocios.py`, `api_financeiro.py` | regras de OS/financeiro e API |
| P2 | `portal_prestador.py`, `servidor_web.py` | HTTP/HTML; revisar por função/rota, não o arquivo inteiro |
| P2 | `gtk_app.py`, `gtk_dialogos.py` | UI grande; revisar por tela/fluxo |
| P2 | `cadastros_v9.py` | cadastros, permissões e vínculos |

Para arquivos gigantes, o escopo é uma função/rota/tela, não “o arquivo
inteiro”. Exemplo: `portal_prestador.py` → `os_form`, `financeiro` ou
`clientes_lista`.

---

## 3. Pacote de revisão

Antes de abrir o ChatGPT/Gemini, monte um pacote com:

```text
Projeto: AUTOSEG (flavor) / Officina (app) / Workaholic (engine)
Stack: Python 3.13, SQLite, HTTP portals, GTK4, Alpine/Nura em teste
Restrições:
  - local-first, sem servidor obrigatório
  - SQLite local, sem ORM obrigatório
  - comportamento e UI atuais preservados
  - sem big-bang; mudanças pequenas e testáveis
  - 0BSD; sem copiar código de licença incompatível
  - servidor de teste pode ter 2 GB de RAM
Arquivo:
  caminho, propósito, tamanho, funções/classes públicas
Chamadores:
  quem importa/chama, rotas/ telas afetadas
Testes:
  suítes existentes, cobertura relevante, como rodar
Dados:
  tabelas lidas/escritas, transações, invariantes
Riscos conhecidos:
  dinheiro, concorrência, permissão, migração, PDF, anexos
Diff:
  `git diff` do ciclo (se houver)
Auditores:
  saída de `audit_comments.py --strict` e `audit_code_rot.py`
Fora de escopo:
  reescrever em Rust, trocar SQLite/ORM, microserviços, redesenhar UI
```

Não incluir:

- banco real, CPF/CNPJ, nomes de clientes, senhas, tokens, anexos privados;
- chaves, cookies, logs com dados pessoais;
- arquivos de produção que não sejam necessários.

---

## 4. Prompt para o revisor externo

Use duas IA diferentes (por exemplo, ChatGPT e Gemini), em sessões separadas.
Não mostre o relatório de uma para a outra antes da conclusão.

Prompt base:

> Você é um revisor de software sênior, independente. Analise o arquivo e o
> contexto abaixo contra boas práticas atuais de engenharia. Pesquise na web
> quando precisar e **cite as fontes**. Não reescreva o arquivo inteiro.
>
> Procure, em ordem de risco:
> 1. perda/corrupção de dados, dinheiro, estoque, permissões e status;
> 2. concorrência, transações, idempotência e falhas parciais;
> 3. exceções engolidas, erros virando sucesso, mensagens enganosas;
> 4. regra de negócio duplicada ou contraditória;
> 5. complexidade desnecessária, código morto, abstração sem consumidor;
> 6. testes ausentes ou frágeis;
> 7. segurança, privacidade e LGPD;
> 8. oportunidades de simplificação incremental.
>
> Responda em tabela:
> severidade (P0–P3) | arquivo:linha | problema | evidência | teste que
> reproduz | sugestão incremental | esforço.
>
> Não dê conselho genérico. Se não houver evidência no código, diga
> “não verificável”. Não proponha reescrita total, troca de linguagem,
> microserviços, ORM ou framework sem justificativa forte. Preserve o
> comportamento e a UI atuais.

Para pesquisa de boas práticas:

> Compare o desenho com implementações maduras de problemas semelhantes
> (SQLite, filas, PDF, dinheiro em centavos, estados de OS, permissões).
> Traga 2–3 referências com link e explique o que se aplica **neste** código.
> Aponte o que não se aplica e por quê.

---

## 5. Triagem dos achados

O relatório da IA não é um plano de execução. O dono e o agente triagem:

| Decisão | Critério |
|---|---|
| **Corrigir agora** | P0/P1 com evidência e teste viável |
| **Corrigir depois** | P2/P3, ou depende de outra fatia |
| **Rejeitar** | sugestão genérica, exigiria rewrite, não se aplica ao contexto |
| **Investigar** | dúvida real; criar spike/teste antes |

Registrar cada decisão em `docs/reviews/AAAA-MM-DD-<arquivo>.md` com:

- data, arquivo, escopo, modelos usados;
- resumo dos achados;
- o que foi aceito/rejeitado e por quê;
- testes existentes e testes propostos;
- risco residual;
- próximo passo.

---

## 6. Implementação

- Uma correção por commit, com teste.
- Não misturar limpeza estrutural com feature nova.
- Não copiar código da IA sem entender, testar e checar licença.
- Se a sugestão for “reescrever o módulo”, quebrar em fatias e provar com
  testes de caracterização.
- Rodar:

```bash
python3 -m py_compile <arquivos>
python3 -m unittest <suítes relevantes>
python3 scripts/audit_comments.py --strict
python3 scripts/audit_code_rot.py
```

- Para N3/N4, a revisão externa de IA **não substitui** o revisor humano:
  use o relatório como preparação para ele.

---

## 7. Cadência sugerida

```text
Toda semana:      auditor automático (comentários + podridão)
Todo mês:        1 arquivo P0/P1 revisado por ChatGPT + Gemini
Antes de features: 1–2 arquivos críticos e triagem concluída
Antes de release: fluxo P0 + revisão humana externa
Depois de incidente: revisão do arquivo envolvido
A cada trimestre: revisão de arquitetura, não de arquivo
```

Não criar uma “rodada de limpeza” com 20 arquivos. O objetivo é criar ritmo,
não uma nova maratona de IA.

---

## 8. Métricas

- achados P0/P1 aceitos e corrigidos;
- regressões causadas por correções;
- tempo de revisão/triagem;
- arquivos revisados por ciclo;
- dívida reduzida (auditores antes/depois);
- sugestões rejeitadas por serem genéricas ou exigirem rewrite.

---

## 9. Limites

- IA externa pode inventar API, versão ou comportamento; exija fonte/evidência.
- IA externa não conhece todo o sistema; forneça contexto e peça “não
  verificável” quando faltar dado.
- IA externa pode sugerir overengineering; filtre pelo contexto local-first,
  2 GB, SQLite e equipe pequena.
- IA externa não é revisão humana, jurídica ou fiscal.
- Enviar código para serviço externo exige revisão de privacidade/contrato:
  somente código, nunca dados reais.

---

## 10. Primeiro ciclo recomendado

Quando for começar:

1. escolher **`fluxo_os.py`** ou **`pdf_cliente_v9.py`**;
2. montar o pacote;
3. rodar ChatGPT e Gemini em separado, com pesquisa;
4. triagem P0–P3;
5. corrigir no máximo 2–3 achados com testes;
6. registrar o resultado em `docs/reviews/`.

Não começar por `portal_prestador.py` inteiro. É grande demais; primeiro
escolha uma função/rota.

## 11. Documentos relacionados

- `docs/REVIEW_WITHOUT_DEVELOPER.md`
- `docs/CODE_ROT_CLEANUP_PLAN.md`
- `docs/CODE_COMMENT_POLICY.md`
- `AGENTS.md`
- `docs/HUMAN_CENTERED_DECISIONS.md`
