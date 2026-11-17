"""Actions for the canonical finance section."""
from .common import a

ACTIONS = (
    a('finance.own', 'finance', 'Meu financeiro', 'finance.view.own', 'financeiro_pessoal', 'list', 'carregar_financeiro', '/financeiro', priority='primary'),
    a('finance.company', 'finance', 'Financeiro da empresa', '*', 'resumo_financeiro', 'list', 'carregar_financeiro', '/financeiro'),
    a('finance.receive', 'finance', 'Confirmar recebimento', 'finance.view.own', 'marcar_recebido', 'finance_write', '_marcar_recebido', '/financeiro'),
    a('finance.due', 'finance', 'Alterar vencimento', 'finance.view.own', 'definir_vencimento', 'finance_write', '_alterar_vencimento', '/financeiro'),
)
