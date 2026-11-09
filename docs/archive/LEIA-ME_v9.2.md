# AUTOSEG v9.2 — correção de cadastro e login do cliente

A **v9.1** expunha o login antigo por ID na página `/cliente` enquanto o cadastro de CPF/senha estava separado em `/pj`. A **v9.2** corrige essa divergência.

- `/cliente`: entrada principal por CPF e senha escolhida no cadastro.
- `/cliente/cadastro`: formulário com nome, CPF, telefone, senha e confirmação. O cadastro mantém compatibilidade com a conta pessoal do fluxo PJ (`/pj`).
- `/cliente/legado`: mantém o acesso anterior por ID e senha às OS antigas.
- `/clientes/novo` e `/clientes/{id}` no portal administrativo: senha opcional e confirmação, exigindo mínimo de 10 caracteres. Alteração de cadastro sem senha não redefine credencial.
- Desktop, opção **ACESSO WEB / SENHA**: permite escolher e confirmar uma senha, em vez de gerar uma senha aleatória.
- Senhas não são salvas em texto puro; continuam usando o hash existente do projeto.

**Nota importante:** contas por CPF de `v9_usuarios` e acessos legados por ID de `cliente_acessos` são mecanismos existentes distintos. O cadastro CPF **não vincula automaticamente** OS antigas a um CPF (isso exigiria validação de identidade). Para consultar as OS antigas utilize `/cliente/legado` até o vínculo ser implantado.

**Instalação:** faça cópia da pasta `~/GestaoServicos` e feche a versão anterior. Extraia este ZIP na pasta Downloads e rode `bash ~/Downloads/AUTOSEG_v9_2/INSTALAR_NO_MAC.command`. Depois inicie com `bash ~/GestaoServicos/INICIAR_AUTOSEG.command`.

O instalador exige a pasta antiga existente, faz backup consistente do banco de dados antes de copiar módulos e **não substitui** `dados.db`, `banco.py` ou `servidor_web.py`.

**Testes:** `python test_v92.py` e `python test_v91.py`, com banco temporário fictício. Testes reais no Mac ainda são necessários. Não exponha o Quick Tunnel a dados reais sem auditoria de segurança.

# AUTOSEG — v9.1 (correção de fluxo, fotos, portais e Cloudflare)

**Atualização sobre a v9, sem substituir `dados.db`, `banco.py`, `servidor_web.py`, imagens ou PDFs históricos.** Instale somente sobre a pasta original `~/GestaoServicos`.

## Instalação no Mac

1. Feche o aplicativo AUTOSEG e, se possível, finalize os túneis de teste antigos.
2. Extraia o ZIP da v9.1 na pasta Downloads.
3. Execute:

```bash
cd ~/Downloads/AUTOSEG_v9_1
bash ./INSTALAR_NO_MAC.command
bash ~/GestaoServicos/INICIAR_AUTOSEG.command
```

O instalador verifica a estrutura original, compila os módulos, realiza backup consistente do SQLite e só depois copia o código. A pasta de backup estará em `~/GestaoServicos/backups/antes_v9_1_...`.

## Correções incluídas

- **Pessoa física e jurídica:** conta pessoal com CPF, telefone e **senha escolhida e confirmada** no cadastro em `/pj/cadastro`. A URL `/pj` foi preservada por compatibilidade, mas a conta pode ser usada por PF para solicitar atendimento a qualquer condomínio/empresa cadastrado. O login antigo `/cliente` por ID e senha segue funcionando; ele possui atalho para o novo cadastro por CPF.
- **Busca por nome ou CNPJ:** a pesquisa autenticada em `/pj/organizacoes` localiza organizações; CNPJ só é aceito como busca exata e **nunca aparece nos resultados**.
- **Solicitar sem vínculo:** o usuário pode abrir chamado sem ser síndico e sem aprovação prévia. A AUTOSEG analisa e confirma com o síndico por WhatsApp antes de liberar execução da OS.
- **Contato por WhatsApp:** o painel dos chamados exibe um botão com a mensagem pronta para o síndico (número com DDD confirmado no cadastro). Se não há contato validado, usa `https://wa.me/<numero-configurado>`. A mensagem inclui o número do chamado e, quando houver link público 8766 verificado, o link do painel do síndico. O `wa.me` **não envia automaticamente**: um operador deve abrir a conversa e tocar em Enviar. Para envio automático real será necessária integração oficial com uma API do WhatsApp Business.
- **Painel do síndico:** acompanha chamados de outras pessoas vinculados ao condomínio. Não existe exigência de aprovação online para que alguém faça a solicitação.
- **Fotos no PDF:** anexos de imagem passam a ser **incluídos por padrão**, sem aprovação de administrador. O prestador pode ocultar individualmente uma foto por privacidade. PDFs emitidos anteriormente continuam imutáveis; **publique nova versão da OS** para inserir as fotos no relatório já fechado.
- **Portal do prestador:** menu espelha os módulos operacionais do desktop: Clientes, Ordens de Serviço, Financeiro, Notas Fiscais, E-mails, Histórico e Relatórios. Sem menu de cadastro de prestadores e sem link para acionamento PJ na navegação do prestador. Chamados estão acessíveis pela lista de OS; condomínios, por Clientes. As funções operacionais deixaram de ser ocultadas apenas porque a conta não tem o marcador 'admin'.
- **Cloudflare:** dentro da tela principal do app existem os botões **INICIAR / RECONECTAR TÚNEIS** e **CONFIGURAR INÍCIO AUTOMÁTICO**. O início automático depende de consentimento explícito do administrador, pois os túneis gratuitos criam endereços públicos sem proteção adicional. Após iniciar, os dois endereços efetivamente emitidos são detectados dos logs, confirmados por HTTPS e exibidos no desktop e nos portais. Os túneis gerenciados são encerrados quando o aplicativo fecha.
- **Banco e histórico:** migração aditiva do contato verificado de síndico, inclusive importação do campo legado `clientes.sindico_telefone` quando disponível. Mantém vínculos, OS, PDFs e rascunhos.

## Como acessar

- App desktop: `bash ~/GestaoServicos/INICIAR_AUTOSEG.command`
- Portal do prestador: `http://127.0.0.1:8766/`
- Portal do cliente atual: `http://127.0.0.1:8766/cliente`
- Conta PF/PJ por CPF e senha: `http://127.0.0.1:8766/pj`
- Portal original: `http://127.0.0.1:8765/` (**módulo legado preservado, não substituído**)

## Limites de segurança e integração

Este pacote **não altera** os arquivos originais `banco.py` e `servidor_web.py`; a lógica interna do portal 8765 não foi auditada. Não publique dados reais de clientes nem utilize os Quick Tunnels para operação pública antes de concluir segurança e verificação de identidade. Login por CPF e senha não comprova propriedade do CPF ou do telefone; permissão de síndico requer validação pela AUTOSEG. Túneis gratuitos têm endereço aleatório que muda a cada reinício.

O código foi testado em servidor HTTP local com banco fictício; não houve instalação no seu Mac real. A interface desktop foi verificada por compilação, mas deve ser conferida visualmente no seu equipamento.
