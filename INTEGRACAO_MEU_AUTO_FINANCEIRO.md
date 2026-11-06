# AUTOSEG + Meu Auto Financeiro — instalação e operação

## O que foi integrado

- **Uma única aplicação macOS**: abre o AUTOSEG existente; não há novo `.app` em `/Applications`.
- **Uma única porta para o prestador e o módulo financeiro**: `http://127.0.0.1:8766/auto-financeiro`.
- Se o Cloudflare já publica o Portal do Prestador, a mesma URL seguida de `/auto-financeiro` publica o módulo. **NÃO é necessário outro túnel.**
- A inicialização automática dos túneis já é controlada pela opção **Início automático** na janela do AUTOSEG: precisa de autorização explícita uma vez e `cloudflared` instalado; após isso é reutilizada nas próximas inicializações. **Não publique dados financeiros reais em Quick Tunnels de testes sem proteção externa adicional.**
- Prestadores usam a sessão do Portal do Prestador; familiares entram com conta própria por convite.
- Recebimentos do prestador são conciliados em até ~15 segundos, também após confirmações via portal ou desktop. Os repasses a técnicos secundários só entram quando confirmados. Valores ainda a receber NÃO entram no saldo.
- Banco exclusivo do módulo: `meu_auto_financeiro.db` sob `AUTOSEG_BASE` (por padrão `~/gestaoservicos_MAIN/` no iniciador GTK). Comprovantes: `meu_auto_financeiro_comprovantes/`. **Inclua esses dados no backup privado**, não em ZIP de código.
- Os recebimentos AUTOSEG e o saldo pessoal são exibidos separadamente; despesas pessoais não modificam as tabelas financeiras do AUTOSEG.

## Instalação no Mac (não executada por este pacote)

1. **Faça backup integral do AUTOSEG e do banco real antes de começar.** Feche o aplicativo e os portais.
2. Descompacte este ZIP e abra a pasta `gestaoservicos_MAIN` extraída.
3. Execute `INSTALAR_MEU_AUTO_FINANCEIRO.command` (se o Gatekeeper bloquear, use o Terminal: `zsh INSTALAR_MEU_AUTO_FINANCEIRO.command`).
4. O instalador verifica a versão dos três arquivos que substitui; se forem diferentes do ZIP base, **interrompe para evitar sobrescrever alterações mais recentes**. Ele salva cópias em `~/AUTOSEG_Arquivos/Backups/MeuAutoFinanceiro_.../`.
5. Abra o AUTOSEG existente normalmente. No desktop, use **Meu Auto Financeiro**; no Portal do Prestador, o item **Meu Auto Financeiro**.
6. Para acesso externo, use o controle já existente de túneis. Verifique autenticação e permissões **antes** de disponibilizar informações financeiras reais na internet.

## Reverter

Pare o AUTOSEG. Copie de volta os três arquivos originais guardados na pasta de backup do instalador (`gtk_app.py`, `portal_prestador.py`, `links_publicos.py`) para `~/gestaoservicos_MAIN/`. O módulo e seus dados podem permanecer arquivados sem afetar a versão anterior; não apague os bancos `.db` nem os comprovantes. Se a instalação tiver sido realizada em outro diretório, restaure no mesmo destino escolhido.

## Testes feitos neste ambiente

`python3 -m unittest -v test_meu_auto_financeiro` e testes de compatibilidade selecionados. O empacotamento macOS e a publicação Cloudflare precisam de teste no próprio Mac; não foram executados daqui. Testes usam bancos temporários fictícios.

## Escopo já incluído

Saldo individual, extrato e estorno, entradas manuais recebidas, salários recorrentes com confirmação, família e saldos consolidados, convites e gestão administrativa, contas compartilhadas, comprovantes, empréstimos e conciliação AUTOSEG. Antes de uso em produção, valide os cenários reais com cópias dos dados e revise autorização, TLS, backup e restauração.
