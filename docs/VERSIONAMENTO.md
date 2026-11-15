# Versionamento e homologação

A fonte única da versão é `versao.json`.

## Branches

- `develop`: desenvolvimento; versões `X.Y.Z-dev.N`.
- `main`: produção; versões `X.Y.Z` após homologação.
- `rc`: candidata de homologação, ainda no `develop`.

## Comandos

```bash
python3 versionador.py info
python3 versionador.py verificar
python3 versionador.py proxima --tipo dev
python3 versionador.py avancar --tipo dev
```

`avancar` altera apenas `versao.json` no `develop` quando o arquivo está sem
alterações pendentes. Não faz commit, push, migração nem toca em dados.

## Regra de promoção

Antes de `main`:

1. suíte não visual verde;
2. scripts de aceitação verdes;
3. smoke manual no macOS e nas duas visões do Officina Web;
4. backup e rollback descritos;
5. revisão humana externa quando a mudança for N3/N4;
6. `CHANGELOG.md` atualizado.

O schema SQLite é independente da versão do app. Nunca usar a versão como
número de schema.

## Segurança de dados

Não executar `git reset --hard`, `git clean -fd` ou `git stash -u` em pastas com
dados. Bancos, anexos, PDFs e credenciais ficam fora do Git.
