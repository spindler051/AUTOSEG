"""Local database bootstrap shared by the login screen and the main window."""
from __future__ import annotations

from banco import BANCO, criar_banco
import atendimento_os as aten
import cadastros_v9 as cad9
import catalogo_servicos as catalogo
import composicao
import empresa_financeiro as empresa
import estoque_materiais as estoque
import fluxo_os as fluxo
import prestadores_ext as ext


def preparar_banco_local(banco=None) -> str:
    """Create/upgrade the local schema and return the database path."""
    caminho = str(banco or BANCO)
    criar_banco(caminho)
    ext.instalar(caminho)
    fluxo.instalar(caminho)
    aten.instalar(caminho)
    cad9.instalar(caminho)
    estoque.instalar(caminho)
    empresa.instalar(caminho)
    catalogo.instalar(caminho)
    composicao.instalar()
    composicao.instalar_banco(caminho)
    try:
        fluxo.recuperar_relatorios_antigos(caminho)
    except Exception as erro:
        print('Aviso: recuperação de PDFs anteriores:', erro)
    return caminho
