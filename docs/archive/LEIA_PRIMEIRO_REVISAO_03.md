# AUTOSEG DEV — Revisão 03 | 31/10/2026

**Somente DEV. Nunca substituir a pasta do projeto inteiro, nem copiar para produção.**

## Correções incluídas

- Cadastro de condomínio/empresa e abertura de OS **no mesmo formulário do Portal do Cliente** (telefone com DDD obrigatório), numa operação SQLite transacional.
- Registro imediato em `clientes` + `v9_organizacoes`, com `cliente_id` vinculado, sem fila de validação obrigatória para o cadastro. A OS vai a `ordens_servico` como **Pendente**.
- Pessoa que solicita NÃO recebe acesso de síndico/gestor; nomeação administrativa continua exclusiva do prestador/desktop. Contas e vínculos antigos não são mesclados automaticamente.
- A navegação do prestador prioriza **Clientes** e **Ordens de Serviço**. “Análise de chamados” redireciona para OS; “Condomínios e vínculos” redireciona para Clientes. A tela administrativa de **Nomear síndico/gestor** fica acessível dentro de Clientes, sem remover tabelas históricas.
- Máscaras visuais CPF/CNPJ; CSS com quebra de texto e botões mais responsivos; na tela desktop de prestadores, ações acima da tabela para não sumirem no rodapé.
- Catálogo **Serviços e valores**: mão de obra, materiais, descrição, relatório sugerido, arquivo PDF de orçamento estimativo gerado pelo cliente autenticado, calculado exclusivamente no servidor; não é proposta contratual nem NF.
- Modelos YAML baixáveis dentro do Portal do Prestador e documentação `PADROES_YAML.md`.
- Integração Gmail preparada em `prestadores_config` (opção já existente) e documentada em `GMAIL_API_PREPARACAO.md`. **Nenhum envio real nesta revisão.**

## Procedimento recomendado no Mac

1. Feche o AUTOSEG DEV e os portais. Confirme `git branch --show-current` = `develop` e revise `git status --short`.
2. Faça backup da pasta `GestaoServicos_DEV` e do arquivo SQLite de testes (caso queira manter os testes anteriores).
3. **Prefira `AUTOSEG_DEV_PATCH_03.zip`**: descompacte em uma pasta separada (por exemplo `~/AUTOSEG_REV03_PATCH`), confira `AUTOSEG_REV03_PATCH/LEIA_PRIMEIRO_REVISAO_03.md`, e copie somente o conteúdo de `AUTOSEG_REV03_PATCH` para `~/GestaoServicos_DEV`. Não substitua a pasta DEV no Finder.
4. O ZIP completo também existe para auditoria/restauração de código, mas **não contém** `.git`, `.venv`, `dados_teste`, `.env`, banco real ou credenciais. **Não substitua a pasta DEV atual pelo ZIP completo**.
5. No Terminal:

```zsh
cd "$HOME/GestaoServicos_DEV" || exit 1
"$PWD/.venv/bin/python" -m pip install -r requirements.txt
./VERIFICAR_AUTOSEG_DEV.command
```

6. Se os testes passarem, abra `./INICIAR_AUTOSEG_DEV.command` e teste com clientes e prestadores **fictícios** no banco `dados_teste/autoseg_teste.db`.
7. Só depois da validação faça commit na branch `develop`. **Não faça merge para `main`** e não execute procedimentos de mesclagem dos cadastros reais sem auditoria e backup.

## Limitações e riscos conhecidos

- Cadastros antigos inconsistentes podem permanecer duplicados. Não há migração destrutiva nem fusão automática entre históricos PF/PJ nesta versão.
- O antigo fluxo de análise ainda possui funções internas para preservar dados e compatibilidade, embora removido da navegação principal. Deve ser descontinuado após auditoria.
- Não há envio Gmail OAuth, consulta automática CNPJ, migração de banco real ou garantia de ausência de regressões.
- O catálogo usa preços estimados configurados pelo prestador; não consulta impostos, deslocamento, estoque, disponibilidade ou desconto.
- A integração visual desktop deverá ser validada **no macOS com GTK**: os testes automatizados não substituem homologação gráfica.
