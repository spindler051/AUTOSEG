# Officina

Plataforma genérica de gestão de trabalho, independente de profissão, país ou
interface. O AUTOSEG é um flavor desta base; o Workaholic é o motor de dados.

## Limites

- `workaholic/` — motor, schemas, validação, persistência e contratos.
- `officina/` — contratos e serviços genéricos da aplicação.
- `flavors/autoseg/` — vocabulário, marca, configuração e módulos específicos.
- clientes (GTK, web, CLI) consomem serviços; não são donos das regras.

## Estado

Este diretório é o destino dos contratos genéricos. A aplicação atual ainda usa
módulos legados na raiz; a migração segue o `docs/PLATFORM_MIGRATION_PLAYBOOK.md`
em fatias pequenas, com testes de paridade.
