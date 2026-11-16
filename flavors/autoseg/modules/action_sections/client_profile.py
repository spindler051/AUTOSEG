"""Actions for the canonical client-profile section."""
from .common import a

ACTIONS = (
    a('client-profile.edit', 'client-profile', 'Meu perfil', 'customer.view.own', 'client_web', 'list', '', '/cliente/perfil', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
