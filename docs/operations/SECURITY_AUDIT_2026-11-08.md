# Auditoria de segurança — ações de 2026-11-08

Relatório original: `/Users/idkosx/security-audit-gestaoservicos-dev.md`.

## Resolvido

| ID | Ação |
|---|---|
| A01 | API desktop exige admin nas áreas de prestadores, estoque, empresa, composição, organizações e escritas financeiras. Bind não-loopback exige `AUTOSEG_DESKTOP_TOKEN`; o cliente HTTP envia o header. |
| A02 | Reset de senha legada, desativar, excluir e mesclar cliente exigem admin e são auditados. |
| A03 | Organizações, vínculos, síndico, mesclagem e desativação de cliente exigem admin no portal e na API. |
| A04 | `chmod 700/600` nos diretórios operacionais; refs de backup com PII removidas; `git reflog expire` e `git gc --prune=now`; e-mails do banco de teste trocados por `.invalid`. |
| A05 | Corpo pré-autenticação limitado a 64 KB; timeouts de socket de 15 s; uploads grandes só depois da sessão. |
| A06 | POSTs dos portais validam `Origin`/`Referer` contra o `Host`. |
| A07 | Rate limit e auditoria usam `feedback_portal.ip_requisicao` (CF-Connecting-IP/X-Forwarded-For só em loopback). |
| A09 | Sessões legadas guardam o hash da credencial e são invalidadas na troca de senha. |
| A10 | O formulário de OS não embute mais contatos de todos os clientes; busca o contato do cliente selecionado em `/clientes/<id>/contato`. |
| A12 | `feedback_ia.local.json`, logs e dados operacionais com permissão restrita. |
| A13 | Access log com IP real, método, caminho e status nos portais. |

## Pendente ou parcial

- **A05:** não há pool/limite explícito de threads nem proxy com `client_max_body_size`; recomendado antes de exposição pública.
- **A06:** a proteção é por `Origin`/`Referer`, sem token CSRF nos formulários de login/cadastro.
- **A08:** poda de mapas implementada para autenticação do prestador e sessões do portal; mapas de v9/cliente ainda precisam de TTL global.
- **A10:** `/clientes` ainda lista todos os clientes para prestador; a matriz de vínculo por OS continua pendente.
- **A11:** workflows e lockfile com hashes não foram alterados; dependem de token com escopo `workflow` e revisão de CI.

## Regra

Nenhuma exposição pública de `8766`/`8866` sem Cloudflare Access/WAF/TLS, proxy com limites e revisão humana externa.
