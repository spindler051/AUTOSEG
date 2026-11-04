#!/bin/zsh
cd "$(dirname "$0")" || exit 1
export AUTOSEG_DEV=1
PYTHON="$PWD/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo 'ERRO: ambiente .venv ausente. Crie o ambiente e instale requirements.txt.'
  exit 1
fi
"$PYTHON" -m unittest test_rev04_operacoes test_rev04_http test_rev03_fluxo test_rev03_http test_autoseg_melhorias test_autoseg_http_novo test_v953_fluxo test_pf_pj_responsaveis test_pf_pj_http -v || exit 1
"$PYTHON" -m compileall -q banco.py estoque_materiais.py importacao_yaml.py catalogo_servicos.py portal_prestador.py portal_negocios.py portal_cliente_v94.py portal_v9.py fluxo_os.py servidor_web.py prestadores_ext.py gtk_app.py gtk_comum.py gtk_dialogos.py telemetry || exit 1
if command -v node >/dev/null 2>&1; then
  node --check portal.js || exit 1
fi
echo 'AUTOSEG DEV REV04: testes automatizados aprovados. Verifique também a interface real no Mac.'
