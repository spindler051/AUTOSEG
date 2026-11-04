# Padrões YAML oficiais do AUTOSEG — REV04

**Usar apenas no ambiente de desenvolvimento até homologação.** Os arquivos são texto UTF-8, com `versao: 1`, no máximo 64 KB; sem aliases, âncoras e objetos Python. A importação acontece somente em telas administrativas e preenche um formulário para revisão: **não salva automaticamente**.

## 1. Cadastro de cliente

Arquivo de referência: `modelo_cadastro_cliente.yaml`. Abra **Portal do Prestador > Clientes > Novo cliente > Importar YAML**. A confirmação cadastra o cliente normal no banco `clientes`. Não atribui poderes de síndico.

```yaml
versao: 1
cliente:
  tipo_pessoa: Jurídica
  nome: Condomínio Exemplo Fictício
  documento: ""
  endereco: Rua Simulada
  numero: "120"
  bairro: Centro
  cidade: Porto Alegre
  uf: RS
  telefone: "51999990000"
  email: "exemplo@example.invalid"
  status: Prospect
  observacoes: Apenas testes
```

## 2. Relatório técnico reutilizável

Arquivo: `modelo_relatorio_os.yaml`. Abra a OS e selecione **Pré-visualizar relatório YAML**. **Não há número de OS no arquivo**, porque a OS já está selecionada na página.

```yaml
versao: 1
os:
  diagnostico: Inspeção inicial realizada.
  execucao: Componentes ajustados e testados.
  resultado: Funcionamento restabelecido.
  relatorio_tecnico: Revisão técnica complementar.
  materiais: []
```

Campos omitidos **não** são modificados. Campos preenchidos na OS **não** são substituídos, a menos que você marque **Substituir campos e materiais já preenchidos**. O YAML antigo que possui `numero` continua sendo lido, mas esse campo é ignorado e nunca muda a OS. Materiais são opcionais.

## 3. Catálogo de Serviços e Valores

Arquivo: `modelo_servico.yaml`. No **Portal do Prestador > Serviços e valores > Novo serviço > Importar YAML**, selecione o modelo e confira o formulário pré-preenchido. A edição também pode ser feita no **aplicativo desktop**, sem abrir navegador; o botão Importar YAML está disponível na janela nativa.

```yaml
versao: 1
servico:
  nome: Cadastro de controle remoto — DEMO
  descricao: Cadastrar e verificar controle remoto.
  preco_servico: 50.00
  relatorio_padrao: Programação e testes concluídos.
  materiais:
    - nome: Controle remoto fictício
      quantidade: 1
      valor_unitario: 75.00
```

O catálogo aceita até 30 materiais por serviço. Em branco: `materiais: []`. Os valores utilizam **ponto** como separador decimal no YAML. No formulário, o prestador pode usar vírgula. Materiais do catálogo não geram baixa automática no estoque ao **apenas cadastrar o serviço**: o consumo ocorre na OS que os utiliza.

## 4. Orçamento com vários serviços e materiais

Arquivo: `modelo_orcamento.yaml`. Na tela **Portal do Prestador > Clientes > Novo orçamento**, use **Criar orçamento por YAML** e confira a prévia antes de gerar o PDF. O YAML não cria OS, não cria cobrança financeira e não movimenta estoque.

O arquivo de envio deve ter **somente** `versao` e `orcamento`. As seções `instrucoes`, `modelo` e `exemplo` servem de guia e devem ser removidas, como no modelo de relatório técnico.

```yaml
versao: 1
orcamento:
  cliente_nome: Condomínio Exemplo Fictício
  servicos:
    - nome: Revisão de portão — DEMO
      quantidade: 1
    - id: 12
      quantidade: 2
  materiais:
    - nome: Cabo de rede CAT6 — DEMO
      quantidade: 10
```

Regras:

- Informe exatamente um cliente: `cliente_id`, `cliente_documento` ou `cliente_nome`.
- Cada serviço/material aceita `id` OU `nome`, nunca os dois.
- Serviços precisam existir e estar ativos no catálogo; materiais precisam existir e estar ativos no estoque.
- Serviços usam o preço ativo do catálogo, que já inclui os materiais cadastrados no próprio serviço.
- Materiais adicionais usam o preço de venda ativo do estoque.
- Não existe campo de preço, desconto ou total no YAML.
- Quantidade de serviço: inteiro de 1 a 20. Quantidade de material: maior que zero, até 1.000.
- Limites: 20 serviços e 50 materiais adicionais.
- Não repita serviço/material; ajuste a quantidade em uma única linha.
- O YAML só pré-preenche a tela. A geração do PDF exige confirmação humana.

## Regras de segurança

- Não inclua CPF/CNPJ reais, senhas, tokens ou dados bancários em arquivos de teste.
- Sempre verifique CPF/CNPJ e duplicidades no cadastro antes de salvar.
- A importação de YAML não concede permissões de síndico e não envia e-mails.
- Uma importação de modelo de serviço não gera orçamento nem OS até que alguém execute essas ações.
- Não retire o `versao: 1`, não use tabulação para indentar e não ultrapasse o limite de tamanho.

## Modelo de relatório REV12 (instruções + modelo + exemplo)

O arquivo `modelo_relatorio_os.yaml` agora tem três partes:

- `instrucoes`: objetivo, regras e descrição de cada campo.
- `modelo.os`: estrutura vazia que deve ser preenchida.
- `exemplo`: relato do técnico e saída esperada.

Regras para preenchimento por IA ou pessoa:

1. Usar exclusivamente o relato do técnico.
2. Não inventar procedimentos, materiais, horários, resultados ou recomendações.
3. Preservar os nomes e a estrutura dos campos.
4. Omitir ou deixar vazio o que não foi informado.
5. Corrigir apenas a redação, sem mudar o sentido.
6. Devolver somente `versao` e `os` preenchidos; não devolver `instrucoes`, `modelo` ou `exemplo`.

O backend valida a saída contra os campos permitidos (`diagnostico`, `execucao`,
`resultado`, `relatorio_tecnico`, `materiais`) e rejeita campos desconhecidos,
materiais inválidos e arquivos acima de 64 KB.
