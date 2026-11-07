# Testes executados — AUTOSEG

## Estado atual (nov/2026)

A suíte não visual completa roda com:

```bash
find . -maxdepth 1 -name 'test_*.py' ! -name 'test_visual_*' \
  -exec basename {} .py \; | sort | xargs ./.venv/bin/python -m unittest
```

Estado em 2026-11-07: **301 testes, 0 falhas, 1 skip**.

Scripts de aceitação que também devem passar:

```bash
./.venv/bin/python test_portal_v4.py
./.venv/bin/python test_fluxo_v5.py
./.venv/bin/python test_fluxo_v6.py
./.venv/bin/python test_fluxo_v7.py
./.venv/bin/python test_fluxo_cliente_v94.py
./.venv/bin/python test_rev09_fluxo_os.py
./.venv/bin/python test_importacao_yaml.py
```

Essas suites usam banco, arquivos e portas temporárias; não gravam em
`dados.db`. Cobrem composição modular, fluxo da OS, unidades de materiais,
PDF, feedback, API financeira, portal do cliente, permissões e numeração.

### Testes legados (não executar no CI)

- `test_v9.py`, `test_v91.py`, `test_v92.py` e `test_v94_correcoes.py`:
  descrevem a arquitetura anterior à separação entre portal do cliente e
  portal do prestador; usam rotas e portas que não existem mais.
- Eles ficam preservados como referência histórica. Não indicam regressão da
  versão atual e não substituem os scripts acima.
- `test_portal_v4.py`, `test_fluxo_v5.py`, `test_fluxo_v6.py`,
  `test_fluxo_v7.py`, `test_fluxo_cliente_v94.py` e
  `test_rev09_fluxo_os.py` foram atualizados para a arquitetura atual e
  passaram a integrar a verificação manual.

## Histórico — v9.1

- Compilação dos módulos Python: OK.
- HTTP local com SQLite temporário e dados fictícios: OK.
- Conta com CPF e senha: OK; formulário mostra senha e confirmação.
- Pesquisa exata por CNPJ e ausência de CNPJ nos resultados: OK.
- PF sem vínculo com condomínio abre chamado: OK.
- Botão `wa.me` com telefone do síndico validado: OK.
- Fallback `wa.me/5551992692007`: OK.
- Portal do prestador acessa Clientes, OS, Financeiro, Notas, E-mails, Chamados e Organizações: OK.
- Navegação do prestador sem cadastro de prestadores ou link de acionamento PJ: OK.
- PDF gera páginas válidas com imagem anexada sem autorização prévia: OK. Imagem detectada dentro do PDF.
- Verificação visual do PDF A4 e rodapé: realizada com imagem fictícia.
- Teste Tkinter com tela virtual (histórico, encerramento de OS e módulo PJ): passou; logo original ausente no ambiente de teste, mas preservado no Mac pelo instalador.
- Instalação simulada no HOME temporário: passou, incluindo backup consistente e preservação do banco/arquivos originais.

**Não testado com dados reais:** funcionamento direto no macOS Intel do usuário; `servidor_web.py` legado; registro Cloudflare real (sem conexão externa no ambiente de testes); envio automático de mensagem por WhatsApp (não é oferecido por `wa.me`).

Execute a verificação de instalação/backup antes de utilizar o banco original.

## Regressão v9.2
- `/cliente` oferece login CPF e senha.
- `/cliente/cadastro` tem senha e confirmação.
- Cadastro de usuário via POST e login CPF/senha.
- `/cliente/legado` conserva ID e senha.
- Formulário administrativo de cadastro e edição tem senha opcional e confirmação.
- Senha fornecida pelo administrador é validada e salva via hash.
- `test_v92.py` e `test_v91.py` passaram em banco temporário.
