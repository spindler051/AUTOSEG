# Gestão de Serviços / AUTOSEG + Workaholic (integração inicial)

**Nome da pasta de instalação:** `~/GestaoServicos`.

**Comando de abertura da interface:** `bash ~/GestaoServicos/INICIAR_AUTOSEG.command`.

Este pacote contém a aplicação gráfica AUTOSEG **v9.2** e o protótipo Workaholic **v0.1.0** em `~/GestaoServicos/workaholic/`.
O Workaholic NÃO substitui o aplicativo e NÃO está conectado ao banco `dados.db` nesta versão. A integração será gradual, depois de revisão de contratos e migração com testes.

## Instalação

1. Feche os portais e a GUI antes de atualizar.
2. Guarde cópia externa de `~/GestaoServicos/`.
3. Extraia o ZIP e execute `bash ~/Downloads/GestaoServicos/INSTALAR_NO_MAC.command` (ajuste o caminho se o descompactador usar outro diretório).
4. Abra a interface com `bash ~/GestaoServicos/INICIAR_AUTOSEG.command`.

O instalador exige uma instalação existente com `app.py`, `banco.py`, `servidor_web.py` e `dados.db`. Ele cria backup consistente do banco antes de copiar módulos. Ele não substitui `banco.py`, `servidor_web.py`, `dados.db`, fotos, PDFs, logotipos ou `.venv` existente.

## CLI experimental Workaholic

Instale somente a dependência YAML, se precisar usar o protótipo:

```bash
~/GestaoServicos/.venv/bin/python -m pip install 'PyYAML>=6,<7'
```

Use (com banco de exemplo separado, nunca com `dados.db`):

```bash
bash ~/GestaoServicos/WORKAHOLIC_CLI.command --schema ~/GestaoServicos/workaholic/examples/arts/schema.yaml --storage sqlite --data ~/GestaoServicos/workaholic_artes_teste.db entities
```

O comando futuro `workaholic-cli` será instalado como entrypoint quando a integração do empacotamento for aprovada; por enquanto o `.command` evita alterar o ambiente da GUI.

## Limites

- Não existe GUI Workaholic neste pacote; o frontend continua sendo o AUTOSEG v9.2.
- Os módulos fiscais, PDFs e fluxos AUTOSEG continuam os legados nesta etapa.
- A licença 0BSD em `workaholic/LICENSE` se refere ao subprojeto Workaholic. Não relicencia código legado AUTOSEG nem contribuições de terceiros.
- Portais 8765 e 8766 dependem do código legado e da configuração de execução, e túneis rápidos da Cloudflare são temporários.
- Validar em Mac real antes de colocar o sistema em produção.
