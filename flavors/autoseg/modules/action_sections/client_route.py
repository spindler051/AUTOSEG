"""Actions for the canonical client-route section."""
from .common import a

ACTIONS = (
    a('client-route.list', 'client-route', 'Acompanhar deslocamento', 'work_item.view.own', 'client_web', 'list', '', '/em-rota', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
