# Paridade entre superfícies e papéis

**Atualizado:** 2026-11-11

## Regra

Permissão pertence ao **papel**, não à superfície. GTK, Portal do Prestador e
Portal do Cliente não devem conceder poderes diferentes para o mesmo papel.

**Paridade não é duplicação:** a mesma tela deve compartilhar contrato de
campos, ações, permissões, validações e textos, mas renderizar com widgets
nativos. O contrato funcional está em
`docs/planning/WEB_GTK_SHARED_CONTRACT.md`.

Papéis atuais:

| Papel | Onde entra hoje | Pode |
|---|---|---|
| **Admin** | GTK e Portal do Prestador | administrar a organização, prestadores, estoque, caixa, configuração e OS |
| **Funcionário/prestador** | GTK e Portal do Prestador | trabalhar nas OS próprias ou em que participa; sem administração |
| **Cliente** | Portal do Cliente e `/login` do site (flag) | próprias solicitações/OS, documentos e dados |

Admin e funcionário usam a mesma tabela `prestadores`; a diferença é o vínculo
em `v9_admin_prestadores`. Cliente usa conta própria em `v9_usuarios`.

## O que cada superfície tem hoje

**GTK**

- login de prestador (admin ou funcionário);
- clientes, OS, histórico, financeiro, PJ;
- prestadores, catálogo, composição, estoque, caixa da empresa;
- notas fiscais e e-mails (lista e preparação);
- conexão/servidor e controles dos portais locais.

**Site único (Officina Web, flag ligada)**

- login `/login` para prestador e cliente;
- mesma shell e navegação filtrada por contexto/permissão;
- cliente vê as próprias OS, documentos/PDF e pedido de serviço;
- o portal antigo do cliente na 8765 continua disponível.

**Portal do Prestador**

- login de prestador;
- clientes, OS, catálogo, financeiro, PJ, notas fiscais, e-mails e histórico;
- prestadores, estoque, caixa da empresa e composição de valores (admin);
- sem conexão/servidor, que é configuração do cliente desktop.

**Portal do Cliente**

- login por CPF;
- solicitações, acompanhamento e documentos do próprio cliente;
- não é um portal de prestador.

## Resposta curta

Com as telas de admin adicionadas ao site e as listas de notas/e-mails
adicionadas ao GTK, o conjunto de funções do prestador está praticamente
espelhado. A exceção é **Conexões**, que é configuração do cliente desktop, não
uma função de negócio do servidor.

O GTK continua sem login de cliente; o site já aceita cliente com a flag e o
Portal do Cliente antigo segue separado na 8765.

## Lacunas atuais

- O login do GTK aceita somente prestador; login de cliente no GTK ainda não
  (planejado na peça 6.5, remote-only).
- A API desktop identifica o prestador, mas ainda não aplica todas as regras
  admin × funcionário em cada ação. Isso é a próxima fatia de permissões.
- Esconder um botão na UI não é autorização; a regra precisa viver no serviço.
- As telas de admin existem nos dois lados; a autorização ainda precisa ser
  aplicada no serviço para admin × funcionário.
- A auditoria de 2026-11-10 encontrou lacunas mais graves do que a paridade de
  telas: leitura de qualquer OS/PII por qualquer prestador, API desktop sem
  autorização, admin global sem tenant e participação permanente. O diagnóstico
  completo e a ordem de correção estão em
  `docs/planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md` §2.

## Próximo passo

Ligar `policy.yaml` ao `AppService` e aplicar AUT-001 a AUT-021 no servidor,
fechando o gate P0 de autorização por objeto.

**Login de cliente no GTK:** planejado como peça **6.5**, remote-only, depois
desse gate. Faltam login desktop de cliente, sessão genérica, endpoints
client-safe, navegação reduzida e testes negativos. Ver
[`planning/GTK_CLIENT_MODE.md`](planning/GTK_CLIENT_MODE.md) e
[`ROADMAP.md`](ROADMAP.md).
