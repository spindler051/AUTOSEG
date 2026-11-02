# AUTOSEG — Changelog

## 9.6.0-dev.5 — REV11 — 2026-11-02 — develop/main

- **Interface GTK4/libadwaita** adotada como padrão (branch `feature/gtk4-libadwaita` mesclada): `gtk_app.py`, `gtk_comum.py`, `gtk_dialogos.py`, mesmo backend/banco/regras.
- **Envio automático e assíncrono do relatório por Gmail** ao concluir a OS:
  - `gmail_service.enviar_relatorio_os_concluida` envia o PDF em thread separada e registra status/message_id em `produtividade_email`.
  - Acionado no Portal Prestador e nos desktops GTK4 e Tkinter.
  - Bibliotecas do Google importadas sob demanda; falhas não travam a interface e ficam registradas.
  - `AUTOSEG_GMAIL_DESATIVADO=1` desliga o envio para testes sem rede.
- Inicializadores GTK4 em `/Applications` (clique único): `AUTOSEG.app` (main) e `AUTOSEG DEV.app` (develop).
- Testes: `test_gmail_integracao.py` (enviado, falhou, desativado) e smoke do app GTK4 no macOS.

Pendente: homologação manual do envio real (destinatário válido) e liberação de versão estável.


## 9.6.0-dev.4 — REV10 — 2026-11-02 — develop

- **SALVAR RASCUNHO** agora aparece em destaque no topo e no rodapé do formulário da OS no Portal Prestador, além do desktop. Salva diagnóstico, execução, resultado, relatório, materiais, valores, observações, fotos e legendas sem alterar o status.
- **Legendas de fotos antes da finalização:** cada foto nova mostra prévia e campo “Legenda da foto”; fotos já salvas no rascunho reaparecem com a legenda editável.
- `os_anexos` recebeu `chave` e `sha256`; reenvios do mesmo arquivo atualizam a legenda em vez de duplicar a foto no SQLite.
- A legenda é associada à foto por chave/hash e incluída no PDF final (validado com extração de texto do PDF).
- O rascunho persiste após reiniciar o servidor e é recuperado ao reabrir a OS; teste visual com Chrome/Playwright e teste HTTP automatizado.
- Rodapé do Portal Prestador passa a exibir a versão em execução.

Pendente: homologação manual do usuário e promoção para main.

## 9.6.0-dev.3 — REV09 — 2026-11-02 — develop (validação local)

Fluxo de OS separado em ações independentes:

- **ASSUMIR OS** atribui responsável e horário sem iniciar o atendimento.
- **EM ROTA** registra o deslocamento em `os_deslocamentos`, é idempotente, aparece no Portal Prestador e no Portal Cliente e pode ser cancelado pelo responsável.
- **INICIAR OS** registra o início efetivo, encerra o deslocamento ativo e permite retomada de OS pendente. O fluxo antigo "INICIAR OS — ASSUMIR AUTOMATICAMENTE" foi removido.
- **SALVAR RASCUNHO** no Portal Prestador e no desktop, com persistência dos campos técnicos, materiais, valores e fotos em `produtividade_rascunhos` e `os_rascunhos_web`. Recuperação após reiniciar o servidor testada.
- Portal Prestador exibe Em rota na lista; Portal Cliente exibe Em rota na lista e no detalhe.
- Importação/rateio financeiro e financeiro pessoal do REV07 preservados, incluindo bloqueio de rateio fora da conclusão.
- Importação YAML, pré-visualização, desfazer, catálogo e estoque mantidos dos REV06/REV08.
- Testes novos em `test_rev09_fluxo_os.py` cobrem assumir, em rota, início, rascunho após reinício, conclusão, pendência, cancelamento, YAML sem gravação, PDF autorizado e bloqueio de terceiros.

Pendente: homologação manual das interfaces no Mac, envio Gmail real (depende de OAuth), nota fiscal (somente rascunho) e itens ainda parciais descritos em `ROADMAP.md`.

## 9.6.0-dev.2 — REV08 — 2026-11-02 — develop (validação local pendente)

- Importação YAML de materiais transacional, sem gravações parciais em falhas.
- Materiais de Serviços e Valores integrados ao catálogo único sem alterar estoque ou preços já cadastrados.
- Busca normalizada por nome/código e alertas de estoque negativo/mínimo na interface desktop.
- Prévia e desfazer YAML no Portal Prestador, com proteção dos campos preenchidos na aba; fotos não enviadas continuam exigindo novo upload.
- Correção de teste antigo do Portal Cliente e bloqueio de disparo acidental de Gmail durante descoberta de testes.
- Testes unitários novos; nenhum banco real foi acessado na validação.

Pendente: homologar interfaces no Mac; não estão implementados integralmente os 78 requisitos. Não atualizar main.

## 9.6.0-dev.1 — REV08 — 2026-11-02 — develop

Introduzidos metadados de versão, versionador com controle de branch, testes, CI no develop e checklist de 78 requisitos.

Estado: PREPARAÇÃO. Não há migrações SQLite ou mudanças nos módulos operacionais. Os 78 requisitos continuam em homologação pendente. O branch main não deve ser atualizado antes de testes.

Bloqueio: reconciliar alterações e arquivos não publicados do Mac antes de sincronizar o código remoto com o DEV local.
