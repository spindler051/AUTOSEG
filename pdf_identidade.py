"""Identidade visual AUTOSEG para PDFs (logo no cabeçalho e selo em todas as páginas)."""
import re
from pathlib import Path

import prestadores_ext as ext

# CNPJ principal da empresa, usado nos orçamentos e como referência nos relatórios.
CNPJ_PRINCIPAL = '23.864.393/0001-87'
CNPJ_PRINCIPAL_DIGITOS = re.sub(r'\D', '', CNPJ_PRINCIPAL)


def formatar_cnpj(valor):
    """Formata CNPJ canônico (14 dígitos) sem inventar dados."""
    digitos = re.sub(r'\D', '', str(valor or ''))
    if len(digitos) != 14:
        return ''
    return f'{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}'


def caminho_imagem(nome):
    """Localiza logo.png/icone.png na pasta de dados (MAIN/DEV), no bundle ou no código."""
    candidatos = [
        Path(ext.BASE) / nome,
        Path(__file__).resolve().parent / nome,
        Path.home() / 'gestaoservicos_MAIN' / nome,
        Path.home() / 'GestaoServicos_DEV' / nome,
    ]
    for candidato in candidatos:
        try:
            if candidato.is_file():
                return candidato
        except OSError:
            continue
    return None


def _caminho_icone():
    """Localiza o ícone (icone.png ou icone_devel.png), preferindo o do ambiente."""
    nomes = [ext.nome_icone()]
    nomes.append('icone.png' if ext.nome_icone() == 'icone_devel.png' else 'icone_devel.png')
    for nome in nomes:
        caminho = caminho_imagem(nome)
        if caminho:
            return caminho
    return None


def logo_flowable(largura_max=175, altura_max=40):
    """Retorna uma imagem ReportLab proporcional ou None se logo.png não existir."""
    caminho = caminho_imagem('logo.png')
    if not caminho:
        return None
    try:
        from PIL import Image
        from reportlab.platypus import Image as RLImage
        with Image.open(caminho) as imagem:
            largura, altura = imagem.size
        if not largura or not altura:
            return None
        escala = min(largura_max / largura, altura_max / altura)
        return RLImage(str(caminho), width=largura * escala, height=altura * escala)
    except Exception:
        return None


def desenhar_selo(canvas, documento):
    """Desenha o selo (icone.png, ou icone_devel.png em DEV) no canto superior direito."""
    caminho = _caminho_icone()
    if not caminho:
        return
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        largura_pagina, altura_pagina = A4
        tamanho = 22
        x = largura_pagina - 64
        y = altura_pagina - 32
        canvas.saveState()
        canvas.drawImage(ImageReader(str(caminho)), x, y,
                         width=tamanho, height=tamanho,
                         mask='auto', preserveAspectRatio=True)
        canvas.restoreState()
    except Exception:
        try:
            canvas.restoreState()
        except Exception:
            pass
