# Completude configurável de cliente e OS

O AUTOSEG permite salvar cliente e ordem de serviço com dados faltando. O
registro fica marcado como **Incompletos** e pode ser completado depois.

O que conta como “mínimo” fica em `completude.yaml`, editável em runtime.

## Onde o arquivo é lido

Ordem de procura:

1. `$AUTOSEG_BASE/completude.yaml` (dados/instalação)
2. `completude.yaml` ao lado do código
3. padrão interno, se nenhum existir

No modo local, edite o `completude.yaml` dentro da pasta de dados do usuário:

- macOS: `~/Library/Application Support/AUTOSEG/local/completude.yaml`
- Linux: `~/.local/share/autoseg/local/completude.yaml`

No servidor, use a pasta indicada por `./autoseg paths`. Se o arquivo não
existir na pasta de dados, o padrão versionado em
`flavors/autoseg/config/completude.yaml` é usado.

Não é necessário reiniciar: cada salvamento/lista relê o arquivo. Se o YAML
estiver inválido, o app usa o padrão e registra um aviso no terminal.

## Formato

```yaml
versao: 1

cliente:
  - nome
  # - documento
  # - telefone

ordem_servico:
  - cliente_id
  - descricao
  # - tecnico
```

Lista vazia significa “este registro não tem mínimo”:

```yaml
versao: 1
cliente: []
ordem_servico: []
```

## Campos aceitos

Cliente:

```text
tipo_pessoa, documento, nome, nome_fantasia, endereco, numero, complemento,
bairro, cep, cidade, uf, telefone, email, sindico_nome, sindico_telefone,
sindico_email, administradora, administradora_email, administradora_telefone,
observacoes, status
```

Ordem de serviço:

```text
cliente_id, descricao, tecnico, forma_pagamento, valor_total, urgencia, observacoes
```

## Regras

- Texto vazio, `null` ou valor numérico zero contam como ausente.
- CPF/CNPJ continua sendo validado quando informado, independentemente do
  mínimo configurado.
- Cliente sem nome é permitido; a lista mostra `(sem nome)` e **Incompletos**.
- OS sem descrição é permitida; não pode ser encerrada enquanto estiver
  incompleta.
- O banco tem `clientes.dados_incompletos` e `ordens_servico.dados_incompletos`.
- A lista calcula a completude com a configuração atual; o flag persistido é
  atualizado no próximo salvamento.
- Cliente PJ vazio não cria organização até ter nome.

## Exemplos

Mínimo mais rígido para cliente:

```yaml
cliente:
  - nome
  - documento
  - telefone
```

Mínimo para OS com técnico obrigatório:

```yaml
ordem_servico:
  - cliente_id
  - descricao
  - tecnico
```

## Testes

```bash
python3 test_completude.py
python3 test_importacao_yaml.py
```
