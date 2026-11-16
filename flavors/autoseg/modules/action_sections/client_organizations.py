"""Actions for the canonical client-organizations section."""
from .common import a

ACTIONS = (
    a('client-organizations.list', 'client-organizations', 'Minhas organizações', 'customer.view.own', 'client_web', 'list', '', '/cliente/organizacoes', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
