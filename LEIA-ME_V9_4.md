# Gestão de Serviços AUTOSEG v9.4 — Correção do portal do cliente

Pacote baseado no ZIP `gestaoservicos2.zip` (v9.3), mantendo o nome lógico
**GestaoServicos**. A pasta local `~/GestaoServicos2` continua válida.

## Instalação no Mac
1. Encerre GUI e servidores AUTOSEG; não apague a pasta ativa.
2. Extraia este ZIP na pasta Downloads; surgirá `GestaoServicos/`.
3. Execute:

```bash
bash "$HOME/Downloads/GestaoServicos/ATUALIZAR_AUTOSEG_V9_4.command" "$HOME/GestaoServicos2"
```

4. Abra pelo MESMO comando de sempre:

```bash
bash "$HOME/GestaoServicos2/INICIAR_AUTOSEG.command"
```

O instalador copia **somente** os 5 módulos alterados, faz backup consistente
via SQLite e preserva `dados.db`, `app.py`, `servidor_web.py`, PDFs, imagens e
Workaholic. Não utiliza o instalador v9.2 que tinha caminhos fixos.

## Telas novas
- `/cliente`: CPF e senha (entrada principal).
- `/cliente/cadastro`: criação inicial com CPF e senha.
- `/cliente/painel`: OS PF e chamados PJ da mesma conta.
- `/cliente/perfil`: contato e endereço obrigatórios antes de OS PF.
- `/cliente/nova`: solicitação particular.
- `/cliente/organizacoes`: busca pelo nome ou CNPJ sem revelar CNPJ.
- `/cliente/nova-organizacao`: pré-cadastro com endereço e apartamento/cargo.
- `/cliente/administrar-organizacao`: cadastro de PJ como responsável; vínculo pendente.
- `/cliente/vinculo/novo?org=ID`: pedido de vínculo de responsável para PJ existente.
- `/cliente/chamado/novo?org=ID`: chamado de morador/funcionário/porteiro.
- `/cliente/legado`: acesso antigo por ID e senha preservado.

## Atenção
- Não publicamos CPF/CNPJ nos resultados da pesquisa.
- Pessoa que diz ser síndico/proprietário não recebe privilégios automaticamente.
- Uma pessoa nova não recebe acesso a OS históricas pela coincidência de CPF.
- Os portais web e a GUI são os existentes; esta atualização não altera fiscal,
  PDFs, finance, integração WhatsApp e engine Workaholic.
- O ZIP não contém seu `dados.db` nem documentos pessoais.
- Ainda é necessário testar visualmente no seu Mac e auditar a segurança antes
  de disponibilizar publicamente a clientes reais.

Veja `docs/FLUXO_CLIENTE_V9_4.md` e `docs/MIGRACAO_MODULAR.md`.
