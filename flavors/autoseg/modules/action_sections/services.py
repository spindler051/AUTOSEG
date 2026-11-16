"""Actions for the canonical services section."""
from .common import a

ACTIONS = (
    a('services.list', 'services', 'Consultar serviços', 'work_item.view.involved', 'catalogo_listar', 'list', 'carregar_catalogo', '/servicos', priority='primary'),
    a('services.create', 'services', 'Novo serviço', '*', 'catalogo_salvar', 'create', '_novo_servico', '/servicos/novo', priority='primary'),
    a('services.edit', 'services', 'Editar serviço', '*', 'catalogo_salvar', 'list', '_editar_servico', '/servicos'),
    a('services.archive', 'services', 'Arquivar serviço', '*', 'catalogo_definir_ativo', 'list', '_arquivar_servico', '/servicos', priority='menu', destructive=True, confirm='Arquivar o serviço e preservá-lo no histórico?'),
    a('services.delete', 'services', 'Excluir serviço', '*', 'catalogo_excluir', 'list', '_excluir_servico', '/servicos', priority='menu', destructive=True, confirm='Excluir o serviço cadastrado?'),
    a('services.yaml', 'services', 'Importar serviços YAML', '*', 'catalogo_salvar', 'list', '_importar_servico', '/servicos', priority='menu'),
)
