"""Actions for the canonical providers section."""
from .common import a

ACTIONS = (
    a('providers.list', 'providers', 'Consultar prestadores', '*', 'listar_prestadores', 'list', 'carregar_prestadores', '/prestadores', priority='primary'),
    a('providers.create', 'providers', 'Novo prestador', '*', 'criar_prestador', 'create', '_novo_prestador', '/prestadores', priority='primary'),
    a('providers.edit', 'providers', 'Editar cadastro do prestador', '*', 'atualizar_prestador', 'list', '_editar_prestador', '/prestadores'),
    a('providers.admin_role', 'providers', 'Alternar papel administrador', '*', 'definir_admin', 'list', '_admin_prestador', '/prestadores'),
    a('providers.toggle', 'providers', 'Ativar ou desativar prestador', '*', 'alternar_prestador', 'list', '_alternar_prestador', '/prestadores', priority='menu', destructive=True, confirm='Alterar a situação do prestador?'),
    a('providers.archive', 'providers', 'Arquivar prestador', '*', 'arquivar_prestador', 'list', '_excluir_prestador', '/prestadores', priority='menu', destructive=True, confirm='Arquivar prestador e revogar o acesso?'),
    a('providers.password', 'providers', 'Redefinir senha do prestador', '*', 'redefinir_senha_prestador', 'list', '_senha_prestador', '/prestadores'),
    a('providers.integrations', 'providers', 'Configurar integrações', '*', 'salvar_config_prestador', 'list', '_integracoes_prestador', '/prestadores'),
)
