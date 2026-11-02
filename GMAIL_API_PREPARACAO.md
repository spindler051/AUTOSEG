# Preparação da Gmail API — AUTOSEG DEV

**Situação: preparação de integração, sem envio automático.** O botão de e-mail atual ainda cria rascunhos `.eml`, que o prestador deve revisar e enviar manualmente.

## Configuração por prestador (já disponível no desktop)

Abra **Prestadores e atribuições → E-mail e dados bancários do prestador**. Cada prestador tem configuração individual na tabela `prestadores_config`:

- `provedor_email`: selecionar `Gmail API`.
- `email_remetente`: endereço Gmail autorizado do prestador.
- `credencial_env`: nome de uma variável de ambiente, **nunca** o token.
- Os campos bancários e Pix pertencem somente ao prestador selecionado.

## Implementação futura segura

1. Registrar aplicativo OAuth no Google Cloud; utilizar escopo mínimo `https://www.googleapis.com/auth/gmail.send` para enviar mensagens autorizadas.
2. Autenticar cada prestador individualmente por consentimento OAuth. Verificar a identidade do remetente e as permissões da conta Gmail.
3. Armazenar os segredos no Keychain do macOS ou cofre de credenciais; não guardar `client_secret`, tokens de acesso ou refresh token no SQLite, no YAML ou no Git.
4. Adicionar método de envio que obtenha credenciais **somente do prestador logado**, reconstrua a mensagem com relatório PDF e confirme o destinatário antes do envio.
5. Registrar ID da mensagem Gmail, OS, prestador, data, status, falhas e repetição de envio na auditoria. Não enviar mensagens automaticamente após mudanças de estado de OS sem opt-in.
6. Testar com contas de teste, sem mensagens para clientes reais.

**Ainda não implementado:** autorização OAuth, renovação de credenciais, envio real, cancelamento/retentativas, limites e gestão de falhas da API. A seleção `Gmail API` no desktop não ativa nenhum envio.
