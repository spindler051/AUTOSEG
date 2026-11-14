# Documentação do AUTOSEG

Este é o índice canônico. Se um documento não estiver aqui, trate como
histórico ou rascunho — em especial o conteúdo de `docs/archive/`.

## Comece por

- [Estado atual e próximos passos](HANDOFF.md)
- [Roadmap vigente](ROADMAP.md)
- [Visão de produto](PRODUCT_VISION.md)
- [Testes](../TESTES.md)
- [Regras para agentes e mantenedores](../AGENTS.md)
- [Changelog](../CHANGELOG.md)

## Produto, arquitetura e operação

- [Modos do app, papéis e servidores](APP_MODES_ROLES_AND_SERVERS.md)
- [Login, conta local e conexão](AUTH_AND_CONNECTION_UX.md)
- [Permissões e aprovações](PERMISSIONS_AND_APPROVALS.md)
- [Paridade entre GTK, site e papéis](SURFACE_PARITY.md)
- [Matriz P0 de permissões](PERMISSIONS_P0.md)
- [Arquitetura de segurança](security/SECURITY_ARCHITECTURE.md) — fronteiras, atores, sessões, autorização, exposição, anexos, segredos, logs e riscos conhecidos.
- [Numeração de OS](OS_NUMBERING_REDESIGN.md)
- [Separação GTK × servidor](GTK_SERVER_DECOUPLING.md)
- [GTK4/libadwaita no Linux e macOS](GTK4_LINUX_MACOS.md)
- [Integração com Workaholic](WORKAHOLIC_INTEGRACAO.md)
- [Layout do repositório](REPOSITORY_LAYOUT.md)
- [Migração de plataforma — playbook](PLATFORM_MIGRATION_PLAYBOOK.md)
- [Migração de plataforma — ledger](PLATFORM_MIGRATION_LEDGER.md)
- [Nomes e contrato da CLI](NAMING_AND_CLI.md)
- [Migração para inglês](ENGLISH_MIGRATION_PLAN.md)
- [Versionamento e homologação](VERSIONAMENTO.md)

## Planejamento futuro

Não são compromissos nem autorização de implementação. A ordem prática está no
[`ROADMAP.md`](ROADMAP.md).

- [Site único, identidade e permissões por objeto](planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md) — auditoria do estado atual + arquitetura-alvo; 5.1–5.5 e 6.1–6.4 integradas atrás de flags, com ativação de produção pendente.
- [Officina Web e Officina GTK](planning/OFFICINA_WEB_AND_GTK.md) — como o site e o GTK atuais originam os produtos genéricos; AUTOSEG como primeira prestadora.
- [Unificação real dos portais — P0](planning/PROMPT_PORTAL_UNIFICATION.md) — contrato executado na P0: uma única origem e nenhum fallback legado.
- [Cliente no GTK — peça 6.5](planning/GTK_CLIENT_MODE.md) — análise das lacunas, MVP remote-only e critérios de aceite; planejado, não implementado.
- [Prompt — outbox como único caminho de e-mail](planning/PROMPT_P0_AUTH_OUTBOX_ONLY.md) — próxima fatia do P0-AUTH, sem fallback legado.
- [Contrato compartilhado entre site e GTK](planning/WEB_GTK_SHARED_CONTRACT.md) — mesma tela/comando/permissão, renderização nativa em cada plataforma; documentação, não implementado.
- [Valor negociado na OS](planning/OS_NEGOTIATED_VALUE_UX.md) — checkbox, valor final e desconto explícito no relatório; proposta, não implementado.
- [PGP, multiassinatura e integridade criptográfica](planning/PGP_MULTISIGNATURE_ARCHITECTURE.md)
- [Anti-tampering financeiro com assinaturas PGP](planning/ANTI_TAMPERING_FINANCIAL_LEDGER.md)
- [OS assinada em duas partes e versionamento](planning/SIGNED_OS_TWO_PARTY_AND_VERSIONING.md)
- [Protocolo de trabalho: termos, fluxo e requisitos](planning/WORK_PROTOCOL_TERMINOLOGY_AND_WORKFLOW.md)
- [Guideline de interface multiplataforma](planning/MULTI_PLATFORM_GUI_GUIDELINE.md)
- [Condomínios, compartilhamento e tenancy](planning/CONDO_SHARING_AND_TENANCY.md)
- [Visão multicliente e local-first](planning/VISAO_MULTICLIENTE_LOCAL_FIRST.md)
- [Plano de modo local e sincronização](planning/PLANO_MODO_LOCAL_SYNC.md)
- [Modos local/sync/serverless — análise externa](planning/LOCAL_SYNC_MODES_ANALYSIS.md) — quatro presets, autoridade por entidade, version vectors, Syncthing e direção Rust; análise não implementada.

## Qualidade e processo

- [Política de comentários](CODE_COMMENT_POLICY.md)
- [Plano de limpeza da podridão](CODE_ROT_CLEANUP_PLAN.md)
- [Revisão sem desenvolvedor humano](REVIEW_WITHOUT_DEVELOPER.md)
- [Rotina de revisão com IAs externas](EXTERNAL_AI_REVIEW_ROUTINE.md)
- [Decisões centradas em pessoas](HUMAN_CENTERED_DECISIONS.md)
- [Guia de feedback de uso](USER_FEEDBACK_GUIDE.md)

## Funcionalidades

- [API financeira do prestador](features/API_FINANCEIRO.md)
- [Caixa da empresa](features/CAIXA_EMPRESA.md)
- [Canal de feedback do portal](features/FEEDBACK_PORTAL.md)
- [Materiais e composição da OS](features/MATERIAIS_COMPOSICAO_OS.md)
- [Telemetria aberta](features/OPEN_TELEMETRY.md)
- [Correção financeira da OS](features/OS_FINANCIAL_CORRECTION_UI.md)
- [Interface do Portal do Prestador](features/PROVIDER_PORTAL_UI.md)

## Operação

- [Onde ficam banco e dados](operations/DATA_STORAGE.md)
- [P0-AUTH — estado DEV e congelamento](operations/P0_AUTH_DEV_FREEZE.md)
- [Modelo de branches: main e dev](operations/BRANCH_MODEL.md)
- [Feedbacks da MAIN resolvidos na DEV](operations/MAIN_FEEDBACKS_DEV.md)
- [Separação banco de produção × teste](operations/BANCO_TESTE_PRODUCAO.md)
- [Túnel fixo Cloudflare](operations/TUNEL_FIXO.md)
- [Ações da auditoria de segurança](operations/SECURITY_AUDIT_2026-11-08.md)
- [Preparação da Gmail API](operations/GMAIL_API.md)
- [Padrões YAML](operations/PADROES_YAML.md)

## Feedback e backlog

- [Backlog DEV](feedback/PENDENCIAS_DEV.md)
- [Conhecimento para respostas de feedback](feedback/CONHECIMENTO.md)

## Histórico

- [Arquivo histórico](archive/README.md) — readmes, revisões e planos
  substituídos. Não é documentação vigente.
