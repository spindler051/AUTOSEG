# Instruções para agentes que editarem Workaholic

1. Este repositório é **Workaholic**, não Workcore. Não importar nenhum módulo AUTOSEG para dentro do núcleo.
2. Core tem domínio genérico, API Python e persistência via contrato. Produto AUTOSEG e GUI são camadas externas.
3. Ler `README.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` e `docs/MIGRATION_LEDGER.md` antes de editar.
4. Uma alteração por vez; testes de contrato com **ambos** adaptadores YAML e SQLite.
5. Não inventar regras técnicas, emissão fiscal, requisitos de relatórios ou UX do AUTOSEG; obter revisão das pessoas responsáveis.
6. Não manipular dados reais, tokens, senhas, CPF/CNPJ nem versionar bancos de clientes.
7. Não declarar implementados GUI, plugins Python, Lua, Rust, auditoria ou migração legada: são planos, não entregas.
8. Atualizar `docs/MIGRATION_LEDGER.md` após trabalho testado; documentar falhas e riscos.
9. Priorizar formatos portáveis e contratos independentes de Python para facilitar eventual núcleo Rust e scripting Lua.
10. Mudanças destrutivas exigem backup, migração verificada e rollback. Git deve usar commits pequenos.
