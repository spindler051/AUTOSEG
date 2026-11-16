"""Actions for the canonical desktop-connect section."""
from .common import a

ACTIONS = (
    a('desktop-connect.test', 'desktop-connect', 'Testar conexão', '*', 'ConnectionSettings', 'list', '_testar_conexao', '', priority='primary', surfaces=('gtk',), reason='Device-native controls are not exposed as browser operations.'),
    a('desktop-connect.save', 'desktop-connect', 'Salvar conexão', '*', 'ConnectionSettings', 'list', '_salvar_conexao', '', surfaces=('gtk',), reason='Device-native controls are not exposed as browser operations.'),
)
