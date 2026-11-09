# Decisões aceitas

1. Nome: **Workaholic**; executável `workaholic-cli`, alias `workaholic`.
2. Núcleo novo independente do AUTOSEG legado; migração por adaptadores.
3. Backend genérico com entidades, campos e relacionamentos configuráveis.
4. Estados e transições configuráveis por aplicação.
5. Configuração por YAML e posteriormente GUI usando o mesmo modelo.
6. Registros independentes; visões de calendário, cliente ou estado pertencem à GUI.
7. Armazenamentos YAML e SQLite intercambiáveis por contrato (sem sincronização automática).
8. Multiusuário opcional, **não incluído no protótipo**.
9. Exclusão configurável: arquivar, apagar ou restringir.
10. Auditoria e aprovações configuráveis por entidade (**planejadas**).
11. Core local; API, acesso remoto e Cloudflare ficam acima dele.
12. Extensões híbridas YAML + Python (**planejadas**).
13. Motor de automações e agendamento: decisão adiada.
14. Migração futura para Rust; Lua para scripting interpretado onde necessário.
15. Código original Workaholic sob 0BSD. Avaliar direitos antes de incorporar código legado de terceiros.
