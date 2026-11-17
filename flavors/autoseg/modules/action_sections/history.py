"""Actions for the canonical history section."""
from .common import a

ACTIONS = (
    a('history.list', 'history', 'Consultar histórico', 'work_item.view.involved', 'listar_historico', 'list', 'carregar_historico', '/historico', priority='primary'),
    a('history.open', 'history', 'Abrir OS do histórico', 'work_item.view.involved', 'contexto_os', 'view', '_editar_historico', '/historico'),
    a('history.pdf', 'history', 'Abrir PDF do histórico', 'document.download.involved', 'pdf_publicado', 'download', '_abrir_pdf_historico', '/historico'),
)
