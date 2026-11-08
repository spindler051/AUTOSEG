# Paridade entre superfícies e papéis

**Atualizado:** 2026-11-07

## Regra

Permissão pertence ao **papel**, não à superfície. GTK, Portal do Prestador e
Portal do Cliente não devem conceder poderes diferentes para o mesmo papel.

Papéis atuais:

| Papel | Onde entra hoje | Pode |
|---|---|---|
| **Admin** | GTK e Portal do Prestador | administrar a organização, prestadores, estoque, caixa, configuração e OS |
| **Funcionário/prestador** | GTK e Portal do Prestador | trabalhar nas OS próprias ou em que participa; sem administração |
| **Cliente** | Portal do Cliente | próprias solicitações/OS, documentos e dados |

Admin e funcionário usam a mesma tabela `prestadores`; a diferença é o vínculo
em `v9_admin_prestadores`. Cliente usa conta própria em `v9_usuarios`.

## O que cada superfície tem hoje

**GTK**

- login de prestador (admin ou funcionário);
- clientes, OS, histórico, financeiro, PJ;
- prestadores, catálogo, composição, estoque, caixa da empresa;
- conexão/servidor e controles dos portais locais.

**Portal do Prestador**

- login de prestador;
- clientes, OS, catálogo, financeiro, PJ, notas fiscais, e-mails e histórico;
- sem telas de prestadores, estoque, composição, caixa da empresa ou conexão.

**Portal do Cliente**

- login por CPF;
- solicitações, acompanhamento e documentos do próprio cliente;
- não é um portal de prestador.

## Resposta curta

O site **não** faz tudo que o GTK faz. Faltam no site, hoje: gestão de
prestadores, estoque, composição de valores, caixa da empresa e conexão.

O GTK também **não** faz tudo que o site faz: não tem login de cliente nem todas
as listas de notas/e-mails do Portal do Prestador.

## Lacunas atuais

- O login do GTK aceita somente prestador; login de cliente no GTK ainda não.
- A API desktop identifica o prestador, mas ainda não aplica todas as regras
  admin × funcionário em cada ação. Isso é a próxima fatia de permissões.
- Esconder um botão na UI não é autorização; a regra precisa viver no serviço.
- As telas exclusivas do GTK são lacuna de paridade web, não privilégio extra
  por usar GTK.

## Próximo passo

Ligar `policy.yaml` ao `AppService` e aplicar AUT-001 a AUT-021 no servidor.

**Login de cliente no GTK:** adiado. É nicho para o momento e não entra no
escopo atual. A decisão é manter `Sessao`, `AppService` e `HttpService` limpos
para que esse login seja uma extensão pequena quando houver demanda real, sem
reescrever a autenticação.
