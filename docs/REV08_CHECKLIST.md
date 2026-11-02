# AUTOSEG REV08 — Controle dos 78 requisitos

Todos os itens estão PENDENTES DE HOMOLOGAÇÃO. Existência de código na REV07 não prova conclusão.

## A — OS e prestadores

- [ ] 1. Separar as ações **Atribuir OS** e **Iniciar OS**.
- [ ] 2. Permitir atribuição, remoção e reatribuição de técnicos pelo administrador desktop.
- [ ] 3. Permitir que os próprios técnicos assumam OS abertas ou pendentes sem responsável.
- [ ] 4. Mostrar todas as OS no desktop, independentemente de atribuição.
- [ ] 5. Diferenciar visualmente os seguintes estados:
- [ ] 6. Impedir que dois técnicos assumam simultaneamente a mesma OS.
- [ ] 7. Criar indicador manual **Em rota** para OS abertas ou pendentes atribuídas.
- [ ] 8. Permitir que o técnico responsável ou administrador ative esse indicador.
- [ ] 9. Mostrar o indicador Em rota no acompanhamento do Portal Cliente.
- [ ] 10. Preservar a participação histórica de todos os técnicos.
- [ ] 11. Permitir que uma OS pendente seja retomada por outro técnico sem apagar os atendimentos anteriores.
- [ ] 12. Manter os estados Aberta, Pendente, Concluída e Cancelada, incluindo justificativa de cancelamento.

## B — Rascunhos, YAML e histórico

- [ ] 13. Implementar botão **Salvar rascunho**.
- [ ] 14. Implementar botão **Recuperar rascunho**.
- [ ] 15. Persistir todos os campos preenchidos, incluindo materiais, valores, fotografias, legendas e observações.
- [ ] 16. Permitir recuperação do rascunho mesmo depois de fechar o navegador ou utilizar outro dispositivo.
- [ ] 17. Implementar salvamento automático, identificando sucesso e falha.
- [ ] 18. Permitir importar formulários YAML sem concluir automaticamente a OS.
- [ ] 19. Oferecer duas formas de importação: preencher campos vazios ou substituir campos correspondentes.
- [ ] 20. Criar opção **Desfazer importação YAML**.
- [ ] 21. Restaurar os dados anteriores quando uma importação incorreta for desfeita.
- [ ] 22. Ao marcar uma OS como Pendente, preservar o atendimento realizado como uma etapa histórica.
- [ ] 23. Permitir adicionar novos atendimentos, materiais, fotos e informações posteriormente.
- [ ] 24. Registrar data, horário e técnico responsável por cada etapa.

## C — Fotografias e PDFs

- [ ] 25. Permitir adicionar fotografias antes de finalizar a OS.
- [ ] 26. Exibir imagens em lista vertical de miniaturas.
- [ ] 27. Permitir editar individualmente as legendas.
- [ ] 28. Permitir remover ou substituir imagens antes da conclusão.
- [ ] 29. Inserir fotografias e legendas no relatório PDF.
- [ ] 30. Corrigir a geração, o armazenamento e a abertura dos PDFs.
- [ ] 31. Disponibilizar PDFs no Portal Cliente conforme as permissões.
- [ ] 32. Reunir os atendimentos anteriores no relatório final, identificando os técnicos participantes.

## D — Clientes e permissões

- [ ] 33. Clientes particulares poderão acessar os PDFs das próprias OS concluídas.
- [ ] 34. Em condomínios, somente o síndico autorizado poderá acessar os PDFs pelo Portal Cliente.
- [ ] 35. Moradores poderão abrir chamados e acompanhar o andamento, mas não acessar relatórios técnicos.
- [ ] 36. O e-mail de moradores não poderá ser utilizado automaticamente como destinatário de relatórios.
- [ ] 37. Para condomínios, considerar automaticamente os e-mails cadastrados do síndico e do condomínio.
- [ ] 38. Criar campo para adicionar um destinatário extra durante a finalização da OS.
- [ ] 39. Exigir pelo menos um e-mail válido antes de permitir a conclusão da OS.
- [ ] 40. Não aplicar essa restrição ao abrir, iniciar, deixar pendente ou cancelar uma OS.
- [ ] 41. Corrigir a integração Gmail para enviar mensagens reais pela API, sem substituir o envio por downloads de arquivos `.eml`.
- [ ] 42. Registrar sucesso ou falha de envio, com possibilidade de reenvio sem duplicação.
- [ ] 43. Aplicar as permissões de acesso aos PDFs diretamente no servidor.

## E — Financeiro

- [ ] 44. Criar visualização financeira consolidada no desktop.
- [ ] 45. Criar visualização financeira individual no Portal Prestador.
- [ ] 46. Permitir cadastrar dados bancários em campo de texto livre por técnico.
- [ ] 47. Incluir os dados bancários do responsável pelo recebimento na cobrança enviada à imobiliária.
- [ ] 48. Permitir cadastrar técnicos secundários participantes de uma OS.
- [ ] 49. Permitir a distribuição dos valores exclusivamente quando o técnico selecionar **Concluída**, antes da confirmação final.
- [ ] 50. Impedir distribuição financeira em OS pendentes ou canceladas.
- [ ] 51. Registrar o valor bruto cobrado.
- [ ] 52. Registrar individualmente o valor líquido de cada técnico.
- [ ] 53. Manter o técnico finalizador como responsável pelo recebimento integral do cliente ou imobiliária.
- [ ] 54. Registrar os repasses manuais destinados aos técnicos secundários.
- [ ] 55. Permitir acompanhar repasses pendentes, parciais ou concluídos.
- [ ] 56. Evitar duplicação de valores no financeiro consolidado.
- [ ] 57. Preservar a participação histórica de técnicos mesmo quando não receberem pagamento.
- [ ] 58. Permitir que técnicos acessem somente os PDFs das OS em que participaram, respeitando também as permissões administrativas.

## F — Materiais e estoque

- [ ] 59. Criar catálogo único de materiais com identificador permanente.
- [ ] 60. Permitir cadastro de materiais diretamente pelo desktop.
- [ ] 61. Incluir automaticamente no catálogo os materiais cadastrados em Produtos e Serviços.
- [ ] 62. Incluir automaticamente novos materiais registrados durante uma OS.
- [ ] 63. Implementar busca com sugestões de materiais semelhantes.
- [ ] 64. Exibir identificação, nome e unidade de medida nas sugestões.
- [ ] 65. Evitar duplicações causadas por diferenças de maiúsculas, espaços ou acentuação.
- [ ] 66. Verificar o catálogo antes de cadastrar materiais provenientes de YAML.
- [ ] 67. Permitir excluir ou mesclar cadastros duplicados no desktop sem comprometer registros históricos.
- [ ] 68. Separar o cadastro de materiais da movimentação de estoque.
- [ ] 69. Restringir o gerenciamento das quantidades em estoque à interface administrativa.
- [ ] 70. Não modificar automaticamente os saldos apenas pelo cadastro de materiais ou serviços.

## G — Cadastros e estabilidade

- [ ] 71. Criar seleção das 27 unidades federativas brasileiras, mostrando sigla e nome completo.
- [ ] 72. Preservar as UFs já cadastradas.
- [ ] 73. Aplicar a identidade visual AUTOSEG aos portais.
- [ ] 74. Melhorar a experiência em celulares e a legibilidade geral.
- [ ] 75. Investigar a falha intermitente de log ao iniciar outra OS.
- [ ] 76. Evitar operações duplicadas quando ocorrerem falhas de conexão.
- [ ] 77. Preservar o funcionamento dos túneis Cloudflare na inicialização, sem introduzir autenticação adicional por e-mail.
- [ ] 78. Preservar o banco real, os backups e a separação entre ambientes de desenvolvimento e produção.

## Liberação

- [ ] Backup e recuperação de SQLite e anexos confirmados.
- [ ] Código remoto conciliado com alterações locais do Mac.
- [ ] Testes de regressão, desktop, portais e permissões aprovados.
- [ ] PDF, Gmail, financeiro, YAML, estoque e fluxos revisados.
- [ ] Autorização de homologação antes de atualizar MAIN.
