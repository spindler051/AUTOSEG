# AUTOSEG — REV04 / Instalação DEV segura / 31-10-2026

**NUNCA copie a pasta completa por cima do projeto. NUNCA renomeie ou exclua `GestaoServicos_DEV`.** Use somente o arquivo `AUTOSEG_DEV_PATCH_04.zip`, que é incremental, ou o instalador existente dentro dele.

## Visão geral

- Novo desktop: Serviços e Valores (edição nativa) e Materiais e Estoque.
- Catálogo web: linhas estruturadas de materiais e importação YAML do modelo de serviços.
- Relatório YAML: reutilização sem número de OS; campos existentes preservados, exceto substituição explicitamente marcada.
- OS: materiais informados pelo desktop e pelo prestador passam a movimentar o mesmo estoque SQLite, inclusive saldos negativos. Edição lança somente a diferença; cancelamento estorna; histórico fica preservado.
- O cadastro do produto no catálogo, isoladamente, não baixa estoque. Baixa ocorre ao confirmar materiais da OS.
- A migração de materiais em OS antigas estabelece **linha de base sem nova baixa**, evitando distorção retroativa.
- Estoque **não tem página ou API de administração no Portal do Prestador**; selecionar material para uso numa OS é permitido. Custos, saldos e movimentações só aparecem no desktop.

## Procedimento recomendado no Mac

1. Feche o aplicativo DEV, seus portais e os processos antigos do AUTOSEG.
2. Salve `AUTOSEG_DEV_PATCH_04.zip` em sua pasta de usuário (`/Users/<usuario>`), sem descompactar manualmente pelo Finder.
3. Abra o Terminal e execute **um comando por vez**:

```zsh
cd "$HOME/GestaoServicos_DEV" || exit 1
git branch --show-current
git status --short
```

A branch deve ser `develop`. É normal haver alterações não commitadas da REV03; o instalador criará backup antes de copiar os arquivos. Se mostrar `fatal: not a git repository`, **não prossiga**.

```zsh
mkdir -p "$HOME/AUTOSEG_REV04_EXTRAIDO"
unzip -q -o "$HOME/AUTOSEG_DEV_PATCH_04.zip" -d "$HOME/AUTOSEG_REV04_EXTRAIDO"
```

Confirme que a extração criou `AUTOSEG_REV04_PATCH/INSTALAR_REV04_DEV.command`:

```zsh
ls -l "$HOME/AUTOSEG_REV04_EXTRAIDO/AUTOSEG_REV04_PATCH/INSTALAR_REV04_DEV.command"
```

Instale com **o instalador verificado**, sem copiar a pasta completa:

```zsh
/bin/zsh "$HOME/AUTOSEG_REV04_EXTRAIDO/AUTOSEG_REV04_PATCH/INSTALAR_REV04_DEV.command"
```

O instalador verifica branch `develop`, `.git`, `.venv`, realiza backup da pasta atual e usa cópia SQLite consistente do banco de testes **se existir**. Após a instalação, executa os testes da REV04 no seu `.venv`. Se os testes falharem, não abra o programa e envie a saída do Terminal (não envie senhas).

4. Execute o app DEV:

```zsh
cd "$HOME/GestaoServicos_DEV" || exit 1
./INICIAR_AUTOSEG_DEV.command
```

5. Valide desktop **Serviços e Valores** e **Materiais e Estoque**; depois, no prestador, faça uma OS fictícia com um produto ainda não cadastrado, salve e confira o saldo negativo no desktop. Edite a quantidade e verifique que apenas a diferença foi lançada; faça um ajuste manual positivo. Teste importação YAML de relatório, serviço e cliente.
6. **Não execute `git add`, `git commit` ou `git push` sem revisar o resultado com calma.** Não faça merge de `develop` para `main` antes da homologação e do backup da produção.

## Cuidados de banco

- DEV: `~/GestaoServicos_DEV/dados_teste/autoseg_teste.db`
- Produção: `~/GestaoServicos/dados.db`
- O pacote não contém bancos nem clientes reais, `.git`, `.venv`, credenciais, certificados, tokens ou `.env`.
- O primeiro início instala tabelas de estoque **apenas no banco apontado por GESTAO_BANCO**. No launcher DEV o caminho é fixado em `dados_teste/autoseg_teste.db`.
- O ZIP completo `AUTOSEG_DEV_COMPLETO_REV04.zip` é apenas referência/código-fonte e **não deve substituir** sua pasta DEV.

## Limites

- A interface Tk foi aberta em ambiente gráfico virtual Linux, não em um Mac Intel real. Ajustes finos de layout no Safari/Tk precisam ser verificados no seu computador.
- O mecanismo de estoque permite saldo negativo; não é substituto de inventário físico ou de contabilidade financeira.
- Não houve migração automática nem limpeza de cadastros legados, OAuth Gmail, envio real de e-mail ou execução contra dados de produção.
