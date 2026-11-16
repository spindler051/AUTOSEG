"""Actions for the canonical client-work section."""
from .common import a

ACTIONS = (
    a('client-work.list', 'client-work', 'Minhas ordens', 'work_item.view.own', 'client_web', 'list', '', '/os', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
