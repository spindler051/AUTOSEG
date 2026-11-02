"""Fluxo operacional v7 — solicitação imutável, início e rascunhos técnicos.
Migração não destrutiva: não atualiza campos da OS original nem migra dados
sobrepostos retroativamente para uma falsa versão histórica.
"""
import prestadores_ext as ext

def instalar(banco):
    with ext.db(banco) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS os_solicitacoes (
          os_id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL,
          descricao_original TEXT NOT NULL, observacoes_originais TEXT NOT NULL DEFAULT '',
          criado_em TEXT NOT NULL, origem TEXT NOT NULL DEFAULT 'App');
        CREATE TABLE IF NOT EXISTS os_atendimentos (
          os_id INTEGER PRIMARY KEY, iniciado_em TEXT,
          iniciado_por INTEGER, ator_inicio TEXT NOT NULL DEFAULT '',
          rascunho TEXT NOT NULL DEFAULT '', atualizado_em TEXT,
          ultimo_editor TEXT NOT NULL DEFAULT '');
        """)
        # Para OS legadas, este é o estado atual recuperável, NÃO garante a redação original.
        c.execute("""INSERT OR IGNORE INTO os_solicitacoes
           (os_id,cliente_id,descricao_original,observacoes_originais,criado_em,origem)
           SELECT id,cliente_id,COALESCE(descricao,''),COALESCE(observacoes,''),
                  COALESCE(criado_em,''),COALESCE(origem,'App') FROM ordens_servico""")

def registrar_solicitacao(c,os_id,cliente_id,descricao,observacoes='',origem='App'):
    c.execute("""INSERT OR IGNORE INTO os_solicitacoes
        (os_id,cliente_id,descricao_original,observacoes_originais,criado_em,origem)
        VALUES(?,?,?,?,?,?)""",(os_id,cliente_id,descricao,observacoes,ext.agora(),origem))

def iniciar(banco,os_id,pid=None,ator='Administrador desktop'):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not o or o['status'] not in ext.ATIVAS: raise ValueError('A OS não está ativa.')
        if pid is not None:
            p=c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1',(pid,)).fetchone()
            if not p or ext.responsavel_atual(c,os_id)!=pid:
                raise PermissionError('Assuma a OS antes de iniciar atendimento.')
            ator=p['nome']
        existente=c.execute('SELECT iniciado_em FROM os_atendimentos WHERE os_id=?',(os_id,)).fetchone()
        if existente and existente['iniciado_em']:
            try:
                ext.finalizar_em_rota(c, os_id)
            except Exception:
                pass
            return False
        c.execute('''INSERT INTO os_atendimentos(os_id,iniciado_em,iniciado_por,ator_inicio)
          VALUES(?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
          iniciado_em=excluded.iniciado_em,iniciado_por=excluded.iniciado_por,
          ator_inicio=excluded.ator_inicio''',(os_id,ext.agora(),pid,ator))
        try:
            ext.finalizar_em_rota(c, os_id)
        except Exception:
            pass
        ext.evento(c,os_id,'Atendimento iniciado','Início de execução registrado no local.',pid,ator)
        return True

def salvar_rascunho(c,os_id,relato,ator):
    relato=(relato or '').strip()
    if len(relato)>10000:raise ValueError('O rascunho excede 10.000 caracteres.')
    anterior=c.execute('SELECT rascunho FROM os_atendimentos WHERE os_id=?',(os_id,)).fetchone()
    if anterior and anterior['rascunho']==relato:return
    c.execute('''INSERT INTO os_atendimentos(os_id,rascunho,atualizado_em,ultimo_editor)
      VALUES(?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
      rascunho=excluded.rascunho,atualizado_em=excluded.atualizado_em,
      ultimo_editor=excluded.ultimo_editor''',(os_id,relato,ext.agora(),ator))
    ext.evento(c,os_id,'Rascunho técnico salvo',f'{len(relato)} caracteres salvos.',ator=ator)

def obter(banco,os_id):
    with ext.db(banco) as c:
        s=c.execute('SELECT * FROM os_solicitacoes WHERE os_id=?',(os_id,)).fetchone()
        a=c.execute('SELECT * FROM os_atendimentos WHERE os_id=?',(os_id,)).fetchone()
        return (dict(s) if s else None,dict(a) if a else {})


def iniciar_assumindo(banco,os_id,pid):
    """Um botão: assume (quando autorizado) e inicia; os dois fatos são auditados.

    A validação de assunção é feita em transação pelo módulo de prestadores.
    Para OS já aberta e atribuída a outro prestador, não toma posse.
    """
    with ext.db(banco) as c:
        os_atual=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not os_atual or os_atual['status'] not in ext.ATIVAS:
            raise ValueError('Esta OS não está disponível para iniciar.')
        atual=ext.responsavel_atual(c,os_id)
        status=os_atual['status']
    if atual != pid or status=='Pendente':
        ext.assumir(banco,os_id,pid)
    return iniciar(banco,os_id,pid)


def assumir_os(banco, os_id, pid):
    import prestadores_ext as ext
    return ext.assumir(banco, os_id, pid)
