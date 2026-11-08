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
- `officina/` — esqueleto e destino dos contratos genéricos.
- `flavors/autoseg/` — marca, configuração e modelos já movidos.
- `application/` — serviço genérico ainda na raiz, será movido para
  `officina/application/` em uma fatia própria.
- Módulos legados na raiz — portais, GTK, API, auth, feedback e fiscal. Serão
  movidos em fatias, com adaptadores e testes de paridade.

## Regras

1. Core não importa flavor.
2. Flavor pode importar contratos de `officina/` e `workaholic/`.
3. Nada novo de AUTOSEG deve nascer na raiz.
4. Toda movimentação de código mantém um caminho de compatibilidade e testes
   verdes.
5. Não mover banco, anexos, logs ou dados de usuário para dentro do repositório.

## Próximas fatias

1. Mover `application/` para `officina/application/` com shims temporários.
2. Extrair o catálogo de serviços para um adaptador genérico.
3. Mover portais e GTK para `flavors/autoseg/modules/` e `apps/`.
4. Mover testes para `tests/` e padronizar a descoberta.
