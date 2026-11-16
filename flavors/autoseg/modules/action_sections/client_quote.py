"""Actions for the canonical client-quote section."""
from .common import a

ACTIONS = (
    a('client-quote.view', 'client-quote', 'Orçamento', 'work_item.view.own', 'client_web', 'list', '', '/cliente/orcamento', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
