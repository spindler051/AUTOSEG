# AUTOSEG REV10 — Rascunho e legendas de fotos

> **Documento histórico.** O frontend Tkinter (`app.py`) foi removido na versão `9.6.0-dev.12`. O frontend desktop atual é `gtk_app.py` (GTK4/libadwaita).


Data: 2026-11-02
Versão: 9.6.0-dev.4 (REV10)
Branch de desenvolvimento: `develop`
Branch de produção: `main` (merge `93031a5`)

## Correções entregues

### SALVAR RASCUNHO

- Botão visível no topo (sticky) e no rodapé do formulário de OS do Portal Prestador.
- Também disponível no desktop (`app.py`, formulário da OS).
- Salva sem alterar o status: diagnóstico, execução, resultado, relatório técnico, observações, materiais, quantidades, valores, fotos e legendas.
- Persiste em `produtividade_rascunhos`, `os_rascunhos_web`, `os_detalhes_os`, `materiais_os`, `os_anexos` e `v9_anexos_visiveis`.
- Recuperação automática ao reabrir a OS e após reiniciar o servidor.
- Confirmação “Rascunho salvo com sucesso” e mensagens de erro do servidor.

### Legendas das fotos antes da finalização

- Cada arquivo selecionado exibe prévia no navegador e um campo **Legenda da foto**.
- Fotos já salvas no rascunho reaparecem com prévia e legenda editável.
- A associação usa `os_anexos.chave` e `os_anexos.sha256`; reenviar o mesmo arquivo atualiza a legenda e não duplica a foto.
- A legenda é gravada em `v9_anexos_visiveis.legenda` e lida pelo gerador de PDF.
- A finalização atualiza as legendas antes de gerar/publicar o PDF; teste extrai o texto do PDF e confirma as legendas finais.

## Testes executados

| Teste | Resultado |
|---|---|
| `test_rev09_fluxo_os.py` (HTTP, fotos, deduplicação, PDF com legenda) | PASSOU |
| `test_visual_rev10.py` (Chrome/Playwright: botões, prévias, legendas, salvar, reabrir, editar) | PASSOU |
| `test_visual_persistencia_rev10.py` (reinício do servidor + legenda recuperada) | PASSOU |
| `test_tk_v9.py` (botão SALVAR RASCUNHO no desktop) | PASSOU |
| `test_fluxo_v7.py`, `test_autoseg_melhorias.py`, `test_produtividade_rev07.py`, `test_pf_pj_*`, `test_rev04/05/08` | PASSOU |

Evidências visuais: `~/AUTOSEG_DIST/evidencias/01..07-*.png`.

## Aplicativo macOS

- Bundle: `~/Applications/AUTOSEG.app`
- Ícone: `~/AUTOSEG_DIST/AUTOSEG.icns`, gerado de `icone.png` (1254×1254, RGBA, transparência preservada).
- Identificador: `br.com.autoseg.gestaoservicos`
- Versão do bundle: 9.6.0
- Dados: `~/gestaoservicos_MAIN/dados.db` (fora do bundle)
- Instância única por `flock` em `~/gestaoservicos_MAIN/.autoseg.lock`.
- Portas: cliente 8765, prestador 8766.

## Limitações

- Envio Gmail depende de OAuth local e não foi disparado.
- NFS-e permanece rascunho JSON.
- A homologação visual no app MAIN não usa credenciais de produção; o fluxo foi validado no DEV com Chrome e servidor real.
