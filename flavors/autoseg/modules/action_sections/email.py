"""Actions for the canonical email section."""
from .common import a

ACTIONS = (
    a('email.list', 'email', 'Consultar e-mails', 'work_item.view.involved', 'listar_relatorios', 'list', 'carregar_emails', '/emails', priority='primary'),
    a('email.open', 'email', 'Abrir OS do e-mail', 'work_item.view.involved', 'contexto_os', 'view', '_abrir_os_documento', '/emails'),
    a('email.prepare', 'email', 'Preparar e-mail', 'work_item.send.own', 'preparar_email', 'send', '_preparar_documento', '/emails'),
)
