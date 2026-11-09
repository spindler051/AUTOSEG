# AUTOSEG REV09 — Auditoria e validação

> **Documento histórico.** O frontend Tkinter (`app.py`) foi removido na versão `9.6.0-dev.12`. O frontend desktop atual é `gtk_app.py` (GTK4/libadwaita).


Data: 2026-11-02
Versão local: 9.6.0-dev.3 (REV09) sobre `develop`
Versão remota integrada: `origin/develop` (REV07/REV08) + `origin/main` (CI v9.4.1)

## Arquitetura encontrada

- Desktop: `app.py` (Tkinter) inicia `PortalPrestador` na porta 8766 e `ServidorPortal` na 8765.
- Portal do Prestador: `portal_prestador.py`, HTTP próprio, autenticação de prestadores (`prestadores_ext.autenticar`).
- Portal do Cliente: `servidor_web.py` + `portal_cliente_v94.py`, login por CPF/senha (`cadastros_v9`, `cliente_fluxo_v94`).
- Banco: SQLite em `dados.db` (produção) ou `GESTAO_BANCO` (DEV em `dados_teste/autoseg_teste.db`).
- PDFs: `pdf_cliente_v9.py` gera; `fluxo_os.publicar_relatorio` versiona em `relatorios_pdf/publicados` com SHA-256.
- YAML: `importacao_yaml.py`; modelos `modelo_*.yaml`.
- Estoque/catálogo: `estoque_materiais.py`, `catalogo_servicos.py`.
- Produtividade/financeiro: `produtividade_os.py` (rateios, repasses, rascunhos, deslocamentos, financeiro pessoal).
- Versionamento: `versionador.py`, `versao.json`, CI em `.github/workflows`.

## Tabelas principais

`clientes`, `ordens_servico`, `materiais_os`, `financeiro`, `prestadores`, `os_prestadores`,
`os_responsaveis`, `os_eventos`, `os_anexos`, `os_encerramentos`, `os_documentos`,
`os_entregas`, `os_solicitacoes`, `os_atendimentos`, `v9_*`, `produtividade_*`,
`os_deslocamentos`, `os_rascunhos_web`, `estoque_*`, `catalogo_*`.

## Conciliação com o repositório

- `develop` local estava 31 commits atrás de `origin/develop`, com alterações locais não publicadas.
- Foi criado backup completo antes de qualquer mudança.
- Foi feito commit local e merge com `origin/develop`; rateio, financeiro pessoal, produtividade e versionador remotos foram preservados, além do fluxo REV09 local.
- `main` remota não foi reescrita nem recebeu force-push.

## Funcionalidades implementadas nesta revisão

1. `ASSUMIR OS` independente, com registro em `os_responsaveis` e evento, sem iniciar atendimento.
2. `EM ROTA` em `os_deslocamentos`, idempotente, com cancelamento pelo responsável e evento.
3. `INICIAR OS` independente, encerra deslocamento ativo e permite retomada de pendente.
4. Portal Prestador e desktop mostram `SALVAR RASCUNHO`; rascunho persiste em `produtividade_rascunhos` e `os_rascunhos_web`, incluindo campos técnicos, materiais e fotos.
5. Portal Cliente mostra `Em rota` na lista e no detalhe.
6. Conclusão, pendência e cancelamento mantidos, com PDF versionado e bloqueio de acesso por terceiros.
7. Importação YAML continua apenas pré-visualizando; nada é gravado sem confirmação.

## Testes executados

| Teste | Resultado |
|---|---|
| `test_rev09_fluxo_os.py` (16 critérios, HTTP real) | PASSOU |
| `test_fluxo_v7.py` | PASSOU |
| `test_autoseg_melhorias.py` (8 testes) | PASSOU |
| `test_produtividade_rev07.py` (9 testes) | PASSOU |
| `test_pf_pj_http.py` / `test_pf_pj_responsaveis.py` | PASSOU |
| `test_rev05_seguro.py` (5 testes) | PASSOU |
| `test_cadastro_v951.py` | PASSOU |
| `test_tk_v9.py` (Tkinter real, botão SALVAR RASCUNHO) | PASSOU |
| Migração em cópia do banco DEV (14 clientes, 10 OS, 3 prestadores, 5 financeiro) | contagens preservadas |

Testes antigos `test_fluxo_v5.py`, `test_fluxo_v6.py` e `test_fluxo_cliente_v94.py` já falhavam antes desta revisão por usarem a rota removida `/cliente/entrar` no servidor do prestador; foram substituídos pelo fluxo REV09 e pelos testes de portal vigentes.

## Limitações

- Homologação manual no navegador/Mac não foi executada nesta sessão; os testes HTTP usam servidores reais em portas temporárias.
- Envio Gmail real depende de OAuth local e não foi disparado.
- Emissão de NFS-e permanece como rascunho JSON, sem integração fiscal.
- Rateio exige OS concluída e técnico responsável; OS pendente/cancelada permanece bloqueada.
