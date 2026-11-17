"""PJ navigation maps two *distinct* existing resource domains.

Web `/pj-publicas` processes unregistered public requests via solicitacoes_pj;
GTK V9 operates registered organization calls and links via cadastros_v9.
Do not infer that a public request is a V9 chamado or share object identifiers.
No new grants are introduced: these actions remain administrator-only.
"""
from .common import a

ACTIONS = (
    # Web: solicitacoes_pj / pj_publico only.
    a('public.request.list', 'public', 'Solicitações públicas PJ', '*',
      'pj_publico.listar', 'list', '', '/pj-publicas', priority='primary',
      surfaces=('web',), reason='Public requests use pj_publico, not GTK V9 chamados.'),
    a('public.request.accept', 'public', 'Aceitar solicitação pública', '*',
      'pj_publico.aceitar', 'list', '', '/pj-publicas',
      surfaces=('web',), reason='Acceptance is a public-request operation.'),
    a('public.request.reject', 'public', 'Recusar solicitação pública', '*',
      'pj_publico.recusar', 'list', '', '/pj-publicas', priority='menu',
      destructive=True, confirm='Recusar solicitação pública e registrar o motivo?',
      surfaces=('web',), reason='Public requests are Web-managed.'),
    # GTK V9: registered organization chamados.
    a('pj.chamado.list', 'public', 'Chamados PJ', '*', 'painel_pj',
      'list', 'carregar_pj', '', priority='primary', surfaces=('gtk',),
      reason='GTK V9 list uses registered organizations and their chamados.'),
    a('pj.chamado.analyze', 'public', 'Analisar chamado PJ', '*',
      'analisar_chamado', 'list', '_analisar_chamado', '', surfaces=('gtk',),
      reason='V9 organization chamado, not public request.'),
    a('pj.chamado.confirm', 'public', 'Confirmar chamado PJ', '*',
      'confirmar_chamado', 'list', '_confirmar_chamado', '', surfaces=('gtk',),
      reason='V9 organization chamado, not public request.'),
    a('pj.chamado.create_work', 'public', 'Gerar OS do chamado PJ', '*',
      'gerar_os_chamado', 'list', '_gerar_os_chamado', '', surfaces=('gtk',),
      reason='V9 organization chamado, not public request.'),
    a('pj.chamado.reject', 'public', 'Recusar chamado PJ', '*',
      'analisar_chamado', 'list', '_recusar_chamado', '', priority='menu',
      destructive=True, confirm='Recusar chamado e registrar o motivo?',
      surfaces=('gtk',), reason='V9 organization chamado.'),
    a('pj.organization.verify', 'public', 'Validar organização', '*',
      'validar_organizacao', 'list', '_validar_organizacao', '', surfaces=('gtk',),
      reason='V9 organization verification.'),
    a('pj.organization.merge', 'public', 'Mesclar organizações', '*',
      'mesclar_organizacoes', 'list', '_mesclar_organizacoes', '', priority='menu',
      destructive=True, confirm='Mesclar organizações e preservar históricos?',
      surfaces=('gtk',), reason='V9 organization merging.'),
)
