"""Actions for the canonical finance section."""
from .common import a

ACTIONS = (
    a('finance.own', 'finance', 'Meu financeiro', 'finance.view.own', 'financeiro_pessoal', 'list', 'carregar_financeiro', '/financeiro', priority='primary'),
    a('finance.company', 'finance', 'Financeiro da empresa', '*', 'resumo_financeiro', 'list', 'carregar_financeiro', '/financeiro'),
    a('finance.receive', 'finance', 'Confirmar recebimento', '*', 'marcar_recebido', 'list', '_marcar_recebido', '/financeiro'),
    a('finance.due', 'finance', 'Alterar vencimento', '*', 'definir_vencimento', 'list', '_alterar_vencimento', '/financeiro'),
)
