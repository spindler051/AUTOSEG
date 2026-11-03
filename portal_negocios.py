"""Regras transacionais das telas web AUTOSEG (usa o banco SQLite do desktop).

Não altera a definição das tabelas originais. Cada operação sensível gera auditoria.
"""
import re
import sqlite3
from decimal import Decimal, InvalidOperation
from datetime import datetime
import prestadores_ext as ext
import fluxo_os as fluxo
import atendimento_os as aten
import estoque_materiais as estoque
import cadastros_v9 as cad
import composicao

CLIENTE_CAMPOS = (
    'tipo_pessoa documento nome nome_fantasia endereco numero complemento bairro cep '
    'cidade uf telefone email sindico_nome sindico_telefone sindico_email '
    'administradora administradora_email administradora_telefone observacoes status'
).split()
OS_FORMAS = ('PIX','Transferência','Dinheiro','Cartão','Boleto','Outro')


def dinheiro(value):
    v = Decimal(str(value or 0)).quantize(Decimal('.01'))
    return 'R$ '+f'{v:,.2f}'.replace(',','@').replace('.',',').replace('@','.')


def numero(value, nome='Valor'):
    t=str(value if value is not None else '').strip().replace('R$','').replace(' ','')
    if ',' in t: t=t.replace('.','').replace(',','.')
    try: d=Decimal(t or '0').quantize(Decimal('0.01'))
    except (ValueError, InvalidOperation): raise ValueError(f'{nome} inválido.')
    if not d.is_finite() or d<0 or d>100000000: raise ValueError(f'{nome} fora dos limites.')
    return float(d)


def texto(d,chave,maximo=5000):
    s=str(d.get(chave,'') or '').strip()
    if len(s)>maximo: raise ValueError(f'Campo {chave} excedeu o limite de {maximo} caracteres.')
    return s


def lista_materiais(d):
    itens=d.get('material_item[]',[])
    quantidades=d.get('material_qtd[]',[])
    unitarios=d.get('material_unit[]',[])
    if isinstance(itens,str): itens=[itens]
    if isinstance(quantidades,str): quantidades=[quantidades]
    if isinstance(unitarios,str): unitarios=[unitarios]
    if len(itens)>100: raise ValueError('Limite de 100 materiais por OS.')
    result=[]
    for i, raw in enumerate(itens):
        nome=str(raw).strip()
        if not nome: continue
        if len(nome)>180: raise ValueError('Nome do material muito longo.')
        qtd=numero(quantidades[i] if i<len(quantidades) else '0','Quantidade')
        unit=numero(unitarios[i] if i<len(unitarios) else '0','Valor unitário')
        if qtd<=0: raise ValueError(f'Quantidade do material {nome} precisa ser positiva.')
        result.append({'item':nome,'quantidade':qtd,'valor_unitario':unit,'valor_total':round(qtd*unit,2)})
    return result


def criar_auditoria(c):
    c.execute('''CREATE TABLE IF NOT EXISTS portal_auditoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT, prestador_id INTEGER NOT NULL,
        acao TEXT NOT NULL, referencia TEXT NOT NULL, detalhes TEXT NOT NULL,
        criado_em TEXT NOT NULL)''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_portal_auditoria_data ON portal_auditoria(criado_em)')


def audit(c,pid,acao,referencia,detalhes):
    criar_auditoria(c)
    c.execute('INSERT INTO portal_auditoria(prestador_id,acao,referencia,detalhes,criado_em) VALUES(?,?,?,?,?)',
        (pid,acao,str(referencia),str(detalhes)[:4000],ext.agora()))


def cliente_salvar(banco,d,pid,cliente_id=None):
    values={x:texto(d,x,2500 if x=='observacoes' else 250) for x in CLIENTE_CAMPOS}
    if not values['nome']: raise ValueError('Nome do cliente é obrigatório.')
    if values['status'] not in ('Ativo','Inativo','Prospect'): raise ValueError('Situação do cliente inválida.')
    if values['tipo_pessoa'] not in ('Física','Jurídica'): raise ValueError('Tipo de pessoa inválido.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        anterior=None
        if cliente_id is not None:
            anterior=c.execute('SELECT * FROM clientes WHERE id=?',(cliente_id,)).fetchone()
            if not anterior: raise ValueError('Cliente não encontrado.')
        doc_novo=cad.digitos(values['documento'])
        mudou_documento=(cliente_id is None or anterior['tipo_pessoa']!=values['tipo_pessoa']
                         or cad.digitos(anterior['documento'])!=doc_novo)
        if mudou_documento:
            values['documento']=cad.validar_documento(values['tipo_pessoa'],doc_novo)
            duplicado=cad.buscar_documento_duplicado(c,values['documento'],cliente_id)
            if duplicado:
                raise ValueError(f"CPF/CNPJ já cadastrado para {duplicado['nome']}.")
        else:
            values['documento']=doc_novo
        if cliente_id is None:
            cols=','.join(CLIENTE_CAMPOS)
            p=','.join('?' for _ in CLIENTE_CAMPOS)
            x=c.execute(f'INSERT INTO clientes({cols},criado_em) VALUES({p},?)',
                  [values[k] for k in CLIENTE_CAMPOS]+[ext.agora()])
            cid=x.lastrowid
            audit(c,pid,'Cliente criado',cid,values['nome'])
        else:
            updates={k:f'{anterior[k]} → {values[k]}' for k in CLIENTE_CAMPOS if str(anterior[k] or '')!=values[k]}
            if updates:
                c.execute('UPDATE clientes SET '+','.join(f'{k}=?' for k in CLIENTE_CAMPOS)+' WHERE id=?',
                          [values[k] for k in CLIENTE_CAMPOS]+[cliente_id])
                audit(c,pid,'Cliente alterado',cliente_id,str(updates))
            cid=cliente_id
        if values['tipo_pessoa']=='Jurídica' and values['status']!='Inativo':
            cad.sincronizar_cliente_pj(c,cid)
    return cid


def cliente_excluir(banco,cid,pid):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT nome FROM clientes WHERE id=?',(cid,)).fetchone()
        if not row: raise ValueError('Cliente inexistente.')
        if c.execute('SELECT 1 FROM ordens_servico WHERE cliente_id=?',(cid,)).fetchone():
            raise ValueError('Cliente possui OS vinculada. Marque-o como Inativo.')
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v9_usuarios'").fetchone():
            if c.execute('SELECT 1 FROM v9_usuarios WHERE cliente_pf_id=?',(cid,)).fetchone():
                raise ValueError('Cliente possui conta no portal. Desative o cadastro.')
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='v9_organizacoes'").fetchone():
            orgs=c.execute('SELECT id FROM v9_organizacoes WHERE cliente_id=?',(cid,)).fetchall()
            for org in orgs:
                if (c.execute('SELECT 1 FROM v9_chamados WHERE organizacao_id=?',(org['id'],)).fetchone()
                    or c.execute('SELECT 1 FROM v9_vinculos WHERE organizacao_id=?',(org['id'],)).fetchone()):
                    raise ValueError('Condomínio possui chamados ou vínculos. Desative em vez de excluir.')
            for org in orgs:
                c.execute('DELETE FROM v9_organizacoes WHERE id=?',(org['id'],))
        audit(c,pid,'Cliente excluído',cid,row['nome'])
        c.execute('DELETE FROM clientes WHERE id=?',(cid,))


def os_salvar(banco,d,pid,oid=None):
    """Insere/edita uma OS, materiais, relatório e estado numa transação SQLite."""
    try: cliente_id=int(d['cliente_id'])
    except (KeyError,ValueError,TypeError): raise ValueError('Selecione o cliente.')
    descricao=texto(d,'descricao')
    if not descricao: raise ValueError('Preencha a descrição do serviço.')
    tecnico=texto(d,'tecnico',250)  # Pessoa atendida no local; coluna legada mantida.
    forma=texto(d,'forma_pagamento',60)
    if forma not in OS_FORMAS: raise ValueError('Forma de pagamento inválida.')
    observacoes=texto(d,'observacoes')
    relato=texto(d,'relatorio_tecnico',5000)
    acao=texto(d,'acao_status',30)
    if acao not in ('salvar','Pendente','Concluída','Cancelada'):
        raise ValueError('Operação inválida.')
    if acao!='salvar' and not relato:
        raise ValueError('Informe o relatório técnico para registrar a situação.')
    motivo=texto(d,'motivo_encerramento',2000)
    if acao in ('Cancelada','Não realizada') and not motivo:
        raise ValueError('O motivo é obrigatório para cancelar ou indicar não realização.')
    imagens=[x for x in d.get('imagens_encerramento[]',[]) if isinstance(x,tuple) and x[0]]
    imagem=d.get('imagem_encerramento')
    if imagem and isinstance(imagem,tuple) and imagem[0]:imagens.append(imagem)
    if len(imagens)>10:raise ValueError('O limite é de 10 imagens por envio.')
    chaves=list(d.get('foto_chave[]',[]) or [])
    legendas_fotos=list(d.get('foto_legenda[]',[]) or [])
    visiveis_fotos=list(d.get('foto_visivel[]',[]) or [])
    anexo_ids=list(d.get('anexo_id[]',[]) or [])
    anexo_legendas=list(d.get('anexo_legenda[]',[]) or [])
    anexo_visiveis=list(d.get('anexo_visivel[]',[]) or [])
    if isinstance(chaves,str):chaves=[chaves]
    if isinstance(legendas_fotos,str):legendas_fotos=[legendas_fotos]
    if isinstance(visiveis_fotos,str):visiveis_fotos=[visiveis_fotos]
    if isinstance(anexo_ids,str):anexo_ids=[anexo_ids]
    if isinstance(anexo_legendas,str):anexo_legendas=[anexo_legendas]
    if isinstance(anexo_visiveis,str):anexo_visiveis=[anexo_visiveis]
    for item in imagens:
        if len(item[1])>8*1024*1024:raise ValueError('Cada imagem deve ter no máximo 8 MB.')
        ext.validar_imagem(item[1])
    materiais=lista_materiais(d)
    mao_obra=numero(d.get('valor_mao_obra','0'),'Valor da mão de obra')
    total_mat=round(sum(m['valor_total'] for m in materiais),2) if materiais else numero(
        d.get('valor_materiais_manual','0'),'Valor de materiais')
    soma=round(mao_obra+total_mat,2)
    override=texto(d,'valor_total_override',30)
    total=numero(override,'Total negociado') if override else soma
    try:
        tempo_horas=float(str(d.get('tempo_horas','0') or '0').replace(',','.'))
    except ValueError:
        raise ValueError('Tempo de execução inválido.') from None
    if tempo_horas<0:raise ValueError('Tempo de execução não pode ser negativo.')
    comp=composicao.calcular(
        total_centavos=int(round(total*100)),materiais_centavos=int(round(total_mat*100)),
        horas=tempo_horas, mao_obra_centavos=int(round(mao_obra*100)))
    comp_json=composicao.para_json(comp)
    composicao.instalar_banco(banco)
    # Valor total é calculado do serviço + materiais; não aceita divergência silenciosa.
    aten.instalar(banco)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        if not c.execute('SELECT 1 FROM clientes WHERE id=?',(cliente_id,)).fetchone():
            raise ValueError('Cliente não encontrado.')
        if oid is None:
            # A função central do banco original é a mesma utilizada no aplicativo desktop.
            from banco import proximo_numero_os
            n=proximo_numero_os(c.cursor())
            cur=c.execute('''INSERT INTO ordens_servico
                (numero_os,cliente_id,data_abertura,tecnico,descricao,valor_mao_obra,
                 valor_materiais,valor_total,forma_pagamento,status,observacoes,
                 tempo_horas,composicao_json,criado_em)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
               (n,cliente_id,datetime.now().strftime('%d/%m/%Y %H:%M'),tecnico,descricao,
                mao_obra,total_mat,total,forma,'Aberta',observacoes,
                tempo_horas,comp_json,ext.agora()))
            oid=cur.lastrowid
            aten.registrar_solicitacao(c,oid,cliente_id,descricao,observacoes,'Prestador')
            ext.evento(c,oid,'OS criada via portal','Cadastro pelo portal web.',pid,'Prestador')
            audit(c,pid,'OS criada',oid,f'{n} / cliente {cliente_id}')
        else:
            old=c.execute('SELECT * FROM ordens_servico WHERE id=?',(oid,)).fetchone()
            if not old: raise ValueError('OS não existe.')
            versao=d.get('_versao_os')
            if versao is not None and str(versao)!=(old['atualizado_em'] or ''):
                raise ValueError('Esta OS foi atualizada por outra pessoa. Reabra a tela antes de salvar para evitar perda de dados.')
            if old['status'] not in ext.ATIVAS:
                raise ValueError('OS encerrada. Para corrigir um documento já publicado, utilize o desktop e publique nova versão.')
            original=c.execute('SELECT cliente_id,descricao_original,observacoes_originais FROM os_solicitacoes WHERE os_id=?',(oid,)).fetchone()
            if original:
                cliente_id=original['cliente_id']
                descricao=original['descricao_original']
                if old['origem']=='Portal':
                    observacoes=old['observacoes'] or original['observacoes_originais']
            atual=ext.responsavel_atual(c,oid)
            if atual not in (None,pid):
                raise PermissionError('Assuma a OS antes de salvar rascunho, fotos ou alterar a situação.')
            if acao in ('Pendente','Concluída','Cancelada','Não realizada') and atual not in (None,pid):
                raise PermissionError('Para mudar o status, assuma uma OS pendente ou solicite transferência de responsabilidade.')
            old_dict=dict(old)
            updated={'cliente_id':cliente_id,'tecnico':tecnico,'descricao':descricao,
                'valor_mao_obra':mao_obra,'valor_materiais':total_mat,'valor_total':total,
                'forma_pagamento':forma,'observacoes':observacoes,'tempo_horas':tempo_horas}
            diffs=[f'{k}: {old_dict.get(k)!r} → {v!r}' for k,v in updated.items() if str(old_dict.get(k) or '')!=str(v)]
            c.execute('''UPDATE ordens_servico SET cliente_id=?,tecnico=?,descricao=?,valor_mao_obra=?,
                valor_materiais=?,valor_total=?,forma_pagamento=?,observacoes=?,
                tempo_horas=?,composicao_json=?,atualizado_em=? WHERE id=?''',
                (cliente_id,tecnico,descricao,mao_obra,total_mat,total,forma,observacoes,
                 tempo_horas,comp_json,ext.agora(),oid))
            if diffs: ext.evento(c,oid,'OS editada via portal','; '.join(diffs)[:4000],pid,'Prestador')
            if diffs: audit(c,pid,'OS alterada',oid,'; '.join(diffs))
        old_mat=[(r['item'],float(r['quantidade']),float(r['valor_unitario'])) for r in
                 c.execute('SELECT item,quantidade,valor_unitario FROM materiais_os WHERE os_id=? ORDER BY id',(oid,))]
        if oid is not None and 'material_item[]' not in d and old_mat and not d.get('materiais_presentes'):
            materiais=[dict(item=r[0],quantidade=r[1],valor_unitario=r[2],valor_total=round(r[1]*r[2],2)) for r in old_mat]
            new_mat=list(old_mat)
        else:
            new_mat=[(m['item'],m['quantidade'],m['valor_unitario']) for m in materiais]
        if old_mat!=new_mat:
            c.execute('DELETE FROM materiais_os WHERE os_id=?',(oid,))
            for m in materiais:
                c.execute('INSERT INTO materiais_os(os_id,item,quantidade,valor_unitario,valor_total) VALUES(?,?,?,?,?)',
                    (oid,m['item'],m['quantidade'],m['valor_unitario'],m['valor_total']))
            ext.evento(c,oid,'Materiais alterados','Antes: '+repr(old_mat)[:1200]+'; depois: '+repr(new_mat)[:1200],pid,'Prestador')
        if acao=='salvar':
            aten.salvar_rascunho(c,oid,relato,f'Prestador ID {pid}')
        elif relato:
            aten.salvar_rascunho(c,oid,relato,f'Prestador ID {pid}')
            ext.evento(c,oid,'Relatório técnico',relato,pid,'Prestador')
        if acao=='Pendente':
            if c.execute("UPDATE ordens_servico SET status='Pendente' WHERE id=? AND status IN ('Aberta','Pendente')",(oid,)).rowcount!=1:
                raise ValueError('OS não está ativa.')
            ext.evento(c,oid,'Pendência','Atendimento pendente conforme relatório técnico.',pid,'Prestador')
        # Fotos e legendas valem tanto para rascunho quanto para encerramento.
        for indice,item in enumerate(imagens):
            chave=chaves[indice] if indice<len(chaves) else None
            legenda=legendas_fotos[indice] if indice<len(legendas_fotos) else ''
            visivel=str(visiveis_fotos[indice])!='0' if indice<len(visiveis_fotos) else True
            ext.registrar_imagem_transacao(c,oid,pid,item[0],item[1],permitir_colaboracao=True,
                                           chave=chave,legenda=legenda,visivel=visivel)
        for indice,anexo_id in enumerate(anexo_ids):
            try:anexo_id=int(anexo_id)
            except (TypeError,ValueError):continue
            legenda=anexo_legendas[indice] if indice<len(anexo_legendas) else ''
            visivel=str(anexo_visiveis[indice])!='0' if indice<len(anexo_visiveis) else True
            ext.definir_legenda_anexo_c(c,oid,anexo_id,legenda,visivel)
        if acao in fluxo.FIM:
            fluxo.aplicar_encerramento(c,oid,acao,relato,motivo,
                 prestador_id=pid,ator=f'Prestador ID {pid}')
            if acao=='Concluída':
                # Rateio validado e persistido na MESMA transação do encerramento.
                # Se a distribuição for inválida, toda conclusão é revertida.
                import produtividade_os as prod
                prod.registrar_rateios_na_transacao(c,oid,pid,total,d)
            audit(c,pid,'OS encerrada',oid,acao+(' | Motivo: '+motivo if motivo else ''))
        # Estoque: lançamento/estorno transacional e idempotente, sem expor administração na web.
        estoque.reconciliar_os_conexao(c,oid,f'Prestador #{pid}')
        # Mantém financeiro Aguardando sincronizado após edição de OS já concluída.
        if acao=='salvar':
            f=c.execute('SELECT id,status FROM financeiro WHERE os_id=? ORDER BY id LIMIT 1',(oid,)).fetchone()
            if f and f['status']=='Aguardando pagamento':
                c.execute('UPDATE financeiro SET valor=?,forma_pagamento=?,cliente_id=? WHERE id=?',(total,forma,cliente_id,f['id']))
    return oid


def financeiro_receber(banco,fid,pid):
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        f=c.execute('SELECT os_id,status,valor FROM financeiro WHERE id=?',(fid,)).fetchone()
        if not f: raise ValueError('Lançamento não encontrado.')
        if f['status']=='Recebido': raise ValueError('Este lançamento já está recebido.')
        c.execute("UPDATE financeiro SET status='Recebido',data_pagamento=? WHERE id=?",
            (datetime.now().strftime('%d/%m/%Y'),fid))
        ext.evento(c,f['os_id'],'Pagamento recebido',f'Recebimento confirmado no portal: {dinheiro(f["valor"])}',pid,'Prestador')
        audit(c,pid,'Recebimento confirmado',fid,dinheiro(f['valor']))
