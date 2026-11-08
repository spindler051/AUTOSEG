# AUTOSEG flavor

AUTOSEG é a distribuição de segurança e automação sobre o Officina. Esta pasta
guarda o que é específico do flavor: marca, configuração, modelos e, no futuro,
módulos de portal/fiscal. O código genérico deve ficar em `officina/` e o motor
em `workaholic/`.

## Estrutura

- `branding/` — logo e ícones da distribuição.
- `config/` — configurações padrão do flavor.
- `templates/` — modelos YAML de cliente, serviço, orçamento e relatório.
- `docs/` — índice da documentação específica do AUTOSEG.

## Regra

Core não importa flavor. O flavor pode depender de contratos do Officina e do
Workaholic. A migração é incremental; módulos legados continuam na raiz até
serem extraídos com testes de paridade.
