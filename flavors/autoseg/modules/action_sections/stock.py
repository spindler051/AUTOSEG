"""Actions for the canonical stock section."""
from .common import a

ACTIONS = (
    a('stock.view', 'stock', 'Consultar estoque', 'stock.view', 'listar_materiais_estoque', 'list', 'carregar_estoque', '/estoque', priority='primary'),
    a('stock.create', 'stock', 'Novo material', '*', 'estoque_cadastrar', 'create', '_novo_material', '/estoque/novo', priority='primary'),
    a('stock.edit', 'stock', 'Editar material', '*', 'estoque_cadastrar', 'list', '_editar_material', '/estoque'),
    a('stock.adjust', 'stock', 'Ajustar quantidade', '*', 'estoque_ajuste', 'list', '_ajustar_material', '/estoque'),
    a('stock.history', 'stock', 'Ver histórico de movimentos', 'stock.view', 'estoque_movimentos', 'list', '_historico_material', '/estoque'),
    a('stock.delete', 'stock', 'Excluir material', '*', 'estoque_excluir', 'list', '_excluir_material', '/estoque', priority='menu', destructive=True, confirm='Excluir material do estoque?'),
    a('stock.import', 'stock', 'Importar estoque YAML', '*', 'estoque_importar_lote', 'list', '_importar_materiais', '/estoque', priority='menu'),
)
