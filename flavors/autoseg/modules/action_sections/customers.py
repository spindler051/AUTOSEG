"""Actions for the canonical customers section."""
from .common import a

ACTIONS = (
    a('customers.list', 'customers', 'Consultar clientes', 'customer.view.involved', 'listar_clientes', 'list', 'carregar_clientes', '/clientes', priority='primary'),
    a('customers.create', 'customers', 'Novo cliente', 'customer.create', 'salvar_cliente', 'create', 'novo_cliente', '/clientes/novo', priority='primary'),
    a('customers.edit', 'customers', 'Editar cliente', 'customer.edit.involved', 'salvar_cliente', 'edit', '_editar_cliente', '/clientes/{id}'),
    a('customers.deactivate', 'customers', 'Desativar cliente', '*', 'desativar_cliente', 'edit', '_desativar_cliente', '/clientes/{id}', priority='menu', destructive=True, confirm='Desativar o cliente? O histórico será mantido.'),
    a('customers.delete', 'customers', 'Excluir cliente', '*', 'excluir_cliente', 'edit', '_excluir_cliente', '/clientes/{id}', priority='menu', destructive=True, confirm='Excluir cliente sem OS vinculadas? Esta ação é irreversível.'),
    a('customers.merge', 'customers', 'Mesclar clientes', '*', 'mesclar_clientes', 'edit', '_mesclar_cliente', '/clientes/{id}'),
    a('customers.password', 'customers', 'Redefinir senha do cliente', '*', 'definir_senha_cliente', 'edit', '_senha_cliente', '/clientes/{id}'),
    a('customers.yaml', 'customers', 'Importar cliente YAML', 'customer.create', 'salvar_cliente', 'create', '_importar_cliente_yaml', '/clientes/novo', priority='menu'),
    a('customers.new_work', 'customers', 'Abrir OS para cliente', 'work_item.create', 'salvar_os', 'create', '_nova_os_cliente', '/os/nova'),
)
