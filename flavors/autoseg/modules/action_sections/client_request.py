"""Actions for the canonical client-request section."""
from .common import a

ACTIONS = (
    a('client-request.create', 'client-request', 'Solicitar serviço', 'work_item.create.request', 'client_web', 'create', '', '/solicitar', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
