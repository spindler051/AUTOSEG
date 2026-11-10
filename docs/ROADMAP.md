# Roadmap vigente

**Atualizado:** 2026-11-10
**Foco:** produção do AUTOSEG. Arquitetura genérica e outros toolkits ficam
para depois.

> **Direção registrada em 2026-11-10:** o AUTOSEG terá **um site, um link e um
> login**, com conta/vínculo/contexto e política por objeto. A implementação
> começa por identidade e permissões, não pela interface. O AUTOSEG é a primeira
> prestadora de serviço do ecossistema Officina; Officina Web/GTK são extrações
> posteriores. Ver
> [`planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md`](planning/UNIFIED_SITE_AND_OBJECT_PERMISSIONS.md)
> e [`planning/OFFICINA_WEB_AND_GTK.md`](planning/OFFICINA_WEB_AND_GTK.md).

## Agora

1. **Fechar a numeração de OS na MAIN**
   - ensaiar a migração em cópia da MAIN;
   - backup, janela de manutenção e smoke;
   - manter aliases para links, PDFs e e-mails antigos;
   - não reescrever documentos já publicados.
2. **Login e troca real de modo no GTK**
   - conta local × conta do servidor com vínculo explícito;
   - token revogável para “lembrar este dispositivo”;
   - flag em DEV até revisão humana externa.
3. **Permissões em runtime**
   - ligar `policy.yaml` ao `AppService`;
   - aplicar AUT-001 a AUT-021 no servidor, não só na interface;
   - employee vê apenas OS próprias ou em que participa; customer vê apenas as
     próprias.
4. **API remota mínima**
   - clientes e OS;
   - `HttpService` usando o mesmo contrato do modo local;
   - sem fallback silencioso para o banco local.

## Próximo

- sincronização híbrida com servidor como autoridade de numeração, financeiro e
  estoque;
- backup/restauração verificados;
- revisão externa dos módulos de dinheiro, autenticação, permissões, schema e
  migração;
- primeiros ciclos de revisão com IA externa registrados em `docs/reviews/`.

## Depois

- protocolo de trabalho genérico: vocabulário, fluxo configurável e requisitos
  de conclusão por flavor; planejamento em
  [`planning/WORK_PROTOCOL_TERMINOLOGY_AND_WORKFLOW.md`](planning/WORK_PROTOCOL_TERMINOLOGY_AND_WORKFLOW.md);
- Workaholic como motor real, uma fatia por vez;
- app GTK genérico e flavor AUTOSEG;
- CLI;
- clientes móveis/PWA;
- Qt, WinUI, Jetpack Compose e SwiftUI **somente** se o núcleo e o contrato de
  aplicação estiverem estáveis;
- sync LAN e P2P/WAN apenas depois de servidor central estável.

## Fora de escopo por enquanto

- reescrever tudo de uma vez;
- 20 GUIs em 20 toolkits;
- sincronizar `dados.db` como arquivo;
- trocar SQLite por Postgres sem dor real;
- publicar na MAIN sem revisão humana externa para mudanças N3/N4.

## Critério para avançar

Uma fase só termina com teste automatizado, smoke manual descrito, backup e
rollback quando houver dados, e documentação atualizada. O estado detalhado
está em [`HANDOFF.md`](HANDOFF.md).
