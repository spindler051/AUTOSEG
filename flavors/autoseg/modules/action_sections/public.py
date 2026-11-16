"""Actions for the canonical public section."""
from .common import a

ACTIONS = (
    a('public.list', 'public', 'Solicitações de condomínios', '*', 'painel_pj', 'list', 'carregar_pj', '/pj-publicas', priority='primary'),
    a('public.analyze', 'public', 'Analisar chamado', '*', 'analisar_chamado', 'list', '_analisar_chamado', '/pj-publicas'),
    a('public.confirm', 'public', 'Confirmar chamado', '*', 'confirmar_chamado', 'list', '_confirmar_chamado', '/pj-publicas'),
    a('public.create_work', 'public', 'Gerar OS do chamado', '*', 'gerar_os_chamado', 'list', '_gerar_os_chamado', '/pj-publicas'),
    a('public.reject', 'public', 'Recusar chamado', '*', 'analisar_chamado', 'list', '_recusar_chamado', '/pj-publicas', priority='menu', destructive=True, confirm='Recusar solicitação e registrar o motivo?'),
    a('public.verify', 'public', 'Validar organização', '*', 'validar_organizacao', 'list', '_validar_organizacao', '/pj-publicas'),
    a('public.merge', 'public', 'Mesclar organizações', '*', 'mesclar_organizacoes', 'list', '_mesclar_organizacoes', '/pj-publicas', priority='menu', destructive=True, confirm='Mesclar organizações e preservar os históricos?'),
)
