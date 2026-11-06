# Testes executados — AUTOSEG

## Estado atual (nov/2026)

Execute na raiz do projeto, com o ambiente virtual:

```bash
./.venv/bin/python -m unittest test_composicao
./.venv/bin/python -m unittest test_rev12_correcoes
./.venv/bin/python -m unittest test_feedback_portal
./.venv/bin/python -m unittest test_api_financeiro
./.venv/bin/python -m unittest test_autoseg_melhorias
./.venv/bin/python -m unittest test_pdf_relatorio
./.venv/bin/python test_importacao_yaml.py
```

Essas suites usam banco, arquivos e portas temporárias; não gravam em
`dados.db`. Cobrem composição modular, fluxo da OS, unidades de materiais,
PDF, feedback e API financeira.

O CI da `main` executa exatamente essa lista em passos separados. O CI da
`develop` executa `test_versionador`, `test_produtividade_rev07`,
`test_composicao`, `test_autoseg_melhorias` e `test_importacao_yaml.py`.

### Testes legados (não executar no CI)

- `test_v94_correcoes.py` e `test_portal_v4.py`: pertencem ao portal antigo
  v9.4.1 e não acompanham a rota atual `/cliente`.
- `test_autoseg_http_novo.py`: depende de uma versão anterior do servidor HTTP.

Eles ficam preservados como referência histórica. Não indicam regressão da
versão atual.

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
