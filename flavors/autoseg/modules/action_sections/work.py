"""Actions for the canonical work section."""
from .common import a

ACTIONS = (
    a('work.create', 'work', 'Nova OS', 'work_item.create', 'salvar_os', 'create', 'nova_os', '/os/nova', priority='primary'),
    a('work.open', 'work', 'Abrir OS', 'work_item.view.involved', 'contexto_os', 'view', '_editar_os', '/os/{id}'),
    a('work.edit', 'work', 'Editar OS', 'work_item.edit.involved', 'salvar_os', 'edit', '_editar_os', '/os/{id}'),
    a('work.assign', 'work', 'Atribuir prestador', '*', 'atribuir_os', 'assign', '_atribuir_os_selecionada', '/os/{id}'),
    a('work.assume', 'work', 'Assumir OS', 'work_item.view.involved', 'os_commands.assumir', 'assume', '_assumir_os_selecionada', '/os/{id}'),
    a('work.start', 'work', 'Iniciar atendimento', 'work_item.start.own', 'iniciar_os', 'start', '_iniciar_os_selecionada', '/os/{id}'),
    a('work.route', 'work', 'Iniciar rota', 'work_item.start.own', 'os_commands.em_rota', 'start', '_rota_os_selecionada', '/os/{id}'),
    a('work.conclude', 'work', 'Concluir OS', 'work_item.conclude.own', 'salvar_os', 'conclude', '_encerrar_os', '/os/{id}'),
    a('work.cancel', 'work', 'Cancelar OS', 'work_item.cancel.own', 'salvar_os', 'cancel', '_encerrar_os', '/os/{id}', priority='secondary', destructive=True, confirm='Cancelar a OS? O histórico será preservado.'),
    a('work.archive', 'work', 'Arquivar OS', '*', 'arquivar_os', 'archive', '_arquivar_os_selecionada', '/os/{id}', priority='menu', destructive=True, confirm='Arquivar a OS? Ela deixará as listas operacionais.'),
    a('work.reopen', 'work', 'Reabrir OS', 'work_item.reopen.all', 'reabrir_os', 'reopen', '_reabrir_os_selecionada', '/os/{id}', priority='menu', destructive=True, confirm='Reabrir a OS? A situação operacional será alterada.'),
    a('work.publish', 'work', 'Publicar PDF', 'work_item.publish.own', 'publicar_pdf', 'publish', '_publicar_pdf_os_selecionada', '/os/{id}'),
    a('work.email', 'work', 'Preparar e-mail', 'work_item.send.own', 'preparar_email', 'send', '_preparar_email_os_selecionada', '/os/{id}'),
    a('work.invoice', 'work', 'Preparar nota fiscal', 'work_item.send.own', 'preparar_nota', 'send', '_preparar_nota_os_selecionada', '/os/{id}'),
    a('work.attach', 'work', 'Fotos e anexos', 'work_item.attach.involved', 'salvar_os', 'attach', '_editar_os', '/os/{id}'),
    a('work.materials', 'work', 'Materiais e composição', 'work_item.edit.involved', 'salvar_os', 'edit', '_editar_os', '/os/{id}'),
    a('work.draft', 'work', 'Salvar rascunho', 'work_item.edit.involved', 'salvar_os', 'edit', '_editar_os', '/os/{id}'),
    a('work.yaml', 'work', 'Importar YAML', 'work_item.create', 'salvar_os', 'create', '_importar_os_yaml', '/os/nova', priority='menu'),
)
