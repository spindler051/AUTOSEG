# Gestão de Serviços AUTOSEG — fluxo do cliente v9.4

## Objetivo
Concentrar a autenticação pública em **/cliente**, com uma única conta pessoal
por CPF e senha. A mesma conta permite atendimento particular (PF) e acionamento
para organização (condomínio/empresa). O Workaholic permanece isolado.

## Regras de negócio
1. Cadastro da conta: **CPF + senha** (confirmação de senha apenas no formulário).
   A senha é armazenada com PBKDF2 como já feito na base v9.3. CPF não comprova
   sozinho a titularidade — não vincular automaticamente a OS antigas.
2. Login principal: `/cliente`; os links `/pj` antigos redirecionam à área
   principal. Acesso antigo `/cliente/legado` por ID/senha é preservado.
3. **OS PF**: antes de abrir, é obrigatório completar nome, telefone, e-mail,
   rua/endereço, número, cidade e UF. Bairro e CEP são opcionais.
   Depois disso, a OS é criada na tabela `ordens_servico`, associada a um
   cliente PF próprio. A pessoa vê suas OS na conta pessoal.
4. **PJ responsável**: após CPF/senha, o usuário cadastra condomínio/empresa
   com nome, endereço e CNPJ. O vínculo `Síndico` (condomínio) ou
   `Administrador` (empresa/proprietário) permanece **Pendente** até validação.
   A busca por organização existente permite também solicitar esse vínculo.
5. **Solicitante PJ**: morador, funcionário ou porteiro abre chamado sem
   precisar ser síndico e sem completar o endereço residencial de seu perfil.
   Informa apartamento ou cargo/função, descrição e urgência.
6. Busca pública interna por nome ou CNPJ exato: os resultados mostram nome,
   tipo e localidade, nunca CNPJ/CPF. Lista paginada em lotes de 100.
7. Não encontrado: criar **pré-cadastro** com nome, tipo, endereço e
   apartamento/cargo; CNPJ é opcional. O usuário segue para o chamado.
8. Chamados PJ permanecem `Aguardando AUTOSEG`; a equipe contata o responsável
   e registra a confirmação pelo fluxo de análise já existente.

## Módulos alterados
- `portal_cliente_v94.py`: fluxo HTTP e formulários do cliente;
- `cliente_fluxo_v94.py`: regras da conta PF, perfil e solicitações PF;
- `cadastros_v9.py`: migrações aditivas e persistência de endereço/unidade;
- `portal_prestador.py`: roteamento das páginas do cliente;
- `portal_v9.py`: escopo do cookie de sessão compartilhado `/`.

## Esquema (migração aditiva)
- `v9_usuarios`: `endereco`, `numero`, `bairro`, `cidade`, `uf`, `cep`,
  `perfil_completo`, `cliente_pf_id`.
- `v9_organizacoes`: `endereco`.
- `v9_vinculos`: `unidade`.

Não são removidas tabelas, registros ou colunas anteriores. A migração ocorre
em `cadastros_v9.instalar()` na inicialização do portal.

## Limites e revisão humana
- Senhas/CPF são uma credencial inicial, não verificação documental de identidade.
- Novo cadastro PF **não herda automaticamente** as OS do acesso por ID.
- Vínculos de responsável só se tornam aprovados após validação da AUTOSEG.
- WhatsApp via `wa.me` abre a mensagem, mas não envia automaticamente.
- Antes de produção externa, revisar sessão, proteção CSRF, proteção contra
  abuso e obrigações LGPD; teste local não equivale a auditoria de segurança.
- A camada técnica e fiscal não foi alterada.

## Testes
`python test_fluxo_cliente_v94.py` usa banco temporário. Validar também
`python test_fluxo_v7.py` (regressão do prestador).
Alguns testes antigos v4/v5/v6/v9/v9.1/v9.2 codificam fluxos antigos ou já
falhavam no snapshot recebido; precisam ser revisados separadamente.
