# Configuração opcional de túnel permanente AUTOSEG

Este arquivo é um **modelo**, não contém credenciais nem ativa um serviço. Para publicar aplicações com nomes fixos, é necessária uma conta Cloudflare e um domínio seu configurado na plataforma. Antes, revisite a segurança de `servidor_web.py` (porta 8765) e confirme proteção de login/Cloudflare Access nos dois endereços.

Procedimento para túnel local gerenciado (alternativamente use painel Cloudflare, recomendado pela própria Cloudflare):

1. `cloudflared tunnel login`
2. `cloudflared tunnel create autosseg`
3. Copie `CLOUDFLARE_TUNEL_FIXO_EXEMPLO.yml` para `~/.cloudflared/config.yml` e edite **UUID, credenciais, subdomínios** para os seus valores, sem compartilhar a chave JSON.
4. Crie rotas DNS para os dois subdomínios:

   ```bash
   cloudflared tunnel route dns autosseg sistema.seudominio.com
   cloudflared tunnel route dns autosseg portal.seudominio.com
   ```

5. `cloudflared tunnel ingress validate` e `cloudflared tunnel run autosseg`.

O mesmo túnel roteia as portas distintas `8765` e `8766`. O arquivo final precisa terminar com a regra catch-all `http_status:404`. Esse tipo de túnel não deve ser iniciado com dados reais antes da configuração de autenticação de acesso e da revisão de segurança dos serviços.

Documentação oficial: https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/
