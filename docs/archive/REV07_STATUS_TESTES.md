# AUTOSEG REV07 — Branch de teste e limites de homologação

**Branch:** `teste/produtividade-rev07`  
**PR:** https://github.com/spindler051/AUTOSEG/pull/6  
**Base remota:** `develop` do GitHub (não substitui o pacote REV06_DEV local).  
**Estado:** EXPERIMENTAL — NÃO INSTALAR EM PRODUÇÃO.

## Entregue com commits

- Atribuição de OS sem início automático; OS Pendente atribuída não pode ser assumida por colega enquanto o responsável não a liberar. Reatribuição administrativa restrita ao desktop.
- `Em rota` manual por técnico responsável, histórico, remoção ao iniciar e na troca de responsável; indicador aparece no painel do cliente PJ.
- Rascunho editável persistido no SQLite; botões Salvar/Recuperar, envio prévio de fotos e miniaturas de fotos existentes; registros incrementais de etapas Pendente/Concluída.
- Bloqueio de acesso a PDF condominial por moradores no Portal Cliente e acesso a documentos/anexos do Portal Prestador restrito aos participantes.
- Validação de ao menos um e-mail ao concluir; destinatários automáticos PF/condomínio/síndico, mais adicional; morador não é destinatário automático.
- Adaptador Gmail OAuth, anexo PDF, status de envio. **Envio real desligado por padrão**: habilitar somente em ambiente controlado com `AUTOSEG_GMAIL_ENVIO=1` e token privado em `~/.config/autoseg/gmail/token.json`. Falha deixa registro de pendência, não confirma envio.
- Rateio transacional exclusivo na conclusão, valores em centavos e repasses manuais, dados bancários por técnico, visões de financeiro pessoal e restrição de acesso.
- Testes de SQLite para atribuição, deslocamento, rascunho, etapas, PDF, validação de e-mail, rateio e repasses; CI usa Python 3.13.

## PENDENTE — não considerar entrega completa

1. **Reconciliar o ZIP REV06 mais recente com o `develop` do GitHub.** O código remoto está atrasado e carece de `importacao_yaml.py`, `catalogo_servicos.py`, `estoque_materiais.py` e outros módulos do pacote local. Estas rotinas devem ser reconciliadas ANTES de implantar.
2. YAML reversível, prévia de diferenças, mescla com rascunho e descarte seguro após upload errado.
3. Catálogo central de materiais com autocomplete, IDs estáveis e deduplicação no desktop/portal/OS; estoque exclusivo do desktop.
4. Cadastro de UF 27 estados em todas as interfaces, identidade visual e melhoria responsiva.
5. Tela desktop de `Em rota` e financeiro consolidado por prestador, com controle de repasse.
6. Interface completa de múltiplos técnicos e legenda por fotografia na mesma etapa de conclusão (o branch permite ajustar legendas nas fotos já salvas).
7. Consolidar etapas no PDF final, com autoria e fotos, revisão de permissões dos demais downloads e vínculos sindicais.
8. Gmail: configuração OAuth do Mac, teste real com e-mail de teste, idempotência e rotina explícita de reenvio; não usar automaticamente dados pessoais de teste.
9. Rascunho: autosave e controle de concorrência na UI (a API já oferece `versao_esperada`); falta integrar a versão ao formulário web.
10. Testes fim a fim desktop/Portal Prestador/Portal Cliente em máquina macOS, com banco fictício, túneis e rollback verificado.

## Como validar sem arriscar produção

- Revisar o diff do PR #6 e a aba **Checks**; não mesclar com `main`.
- Fazer backup do banco e anexos e usar somente banco temporário ou de desenvolvimento.
- Instalar dependências de `requirements.txt` com Python 3.13 no ambiente DEV.
- Rodar `python3 -m py_compile produtividade_os.py gmail_service.py portal_prestador.py portal_v9.py servidor_web.py`.
- Rodar `python3 -m unittest -v test_produtividade_rev07`.
- Testar cenários com usuários e e-mails **fictícios**; não ativar envio Gmail real até permissões e destinatários estarem corretos.
- Confrontar arquivos do branch com REV06 ZIP real; reconciliar e repetir testes antes de qualquer promoção para `develop` ou `main`.

**Nota:** commits e execução do CI não equivalem a implantação/homologação local. O banco SQLite de produção continua intocado.
