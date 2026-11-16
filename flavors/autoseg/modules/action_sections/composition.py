"""Actions for the canonical composition section."""
from .common import a

ACTIONS = (
    a('composition.view', 'composition', 'Consultar composição', '*', 'composicao_config', 'list', 'carregar_composicao', '/composicao', priority='primary'),
    a('composition.configure', 'composition', 'Configurar composição', '*', 'composicao_salvar', 'list', '_salvar_config_composicao', '/composicao'),
    a('composition.add', 'composition', 'Novo componente', '*', 'composicao_salvar', 'create', '_novo_componente', '/composicao/novo'),
    a('composition.edit', 'composition', 'Editar componente', '*', 'composicao_salvar', 'list', '_editar_componente', '/composicao'),
    a('composition.activate', 'composition', 'Ativar ou desativar componente', '*', 'composicao_salvar', 'list', '_alternar_componente', '/composicao', priority='menu', destructive=True, confirm='Alterar a disponibilidade do componente?'),
    a('composition.delete', 'composition', 'Excluir componente', '*', 'composicao_salvar', 'list', '_excluir_componente', '/composicao', priority='menu', destructive=True, confirm='Excluir componente da composição?'),
    a('composition.recalculate', 'composition', 'Recalcular composições', '*', 'composicao_recalcular', 'list', '_recalcular_composicoes', '/composicao', priority='menu', destructive=True, confirm='Recalcular composições das OS abertas?'),
)
