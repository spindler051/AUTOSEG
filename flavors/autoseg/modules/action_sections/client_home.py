"""Actions for the canonical client-home section."""
from .common import a

ACTIONS = (
    a('client-home.open', 'client-home', 'Painel do cliente', 'customer.view.own', 'client_web', 'list', '', '/', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
