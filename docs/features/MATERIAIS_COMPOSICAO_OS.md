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

O total negociado é autoritativo. Se não cobrir a hora técnica mínima de
R$ 100,00, a gravação é recusada com mensagem; não há desconto automático.

O formulário tem **Aplicar composição padrão** marcado por padrão, um seletor
de **Base dos percentuais** e a prévia dos componentes antes de salvar.

## Caso OS-0023

- Base dos percentuais: **visita mínima**.
- Caixa de passagem: R$ 49,25.
- Cabo 20A: 1 m, R$ 10,00.
- Tubo termo retrátil: 5 cm, R$ 1,00/cm, total R$ 5,00.
- Materiais: R$ 65,00.
- Visita mínima: R$ 250,00.
- Administrativo: 10% da visita = R$ 25,00.
- Operacional: 10% da visita = R$ 25,00.
- Risco: 10% da visita = R$ 25,00.
- Hora técnica: R$ 135,00.
- Total: R$ 450,00.
- Sem desconto.
- Feedback: `portal_feedback` id 26.
- Backup: `backups/dados_antes_composicao_visita_os0023_20261105_231929.db`.
