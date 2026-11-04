# Integração com o Workaholic

> **Status:** o Workaholic não foi abandonado. Ele é o motor genérico planejado
> para o produto de longo prazo, mas hoje está integrado apenas na fatia de
> clientes. As demais entidades continuam nas tabelas legadas até a migração
> por adaptadores. Ver `docs/PRODUCT_VISION.md`.

## O que é o Workaholic

O Workaholic é o núcleo genérico de gestão de trabalho: entidades, campos,
estados, transições, relações, CRUD, validação e versionamento. A mesma base
serve para eletricistas, músicos, artistas 2D ou qualquer outro negócio; o que
muda é o schema YAML e os módulos específicos de cada aplicação.

O AUTOSEG é uma configuração desse núcleo para manutenção e serviços. As
regras que são realmente do nosso nicho continuam no AUTOSEG:

- CPF/CNPJ e duplicidade de documento;
- condomínios, chamados e aprovação em camadas;
- portais do cliente e do prestador;
- PDF, relatórios, repasses e produtividade;
- Gmail, Asaas e demais integrações.

## Estado atual

Primeira fatia migrada: **clientes**.

```text
GTK (mesmas telas)
  └─ integracao/clientes.py
       └─ Workaholic RecordService
            └─ RepositorioClientes
                 └─ tabela clientes existente
```

O que o Workaholic faz nessa fatia:

- carrega o schema `integracao/schema_autoseg.yaml`;
- valida tipos, campos permitidos e valores de `tipo_pessoa`/`status`;
- cria, lê, lista e atualiza registros;
- versiona os registros e oferece bloqueio otimista no repositório.

O que o adaptador do AUTOSEG faz:

- mapeia o registro genérico para as colunas da tabela `clientes`;
- valida CPF/CNPJ e documento duplicado;
- calcula `dados_incompletos` com `completude.yaml`;
- sincroniza pessoa jurídica com `v9_organizacoes`;
- mantém o `id` inteiro legado, sem UUID e sem migração de dados.

## Banco de dados

Nenhum dado foi movido. A única mudança é aditiva na tabela `clientes`:

```sql
ALTER TABLE clientes ADD COLUMN versao INTEGER NOT NULL DEFAULT 1;
ALTER TABLE clientes ADD COLUMN atualizado_em TEXT;
```

Essas colunas são criadas por `banco.criar_banco()` em bancos antigos.

Os registros continuam nas tabelas normalizadas. O repositório genérico de
JSON do Workaholic (`records`) **não** é usado nesta fatia, porque os portais,
PDFs e relatórios consultam `clientes`, `ordens_servico` e `financeiro`
diretamente. Migrar para `records` agora seria reescrever todas essas consultas
e migrar dados de produção: um projeto separado, não uma modularização.

## Comportamento preservado

- mesmas telas e mesmos campos;
- cliente incompleto continua permitido e marcado como `dados_incompletos`;
- documento só é validado quando é novo ou muda;
- documento duplicado continua bloqueado;
- cliente jurídico ativo continua sincronizando a organização;
- exclusão/desativação continua no fluxo legado, que grava o histórico em
  `v9_historico_clientes` e decide entre desativar e excluir.

## Próximas fatias

Ordem recomendada:

1. `ordem_servico` — o fluxo central de trabalho.
2. `catalogo_servicos` e `materiais`.
3. `financeiro`.
4. `prestadores`.

Para cada entidade:

1. acrescentar a entidade em `integracao/schema_autoseg.yaml`;
2. implementar o mapeamento no repositório do adaptador;
3. trocar as leituras/escritas da interface pela camada de integração;
4. manter as regras específicas no adaptador, nunca no núcleo;
5. adicionar teste de regressão antes de remover o caminho antigo.

## Limites conhecidos

- Portal, desktop e importadores ainda escrevem direto em `clientes` e não
  incrementam `versao`; a tela mantém o comportamento último-que-salva, igual
  ao anterior. Migrar esses escritores antes de remover as escritas diretas.
- A desativação de cliente ainda usa `cadastros_v9.desativar_cliente` para
  preservar o evento de histórico.
- O schema é por aplicação. O exemplo `workaholic/examples/autoseg` é
  demonstrativo; a configuração real fica em `integracao/schema_autoseg.yaml`.

## Testes

```bash
python3 -m unittest -v test_integracao_clientes.py
python3 -m unittest discover -s workaholic/tests -v
```
