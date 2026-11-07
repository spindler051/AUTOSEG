# Política de comentários e código gerado

**Status:** regra de engenharia. Vale para código novo e para qualquer arquivo
que for tocado.

## 1. Por que isto existe

Um comentário que repete o prompt do usuário não é apenas feio: ele costuma
indicar que a implementação não foi modelada com clareza. O agente transforma a
solicitação em texto dentro do código, em vez de traduzi-la em comportamento,
testes e nomes bons.

Sintomas típicos:

- `# O usuário pediu para ...`
- `# IMPORTANTE: implemente ...`
- `# REV12: ...`
- `# shortcut: ...`
- `# A IA deve ...`
- comentário que repete o nome da função ou o `if` da linha seguinte;
- blocos de comentário com bullets copiados de um prompt;
- regras duplicadas em comentários e no código, que divergem com o tempo.

O comentário não muda o comportamento em runtime, mas é um **sinal** de código
circular, redundante ou mal separado. O remédio principal é teste de
comportamento + implementação pequena; o comentário é consequência.

## 2. Regras

1. **Comentário explica por quê, não o quê.** O “o quê” deve estar no nome da
   função, nos tipos e nos testes.
2. **Nunca colar prompt, spec ou pedido do usuário no código.** Spec vai para
   `docs/`, issue ou ADR.
3. **Sem histórico de revisão no código.** `REV12`, `v9.4.1`, “correção do
   feedback 104” pertencem ao Git e ao `CHANGELOG.md`.
4. **Sem nome de ferramenta de IA em comentário de produto.** `OpenCode`,
   `ChatGPT`, `DeepSeek`, “a IA” etc. só são aceitáveis no próprio módulo de
   feedback/IA, onde são o domínio, ou em documentação.
5. **Sem `shortcut`, `workaround`, `hack` ou “gambiarra”** sem link para issue,
   motivo e condição de remoção.
6. **Comentário que repete a linha seguinte deve ser apagado.** Exemplo ruim:
   ```python
   # incrementa a versão
   versao += 1
   ```
7. **Docstring é contrato, não narração.** Descreva entradas, saídas, erros,
   efeitos colaterais e invariantes não óbvios.
8. **TODO/FIXME precisa de issue, dono ou prazo.** Sem isso, vira dívida
   invisível.
9. **Prefira teste a comentário para comportamento.** Se uma regra pode ser
   testada, teste.
10. **Idioma:** código novo e comentários novos em inglês; arquivos legados em
    português podem manter o idioma até serem tocados, mas sem piorar.

## 3. Exemplos

### Ruim

```python
# O usuário pediu para garantir que o rateio seja validado antes de concluir.
if total_rateio > total:
    raise ValueError(...)
```

```python
# REV12: agora o financeiro cancela o pagamento.
```

```python
# shortcut: o portal ainda escreve direto no banco.
```

### Bom

```python
# O rateio é validado na mesma transação do encerramento; se falhar, a OS
# inteira sofre rollback.
if total_rateio > total:
    raise ValueError(...)
```

```python
# Escritores legados ainda ignoram o adaptador e não incrementam a versão.
# Chamadas diretas ao adaptador usam bloqueio otimista.
```

```python
# TODO(#123, 2026-12-01): remover quando o portal usar o adaptador.
```

## 4. O que fazer quando o código está circular/redundante

1. **Não “conserte” só o comentário.** O comentário é sintoma.
2. Escreva um teste de caracterização do comportamento atual.
3. Reduza a função: nomes claros, uma responsabilidade, sem ramos duplicados.
4. Remova o comentário que virou desnecessário.
5. Rode o teste de novo. Se o teste não consegue expressar a regra, aí sim um
   comentário curto de “por quê” é legítimo.

## 5. Auditoria

Ferramenta local:

```bash
python3 scripts/audit_comments.py
python3 scripts/audit_comments.py --strict
```

- `[ALTO]` — prompt/IA/revisão/shortcut: corrigir.
- `[BAIXO]` — linguagem imperativa: revisar; pode ser invariante legítima.
- `--strict` retorna código 1 se houver achados altos; use no CI quando o
  workflow tiver permissão.

O script ignora `feedback_ai.py`/`feedback_portal.py`, onde IA e prompt são o
próprio domínio, e não substitui revisão humana.

## 6. Checklist de revisão

- [ ] O comentário repete o pedido do usuário ou a spec?
- [ ] O comentário repete o código/nome da função?
- [ ] Tem `REVxx`, versão ou nome de ferramenta de IA?
- [ ] Tem `shortcut`/`hack` sem issue?
- [ ] A regra poderia estar em teste em vez de comentário?
- [ ] A docstring descreve contrato, não uma história?
- [ ] O diff inteiro parece “prompt traduzido” em vez de código modelado?

## 7. Exceções

- `feedback_ai.py` e `feedback_portal.py` podem mencionar provedores e prompts
  porque isso é o domínio do feedback.
- `docs/`, `CHANGELOG.md` e issues podem citar IA, revisões e pedidos; o código
  de produção, não.
- Licenças e cabeçalhos legais são permitidos.

## 8. Relação com o restante do projeto

- `AGENTS.md` — regra para agentes.
- `docs/FUNDAMENTAL_STRUCTURAL_PROBLEMS.md` — dívida estrutural.
- `docs/PLATFORM_MIGRATION_PLAYBOOK.md` — uma fatia por vez.
- `docs/GTK_SERVER_DECOUPLING.md` — separação de UI/servidor.
- `docs/MULTI_PLATFORM_GUI_GUIDELINE.md` — interfaces.
