"""Actions for the canonical home section."""
from .common import a

ACTIONS = (
    a('home.refresh', 'home', 'Atualizar dados', 'work_item.view.involved', 'resumo_inicio', 'list', '_atualizar_tudo', '/', priority='primary'),
    a('home.recent', 'home', 'Abrir OS recente', 'work_item.view.involved', 'listar_os_recentes', 'list', '_abrir_os_inicio', '/os'),
)
