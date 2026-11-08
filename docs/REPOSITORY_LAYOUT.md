# Repository layout

Estrutura-alvo do monorepo:

```text
workaholic/                 motor genérico: schemas, validação, persistência
officina/                   plataforma genérica: contratos e serviços
  contracts/                contratos estáveis (destino)
  application/              serviços de aplicação (destino)
flavors/autoseg/            distribuição AUTOSEG
  branding/                 logo e ícones
  config/                   policy, numeração, completude, composição, texto
  templates/                modelos YAML de cliente, serviço, orçamento e relatório
  modules/                  portais, fiscal e integrações (destino)
apps/                       clientes: GTK, web, CLI (destino)
packages/                   bibliotecas compartilhadas (destino)
tests/                      testes de unidade e integração (destino)
docs/                       documentação do produto e do processo
scripts/                    automação de desenvolvimento e release
packaging/                  empacotamento Linux/macOS
```

## Estado atual (transição)

- `workaholic/` — motor existente.
- `officina/core/` — banco, OS, financeiro, catálogo, estoque, composição,
  numeração, completude, runtime, versão e providers.
- `officina/application/` — contratos e serviços de aplicação.
- `officina/integration/` — adaptadores de clientes e Workaholic.
- `officina/repositories/` — consultas de OS.
- `officina/telemetry/` — telemetria genérica.
- `flavors/autoseg/modules/` — portais, GTK, API, auth, feedback, fiscal,
  e-mail, túneis e integrações brasileiras.
- `flavors/autoseg/web/` — `portal.js` e site estático.
- `flavors/autoseg/scripts/` — geração de dados fictícios e reset DEV.
- `tests/` — suíte de testes.
- `scripts/autoseg/` — launchers e automação do flavor.
- `data/` — dados locais de DEV (ignorado pelo Git).
- A raiz guarda apenas README, LICENSE, docs, `autoseg`, requirements,
  versão, empacotamento e configuração do repositório.

## Regras

1. Core não importa flavor.
2. Flavor pode importar contratos de `officina/` e `workaholic/`.
3. Nada novo de AUTOSEG deve nascer na raiz.
4. Toda movimentação de código mantém um caminho de compatibilidade e testes
   verdes.
5. Não mover banco, anexos, logs ou dados de usuário para dentro do repositório.

## Próximas fatias

1. Extrair o catálogo de serviços para um contrato genérico do Workaholic.
2. Extrair OS e financeiro para adaptadores genéricos.
3. Separar fiscal/NF-e em um módulo de locale brasileiro.
4. Mover scripts de inicialização para `scripts/` com um único comando `officina`.
