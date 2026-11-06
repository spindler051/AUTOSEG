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

A composição da OS usa `composicao.calcular_os`:

- materiais reais;
- visita e demais componentes fixos do `composicao.yaml`;
- hora técnica com mínimo de R$ 100,00;
- percentuais calculados sobre o total negociado;
- se os percentuais integrais não couberem, o residual é dividido
  proporcionalmente entre eles;
- se nem materiais + visita + hora mínima couberem, a diferença vira uma linha
  de desconto;
- o total negociado nunca é elevado silenciosamente.

O formulário tem **Aplicar composição padrão** marcado por padrão e mostra a
prévia dos componentes antes de salvar. O total negociado continua
autoritativo.

## Caso OS-0023

- Caixa de passagem: R$ 49,25.
- Cabo 20A: 1 m, R$ 10,00.
- Tubo termo retrátil: 5 cm, R$ 1,00/cm, total R$ 5,00.
- Materiais: R$ 65,00.
- Visita mínima: R$ 250,00.
- Hora técnica: R$ 100,00.
- Percentuais integrais de 10% (R$ 45,00 cada) não cabem em R$ 450,00; o
  residual de R$ 35,00 foi dividido em R$ 11,67, R$ 11,67 e R$ 11,66.
- Total: R$ 450,00.
- Feedback: `portal_feedback` id 26.
- Backup: `backups/dados_antes_correcao_os0023_20261105_221657.db`.
