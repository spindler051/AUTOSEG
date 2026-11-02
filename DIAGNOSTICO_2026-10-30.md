# Diagnóstico técnico do ZIP — AUTOSEG DEV

**Origem analisada:** ZIP enviado pelo usuário em 30/10/2026. Os arquivos de código foram analisados em cópia temporária; não foi executada gravação em base de produção.

## Arquitetura encontrada

- `app.py`: interface desktop Tkinter, inicializa `banco`, extensões, portais.
- `banco.py`: SQLite principal, `BANCO` respeita `GESTAO_BANCO`.
- `cadastros_v9.py`: `v9_usuarios`, `v9_organizacoes`, `v9_vinculos`, `v9_chamados`; converte chamados em OS.
- `cliente_fluxo_v94.py`/`portal_cliente_v94.py`: conta de CPF, PF e solicitações de organizações.
- `portal_prestador.py`/`portal_negocios.py`: web do prestador, clientes, OS, materiais, PDF, registros financeiros.
- `prestadores_ext.py`: usuários prestadores, atribuições, anexos, rascunho `.eml` e PDF.
- `portal.js`: interações das tabelas e do formulário de OS do prestador.

## Fluxo correto de solicitação

`Portal do Cliente -> v9_chamados -> cadastros_v9._criar_os_no_registro -> clientes provisório (se necessário) -> ordens_servico(status=Pendente) -> os_solicitacoes -> lista de OS ativas do prestador`.

O código do ZIP já implementava esse fluxo para organizações. Esta entrega acrescenta teste de regressão e reconciliador também na inicialização do servidor do prestador. **Isso não prova que todos os cenários HTTP na instalação do usuário funcionam:** testar no Mac com contas e documentos fictícios.

## Diagnóstico dos cadastros

Não são necessariamente dois arquivos de bancos: são **tabelas e fluxos distintos no mesmo SQLite**. O cadastro administrativo novo podia ser criado após a rotina `cad.instalar`, deixando a organização ainda ausente para o portal cliente. A sincronização imediata agora acontece ao salvar pelo desktop e prestador, com bloqueio de conflito de CNPJ. Organizações antigas, já mescladas ou com dados divergentes não são unificadas automaticamente.

## Entregas desta etapa

- Sincronização transacional de PJ, proteção de exclusão e de CNPJs divergentes.
- Seleção pesquisável de cliente na criação de OS; filtragem das tabelas carregadas no prestador.
- Zero materiais por padrão; remover fotos selecionadas no desktop e na web sem recarregar.
- Importação YAML revisável, não automática, apenas no prestador.
- Configurações de banco/PIX e referência de credencial de e-mail por prestador; rascunho EML com dados configurados.
- Reconciliador de solicitações órfãs ao iniciar o prestador.

## Testes

- `python test_autoseg_melhorias.py`: oito cenários com SQLite temporário.
- `python test_autoseg_http_novo.py`: teste ponta a ponta HTTP com servidores locais temporários; solicitação do cliente aparece como OS pendente no prestador.
- `python test_v953_fluxo.py`: casos legados compatíveis.
- `python -m compileall -q ...`: compilação sintática.
- Testes legados como `test_v92.py`, `test_v94_correcoes.py` e `test_v953_http.py` falhavam por pressupostos/rótulos/portas antigos; não devem ser tomados como aprovação ou reprovação funcional da nova arquitetura sem atualização.

**Pendentes de homologação:** interface macOS Intel, imagens reais (fictícias), SMTP/APIs externas, migração de dados anteriores, conexões Cloudflare e integridade de PDFs publicados.
