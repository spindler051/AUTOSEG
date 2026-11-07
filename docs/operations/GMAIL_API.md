# Gmail API

O AUTOSEG tem adaptador Gmail OAuth para enviar o relatório da OS com PDF
anexado. O envio real continua opcional e deve ser validado antes de uso com
clientes reais.

## Configuração

- Credenciais OAuth em `~/.config/autoseg/gmail/credentials.json`.
- Token em `~/.config/autoseg/gmail/token.json` (permissão privada, fora do
  Git).
- Escopo mínimo: `https://www.googleapis.com/auth/gmail.send`.
- `AUTOSEG_GMAIL_DESATIVADO=1` desliga o envio para testes sem rede.
- Cada prestador tem configuração individual em `prestadores_config`
  (`provedor_email`, `email_remetente`, `credencial_env`).

## Regras

1. O envio ocorre em thread separada; a interface não bloqueia.
2. Falha fica registrada como pendência, nunca como enviada.
3. Não guardar `client_secret`, token de acesso ou refresh token no SQLite,
   YAML ou Git.
4. Testar com contas fictícias; não usar dados reais sem backup e revisão.
5. Reenvio deve ser explícito e auditado.

## Testes

```bash
./.venv/bin/python -m unittest -v test_gmail_integracao
```

O teste não envia e-mail real quando `AUTOSEG_GMAIL_DESATIVADO=1`.
