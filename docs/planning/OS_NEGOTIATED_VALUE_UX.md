# Valor negociado na OS — UX com checkbox e desconto explícito

**Status:** proposta de produto. **Não implementado.** A prioridade imediata
continua sendo o AUTOSEG funcionando; este documento registra a UX desejada
para uma próxima fatia.

**Última atualização:** 2026-11-10

---

## 1. O problema

Hoje o formulário da OS tem vários controles que parecem competir para definir
o mesmo valor:

- **Valor do serviço — mão de obra, sem materiais**;
- **Valor final da OS (R$), opcional**;
- **Aplicar composição padrão**;
- **Taxa mínima de visita** (Cobrar / Não cobrar);
- **Composição dos valores** (base `total` ou `visita`).

O campo **Valor final da OS** já é, na prática, um valor negociado: quando
informado, ele prevalece sobre serviço + materiais. O problema é que ele
**redistribui** o total entre os componentes. Se o total calculado é R$ 260,00
e o negociado é R$ 230,00, o sistema reduz a mão de obra (ou a visita) para
fechar em R$ 230,00. O relatório não mostra “desconto de R$ 30,00”; mostra uma
composição menor. Isso é contábil e visualmente confuso.

**Decisão desejada:** separar claramente:

- **total calculado** (nominal), por exemplo R$ 260,00;
- **valor negociado** (final), por exemplo R$ 230,00;
- **desconto negociado** = calculado − negociado = R$ 30,00.

O desconto aparece como linha própria no relatório/PDF. A composição nominal
não é reescrita para esconder o desconto.

---

## 2. Histórico

A busca no histórico do site não encontrou um botão chamado “valor negociado”
que tenha sido removido. O que existia era o campo opcional:

```text
Total negociado (R$), opcional — substitui a soma
```

Ele foi renomeado para **Valor final da OS (R$), opcional** no ciclo
`9.6.0-dev.73`, com a explicação de que o valor final é autoritativo. O commit
`cd6134e` apenas acrescentou uma nota explicativa; não removeu botão.

Se você lembra de um botão, ele pode ter sido de uma versão anterior ao
histórico atual ou de outra superfície (GTK/versão antiga). O importante é que
a ideia de **valor negociado com desconto explícito** não está implementada
hoje.

---

## 3. UX proposta

### 3.1 Formulário principal (sem poluição)

```text
Materiais
  Interfone 13 teclas       1 un     R$ 89,00

Total calculado da OS                 R$ 260,00

[ ] Valor negociado
      Total final negociado (R$)      R$ 230,00
      Desconto negociado              −R$ 30,00

[ ] Aplicar composição padrão
      Mão de obra / hora técnica      R$ 93,00
      Custos administrativos (10%)    R$ 26,00
      Custos operacionais (10%)       R$ 26,00
      Margem de risco (10%)           R$ 26,00
      Taxa mínima de visita           R$ 89,00? (ou “Não cobrar”)
```

Os valores acima são ilustrativos. A composição é calculada sobre o **total
calculado** (R$ 260,00); o desconto é aplicado depois.

**Regra de visibilidade:**

- a checkbox **Valor negociado** fica sempre visível, mas o campo de valor
  final e a linha de desconto só aparecem quando ela está marcada;
- sem a checkbox, o total da OS é o total calculado;
- com a checkbox, o total da OS é o valor final negociado; o desconto é
  mostrado em tempo real;
- a composição detalhada pode ficar dentro de um `<details>` **“Ver
  composição”** para não competir com o valor principal.

### 3.2 Opções avançadas

Para não ter três selects disputando atenção, mover para **“Opções da
composição”** (fechado por padrão):

- **Taxa mínima de visita**: Cobrar / Não cobrar;
- **Base dos percentuais**: Total da OS / Visita mínima;
- explicação curta de cada uma.

O usuário comum não precisa abrir isso em toda OS. O padrão configurado pela
prestadora vale quando ele não abre.

### 3.3 Relatório/PDF

```text
Composição do valor
  Materiais                         R$ 89,00
  Mão de obra / hora técnica        R$ 93,00
  Custos administrativos (10%)      R$ 26,00
  Custos operacionais (10%)         R$ 26,00
  Margem de risco (10%)             R$ 26,00

  Subtotal                         R$ 260,00
  Desconto negociado               −R$ 30,00
  Total da OS                      R$ 230,00
```

O desconto é uma linha negativa explícita. O cliente vê o valor cheio, o
desconto e o total. O financeiro e o rateio usam o **total final** (R$ 230,00),
salvo regra específica de absorção do desconto (ver §6).

---

## 4. Regras de negócio

1. **Total calculado** é a soma da composição nominal: materiais + mão de obra
   + visita (se cobrada) + custos percentuais.
2. **Total final** é o total calculado quando a checkbox está desmarcada.
3. Com **Valor negociado** marcado:
   - o total final é o valor informado;
   - o desconto é `total calculado − total final`;
   - o desconto não pode ser negativo (valor final maior que o calculado). Se
     o usuário digitar um valor maior, o campo mostra aviso e não salva, ou
     trata como “sem desconto” com confirmação. Preferência: bloquear com
     mensagem clara.
4. **Materiais** continuam entrando no total calculado. Se o total final for
   menor que os materiais, a operação é recusada com mensagem.
5. **Mão de obra e custos** são calculados sobre o total calculado. O desconto
   é uma linha separada; não redistribuir a composição para esconder o
   desconto.
6. **Rateio e financeiro** usam o total final. O desconto precisa ter uma regra
   explícita de quem absorve (ver §6).
7. **Persistência:** guardar no `composicao_json`:
   - `subtotal_centavos`;
   - `valor_negociado_centavos` (quando marcado);
   - `desconto_centavos`;
   - `total_centavos` (final).
8. **Reabertura:** a checkbox, o valor negociado e o desconto voltam iguais.
9. **Compatibilidade:** OS antigas com `valor_total_override` são tratadas como
   “valor negociado” na primeira reabertura; o subtotal é reconstruído a partir
   dos componentes e o desconto é calculado. Nada é reescrito silenciosamente
   sem evento/auditoria.

---

## 5. O que NÃO fazer

- Não adicionar três campos/selects para a mesma decisão.
- Não chamar o valor final de “Total negociado” e deixá-lo sempre visível sem
  explicar que ele é um desconto.
- Não recalcular a mão de obra para “esconder” o desconto.
- Não mostrar desconto negativo no PDF.
- Não permitir valor final abaixo dos materiais.
- Não criar um botão “Aplicar”/“Salvar” só para confirmar o valor; o auto-save
  continua valendo.

---

## 6. Decisões que precisam do dono do produto

1. **O total calculado inclui materiais?**
   - Proposta: sim. Exemplo: materiais R$ 89,00 + serviço R$ 171,00 = total
     calculado R$ 260,00; negociado R$ 230,00; desconto R$ 30,00.
   - Alternativa: o campo principal é “valor do serviço” (R$ 171,00) e os
     materiais são somados à parte. Isso preserva o formulário atual, mas exige
     o usuário pensar em serviço + materiais.

2. **Quem absorve o desconto no rateio?**
   - Opção A: o desconto reduz o total rateável; as parcelas dos colaboradores
     são proporcionais ao total final.
   - Opção B: o desconto é absorvido pela prestadora/responsável; as parcelas
     dos colaboradores continuam calculadas sobre o total nominal.
   - Opção C: o desconto é distribuído apenas na parcela do responsável.
   - Isso muda dinheiro de terceiros; precisa de decisão explícita.

3. **Quem pode marcar “Valor negociado”?**
   - Proposta: responsável/finalizador e admin da prestadora, como os demais
     campos de valor.
   - O desconto deve gerar evento de auditoria com valor calculado, valor
     negociado e desconto.

4. **O desconto aparece para o cliente no PDF?**
   - Proposta: sim, como linha “Desconto negociado −R$ 30,00”, para dar
     transparência e evitar que o cliente compare o subtotal com o total sem
     entender a diferença.

5. **Desconto fixo ou percentual?**
   - Proposta inicial: valor fixo em reais. Percentual pode vir depois, se
     houver uso real.

---

## 7. Testes previstos

- total calculado 260, negociado 230 → total 230, desconto 30;
- checkbox desmarcada → total 260, sem linha de desconto;
- valor negociado maior que o calculado → bloqueio com mensagem;
- valor negociado menor que materiais → bloqueio com mensagem;
- reabrir a OS → checkbox, valor e desconto restaurados;
- PDF → subtotal 260, desconto −30, total 230;
- financeiro/rateio → usam o total final (ou a regra escolhida em §6.2);
- OS antiga com `valor_total_override` → migra para o novo formato sem perder
  o total;
- auto-save → sem botão “Salvar”, sem reload.

---

## 8. Relação com o código atual

- `flavors/autoseg/modules/portal_prestador.py` — campos `valor_mao_obra`,
  `valor_total_override`, `aplicar_composicao`, `cobrar_visita`,
  `base_percentuais`.
- `officina/core/portal_negocios.py` — `os_salvar` calcula a composição e usa
  `total_negociado`.
- `officina/core/composicao.py` — `calcular_os`, `calcular_os_sem_visita`,
  `declarativa`; precisa de um campo/linha de desconto e de subtotal.
- `flavors/autoseg/modules/pdf_cliente_v9.py` — hoje renderiza componentes e
  total; precisa renderizar subtotal, desconto e total.
- `docs/COMPOSICAO_VALORES.md` e
  `docs/features/MATERIAIS_COMPOSICAO_OS.md` — atualizar quando implementar.

---

## 9. Resumo em uma frase

**O valor negociado não deve ser um novo jeito de redistribuir a composição; deve
ser uma checkbox que revela um valor final e uma linha de desconto explícita,
calculada sobre o total nominal.**
