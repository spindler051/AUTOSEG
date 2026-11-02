# AUTOSEG — Versionamento e homologação

A versão atual é **9.6.0-dev.1 / REV08**. Não representa a homologação das 78 melhorias.

- develop: desenvolvimento, versões X.Y.Z-dev.N.
- main: produção, versões X.Y.Z após aprovação no Mac.
- rc: versão candidata de homologação, ainda no develop.
- versao.json é a fonte única de identidade da versão; schema SQLite é independente.

Comandos: python3 versionador.py info | verificar | proxima --tipo dev | avancar --tipo dev.

O comando avancar altera apenas versao.json no branch develop se o arquivo de versão estiver sem alterações; não faz commit, push, migração ou manipulação de dados.

AVISO: O Mac possui alterações locais em ~/GestaoServicos_DEV, incluindo YAML, catálogo e estoque ausentes ou divergentes no GitHub. Antes de atualizar: faça backup do SQLite e anexos e reconcilie os diffs. Não execute git reset --hard, git clean -fd nem git stash -u indiscriminadamente. Mantenha ~/gestaoservicos_MAIN e seus dados separados.

Promova para main somente após testes de desktop, portais, segurança de PDF, Gmail, reversão e homologação. Registre changelog e tag anotada vX.Y.Z.
