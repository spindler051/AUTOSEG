# Meu Auto Financeiro

## O que está integrado

- Uma única aplicação macOS; não há `.app` separado.
- Uma única porta para o prestador e o módulo financeiro:
  `http://127.0.0.1:8766/auto-financeiro`.
- Se o Cloudflare já publica o Portal do Prestador, a mesma URL seguida de
  `/auto-financeiro` publica o módulo. Não é necessário outro túnel.
- Os túneis seguem o controle existente de **Início automático**. Não publique
  dados financeiros reais em Quick Tunnels de teste sem proteção adicional.
- Prestadores usam a sessão do Portal do Prestador; familiares entram com conta
  própria por convite.
- Recebimentos do prestador são conciliados em até ~15 segundos, inclusive após
  confirmações via portal ou desktop. Repasses a técnicos secundários só entram
  quando confirmados. Valores a receber não entram no saldo.
- Banco exclusivo: `meu_auto_financeiro.db` sob `AUTOSEG_BASE`.
  Comprovantes: `meu_auto_financeiro_comprovantes/`. Inclua esses arquivos no
  backup privado; nunca em ZIP de código.
- Recebimentos AUTOSEG e saldo pessoal aparecem separados. Despesas pessoais
  não alteram as tabelas financeiras do AUTOSEG.

## Operação

O módulo já faz parte do aplicativo; não há instalador separado. Antes de usar
dados reais:

1. faça backup integral do AUTOSEG e do banco;
2. feche o app e os portais;
3. valide o fluxo com uma cópia dos dados;
4. confira autenticação, permissões, TLS e restauração.

Para reverter uma atualização, restaure os arquivos do backup e mantenha os
bancos e comprovantes arquivados. Não apague `meu_auto_financeiro.db` nem a
pasta de comprovantes.

## Testes

```bash
./.venv/bin/python -m unittest discover -s tests -p 'test_meu_auto_financeiro.py' -v
```

Testes usam bancos temporários fictícios. Empacotamento macOS e publicação
Cloudflare precisam ser validados no Mac real.
