"""Actions for the canonical client-documents section."""
from .common import a

ACTIONS = (
    a('client-documents.list', 'client-documents', 'Meus documentos', 'document.view.own', 'client_web', 'list', '', '/documentos', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
