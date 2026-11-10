# Composição configurável do valor

A composição detalha o valor de um serviço ou de uma OS em componentes
financeiros. Ela é calculada automaticamente no cadastro do serviço, no
orçamento, na gravação da OS e no encerramento. O PDF do orçamento e o PDF
final da OS mostram a composição com valor e participação percentual.

Nenhuma taxa, categoria ou componente é fixo no código. O administrador cria,
edita, reordena, ativa, desativa e exclui componentes em runtime.

## Onde fica a configuração

- Modelo inicial versionado: `composicao_padrao.yaml`.
- Configuração efetiva: `$AUTOSEG_BASE/composicao.yaml`.
- Se o arquivo efetivo não existir, o app copia o modelo para lá.
- A tela **Composição de valores** do GTK edita o arquivo efetivo e recarrega
  os cálculos sem reiniciar o aplicativo.
- O arquivo `composicao.yaml` é dado local e fica fora do Git; o modelo
  `composicao_padrao.yaml` é versionado.

## Estrutura

```yaml
versao: 1
moeda: BRL
horas_padrao: 1.0
componentes:
  - id: materiais
    nome: Materiais
    descricao: Custo dos materiais utilizados.
    modo: materiais
    valor: 0
    ativo: true
    obrigatorio: true
    ordem: 1
    aplicavel_a: []

  - id: hora_tecnica
    nome: Mão de obra / hora técnica
    modo: hora
    valor: 10000       # centavos por hora
    horas_padrao: 1.0
    ativo: true
    obrigatorio: true
    ordem: 2

  - id: visita
    nome: Taxa mínima de visita
    modo: fixo
    valor: 3000        # centavos
    ativo: true
    ordem: 3

  - id: administrativo
    nome: Custos administrativos
    modo: percentual
    valor: 10          # 10% do valor final
    ativo: true
    ordem: 4

  - id: outros
    nome: Outros custos e margem
    modo: residual
    ativo: true
    ordem: 5
```

### Modos de cálculo

| Modo | Significado |
|---|---|
| `materiais` | Usa o custo real dos materiais informados. Sem materiais, R$ 0,00. |
| `fixo` | Valor fixo em centavos. |
| `hora` | Horas de execução × valor da hora em centavos. |
| `percentual` | Percentual do valor final. |
| `formula` | Expressão com IDs de componentes anteriores. |
| `residual` | Recebe a diferença até o valor final. |

As fórmulas aceitam apenas números, IDs de componentes anteriores e as
operações `+`, `-`, `*`, `/` e parênteses. Exemplo:

```yaml
modo: formula
formula: hora_tecnica * 0.1
```

### Campos

- `id`: identificador estável; é usado nas fórmulas.
- `nome` e `descricao`: aparecem na tela e no PDF.
- `ativo`: componente desativado não entra no cálculo.
- `obrigatorio`: indica que o componente deve existir na composição.
- `ordem`: define a ordem de cálculo e de apresentação.
- `aplicavel_a`: lista de nomes de serviços; vazio significa todos.
- `horas_padrao`: usada quando a OS/serviço não informa horas.

## Como o total é fechado

O valor final é sempre autoritativo:

1. Componentes de materiais, fixos, hora e fórmula são calculados primeiro.
2. Componentes percentuais usam o valor final.
3. Se existir um residual, ele recebe a diferença.
4. Se a soma dos componentes fixos ultrapassar o total, os componentes são
   proporcionalizados e o residual fica em R$ 0,00. O resultado traz um aviso.
5. Se não existir residual, todos os componentes são distribuídos
   proporcionalmente para fechar exatamente no total.
6. A diferença de arredondamento é aplicada ao residual ou ao maior
   componente, garantindo soma exata em centavos.

Quando o usuário informa apenas o valor final, o total não muda. Quando não
informa o total, o motor calcula o total a partir dos componentes e dos
percentuais configurados.

## Composição específica da OS (`calcular_os`)

A OS escolhe uma **base de percentuais** configurada em `composicao.yaml`.
A base é resolvida por componente ou por campo, sem `if` fixo para visita:

```yaml
bases_percentuais:
  total:
    nome: Total da OS
    cobertura: separado
  visita:
    nome: Visita mínima
    componente: visita
    cobertura: incluido
  # novo_campo:
  #   nome: Nova base
  #   campo: novo_campo
  #   cobertura: incluido
base_percentuais_padrao: total
```

- `total`: percentuais calculados sobre o total e exibidos em linhas próprias.
- `componente`: percentuais calculados sobre o valor de um componente existente
  (por exemplo, a visita).
- `campo`: percentuais calculados sobre um campo futuro da OS.
- `cobertura: separado`: os percentuais somam ao total e a hora técnica recebe
  o restante.
- `cobertura: incluido`: os percentuais ficam dentro da base (filhos), sem
  somar novamente. A hora técnica recebe `total − materiais − base`.
- O **valor final da OS** (campo `valor_total_override`, antes exibido como
  “Total negociado”) é autoritativo. Se não cobrir a hora mínima, a OS salva
  com aviso e a hora é ajustada; a gravação não é recusada por causa do mínimo.
- A **taxa mínima de visita é opcional por OS**. No formulário, o seletor
  **Taxa mínima de visita** permite **Cobrar** ou **Não cobrar**.
- Com **Não cobrar**, a linha da visita não entra na composição, os custos
  percentuais continuam incidindo sobre o valor final e a mão de obra recebe o
  restante depois de materiais e custos.
- Exemplo com a configuração do MAIN (três custos de 10%), total R$ 230,00 e
  materiais R$ 89,00: administrativo R$ 23,00 + operacional R$ 23,00 + risco
  R$ 23,00 = R$ 69,00; mão de obra = R$ 230,00 − R$ 89,00 − R$ 69,00 =
  **R$ 72,00**. A visita fica em R$ 0,00 e o total permanece R$ 230,00. Se a
  mão de obra ficar abaixo do mínimo configurado, a OS salva com aviso.
- Sem valor final informado, o total é exatamente `mão de obra + materiais`.
  A composição apenas distribui esse valor entre os componentes; visita,
  percentuais e custos **não são somados por cima** do valor informado.
- Para uma OS sem **nenhuma** composição (somente mão de obra + materiais),
  desmarque “Aplicar composição padrão”.
- OS de garantia/cortesia com mão de obra zero mantêm o comportamento
  anterior.

Exemplo com a configuração do MAIN (visita R$ 250,00, três custos de 10% e
sem deslocamento separado), serviço de R$ 1.500,00 e nenhum material:

- base `total`: hora técnica R$ 800,00 + visita R$ 250,00 + três custos de
  R$ 150,00 = R$ 1.500,00;
- base `visita`: hora técnica R$ 1.250,00 + visita R$ 250,00 (com três filhos
  de R$ 25,00 dentro dela) = R$ 1.500,00.

Em ambas as bases o total permanece R$ 1.500,00. A divisão interna depende dos
componentes ativos e dos percentuais configurados no `composicao.yaml`.

Exemplo da OS-0023 (total R$ 450,00, base `visita`):

- materiais R$ 65,00;
- visita R$ 250,00;
- administrativo, operacional e risco: 10% da visita = R$ 25,00 cada,
  dentro da visita;
- hora técnica: R$ 135,00;
- total: R$ 450,00.

## Persistência

Colunas aditivas:

```text
catalogo_servicos.tempo_horas
catalogo_servicos.composicao_json
ordens_servico.tempo_horas
ordens_servico.composicao_json
ordens_servico.base_percentuais
```

O JSON guarda o total, os componentes, os valores em centavos, os percentuais
e o aviso de proporcionalização. O PDF usa o snapshot gravado; se ele não
existir, calcula na hora com a configuração atual.

- Serviço cadastrado/alterado: grava a composição do preço + materiais.
- OS criada/alterada: grava a composição do valor total.
- OS encerrada: preserva composições modulares (`calcular_os`) e declarativas;
  recalcula pela regra legada apenas quando não há composição autoritativa.
- `Recalcular` na tela de composição atualiza serviços e OS abertas. OSs com
  base modular são recalculadas na mesma base; declarativas e OSs que não
  fecham com a nova configuração são preservadas e contadas como mantidas.
- Desktop e portal usam a mesma decisão: uma OS com JSON modular continua
  modular ao ser editada no GTK; OSs antigas mantêm a regra explícita de
  materiais + mão de obra.

## PDFs

O PDF do orçamento (`catalogo_servicos.pdf_orcamento`) mostra:

- itens e total estimado;
- tabela **Composição do valor** com componente, valor e percentual.

O PDF final da OS (`pdf_cliente_v9.gerar`) mostra:

- **Solicitação original**;
- **Atendimento realizado**;
- **Materiais utilizados**, apenas quando existem linhas de material;
- **Garantia** (ou o título configurado em `texto_os.yaml`), quando houver
  texto, sempre antes da composição;
- **Composição do valor**, sem a linha de materiais quando ela for R$ 0,00;
- **Valores e pagamento** com total, forma de pagamento e situação;
- **Registro fotográfico**, quando houver.

A numeração acompanha as seções realmente exibidas. Sem materiais e sem
garantia, a composição é **03** e os valores são **04**. Com garantia, ela é
**03**, a composição passa a **04** e os valores a **05**. Com materiais, a
ordem é materiais, garantia (quando houver), composição e valores.

## Tela de administração

No GTK, abra **Composição de valores**:

- **Novo componente** cria um componente;
- **Editar** altera nome, descrição, modo, valor, fórmula, horas, aplicação,
  obrigatoriedade e situação;
- **Ativar/desativar** liga ou desliga o componente;
- **Subir/Descer** reordena;
- **Excluir** remove (mantendo pelo menos um componente);
- **Ver composição** simula um valor final, materiais, horas e tipo de serviço;
- **Recalcular** atualiza as composições persistidas de serviços e OS abertas.

## Testes

```bash
python3 -m unittest -v test_composicao.py
```

Os testes cobrem: exemplo de R$ 200,00, materiais zerados, total calculado,
total menor que componentes fixos, configuração em runtime, componente
inativo, fórmula, aplicação por tipo, arredondamento e persistência no
catálogo.
