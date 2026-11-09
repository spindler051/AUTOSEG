# AUTOSEG DEV — Revisão 01 | 30/10/2026

**Entregue somente para desenvolvimento e testes. Não copiar para `GestaoServicos` (produção).**

Este pacote contém **apenas os arquivos criados ou alterados**. Não contém banco `.db`, pasta `.git`, ambiente `.venv`, clientes reais, anexos ou tokens. Não reinstala nem reescreve o ambiente Git. O Portal do Cliente mantém o visual anterior.

## Alterações incluídas

1. Cadastros pessoa jurídica do desktop e prestador sincronizam com `v9_organizacoes` imediatamente; validações bloqueiam vínculos de CNPJ divergente.
2. Solicitações no Portal do Cliente geram OS pendentes, com recuperação de solicitações antigas órfãs na inicialização do prestador. Testado via HTTP com SQLite temporário.
3. Busca no seletor de cliente ao criar OS e filtro nas tabelas carregadas do Portal do Prestador.
4. Formulário de OS começa com **zero materiais** e permite remover todos, inclusive os anteriormente salvos.
5. Remoção das fotos selecionadas **antes do envio**, sem perder outros dados do formulário; também no desktop.
6. Exclusão protegida de cadastro sem OS, vínculos, chamados ou conta associada.
7. YAML de cadastro e relatório no prestador, com validação e pré-visualização antes de salvar.
8. Configuração de dados bancários/PIX, remetente e referência da variável de credencial por prestador no desktop; rascunho `.eml` sem envio automático.
9. Diagnóstico, 28 itens de planejamento e testes de regressão.

## Instalação manual — somente no Mac DEV

**Antes de começar:** feche o AUTOSEG DEV, o Portal do Prestador e o Portal do Cliente, e confira que não há alterações de código suas ainda não salvas no Git. Caso haja, faça commit ou backup primeiro. Mantenha `main` e o banco da produção intocados.

Os comandos abaixo pressupõem que você salvou `AUTOSEG_DEV_PATCH_01.zip` em `Downloads`.

```zsh
cd "$HOME/GestaoServicos_DEV" || exit 1
git switch develop
git status --short
```

Se aparecerem arquivos modificados que você não reconhece, **não aplique o pacote antes de conferir**. Se a branch `develop` estiver limpa:

```zsh
mkdir -p "$HOME/Downloads/AUTOSEG_PATCH_01"
unzip -q -o "$HOME/Downloads/AUTOSEG_DEV_PATCH_01.zip" -d "$HOME/Downloads/AUTOSEG_PATCH_01"
cp -R "$HOME/Downloads/AUTOSEG_PATCH_01/GestaoServicos_DEV/." "$HOME/GestaoServicos_DEV/"
cd "$HOME/GestaoServicos_DEV" || exit 1
"$PWD/.venv/bin/python" -m pip install 'PyYAML>=6,<7'
./VERIFICAR_AUTOSEG_DEV.command
```

Se passar, abra `./INICIAR_AUTOSEG_DEV.command`, faça os testes de interface e confira o que mudou:

```zsh
cd "$HOME/GestaoServicos_DEV"
git status --short
```

Só faça um commit na branch `develop` depois da validação. **Não execute `git merge` para `main` nem copie nada para a produção ainda.**

## Testes realizados na cópia isolada

- Oito testes de unidade no banco temporário (`test_autoseg_melhorias.py`).
- Um teste HTTP ponta a ponta no localhost com banco e servidores temporários (`test_autoseg_http_novo.py`).
- Quatro testes compatíveis anteriores (`test_v953_fluxo.py`).
- Compilação Python e verificação de sintaxe JavaScript.

**Limitações:** os testes não substituem navegação real no Mac, revisão de registros existentes nem garantia de ausência de regressões. Não houve fusão automática de cadastros legados, recuperação de vínculos antigos, migração da produção, integração de envio de e-mail/API, consulta CNPJ pública ou backup/restauração automatizados. Consulte `KNOWN_ISSUES.md` e `ROADMAP.md`.

## Reverter antes do commit

Se a branch estava limpa antes da aplicação, você pode voltar os arquivos versionados ao último commit, por exemplo:

```zsh
cd "$HOME/GestaoServicos_DEV" || exit 1
git restore -- cadastros_v9.py portal.js portal_negocios.py portal_prestador.py prestadores_ext.py requirements.txt
```

Os **arquivos novos** da revisão continuarão no diretório e devem ser revisados/removidos separadamente. Esse procedimento **não restaura o banco de dados de testes** caso você tenha criado dados manualmente durante os testes; preserve-o separadamente se necessário.
