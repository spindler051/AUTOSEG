"""Actions for the canonical invoices section."""
from .common import a

ACTIONS = (
    a('invoices.list', 'invoices', 'Consultar notas fiscais', 'work_item.view.involved', 'listar_relatorios', 'list', 'carregar_notas', '/notas', priority='primary'),
    a('invoices.open', 'invoices', 'Abrir OS da nota', 'work_item.view.involved', 'contexto_os', 'view', '_abrir_os_documento', '/notas'),
    a('invoices.prepare', 'invoices', 'Preparar nota fiscal', 'work_item.send.own', 'preparar_nota', 'send', '_preparar_documento', '/notas'),
)
