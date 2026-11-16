"""Actions for the canonical desktop-web section."""
from .common import a

ACTIONS = (
    a('desktop-web.open', 'desktop-web', 'Abrir Officina Web', '*', 'WebAccessManager', 'list', '_abrir_portal_navegador', '', priority='primary', surfaces=('gtk',), reason='Device-native controls are not exposed as browser operations.'),
    a('desktop-web.start', 'desktop-web', 'Ligar ou desligar servidor', '*', 'WebAccessManager', 'list', '_alternar_servidor', '', priority='menu', destructive=True, confirm='Alterar o servidor local e o acesso externo?', surfaces=('gtk',), reason='Device-native controls are not exposed as browser operations.'),
)
