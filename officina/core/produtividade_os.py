"""AUTOSEG produtividade: estado de deslocamento, rascunhos e políticas.
Migrações aditivas em SQLite, sem rede externa e sem mover dados antigos.
"""
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
from officina.core import prestadores_ext as ext
CAMPOS = (
    'v9_diagnostico','v9_execucao','v9_resultado','relatorio_tecnico',
    'valor_mao_obra','valor_materiais_manual','valor_total_override',
    'forma_pagamento','tecnico','motivo_encerramento',
    'material_item[]','material_qtd[]','material_unit[]',
    'destinatario_sel[]','emails_adicionais'
)


def instalar(banco):
    with ext.db(banco) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS produtividade_deslocamentos(
            os_id INTEGER PRIMARY KEY, prestador_id INTEGER NOT NULL,
            em_rota INTEGER NOT NULL DEFAULT 0,
            atualizado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS produtividade_rascunhos(
            os_id INTEGER PRIMARY KEY, prestador_id INTEGER NOT NULL,
            versao INTEGER NOT NULL DEFAULT 1,
            dados_json TEXT NOT NULL, atualizado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS produtividade_etapas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            os_id INTEGER NOT NULL, prestador_id INTEGER NOT NULL,
            situacao TEXT NOT NULL, dados_json TEXT NOT NULL,
            hash_conteudo TEXT NOT NULL, registrado_em TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_prod_etapas_os
            ON produtividade_etapas(os_id,id);
        CREATE TABLE IF NOT EXISTS produtividade_email(
            os_id INTEGER PRIMARY KEY,
            destinatarios_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pendente',
            message_id TEXT, erro TEXT, atualizado_em TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS produtividade_rateios(
            os_id INTEGER NOT NULL, tecnico_id INTEGER NOT NULL,
            valor_centavos INTEGER NOT NULL CHECK(valor_centavos>=0),
            definidor_id INTEGER NOT NULL, registrado_em TEXT NOT NULL,
            PRIMARY KEY(os_id,tecnico_id));
        CREATE TABLE IF NOT EXISTS produtividade_repasses(
            os_id INTEGER NOT NULL, tecnico_id INTEGER NOT NULL,
            pago_centavos INTEGER NOT NULL DEFAULT 0 CHECK(pago_centavos>=0),
            enviado_centavos INTEGER NOT NULL DEFAULT 0 CHECK(enviado_centavos>=0),
            enviado_em TEXT, confirmado_em TEXT, confirmado_por INTEGER,
            atualizado_em TEXT NOT NULL,
            PRIMARY KEY(os_id,tecnico_id));
        CREATE TABLE IF NOT EXISTS produtividade_bancos(
            prestador_id INTEGER PRIMARY KEY, dados_texto TEXT NOT NULL,
            atualizado_em TEXT NOT NULL);
        """)
        colunas = {r['name'] for r in c.execute(
            'PRAGMA table_info(produtividade_repasses)')}
        adicoes = (
            ('enviado_centavos',
             'INTEGER NOT NULL DEFAULT 0 CHECK(enviado_centavos>=0)'),
            ('enviado_em', 'TEXT'),
            ('confirmado_em', 'TEXT'),
            ('confirmado_por', 'INTEGER'),
        )
        for nome, definicao in adicoes:
            if nome not in colunas:
                c.execute(
                    f'ALTER TABLE produtividade_repasses ADD COLUMN {nome} {definicao}')
        # Histórico anterior tratava "pago" como confirmação imediata.
        c.execute(
            'UPDATE produtividade_repasses SET enviado_centavos=pago_centavos '
            'WHERE enviado_centavos=0 AND pago_centavos>0')
        c.execute(
            'UPDATE produtividade_repasses SET '
            'enviado_em=COALESCE(enviado_em,atualizado_em), '
            'confirmado_em=COALESCE(confirmado_em,atualizado_em) '
            'WHERE pago_centavos>0')


def _os_ativa_responsavel(c,os_id,pid):
    os_=c.execute('SELECT status,arquivada FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
    if not os_ or os_['status'] not in ext.ATIVAS:
        raise ValueError('OS não está ativa.')
    if 'arquivada' in os_.keys() and os_['arquivada']:
        raise ValueError('OS arquivada: edição bloqueada. O histórico permanece preservado.')
    if ext.responsavel_atual(c,os_id)!=pid:
        tem_admin=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                 "AND name='v9_admin_prestadores'").fetchone())
        admin=(c.execute('SELECT 1 FROM v9_admin_prestadores WHERE prestador_id=?',
                         (pid,)).fetchone() if tem_admin else None)
        if not admin:
            raise PermissionError('Somente o técnico atribuído ou um administrador pode alterar esta OS.')
    return os_


def em_rota(banco,os_id):
    with ext.db(banco) as c:
        r=c.execute('SELECT em_rota,prestador_id,atualizado_em FROM produtividade_deslocamentos WHERE os_id=?',(os_id,)).fetchone()
        return dict(r) if r else {'em_rota':0,'prestador_id':None,'atualizado_em':None}


def marcar_em_rota(banco,os_id,pid,ativo=True,admin=False,authorize=None):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        if authorize is not None:
            authorize(c)
        o=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
        if not o or o['status'] not in ext.ATIVAS:
            raise ValueError('Somente OS ativas podem estar em rota.')
        responsavel=ext.responsavel_atual(c,os_id)
        if responsavel is None:
            raise ValueError('Atribua um técnico antes de marcar Em rota.')
        if not admin and responsavel!=pid:
            raise PermissionError('Somente o responsável ou administrador pode alterar Em rota.')
        novo=1 if ativo else 0
        c.execute("""INSERT INTO produtividade_deslocamentos(os_id,prestador_id,em_rota,atualizado_em)
            VALUES(?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
            prestador_id=excluded.prestador_id,em_rota=excluded.em_rota,
            atualizado_em=excluded.atualizado_em""",(os_id,responsavel,novo,ext.agora()))
        ext.evento(c,os_id,'Em rota' if ativo else 'Saiu de rota',
                   'Deslocamento informado manualmente, sem localização GPS.',pid,'Administrador' if admin else f'Prestador {pid}')
        return novo


def limpar_rota_ao_iniciar(banco,os_id):
    with ext.db(banco) as c:
        c.execute('UPDATE produtividade_deslocamentos SET em_rota=0, atualizado_em=? WHERE os_id=?',
                  (ext.agora(),os_id))


def _payload(d):
    resultado={}
    for campo in CAMPOS:
        valor=d.get(campo, [] if campo.endswith('[]') else '')
        if campo.endswith('[]'):
            if not isinstance(valor,list): valor=[valor]
            if len(valor)>100:raise ValueError('Rascunho com materiais demais.')
            resultado[campo]=[str(v)[:350] for v in valor]
        else:
            resultado[campo]=str(valor)[:20000]
    conteudo=json.dumps(resultado,ensure_ascii=False)
    if len(conteudo.encode('utf-8'))>250000:
        raise ValueError('Rascunho maior que 250 KB. Imagens são anexos separados.')
    return conteudo


def salvar_rascunho(banco,os_id,pid,d,versao_esperada=None):
    conteudo=_payload(d)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        _os_ativa_responsavel(c,os_id,pid)
        atual=c.execute('SELECT versao FROM produtividade_rascunhos WHERE os_id=?',(os_id,)).fetchone()
        if versao_esperada is not None and int(versao_esperada)!=(atual['versao'] if atual else 0):
            raise ValueError('O rascunho foi alterado. Recarregue antes de substituir a versão atual.')
        versao=(atual['versao']+1) if atual else 1
        c.execute("""INSERT INTO produtividade_rascunhos
            (os_id,prestador_id,versao,dados_json,atualizado_em) VALUES(?,?,?,?,?)
            ON CONFLICT(os_id) DO UPDATE SET prestador_id=excluded.prestador_id,
            versao=excluded.versao,dados_json=excluded.dados_json,
            atualizado_em=excluded.atualizado_em""",
            (os_id,pid,versao,conteudo,ext.agora()))
        return versao


def recuperar_rascunho(banco,os_id,pid):
    with ext.db(banco) as c:
        _os_ativa_responsavel(c,os_id,pid)
        r=c.execute('SELECT * FROM produtividade_rascunhos WHERE os_id=?',(os_id,)).fetchone()
        if not r:return None
        return {'versao':r['versao'],'autor_id':r['prestador_id'],
                'atualizado_em':r['atualizado_em'],'dados':json.loads(r['dados_json'])}


def registrar_etapa(banco,os_id,pid,situacao,d):
    if situacao not in ('Pendente','Concluída'):
        raise ValueError('Etapa de atendimento inválida.')
    conteudo=_payload(d)
    digest=sha256(conteudo.encode('utf-8')).hexdigest()
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        if ext.responsavel_atual(c,os_id)!=pid and not ext.administrador(c,pid):
            raise PermissionError('Somente o responsável ou administrador registra etapa.')
        anterior=c.execute("""SELECT id FROM produtividade_etapas
            WHERE os_id=? AND prestador_id=? AND situacao=? AND hash_conteudo=?
            ORDER BY id DESC LIMIT 1""",(os_id,pid,situacao,digest)).fetchone()
        if anterior:return anterior['id']
        return c.execute("""INSERT INTO produtividade_etapas
            (os_id,prestador_id,situacao,dados_json,hash_conteudo,registrado_em)
            VALUES(?,?,?,?,?,?)""",(os_id,pid,situacao,conteudo,digest,ext.agora())).lastrowid


def listar_etapas(banco,os_id):
    with ext.db(banco) as c:
        return [dict(r) for r in c.execute("""SELECT e.*,p.nome tecnico
            FROM produtividade_etapas e LEFT JOIN prestadores p ON p.id=e.prestador_id
            WHERE e.os_id=? ORDER BY e.id""",(os_id,))]


def _email_validado(s):
    email=str(s or '').strip()
    if not email:return ''
    if len(email)>254 or re.fullmatch(r'[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+',email) is None:
        raise ValueError('E-mail de destino inválido.')
    return email.lower()


def contatos_email_os(banco,os_id):
    """Contatos autorizados da OS, sem escolher automaticamente por ninguém."""
    with ext.db(banco) as c:
        cl=c.execute("""SELECT cl.tipo_pessoa,cl.email,cl.sindico_email,cl.administradora_email
            FROM ordens_servico o JOIN clientes cl ON cl.id=o.cliente_id
            WHERE o.id=?""",(os_id,)).fetchone()
    if not cl:raise ValueError('OS não encontrada.')
    return {
        'cliente': cl['email'] or '',
        'sindico': cl['sindico_email'] or '',
        'administradora': cl['administradora_email'] or '',
        'tipo_pessoa': cl['tipo_pessoa'],
    }


def destinatarios_para_os(banco,os_id,selecionados=None,adicionais=''):
    """Monta a lista final a partir das caixas marcadas + e-mails manuais.

    Seleção explícita nunca é sobrescrita pelo síndico. Quando `selecionados`
    é None (desktop legado), usa o comportamento anterior: cliente + síndico.
    """
    import re as _re
    contatos=contatos_email_os(banco,os_id)
    if selecionados is None:
        chaves=['cliente'] if contatos['tipo_pessoa']=='Física' else ['sindico','cliente']
    else:
        if isinstance(selecionados,str):selecionados=[selecionados]
        chaves=[str(x) for x in selecionados]
    resultado=[]
    for chave in chaves:
        e=_email_validado(contatos.get(chave,''))
        if e and e not in resultado:resultado.append(e)
    for valor in _re.split(r'[,;\s]+',str(adicionais or '')):
        e=_email_validado(valor)
        if e and e not in resultado:resultado.append(e)
    if not resultado:
        raise ValueError('Selecione ao menos um destinatário válido para finalizar esta OS.')
    return resultado


def destinatarios_conclusao(banco,os_id,adicional=''):
    """Compatibilidade: cliente + síndico (desktop) + e-mail adicional."""
    return destinatarios_para_os(banco,os_id,None,adicional)


def participou(c,os_id,pid):
    if ext.responsavel_atual(c,os_id)==pid:return True
    if c.execute('SELECT 1 FROM os_prestadores WHERE os_id=? AND prestador_id=?',(os_id,pid)).fetchone():return True
    if c.execute('SELECT 1 FROM os_eventos WHERE os_id=? AND prestador_id=?',(os_id,pid)).fetchone():return True
    return bool(c.execute('SELECT 1 FROM os_conclusoes WHERE os_id=? AND prestador_id=?',(os_id,pid)).fetchone())


def controlar_pdf(banco,os_id,pid):
    with ext.db(banco) as c:
        if not participou(c,os_id,pid):
            raise PermissionError('Este prestador não participou da OS.')


def registrar_envio(banco,os_id,destinatarios,status='pendente',message_id=None,erro=''):
    if status not in ('pendente','enviado','falhou'):raise ValueError('Estado de e-mail inválido.')
    with ext.db(banco) as c:
        c.execute("""INSERT INTO produtividade_email
        (os_id,destinatarios_json,status,message_id,erro,atualizado_em)
        VALUES(?,?,?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
        destinatarios_json=excluded.destinatarios_json,status=excluded.status,
        message_id=excluded.message_id,erro=excluded.erro,
        atualizado_em=excluded.atualizado_em""",
        (os_id,json.dumps(destinatarios),status,message_id,(erro or '')[:500],ext.agora()))


def _centavos(valor):
    """Dinheiro em centavos inteiros, sem ponto flutuante."""
    try:
        entrada=str(valor or '0').strip().replace('R$','').replace(' ','')
        if ',' in entrada:entrada=entrada.replace('.','').replace(',','.')
        montante=Decimal(entrada)
        if not montante.is_finite() or montante<0 or montante>Decimal('10000000'):
            raise ValueError('Valor de rateio fora dos limites.')
        return int((montante*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    except (InvalidOperation,TypeError) as erro:
        raise ValueError('Valor de rateio inválido.') from erro


def registrar_rateios_na_transacao(c,os_id,finalizador_id,valor_bruto,d):
    """Chamar dentro da transação de conclusão; Pendente/Cancelada não têm rateio."""
    os_atual=c.execute('SELECT status FROM ordens_servico WHERE id=?',(os_id,)).fetchone()
    final=c.execute('SELECT prestador_id FROM os_encerramentos WHERE os_id=?',(os_id,)).fetchone()
    if not os_atual or os_atual['status']!='Concluída' or not final or final['prestador_id']!=finalizador_id:
        raise PermissionError('Somente o técnico finalizador pode definir valores ao concluir.')
    tecnicos=d.get('rateio_tecnico[]',[])
    valores=d.get('rateio_valor[]',[])
    if not isinstance(tecnicos,list):tecnicos=[tecnicos]
    if not isinstance(valores,list):valores=[valores]
    if len(tecnicos)>25 or len(tecnicos)!=len(valores):
        raise ValueError('Rateio incompleto ou com técnicos demais.')
    bruto=_centavos(valor_bruto)
    existentes=c.execute('''SELECT tecnico_id,valor_centavos FROM produtividade_rateios
        WHERE os_id=?''',(os_id,)).fetchall()
    if existentes:
        if any(str(x).strip() for x in tecnicos) or any(str(x).strip() for x in valores):
            raise ValueError('Esta OS já possui rateio definido. Ajuste em '
                             'Rateio e colaboradores antes de concluir.')
        # Um responsável transferido pode carregar uma parcela antiga de
        # secundário. O finalizador recebe o restante automaticamente; a soma
        # da parcela antiga com o restante duplicaria o valor.
        propria=next((x for x in existentes
                      if int(x['tecnico_id'])==int(finalizador_id)),None)
        if propria:
            rep=c.execute('''SELECT pago_centavos,enviado_centavos
                             FROM produtividade_repasses
                             WHERE os_id=? AND tecnico_id=?''',
                          (os_id,finalizador_id)).fetchone()
            if rep and (int(rep['pago_centavos'] or 0)>0
                        or int(rep['enviado_centavos'] or 0)>0):
                raise ValueError('O finalizador tem repasse já enviado ou confirmado; '
                                 'ajuste o rateio antes de concluir.')
            c.execute('DELETE FROM produtividade_rateios WHERE os_id=? AND tecnico_id=?',
                      (os_id,finalizador_id))
            c.execute('DELETE FROM produtividade_repasses WHERE os_id=? AND tecnico_id=?',
                      (os_id,finalizador_id))
            ext.evento(c,os_id,'Rateio do finalizador absorvido',
                      f'Parcela de {int(propria["valor_centavos"] or 0)} centavos '
                      'do finalizador foi incorporada ao restante.',
                      finalizador_id,f'Prestador {finalizador_id}')
            existentes=[x for x in existentes
                        if int(x['tecnico_id'])!=int(finalizador_id)]
        total_existente=sum(int(x['valor_centavos'] or 0) for x in existentes)
        if total_existente>bruto:
            raise ValueError('O rateio definido supera o valor total da OS. '
                             'Ajuste antes de concluir.')
        ext.evento(c,os_id,'Rateio preservado',
                  f'Bruto {bruto} centavos; secundários {total_existente} centavos; '
                  f'líquido do finalizador {bruto-total_existente} centavos.',
                  finalizador_id,f'Prestador {finalizador_id}')
        return bruto-total_existente
    parcelas={}
    for tid,valor in zip(tecnicos,valores):
        if not str(tid).strip() and not str(valor).strip():continue
        if not str(tid).isdigit():
            raise ValueError('Selecione o técnico secundário.')
        ident=int(tid)
        if ident==finalizador_id or ident in parcelas:
            raise ValueError('Técnico duplicado ou finalizador indicado como secundário.')
        cents=_centavos(valor)
        if cents<=0:raise ValueError('Informe valor positivo para cada técnico secundário.')
        ativo=c.execute('SELECT 1 FROM prestadores WHERE id=? AND ativo=1',(ident,)).fetchone()
        if not ativo:raise ValueError('Técnico secundário não encontrado ou inativo.')
        parcelas[ident]=cents
    if not parcelas:
        return bruto
    if sum(parcelas.values())>bruto:
        raise ValueError('As parcelas dos técnicos superam o valor cobrado pela OS.')
    for ident,cents in parcelas.items():
        c.execute("""INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo)
            VALUES(?,?,?,1) ON CONFLICT(os_id,prestador_id) DO UPDATE SET ativo=1""",
            (os_id,ident,ext.agora()))
        c.execute("""INSERT INTO produtividade_rateios
            (os_id,tecnico_id,valor_centavos,definidor_id,registrado_em)
            VALUES(?,?,?,?,?)""",(os_id,ident,cents,finalizador_id,ext.agora()))
        c.execute("""INSERT INTO produtividade_repasses(os_id,tecnico_id,pago_centavos,atualizado_em)
            VALUES(?,?,0,?)""",(os_id,ident,ext.agora()))
    ext.evento(c,os_id,'Rateio definido',
              f'Bruto {bruto} centavos; secundários {sum(parcelas.values())} centavos; líquido do finalizador {bruto-sum(parcelas.values())} centavos.',
              finalizador_id,f'Prestador {finalizador_id}')
    return bruto-sum(parcelas.values())


def definir_rateio_manual(banco,os_id,ator_id,tecnico_id,valor):
    """Inclui/edita um rateio depois da conclusão, com auditoria.

    Não altera o valor cobrado do cliente. Bloqueia alteração se o repasse
    já tiver sido enviado ou confirmado.
    """
    cents=_centavos(valor)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        o=c.execute('SELECT numero_os,status,valor_total,arquivada FROM ordens_servico WHERE id=?',
                    (os_id,)).fetchone()
        if not o:
            raise ValueError('OS não encontrada.')
        if 'arquivada' in o.keys() and o['arquivada']:
            raise ValueError('OS arquivada: edição bloqueada.')
        if o['status'] in ('Cancelada', 'Não realizada'):
            raise ValueError('OS cancelada ou não realizada não aceita rateio.')
        tem_admin=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                 "AND name='v9_admin_prestadores'").fetchone())
        admin=bool(c.execute('SELECT 1 FROM v9_admin_prestadores WHERE prestador_id=?',
                             (ator_id,)).fetchone()) if tem_admin else False
        if o['status']=='Concluída':
            final=c.execute('SELECT prestador_id FROM os_encerramentos WHERE os_id=?',
                            (os_id,)).fetchone()
            if not final:
                raise ValueError('OS sem encerramento; não há finalizador definido.')
            finalizador_id=int(final['prestador_id'])
        else:
            responsavel=ext.responsavel_atual(c,os_id)
            finalizador_id=int(responsavel) if responsavel is not None else None
        if finalizador_id is None and not admin:
            raise PermissionError('Defina o responsável pela OS ou peça a um administrador '
                                  'para ajustar o rateio.')
        if finalizador_id is not None and finalizador_id!=int(ator_id) and not admin:
            raise PermissionError('Somente o responsável/finalizador ou um administrador '
                                  'pode ajustar o rateio.')
        if not admin and int(tecnico_id)==int(ator_id):
            raise ValueError('Você não pode definir parcela para si mesmo.')
        if finalizador_id is not None and int(tecnico_id)==finalizador_id:
            raise ValueError('O responsável/finalizador recebe o restante automaticamente '
                             'e não pode ter uma parcela separada.')
        alvo=c.execute('SELECT nome FROM prestadores WHERE id=? AND ativo=1',
                       (int(tecnico_id),)).fetchone()
        if not alvo:
            raise ValueError('Técnico secundário não encontrado ou inativo.')
        atual=c.execute('SELECT valor_centavos FROM produtividade_rateios WHERE os_id=? AND tecnico_id=?',
                        (os_id,int(tecnico_id))).fetchone()
        rep=c.execute('''SELECT pago_centavos,enviado_centavos FROM produtividade_repasses
                         WHERE os_id=? AND tecnico_id=?''',(os_id,int(tecnico_id))).fetchone()
        if rep and (int(rep['pago_centavos'])>0 or int(rep['enviado_centavos'])>0):
            raise ValueError('Não é possível alterar um repasse já enviado ou confirmado.')
        outros=c.execute('''SELECT COALESCE(SUM(valor_centavos),0) FROM produtividade_rateios
                            WHERE os_id=? AND tecnico_id!=?''',(os_id,int(tecnico_id))).fetchone()[0]
        total=_centavos(o['valor_total'])
        if int(outros)+cents>total:
            raise ValueError('O rateio ultrapassa o valor total da OS.')
        antes=int(atual['valor_centavos']) if atual else 0
        if cents==0:
            c.execute('DELETE FROM produtividade_rateios WHERE os_id=? AND tecnico_id=?',
                      (os_id,int(tecnico_id)))
            c.execute('DELETE FROM produtividade_repasses WHERE os_id=? AND tecnico_id=?',
                      (os_id,int(tecnico_id)))
            acao='Rateio removido manualmente'
        else:
            c.execute('''INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo)
                         VALUES(?,?,?,1) ON CONFLICT(os_id,prestador_id) DO UPDATE SET ativo=1''',
                      (os_id,int(tecnico_id),ext.agora()))
            c.execute('''INSERT INTO produtividade_rateios
                         (os_id,tecnico_id,valor_centavos,definidor_id,registrado_em)
                         VALUES(?,?,?,?,?) ON CONFLICT(os_id,tecnico_id) DO UPDATE SET
                         valor_centavos=excluded.valor_centavos,definidor_id=excluded.definidor_id,
                         registrado_em=excluded.registrado_em''',
                      (os_id,int(tecnico_id),cents,int(ator_id),ext.agora()))
            c.execute('''INSERT INTO produtividade_repasses(os_id,tecnico_id,pago_centavos,atualizado_em)
                         VALUES(?,?,0,?) ON CONFLICT(os_id,tecnico_id) DO UPDATE SET
                         atualizado_em=excluded.atualizado_em''',
                      (os_id,int(tecnico_id),ext.agora()))
            acao=('Rateio definido' if o['status'] in ext.ATIVAS
                  else 'Rateio ajustado manualmente')
        ext.evento(c,os_id,acao,
                   f'{o["numero_os"]} · {alvo["nome"]}: {antes} → {cents} centavos. '
                   f'Total da OS mantido em {total} centavos.',
                   int(ator_id),f'Prestador {ator_id}')
        return cents


def financeiro_pessoal(banco,pid):
    """Detalha obrigações internas sem somar repasses ao faturamento bruto."""
    with ext.db(banco) as c:
        proprio=[dict(r) for r in c.execute("""SELECT f.id financeiro_id,f.os_id,o.numero_os,
            f.valor,f.forma_pagamento,f.vencimento,f.data_pagamento,
            cl.nome cliente,
            COALESCE((SELECT SUM(r.valor_centavos) FROM produtividade_rateios r
                      WHERE r.os_id=f.os_id
                        AND r.tecnico_id!=e.prestador_id),0) partes_centavos,f.status
            FROM financeiro f
            JOIN ordens_servico o ON o.id=f.os_id
            JOIN clientes cl ON cl.id=o.cliente_id
            JOIN os_encerramentos e ON e.os_id=f.os_id
            WHERE e.prestador_id=? AND COALESCE(o.arquivada,0)=0
              AND f.status!='Cancelado' ORDER BY f.id DESC""",(pid,))]
        meus=[dict(r) for r in c.execute("""SELECT r.os_id,o.numero_os,cl.nome cliente,
            r.valor_centavos,
            COALESCE(p.pago_centavos,0) pago_centavos,
            COALESCE(p.enviado_centavos,0) enviado_centavos,
            p.enviado_em,p.confirmado_em,e.prestador_id de_tecnico,
            (SELECT f.status FROM financeiro f WHERE f.os_id=r.os_id
             ORDER BY f.id DESC LIMIT 1) financeiro_status
            FROM produtividade_rateios r
            JOIN ordens_servico o ON o.id=r.os_id
            JOIN clientes cl ON cl.id=o.cliente_id
            JOIN os_encerramentos e ON e.os_id=r.os_id
            LEFT JOIN produtividade_repasses p ON p.os_id=r.os_id AND p.tecnico_id=r.tecnico_id
            WHERE r.tecnico_id=? AND r.tecnico_id!=e.prestador_id
              AND COALESCE(o.arquivada,0)=0 ORDER BY r.os_id DESC""",(pid,))]
        repassar=[dict(r) for r in c.execute("""SELECT r.os_id,o.numero_os,cl.nome cliente,
            r.tecnico_id,t.nome tecnico,r.valor_centavos,
            COALESCE(p.pago_centavos,0) pago_centavos,
            COALESCE(p.enviado_centavos,0) enviado_centavos,
            p.enviado_em,p.confirmado_em
            FROM produtividade_rateios r
            JOIN ordens_servico o ON o.id=r.os_id
            JOIN clientes cl ON cl.id=o.cliente_id
            JOIN prestadores t ON t.id=r.tecnico_id
            JOIN os_encerramentos e ON e.os_id=r.os_id
            LEFT JOIN produtividade_repasses p ON p.os_id=r.os_id AND p.tecnico_id=r.tecnico_id
            WHERE e.prestador_id=? AND COALESCE(o.arquivada,0)=0
              AND EXISTS (SELECT 1 FROM financeiro f WHERE f.os_id=r.os_id
                          AND f.status='Recebido')
            ORDER BY r.os_id DESC""",(pid,))]
        return {'brutos_proprios':proprio,'receber_de_colegas':meus,'repassar_a_colegas':repassar}


def confirmar_repasse(banco,os_id,finalizador_id,secundario_id,valor=None):
    """Registra que o finalizador enviou o repasse; o recebedor ainda confirma.

    ``valor=None`` means the full amount not yet sent. The portal uses that so
    the finalizer cannot change the rateio amount. Explicit values remain for
    compatibility with internal tools and characterization tests.
    """
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        e=c.execute('SELECT prestador_id FROM os_encerramentos WHERE os_id=?',(os_id,)).fetchone()
        if not e or e['prestador_id']!=finalizador_id:
            raise PermissionError('Somente o finalizador registra o repasse que realizou.')
        fin=c.execute('SELECT status FROM financeiro WHERE os_id=? ORDER BY id DESC LIMIT 1',
                      (os_id,)).fetchone()
        if not fin or fin['status']!='Recebido':
            raise ValueError('Confirme o recebimento do cliente antes de registrar o envio do repasse.')
        item=c.execute('SELECT valor_centavos FROM produtividade_rateios WHERE os_id=? AND tecnico_id=?',
                       (os_id,secundario_id)).fetchone()
        if not item:raise ValueError('Parcela deste técnico não existe.')
        atual=c.execute('''SELECT pago_centavos,enviado_centavos FROM produtividade_repasses
                           WHERE os_id=? AND tecnico_id=?''',(os_id,secundario_id)).fetchone()
        pago=atual['pago_centavos'] if atual else 0
        enviado=atual['enviado_centavos'] if atual else 0
        a_enviar=item['valor_centavos']-pago-enviado
        if a_enviar<=0:raise ValueError('Parcela já enviada ou confirmada.')
        cents=a_enviar if valor is None or str(valor).strip()=='' else _centavos(valor)
        if cents<=0:raise ValueError('Valor de repasse deve ser positivo.')
        if cents>a_enviar:raise ValueError('Repasse excede o valor ainda não enviado.')
        agora=ext.agora()
        c.execute("""INSERT INTO produtividade_repasses
          (os_id,tecnico_id,pago_centavos,enviado_centavos,enviado_em,atualizado_em)
          VALUES(?,?,?,?,?,?)
          ON CONFLICT(os_id,tecnico_id) DO UPDATE SET
          enviado_centavos=excluded.enviado_centavos,
          enviado_em=excluded.enviado_em,atualizado_em=excluded.atualizado_em""",
          (os_id,secundario_id,pago,enviado+cents,agora,agora))
        ext.evento(c,os_id,'Repasse enviado',
                   f'{cents} centavos enviados ao técnico {secundario_id}; '
                   'aguardando confirmação de recebimento.',
                   finalizador_id,f'Prestador {finalizador_id}')
        return a_enviar-cents


def confirmar_recebimento_repasse(banco,os_id,secundario_id,valor=None):
    """The secondary technician confirms that the repasse actually arrived."""
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        item=c.execute('SELECT valor_centavos FROM produtividade_rateios '
                       'WHERE os_id=? AND tecnico_id=?',(os_id,secundario_id)).fetchone()
        if not item:raise ValueError('Parcela deste técnico não existe.')
        atual=c.execute('''SELECT pago_centavos,enviado_centavos FROM produtividade_repasses
                           WHERE os_id=? AND tecnico_id=?''',(os_id,secundario_id)).fetchone()
        if not atual:raise ValueError('Nenhum repasse enviado para confirmação.')
        pago=atual['pago_centavos']
        pendente=atual['enviado_centavos']-pago
        if pendente<=0:raise ValueError('Nenhum repasse aguardando confirmação.')
        cents=pendente if valor is None or str(valor).strip()=='' else _centavos(valor)
        if cents<=0:raise ValueError('Valor de confirmação deve ser positivo.')
        if cents>pendente:raise ValueError('Confirmação excede o valor enviado.')
        agora=ext.agora()
        c.execute('''UPDATE produtividade_repasses SET pago_centavos=?,confirmado_em=?,
                     confirmado_por=?,atualizado_em=? WHERE os_id=? AND tecnico_id=?''',
                  (pago+cents,agora,secundario_id,agora,os_id,secundario_id))
        ext.evento(c,os_id,'Repasse recebido',
                   f'{cents} centavos confirmados pelo técnico {secundario_id}.',
                   secundario_id,f'Prestador {secundario_id}')
        return pendente-cents


def salvar_dados_bancarios(banco,pid,texto):
    """Grava o mesmo campo usado pelo app GTK e pelos e-mails de cobrança."""
    conteudo=str(texto or '').strip()
    with ext.db(banco) as c:
        if not c.execute('SELECT 1 FROM prestadores WHERE id=? AND ativo=1',(pid,)).fetchone():
            raise PermissionError('Prestador inexistente.')
    config=ext.obter_config_prestador(banco,pid)
    config['dados_bancarios_texto']=conteudo
    ext.salvar_config_prestador(banco,pid,config)


def obter_dados_bancarios(banco,pid):
    """Lê o campo oficial compartilhado, migrando o texto antigo do portal."""
    return str(ext.obter_config_prestador(banco,pid).get('dados_bancarios_texto') or '')
