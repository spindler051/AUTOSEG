# Registro de migração

| Item | Status | Evidência | Próximo passo |
|---|---|---|---|
| Novo repositório Workaholic | Protótipo | `pyproject.toml` e pacote Python | Inicializar Git no ambiente do usuário |
| Esquemas de entidades | Protótipo | `domain/schema.py` | Versionamento e migrações de schema |
| YAML / SQLite | Protótipo | `repositories.py` + testes | Transações e testes de concorrência |
| CLI | Protótipo | `cli/main.py` | Melhorar ergonomia e comandos de importação |
| Artes | Exemplo de configuração | `examples/arts/schema.yaml` | Importador verificado de comissões legado |
| AUTOSEG | Exemplo de configuração | `examples/autoseg/schema.yaml` | Inventariar regras e revisar com responsável técnico |
| AUTOSEG clientes | Integração inicial via adaptador | `../integracao/clientes.py`, `../test_integracao_clientes.py` | Migrar OS e os demais escritores legados |
| GUI | Não iniciado | — | Responsável frontend/UX definir contratos |
| Módulos fiscais/PDF | Não iniciado | — | Responsável técnico AUTOSEG especificar |
| Lua / Rust | Futuro | — | ADR de transição sem prazo definido |
| Auditoria/aprovação | Não iniciado | — | Definir semântica e testes |
