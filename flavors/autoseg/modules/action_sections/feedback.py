"""Actions for the canonical feedback section."""
from .common import a

ACTIONS = (
    a('feedback.inbox', 'feedback', 'Consultar feedbacks', '*', 'feedback_portal', 'list', '', '/feedback/recebidos', priority='primary', surfaces=('web',), reason='Web-only section; no authenticated GTK client or browser preference surface.'),
)
