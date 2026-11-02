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

## Persistência

Colunas aditivas:

```text
catalogo_servicos.tempo_horas
catalogo_servicos.composicao_json
ordens_servico.tempo_horas
ordens_servico.composicao_json
```

O JSON guarda o total, os componentes, os valores em centavos, os percentuais
e o aviso de proporcionalização. O PDF usa o snapshot gravado; se ele não
existir, calcula na hora com a configuração atual.

- Serviço cadastrado/alterado: grava a composição do preço + materiais.
- OS criada/alterada: grava a composição do valor total.
- OS encerrada: recalcula e grava a composição antes de publicar o PDF.
- `Recalcular` na tela de composição atualiza serviços e OS abertas.

## PDFs

O PDF do orçamento (`catalogo_servicos.pdf_orcamento`) mostra:

- itens e total estimado;
- tabela **Composição do valor** com componente, valor e percentual.

O PDF final da OS (`pdf_cliente_v9.gerar`) mostra:

- **04 Composição do valor**;
- **05 Valores e pagamento** com total, forma de pagamento e situação;
- **06 Registro fotográfico**, quando houver.

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
