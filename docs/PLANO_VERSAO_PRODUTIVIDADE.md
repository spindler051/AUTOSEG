# AUTOSEG — Modelo de implementação da Versão de Produtividade

**Data:** 2026-11-02  
**Origem:** feedbacks da REV06, [issue #5](https://github.com/spindler051/AUTOSEG/issues/5)  
**Estado:** proposta de implementação; funcionalidades ainda não homologadas.  
**Base:** desenvolver sobre `develop`; não substituir a produção antes da homologação.

## Objetivo

Consolidar OS, técnicos, relatórios, YAML, materiais, Gmail, permissões e financeiro em um fluxo de trabalho seguro, sem perder cadastros, anexos, banco de dados ou histórico existente.

## Regras de negócio

### OS e atribuição
- Estado operacional: `Aberta | Iniciada | Pendente | Concluída | Cancelada`.
- Atribuição: `responsavel_id` opcional, independente de iniciar atendimento.
- Situação do atendimento: `Não iniciado | Em rota | Iniciado`; começar o atendimento grava o status `Iniciada`. Apresentar no desktop `Aberta / Não atribuída`, `Aberta / <nome>`, `Iniciada / <nome>`, `Pendente / Não atribuída`, `Pendente / <nome>`.
- Admin desktop vê todas e atribui/desatribui/reatribui. Prestador assume OS aberta/pendente sem responsável; assumir deve ser atômico para evitar conflito. Apenas responsável ou admin pode marcar `Em rota`; cliente acompanha. Iniciar remove `Em rota`.
- Histórico de participações e alterações não é apagado ao reatribuir.

### Formulário, rascunho e YAML
- `Salvar rascunho`, `Recuperar rascunho`, autosave e indicação de versão/erro. Persistir textos, materiais, valores, fotos e legendas no servidor.
- Importar YAML apenas preenche campos; nunca encerra OS. Oferecer prévia e modos `Preencher vazios` / `Substituir correspondentes`. `Desfazer importação` restaura estado anterior com proteção contra perda de alterações posteriores.
- Ao marcar Pendente, registrar etapa de atendimento (autor, horário, materiais, fotos, observações) no histórico. Outro técnico pode adicionar nova etapa; não sobrescrever as anteriores.
- Fotos em lista vertical com miniatura, legenda, editar/remover antes de encerrar; PDF final agrega etapas e legendas.

### PDF e comunicação
- PF titular: PDF da própria OS concluída. Condomínio: somente síndico autorizado tem acesso a PDFs no Portal Cliente; morador acompanha status da própria OS, mas não acessa PDF.
- Prestador: PDF somente de OS com participação comprovada. Admin: acesso administrativo. Validar sempre no backend e nos endpoints diretos.
- Gmail real, não download de `.eml` como substituto. Guardar status, ID da mensagem ou erro e oferecer reenvio idempotente.
- OS condominial: enviar automaticamente aos e-mails cadastrados do **síndico e do condomínio** (sem duplicar endereços). Não usar automaticamente o e-mail do morador. Permitir **um destinatário adicional** no formulário de conclusão.
- Se não houver e-mail válido do síndico nem do condomínio, exigir ao menos um endereço adicional válido para permitir `Concluída`. Não bloquear `Aberta`, `Pendente` ou `Cancelada`. Separar envio de relatório da cobrança à imobiliária.

### Financeiro
- Apenas o técnico que seleciona `Concluída` define, **antes da confirmação**, valores para técnicos secundários. OS pendente/cancelada não gera rateio.
- O técnico finalizador cobra o valor **bruto** integral da imobiliária e faz repasses manuais. Valor líquido próprio = bruto − parcelas dos demais.
- Desktop: bruto total, líquido por técnico e repasses internos, sem dupla contagem. Portal Prestador: somente dados próprios, com autorização no servidor.
- Campo livre de dados bancários por prestador, incluído no e-mail de cobrança pelo responsável pelo recebimento.
- Participação sem parcela continua no histórico, sem criar crédito automático.

### Materiais e estoque
- Catálogo central com ID estável, criado exclusivamente em: desktop Materiais, portal Produtos e Serviços, formulário da OS.
- Busca/autocomplete por nome com ID e unidade; deduplicação por nome normalizado e revisão de semelhantes, inclusive YAML. Desktop pode mesclar/excluir duplicatas com auditoria.
- Catálogo não é estoque: cadastro não movimenta saldo; estoque e suas operações somente no desktop. Preservar preços históricos da OS.

### Outros
- UF: 27 siglas e nomes completos nos cadastros desktop e portais.
- Identidade visual existente da AUTOSEG, interfaces responsivas.
- Investigar falha de log intermitente, sem atribuir causa sem evidência.
- Túneis Cloudflare com inicialização automática, sem PIN extra por e-mail; verificar segurança antes de publicar.

## Modelo de dados proposto (sujeito à análise do esquema atual)

**Não executar DDL antes de mapear o SQLite atual.** Preferir migrações aditivas, com cópia de segurança e rollback testado.

| Entidade lógica | Campos essenciais |
| --- | --- |
| `os` | id, cliente_id, estado, responsavel_id, situacao_atendimento, versao, timestamps |
| `os_eventos` | id, os_id, tecnico_id, tipo_evento, dados_json, criado_em |
| `os_atendimentos` | id, os_id, tecnico_id, situacao, texto, criado_em, encerrado_em |
| `os_rascunhos` | id, os_id, tecnico_id, versao, payload_json, atualizado_em |
| `os_anexos` | id, os_id, atendimento_id, caminho_servidor, legenda, ordem, hash |
| `materiais_catalogo` | id, nome, nome_normalizado, unidade, sku, ativo |
| `os_materiais` | id, os_id, atendimento_id, material_id, quantidade, preco_snapshot |
| `os_participantes` | os_id, tecnico_id, papel, inicio_em, fim_em |
| `os_rateios` | os_id, tecnico_id, valor, definido_por, criado_em |
| `repasses` | id, os_id, de_tecnico_id, para_tecnico_id, valor, pago, pago_em |
| `envios_email` | id, os_id, tipo, destinatarios, status, message_id, erro, tentativa |
| `os_importacoes_yaml` | id, os_id, autor_id, snapshot_anterior, diferencas, criado_em |

Reutilizar tabelas existentes sempre que possível; os nomes acima são **conceituais**, não afirmação sobre o esquema atual.

## Sequência de implementação

### Fase 0 — Auditoria e proteção da produção
- Inspecionar `develop`, estrutura de pastas, SQLite, fluxos de desktop e portais, Gmail e PDF.
- Inventariar permissões, endpoints, migrations e dados existentes.
- Backup verificável do SQLite e anexos, restore testado; testes em banco fictício.
- Criar cenários automatizados de regressão antes de alterar regras.

### Fase 1 — Corrigir os bloqueios atuais
- Envio Gmail real e status/reenvio; PDF gerado e baixável por usuário autorizado.
- Fotos e legendas antes da conclusão.
- Validar destinatários e e-mail obrigatório no fluxo Concluída.
- Investigar logs e erros de múltiplas OS; corrigir falhas reproduzidas.

### Fase 2 — OS produtiva e rascunhos
- Separar estado, atribuição, deslocamento e início; travas de concorrência.
- Histórico de eventos e atendimentos; rascunho persistente com fotos/materiais.
- YAML com prévia, preenchimento seletivo e desfazer seguro.
- Portal Cliente mostra `Em rota` e `Iniciado`.

### Fase 3 — Catálogo e estoque
- ID único, autocomplete, deduplicação, cadastro nos três pontos.
- Mesclagem segura no desktop; estoque somente no desktop.

### Fase 4 — Financeiro por prestador
- Rateio exclusivo na conclusão, bruto/líquido, repasses manuais.
- Dados bancários, visões isoladas no portal e consolidado desktop.

### Fase 5 — UX, testes e homologação
- UF, identidade visual, responsividade e testes de rede fraca.
- Testes de permissão entre PF, morador, síndico, prestadores e admin.
- Testar migração com cópia de banco real; rollback; checklist de produção.
- Só promover `develop` para `main` após aprovação dos cenários críticos.

## Critérios de aceite mínimos

1. Um técnico assume OS aberta; segundo não consegue assumi-la simultaneamente.
2. Admin reatribui OS pendente sem apagar atendimento anterior.
3. Rascunho com duas fotos/legendas e materiais é recuperado após recarregar e em outro dispositivo.
4. YAML incorreto pode ser desfeito sem perder dados prévios.
5. Morador acompanha OS mas recebe **403** ao solicitar PDF; síndico autorizado consegue baixá-lo.
6. Conclusão condominial sem e-mail de síndico/condomínio exige adicional válido.
7. Gmail envia realmente e registra status; reenvio não duplica cobranças nem conclusões.
8. OS de R$ 1.000: técnico finalizador recebe R$ 1.000 da imobiliária, possui R$ 700 líquidos, repassa R$ 300 a outro; consolidado permanece R$ 1.000.
9. Material novo em OS aparece no catálogo; estoque não é modificado só pelo cadastro.
10. Produção permanece intacta até testes, backup e homologação.

## Entregas recomendadas por fase

Cada fase deve gerar: migração reversível quando necessária; testes; changelog; instruções de execução DEV; evidência de teste no Portal Prestador, Portal Cliente e desktop; e lista explícita de pendências.

**Nota:** este arquivo é o plano de trabalho. Não afirma que as funcionalidades já foram implementadas.
