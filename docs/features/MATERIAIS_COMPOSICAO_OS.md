# Materiais e composição da OS

**Status:** DEV `9.6.0-dev.27`.
**Escopo:** Portal do Prestador e PDF/e-mail do relatório.

## Materiais

- A unidade de medida é um campo de texto com sugestões (`un`, `m`, `cm`,
  `mm`, `g`, `kg`, `L`, `ml`, `h`, `par`, `rolo`, `caixa`, `pacote`) e aceita
  qualquer texto, por exemplo `googleplexes`.
- A quantidade pode ficar vazia para itens sem quantidade fixa. Nesse caso, o
  valor informado é o total do item, não um valor unitário.
- A unidade é persistida em `materiais_os.unidade` e aparece no PDF e no
  e-mail. O estoque ignora itens sem quantidade.
- O nome do material não recebe mais o sufixo “sem quantidade fixa”; a
  ausência de quantidade fica no campo próprio.

## Composição

A composição da OS usa `composicao.calcular_os` com uma **base de percentuais**
configurada no `composicao.yaml`:

- `total`: percentuais sobre o total da OS, em linhas próprias;
- `visita`: percentuais sobre a visita mínima, dentro dela (filhos);
- uma base futura pode apontar para outro componente (`componente:`) ou para
  um campo novo (`campo:`), com `cobertura: separado|incluido`.

O **valor final da OS** é autoritativo. Sem valor final informado, o total é
exatamente `mão de obra + materiais`; a composição apenas distribui esse valor
e nunca soma visita, percentuais ou custos por cima. Se o valor não cobrir a
hora técnica mínima de R$ 100,00, a OS salva com aviso e a hora é ajustada.

A **taxa mínima de visita é opcional por OS**. O formulário tem o seletor
**Taxa mínima de visita** com **Cobrar** ou **Não cobrar**. Com **Não cobrar**,
a visita sai da composição, os percentuais continuam sobre o total e a mão de
obra recebe o restante. Exemplo: total R$ 230,00, materiais R$ 89,00 e três
custos de 10% (R$ 23,00 cada) deixam **R$ 72,00** de mão de obra; o total
continua R$ 230,00.

O formulário tem **Aplicar composição padrão** marcado por padrão, o seletor
**Taxa mínima de visita**, um seletor de **Base dos percentuais** e a prévia
dos componentes antes de salvar. O campo do serviço mostra **Valor do serviço —
mão de obra, sem materiais**. O campo opcional **Valor final da OS** prevalece
sobre serviço + materiais e é restaurado ao reabrir a OS.

No PDF, a seção **Materiais utilizados** só aparece quando existem linhas de
material. A tabela de composição também omite a linha de materiais quando ela
é R$ 0,00, e a numeração das seções seguintes se ajusta.

O aplicativo desktop usa a mesma decisão ao salvar: se o JSON da OS já é
modular, recalcula com a base gravada; se é antigo, mantém a regra explícita
de materiais + mão de obra. A unidade dos materiais também é preservada.

## Caso OS-0023

- Base dos percentuais: **visita mínima**.
- Caixa de passagem: R$ 50,00.
- Cabo 20A: 1 m, R$ 10,00.
- Tubo termo retrátil: 5 cm, R$ 1,00/cm, total R$ 5,00.
- Materiais: R$ 65,75.
- Visita mínima: R$ 250,00.
- Administrativo: 10% da visita = R$ 25,00.
- Operacional: 10% da visita = R$ 25,00.
- Risco: 10% da visita = R$ 25,00.
- Hora técnica: R$ 134,25.
- Total: R$ 450,00.
- Sem desconto.
- Feedback: `portal_feedback` id 26.
- Backup: `backups/dados_antes_composicao_visita_os0023_20261105_231929.db`.
