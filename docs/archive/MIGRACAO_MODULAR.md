# Registro de migração gradual — AUTOSEG / Workaholic

## Estado nesta entrega
- Sistema principal: **Gestão de Serviços AUTOSEG**.
- Engine interna experimental: **`workaholic/`** (inalterada pela v9.4).
- Diretório lógico do projeto: `GestaoServicos`. O sufixo `2` é apenas nome
  do diretório local ativo no Mac da pessoa desenvolvedora.
- `INICIAR_AUTOSEG.command` permanece como inicializador da GUI.

## V9.4 — Portal do cliente
Status: implementado e testado contra banco SQLite temporário.
Mudanças restritas a cadastro pessoal, perfil, solicitação PF, busca/pre-
cadastro de organização e registro de vínculo de responsável.
API HTTP mantida em `portal_prestador.py`; novas regras PF foram separadas
em `cliente_fluxo_v94.py`. Não foram migrados GUI, financeiro ou NFS-e.

## Próximos passos (não executados)
- Consolidar casos de uso independentes de HTTP no serviço de aplicação.
- Extrair contratos genéricos de entidades e repositórios Workaholic.
- Evoluir UX com a pessoa responsável pela GUI.
- Validar relatórios e regras fiscais com a pessoa responsável pelo AUTOSEG.

## Regras para futuras IAs
1. Inspecionar o ZIP/código real antes de alterar qualquer módulo.
2. Não alterar `dados.db` nem atualizar PDFs históricos diretamente.
3. Adicionar migrações idempotentes e reversíveis sempre que possível.
4. Registrar testes e comportamento legado antes de mudar interface.
5. Não conceder acesso administrativo apenas por CPF ou CNPJ informado.
6. Reutilizar `bash ~/GestaoServicos2/INICIAR_AUTOSEG.command` no Mac atual.
