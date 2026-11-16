"""Actions for the canonical settings section."""
from .common import a

ACTIONS = (
    a('settings.preferences', 'settings', 'Preferências de aparência', 'work_item.view.involved', 'prestador_auth.salvar_preferencias', 'list', '', '/configuracoes', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
