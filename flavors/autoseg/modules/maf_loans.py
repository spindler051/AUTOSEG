"""Ponte de empréstimos entre o AUTOSEG e o Meu Auto Financeiro.

O banco do MAF é a fonte única dos empréstimos. Este módulo lê e grava somente
as tabelas de empréstimos, devoluções, alterações e eventos. Nenhum valor entra
no financeiro da empresa.
"""
from __future__ import annotations

import hashlib
import html
import os
import secrets
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

MAF_DB = Path(os.environ.get('AUTOSEG_MAF_DB')
              or Path.home() / 'AUTOSEG_MAF' / 'meu_auto_financeiro.db')
MAF_DOCS = MAF_DB.parent / 'meu_auto_financeiro_comprovantes'
MAX_PROOF = 4 * 1024 * 1024


def _now():
    return datetime.now().isoformat(timespec='seconds')


def _conn():
    con = sqlite3.connect(str(MAF_DB), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=8000')
    return con


def _esc(value):
    return html.escape(str(value or ''), quote=True)


def _reais(centavos):
    return 'R$ ' + f'{int(centavos or 0) / 100:,.2f}'.replace(',', '@').replace('.', ',').replace('@', '.')


def _hash(codigo):
    return hashlib.sha256(str(codigo or '').encode()).hexdigest()


def _evento(c, emprestimo_id, usuario, acao, detalhe):
    c.execute('''INSERT INTO emprestimo_eventos
        (emprestimo_id,usuario_id,email,acao,detalhe,criado_em)
        VALUES(?,?,?,?,?,?)''',
        (emprestimo_id, usuario['id'] if usuario else None,
         str((usuario or {}).get('email') or ''), acao, detalhe, _now()))


def _saldo(c, e):
    pago = c.execute('''SELECT COALESCE(SUM(valor_centavos),0) FROM devolucoes
        WHERE emprestimo_id=? AND confirmado_em IS NOT NULL''', (e['id'],)).fetchone()[0]
    return int(e['valor_centavos'] or 0) - int(pago or 0)


def _usuario_por_pid(c, pid):
    return c.execute('SELECT * FROM usuarios WHERE autoseg_pid=?', (pid,)).fetchone()


def _usuario_por_email(c, email):
    return c.execute('SELECT * FROM usuarios WHERE email=? COLLATE NOCASE',
                     (str(email or '').strip().lower(),)).fetchone()


def _usuario_ou_sombra(c, email):
    email = str(email or '').strip().lower()
    row = _usuario_por_email(c, email)
    if row:
        return row
    cur = c.execute('''INSERT INTO usuarios(nome,email,senha_hash,familia_id,criado_em)
        VALUES(?,?,NULL,NULL,?)''', (email, email, _now()))
    return c.execute('SELECT * FROM usuarios WHERE id=?', (cur.lastrowid,)).fetchone()


def _usuario_para_emprestimo(c, pid, email, criar=False):
    row = _usuario_por_pid(c, pid) or _usuario_por_email(c, email)
    if row:
        if criar and row['autoseg_pid'] is None:
            outro = c.execute('SELECT id FROM usuarios WHERE autoseg_pid=? AND id<>?',
                              (pid, row['id'])).fetchone()
            if not outro:
                c.execute('UPDATE usuarios SET autoseg_pid=? WHERE id=?', (pid, row['id']))
                row = c.execute('SELECT * FROM usuarios WHERE id=?', (row['id'],)).fetchone()
        return row
    if not criar:
        return None
    return _usuario_ou_sombra(c, email)


def _enviar(destinatario, assunto, corpo):
    try:
        from flavors.autoseg.modules import gmail_service
        gmail_service.enviar_email_gmail(destinatario, assunto, corpo)
        return True
    except Exception:
        return False


def _enviar_async(destinatario, assunto, corpo):
    threading.Thread(target=_enviar, args=(destinatario, assunto, corpo),
                     daemon=True, name='AUTOSEG-MAF-Email').start()


def link_status(pid, email, banco=None):
    if not MAF_DB.is_file():
        return {'ok': False, 'motivo': 'Banco do MAF não encontrado.'}
    with _conn() as c:
        row = _usuario_por_pid(c, pid)
        if row:
            return {'ok': True, 'linked': True, 'usuario': dict(row)}
        row = _usuario_por_email(c, email)
        if row:
            return {'ok': True, 'linked': row['autoseg_pid'] is not None,
                    'usuario': dict(row)}
        return {'ok': True, 'linked': False, 'usuario': None}


def request_link_code(pid, email):
    email = str(email or '').strip().lower()
    if not MAF_DB.is_file():
        raise ValueError('Banco do MAF não encontrado.')
    if not email or '@' not in email:
        raise ValueError('O prestador não tem e-mail válido.')
    codigo = f'{secrets.randbelow(1000000):06d}'
    with _conn() as c:
        c.execute('BEGIN IMMEDIATE')
        user = _usuario_por_pid(c, pid)
        if not user:
            user = _usuario_ou_sombra(c, email)
        if user['autoseg_pid'] not in (None, pid):
            raise ValueError('Este usuário MAF já está vinculado a outro prestador.')
        c.execute('''DELETE FROM usuario_codigos
            WHERE usuario_id=? AND tipo='autoseg_link' AND usado_em IS NULL''',
            (user['id'],))
        c.execute('''INSERT INTO usuario_codigos
            (usuario_id,tipo,codigo_hash,novo_email,expira_em,criado_em)
            VALUES(?,?,?,?,?,?)''',
            (user['id'], 'autoseg_link', _hash(codigo), email,
             (datetime.now() + timedelta(minutes=15)).isoformat(timespec='seconds'),
             _now()))
    if not _enviar(email, 'AUTOSEG — confirmar vínculo com o Meu Auto Financeiro',
                   f'<p>Use o código <b>{codigo}</b> para confirmar o vínculo entre '
                   f'seu prestador AUTOSEG e o Meu Auto Financeiro.</p>'
                   '<p>Ele expira em 15 minutos.</p>'):
        raise ValueError('Não foi possível enviar o código para o e-mail do prestador.')
    return True


def confirm_link_code(pid, email, codigo):
    email = str(email or '').strip().lower()
    with _conn() as c:
        c.execute('BEGIN IMMEDIATE')
        user = _usuario_por_pid(c, pid) or _usuario_por_email(c, email)
        if not user:
            raise ValueError('Conta MAF não encontrada.')
        reg = c.execute('''SELECT * FROM usuario_codigos
            WHERE usuario_id=? AND tipo='autoseg_link' AND usado_em IS NULL
            ORDER BY id DESC LIMIT 1''', (user['id'],)).fetchone()
        if not reg or reg['expira_em'] < _now():
            raise ValueError('Código inválido ou expirado.')
        if not secrets.compare_digest(reg['codigo_hash'], _hash(codigo)):
            raise ValueError('Código inválido ou expirado.')
        conflito = c.execute('SELECT id FROM usuarios WHERE autoseg_pid=? AND id<>?',
                             (pid, user['id'])).fetchone()
        if conflito:
            raise ValueError('Este prestador já está vinculado a outra conta MAF.')
        c.execute('UPDATE usuario_codigos SET usado_em=? WHERE id=?', (_now(), reg['id']))
        c.execute('UPDATE usuarios SET autoseg_pid=? WHERE id=?', (pid, user['id']))
        c.execute('''INSERT INTO auditoria(usuario_id,acao,detalhe,criado_em)
                     VALUES(?,?,?,?)''',
                  (user['id'], 'Vínculo AUTOSEG confirmado', f'prestador={pid}', _now()))
    return True


def list_loans(pid, email):
    if not MAF_DB.is_file():
        return []
    email = str(email or '').strip().lower()
    with _conn() as c:
        user = _usuario_por_pid(c, pid) or _usuario_por_email(c, email)
        if user:
            rows = c.execute('''SELECT * FROM emprestimos
                WHERE credor_id=? OR devedor_id=? ORDER BY id DESC''',
                (user['id'], user['id'])).fetchall()
        else:
            rows = c.execute('''SELECT * FROM emprestimos
                WHERE lower(credor_email)=? OR lower(devedor_email)=?
                ORDER BY id DESC''', (email, email)).fetchall()
    return [dict(x) for x in rows]


def _loans_for(pid, email, papel):
    """Empréstimos aceitos em que o prestador é credor ou devedor.

    O principal fica fora do financeiro da empresa; estas linhas alimentam
    apenas as colunas pessoais "A receber" e "Recebidos" do prestador.
    """
    if papel not in ('credor', 'devedor') or not MAF_DB.is_file():
        return []
    email = str(email or '').strip().lower()
    with _conn() as c:
        user = _usuario_por_pid(c, pid) or _usuario_por_email(c, email)
        if not user:
            return []
        rows = c.execute(f'''SELECT e.*,
            COALESCE((SELECT SUM(d.valor_centavos) FROM devolucoes d
              WHERE d.emprestimo_id=e.id AND d.confirmado_em IS NOT NULL),0) AS pago,
            COALESCE((SELECT SUM(d.valor_centavos) FROM devolucoes d
              WHERE d.emprestimo_id=e.id AND d.confirmado_em IS NULL
              AND d.contestado_em IS NULL),0) AS pendente
            FROM emprestimos e WHERE e.{papel}_id=? AND e.aceito_em IS NOT NULL
              AND e.estado NOT IN ('cancelado','quitado')''',
            (user['id'],)).fetchall()
    saida = []
    for row in rows:
        item = dict(row)
        item['restante'] = max(0, int(item['valor_centavos'] or 0) - int(item['pago'] or 0))
        if item['restante'] > 0:
            saida.append(item)
    return saida


def loan_receivables(pid, email):
    """Principal em aberto dos empréstimos em que o prestador é credor."""
    return _loans_for(pid, email, 'credor')


def loan_payables(pid, email):
    """Principal em aberto dos empréstimos em que o prestador é devedor."""
    return _loans_for(pid, email, 'devedor')


def get_loan(pid, email, loan_id):
    if not MAF_DB.is_file():
        return None
    email = str(email or '').strip().lower()
    with _conn() as c:
        user = _usuario_por_pid(c, pid) or _usuario_por_email(c, email)
        row = c.execute('SELECT * FROM emprestimos WHERE id=?', (int(loan_id),)).fetchone()
        if not row:
            return None
        if user and user['id'] in (row['credor_id'], row['devedor_id']):
            return dict(row)
        if email in (str(row['credor_email']).lower(), str(row['devedor_email']).lower()):
            return dict(row)
    return None


def save_proof(arquivo):
    if not arquivo or not isinstance(arquivo, tuple) or not arquivo[0]:
        return None
    nome, conteudo = arquivo
    if not isinstance(conteudo, (bytes, bytearray)):
        raise ValueError('Comprovante inválido.')
    if len(conteudo) > MAX_PROOF:
        raise ValueError('O comprovante deve ter no máximo 4 MB.')
    if not (conteudo.startswith(b'%PDF-') or conteudo.startswith(b'\xff\xd8')
            or conteudo.startswith(b'\x89PNG')):
        raise ValueError('Use PDF, JPG ou PNG como comprovante.')
    sufixo = '.pdf' if conteudo.startswith(b'%PDF-') else (
        '.jpg' if conteudo.startswith(b'\xff\xd8') else '.png')
    MAF_DOCS.mkdir(parents=True, exist_ok=True)
    destino = MAF_DOCS / (secrets.token_hex(20) + sufixo)
    destino.write_bytes(conteudo)
    try:
        os.chmod(destino, 0o600)
    except OSError:
        pass
    return destino.name


def proof_path(nome):
    nome = Path(str(nome or '')).name
    if not nome:
        return None
    caminho = MAF_DOCS / nome
    return caminho if caminho.is_file() else None


def proof_return(pid, email, devolucao_id):
    email = str(email or '').strip().lower()
    with _conn() as c:
        dev = c.execute('''SELECT d.*, e.credor_id, e.devedor_id,
            e.credor_email, e.devedor_email FROM devolucoes d
            JOIN emprestimos e ON e.id=d.emprestimo_id WHERE d.id=?''',
            (int(devolucao_id),)).fetchone()
        if not dev:
            return None
        user = _usuario_por_pid(c, pid) or _usuario_por_email(c, email)
        if user and user['id'] in (dev['credor_id'], dev['devedor_id']):
            return proof_path(dev['comprovante'])
        if email in (str(dev['credor_email']).lower(), str(dev['devedor_email']).lower()):
            return proof_path(dev['comprovante'])
    return None


def create_loan(pid, email, devedor_email, descricao, valor_centavos, vencimento=None):
    devedor_email = str(devedor_email or '').strip().lower()
    email = str(email or '').strip().lower()
    if not devedor_email or devedor_email == email:
        raise ValueError('Informe o e-mail de outra pessoa.')
    if int(valor_centavos) <= 0:
        raise ValueError('O valor precisa ser maior que zero.')
    with _conn() as c:
        c.execute('BEGIN IMMEDIATE')
        credor = _usuario_por_pid(c, pid)
        if not credor:
            raise PermissionError('Confirme o vínculo com o Meu Auto Financeiro antes de criar empréstimos.')
        # O usuário pode ter sido criado pelo sincronismo do AUTOSEG sem e-mail.
        # O e-mail do prestador passa a ser a identidade da conta pendente.
        credor_email = str(credor['email'] or email or f'prestador-{pid}@autoseg.local').strip().lower()
        if not credor['email'] and email:
            try:
                c.execute('UPDATE usuarios SET email=? WHERE id=?', (credor_email, credor['id']))
            except sqlite3.IntegrityError:
                pass
        devedor = _usuario_ou_sombra(c, devedor_email)
        if credor['id'] == devedor['id']:
            raise ValueError('Você não pode emprestar para si mesmo.')
        cur = c.execute('''INSERT INTO emprestimos
            (credor_id,devedor_id,credor_email,devedor_email,descricao,
             valor_centavos,vencimento,estado,criado_em,atualizado_em)
            VALUES(?,?,?,?,?,?,?,'aguardando_aceite',?,?)''',
            (credor['id'], devedor['id'], credor_email, devedor['email'],
             descricao or 'Empréstimo', int(valor_centavos), vencimento or None,
             _now(), _now()))
        _evento(c, cur.lastrowid,
                {'id': credor['id'], 'email': credor_email},
                'Empréstimo criado', f'{_reais(valor_centavos)} para {devedor_email}')
    _enviar_async(devedor_email, 'Meu Auto Financeiro — empréstimo para aceitar',
                  f'<p>Você recebeu um empréstimo de <b>{_reais(valor_centavos)}</b> '
                  f'de {_esc(email)}.</p><p>{_esc(descricao or "Empréstimo")}</p>'
                  '<p>Abra o Meu Auto Financeiro ou o financeiro do AUTOSEG para aceitar.</p>')
    return int(cur.lastrowid)


def act(pid, email, loan_id, acao, d):
    email = str(email or '').strip().lower()
    with _conn() as c:
        c.execute('BEGIN IMMEDIATE')
        user = _usuario_por_pid(c, pid)
        if not user:
            raise PermissionError('Confirme o vínculo com o Meu Auto Financeiro antes de agir.')
        e = c.execute('SELECT * FROM emprestimos WHERE id=?', (int(loan_id),)).fetchone()
        if not e:
            raise ValueError('Empréstimo não encontrado.')
        if user['id'] not in (e['credor_id'], e['devedor_id']):
            raise PermissionError('Somente as partes podem agir.')
        outro_email = e['devedor_email'] if user['id'] == e['credor_id'] else e['credor_email']
        pago = c.execute('''SELECT COALESCE(SUM(valor_centavos),0) FROM devolucoes
            WHERE emprestimo_id=? AND confirmado_em IS NOT NULL''', (e['id'],)).fetchone()[0]
        pendente = c.execute('''SELECT COALESCE(SUM(valor_centavos),0) FROM devolucoes
            WHERE emprestimo_id=? AND confirmado_em IS NULL
            AND contestado_em IS NULL''', (e['id'],)).fetchone()[0]
        estado = e['estado'] or 'aguardando_aceite'
        if acao == 'aceitar':
            if user['id'] != e['devedor_id'] or estado != 'aguardando_aceite':
                raise PermissionError('Aceite indisponível.')
            c.execute("""UPDATE emprestimos SET aceito_em=?,recusado_em=NULL,
                estado='aceito',atualizado_em=? WHERE id=?""", (_now(), _now(), e['id']))
            _evento(c, e['id'], dict(user), 'Empréstimo aceito', 'Devedor aceitou.')
            _enviar_async(outro_email, 'AUTOSEG — empréstimo aceito',
                          f'<p>O empréstimo #{e["id"]} foi aceito.</p>')
        elif acao == 'recusar':
            if user['id'] != e['devedor_id'] or estado != 'aguardando_aceite':
                raise PermissionError('Recusa indisponível.')
            motivo = str(d.get('motivo', '')).strip()[:500]
            c.execute("""UPDATE emprestimos SET recusado_em=?,estado='recusado',
                atualizado_em=? WHERE id=?""", (_now(), _now(), e['id']))
            _evento(c, e['id'], dict(user), 'Empréstimo recusado', motivo or 'Sem motivo.')
            _enviar_async(outro_email, 'AUTOSEG — empréstimo recusado',
                          f'<p>O empréstimo #{e["id"]} foi recusado.</p><p>{_esc(motivo)}</p>')
        elif acao == 'reenviar-aceite':
            if user['id'] != e['credor_id'] or estado != 'recusado':
                raise PermissionError('Reenvio indisponível.')
            c.execute("""UPDATE emprestimos SET recusado_em=NULL,estado='aguardando_aceite',
                atualizado_em=? WHERE id=?""", (_now(), e['id']))
            _evento(c, e['id'], dict(user), 'Aceite reenviado', 'Credor reenviou.')
            _enviar_async(outro_email, 'AUTOSEG — empréstimo para aceitar novamente',
                          f'<p>O empréstimo #{e["id"]} foi reenviado para seu aceite.</p>')
        elif acao == 'enviar':
            if user['id'] != e['credor_id'] or estado in ('cancelado', 'quitado'):
                raise PermissionError('Comprovante indisponível para este empréstimo.')
            nome = save_proof(d.get('comprovante'))
            if not nome:
                raise ValueError('Anexe o comprovante.')
            venc = e['vencimento'] or (date.today() + timedelta(days=30)).isoformat()
            c.execute("""UPDATE emprestimos SET confirmado_envio_em=?,comprovante_envio=?,
                vencimento=?,atualizado_em=? WHERE id=?""",
                (_now(), nome, venc, _now(), e['id']))
            _evento(c, e['id'], dict(user), 'Comprovante do empréstimo',
                    'Credor anexou/atualizou o comprovante.')
            _enviar_async(outro_email, 'AUTOSEG — comprovante do empréstimo',
                          f'<p>O credor anexou o comprovante do empréstimo #{e["id"]}.</p>')
        elif acao == 'receber':
            if user['id'] != e['devedor_id'] or estado != 'enviado':
                raise PermissionError('Recebimento indisponível.')
            c.execute("""UPDATE emprestimos SET confirmado_recebimento_em=?,
                estado='recebido',atualizado_em=? WHERE id=?""", (_now(), _now(), e['id']))
            _evento(c, e['id'], dict(user), 'Recebimento confirmado', 'Devedor confirmou.')
            _enviar_async(outro_email, 'AUTOSEG — recebimento confirmado',
                          f'<p>O devedor confirmou o recebimento do empréstimo #{e["id"]}.</p>')
        elif acao == 'devolver':
            if (user['id'] != e['devedor_id'] or not e['aceito_em']
                    or estado in ('cancelado', 'quitado')):
                raise PermissionError('Devolução indisponível.')
            valor = int(d.get('valor_centavos') or 0)
            if valor <= 0 or valor > int(e['valor_centavos']) - int(pago) - int(pendente):
                raise ValueError('Valor de devolução inválido.')
            nome = save_proof(d.get('comprovante'))
            if not nome:
                raise ValueError('Anexe o comprovante de devolução.')
            c.execute('''INSERT INTO devolucoes(emprestimo_id,valor_centavos,comprovante,enviado_em)
                VALUES(?,?,?,?)''', (e['id'], valor, nome, _now()))
            _evento(c, e['id'], dict(user), 'Devolução enviada', _reais(valor))
            _enviar_async(outro_email, 'AUTOSEG — devolução para confirmar',
                          f'<p>O devedor registrou uma devolução de <b>{_reais(valor)}</b>.</p>')
        elif acao == 'confirmar':
            if user['id'] != e['credor_id']:
                raise PermissionError('Somente o credor confirma.')
            did = int(d.get('devolucao') or 0)
            dev = c.execute('SELECT * FROM devolucoes WHERE id=? AND emprestimo_id=?',
                            (did, e['id'])).fetchone()
            if not dev or dev['confirmado_em']:
                raise ValueError('Devolução não encontrada ou já confirmada.')
            c.execute('UPDATE devolucoes SET confirmado_em=?,confirmado_por=? WHERE id=?',
                      (_now(), user['id'], did))
            restante = int(e['valor_centavos']) - int(pago) - int(dev['valor_centavos'])
            if restante <= 0:
                c.execute("UPDATE emprestimos SET estado='quitado',atualizado_em=? WHERE id=?",
                          (_now(), e['id']))
            _evento(c, e['id'], dict(user), 'Pagamento aceito', _reais(dev['valor_centavos']))
            _enviar_async(outro_email, 'AUTOSEG — pagamento aceito',
                          f'<p>O credor aceitou o pagamento de {_reais(dev["valor_centavos"])}.</p>')
        elif acao == 'recusar-pagamento':
            if user['id'] != e['credor_id']:
                raise PermissionError('Somente o credor analisa o pagamento.')
            did = int(d.get('devolucao') or 0)
            dev = c.execute('SELECT * FROM devolucoes WHERE id=? AND emprestimo_id=?',
                            (did, e['id'])).fetchone()
            if not dev or dev['confirmado_em'] or dev['contestado_em']:
                raise ValueError('Pagamento não encontrado ou já analisado.')
            motivo = str(d.get('motivo', '')).strip()
            if len(motivo) < 3:
                raise ValueError('Informe o motivo da recusa do comprovante.')
            c.execute('''UPDATE devolucoes SET contestado_em=?,motivo_contestacao=?
                         WHERE id=?''', (_now(), motivo[:1000], did))
            _evento(c, e['id'], dict(user), 'Pagamento recusado', motivo)
            _enviar_async(outro_email, 'AUTOSEG — comprovante recusado',
                          f'<p>O credor recusou o comprovante do empréstimo #{e["id"]}.</p>'
                          f'<p>{_esc(motivo)}</p>')
        elif acao == 'alterar':
            if estado in ('cancelado', 'quitado'):
                raise ValueError('Empréstimo encerrado.')
            valor = int(d.get('valor_centavos') or e['valor_centavos'])
            if valor < int(pago):
                raise ValueError('O novo valor não pode ser menor que o já devolvido.')
            if c.execute("SELECT 1 FROM emprestimo_alteracoes WHERE emprestimo_id=? AND estado='pendente'", (e['id'],)).fetchone():
                raise ValueError('Já existe alteração pendente.')
            c.execute('''INSERT INTO emprestimo_alteracoes
                (emprestimo_id,tipo,proposto_por,valor_centavos,vencimento,descricao,
                 estado,criado_em) VALUES(?,?,?,?,?,?,'pendente',?)''',
                (e['id'], 'alteracao', user['id'], valor,
                 str(d.get('vencimento') or e['vencimento'] or ''),
                 str(d.get('descricao') or e['descricao'] or ''), _now()))
            _evento(c, e['id'], dict(user), 'Alteração proposta', _reais(valor))
            _enviar_async(outro_email, 'AUTOSEG — alteração para aceitar',
                          f'<p>Foi proposta uma alteração no empréstimo #{e["id"]}.</p>')
        elif acao in ('aceitar-alteracao', 'recusar-alteracao'):
            alt = c.execute('''SELECT * FROM emprestimo_alteracoes
                WHERE emprestimo_id=? AND estado='pendente' ORDER BY id DESC LIMIT 1''',
                (e['id'],)).fetchone()
            if not alt or alt['proposto_por'] == user['id']:
                raise PermissionError('Alteração indisponível.')
            if acao == 'recusar-alteracao':
                c.execute('''UPDATE emprestimo_alteracoes SET estado='recusada',
                    respondido_em=?,respondido_por=? WHERE id=?''',
                    (_now(), user['id'], alt['id']))
                _evento(c, e['id'], dict(user), 'Alteração recusada', '')
            else:
                if (alt['valor_centavos'] or 0) < int(pago):
                    raise ValueError('O novo valor não pode ser menor que o já devolvido.')
                c.execute('''UPDATE emprestimo_alteracoes SET estado='aceita',
                    respondido_em=?,respondido_por=? WHERE id=?''',
                    (_now(), user['id'], alt['id']))
                if alt['tipo'] == 'cancelamento':
                    c.execute("""UPDATE emprestimos SET estado='cancelado',cancelado_em=?,
                        cancelado_por=?,cancelado_motivo=?,atualizado_em=? WHERE id=?""",
                        (_now(), alt['proposto_por'], alt['motivo'], _now(), e['id']))
                else:
                    c.execute("""UPDATE emprestimos SET valor_centavos=?,vencimento=?,
                        descricao=?,versao=versao+1,atualizado_em=? WHERE id=?""",
                        (alt['valor_centavos'], alt['vencimento'], alt['descricao'],
                         _now(), e['id']))
                _evento(c, e['id'], dict(user), 'Alteração aceita', '')
        elif acao == 'contestar':
            motivo = str(d.get('motivo', '')).strip()
            if len(motivo) < 3:
                raise ValueError('Descreva o motivo.')
            c.execute("""UPDATE emprestimos SET contestado_em=?,motivo_contestacao=?,
                atualizado_em=? WHERE id=?""", (_now(), motivo[:1000], _now(), e['id']))
            _evento(c, e['id'], dict(user), 'Contestação', motivo)
            _enviar_async(outro_email, 'AUTOSEG — contestação',
                          f'<p>O empréstimo #{e["id"]} foi contestado.</p><p>{_esc(motivo)}</p>')
        elif acao == 'resolver':
            c.execute("""UPDATE emprestimos SET contestado_em=NULL,motivo_contestacao='',
                atualizado_em=? WHERE id=?""", (_now(), e['id']))
            _evento(c, e['id'], dict(user), 'Contestação resolvida', '')
        elif acao == 'cancelar':
            motivo = str(d.get('motivo', '')).strip()[:500]
            if user['id'] == e['credor_id'] and estado in ('aguardando_aceite', 'recusado'):
                c.execute("""UPDATE emprestimos SET estado='cancelado',cancelado_em=?,
                    cancelado_por=?,cancelado_motivo=?,atualizado_em=? WHERE id=?""",
                    (_now(), user['id'], motivo, _now(), e['id']))
                _evento(c, e['id'], dict(user), 'Empréstimo cancelado', motivo)
            else:
                if c.execute("SELECT 1 FROM emprestimo_alteracoes WHERE emprestimo_id=? AND tipo='cancelamento' AND estado='pendente'", (e['id'],)).fetchone():
                    raise ValueError('Já existe cancelamento pendente.')
                c.execute('''INSERT INTO emprestimo_alteracoes
                    (emprestimo_id,tipo,proposto_por,motivo,estado,criado_em)
                    VALUES(?,?,?,?,'pendente',?)''',
                    (e['id'], 'cancelamento', user['id'], motivo, _now()))
                _evento(c, e['id'], dict(user), 'Cancelamento proposto', motivo)
                _enviar_async(outro_email, 'AUTOSEG — cancelamento para aceitar',
                              f'<p>Foi proposto o cancelamento do empréstimo #{e["id"]}.</p>')
        else:
            raise ValueError('Ação inválida.')
    return int(loan_id)


def _estado_label(e, saldo):
    labels = {'aguardando_aceite': 'Aguardando aceite', 'aceito': 'Aceito',
              'recusado': 'Recusado', 'enviado': 'Enviado', 'recebido': 'Recebido',
              'quitado': 'Quitado', 'cancelado': 'Cancelado'}
    if saldo <= 0:
        return 'Quitado'
    label = labels.get(e['estado'], e['estado'] or 'Aguardando aceite')
    if (e['vencimento'] and e['vencimento'] < date.today().isoformat()
            and e['estado'] in ('enviado', 'recebido')):
        label = 'Atrasado'
    if e['contestado_em']:
        label += ' · Contestado'
    return label


def render_card(pid, email, csrf):
    if not MAF_DB.is_file():
        return '<section><h2>Empréstimos (MAF)</h2><p class="muted">Banco do Meu Auto Financeiro não encontrado.</p></section>'
    with _conn() as c:
        user = _usuario_por_pid(c, pid)
    link = link_status(pid, email)
    loans = list_loans(pid, email)
    itens = []
    for e in loans:
        with _conn() as c:
            saldo = _saldo(c, e)
        papel = ('Credor' if (user and user['id'] == e['credor_id'])
                 or str(e['credor_email']).lower() == str(email).lower() else 'Devedor')
        estado = e['estado'] or 'aguardando_aceite'
        classe = ('good' if estado == 'quitado' or saldo <= 0
                  else 'bad' if estado in ('cancelado', 'recusado') else '')
        itens.append(
            '<article class="finance-item">'
            '<div class="finance-item-top">'
            f'<a class="finance-item-os" href="/financeiro/maf-emprestimo/{e["id"]}">'
            f'Empréstimo #{e["id"]}</a>'
            f'<span class="finance-item-type">{_esc(papel)}</span></div>'
            f'<p class="finance-item-client">{_esc(e["descricao"] or "Empréstimo")}</p>'
            '<div class="finance-item-values"><span>Restante</span>'
            f'<strong>{_reais(saldo)}</strong></div>'
            f'<p class="finance-item-detail">Principal {_reais(e["valor_centavos"])}'
            f' · venc. {_esc(e["vencimento"] or "—")}</p>'
            '<div class="finance-item-foot">'
            f'<span class="tag {classe}">{_esc(_estado_label(e, saldo))}</span>'
            f'<a class="btn secondary" href="/financeiro/maf-emprestimo/{e["id"]}">Abrir</a>'
            '</div></article>')
    lista = (f'<div class="finance-list">{"".join(itens)}</div>'
             if itens else '<p class="muted">Nenhum empréstimo.</p>')
    if not link.get('linked'):
        aviso = ('<p class="aviso">Confirme o vínculo com o Meu Auto Financeiro para '
                 'aceitar, enviar comprovantes e confirmar devoluções.</p>'
                 '<form method="post" action="/financeiro/maf-vinculo/solicitar">'
                 f'<input type="hidden" name="csrf" value="{_esc(csrf)}">'
                 '<button type="submit">Enviar código de confirmação</button></form>'
                 '<form method="post" action="/financeiro/maf-vinculo/confirmar">'
                 f'<input type="hidden" name="csrf" value="{_esc(csrf)}">'
                 '<label>Código recebido por e-mail</label>'
                 '<input name="codigo" inputmode="numeric" maxlength="6" required>'
                 '<button type="submit" class="secondary">Confirmar vínculo</button></form>')
    else:
        aviso = ('<p class="good">Integração com o Meu Auto Financeiro ativa.</p>'
                 '<p class="muted">Seu e-mail é a identidade. Não precisa criar outra conta MAF.</p>')
    novo = ('<details><summary>Novo empréstimo</summary>'
            '<form method="post" action="/financeiro/maf-emprestimo/criar">'
            f'<input type="hidden" name="csrf" value="{_esc(csrf)}">'
            '<label>E-mail do devedor</label><input type="email" name="devedor_email" required>'
            '<label>Descrição</label><input name="descricao" required>'
            '<label>Valor (R$)</label><input name="valor" inputmode="decimal" required>'
            '<label>Vencimento (opcional)</label><input type="date" name="vencimento">'
            '<button type="submit">Registrar empréstimo</button></form></details>')
    return ('<section><h2>Empréstimos (MAF)</h2>'
            '<p class="muted">Valores pessoais entre prestadores. Não entram no total da empresa.</p>'
            + aviso + lista + novo + '</section>')


def render_detail(pid, email, loan_id, csrf):
    e = get_loan(pid, email, loan_id)
    if not e:
        return None
    with _conn() as c:
        pago = c.execute('''SELECT COALESCE(SUM(valor_centavos),0) FROM devolucoes
            WHERE emprestimo_id=? AND confirmado_em IS NOT NULL''', (e['id'],)).fetchone()[0]
        devs = c.execute('SELECT * FROM devolucoes WHERE emprestimo_id=? ORDER BY id DESC',
                         (e['id'],)).fetchall()
        eventos = c.execute('SELECT * FROM emprestimo_eventos WHERE emprestimo_id=? ORDER BY id DESC',
                            (e['id'],)).fetchall()
        alt = c.execute('''SELECT * FROM emprestimo_alteracoes
            WHERE emprestimo_id=? AND estado='pendente' ORDER BY id DESC LIMIT 1''',
            (e['id'],)).fetchone()
    saldo = int(e['valor_centavos']) - int(pago or 0)
    estado = e['estado'] or 'aguardando_aceite'
    is_credor = str(e['credor_email']).lower() == str(email).lower()
    is_devedor = str(e['devedor_email']).lower() == str(email).lower()
    corpo = (f'<p><b>{_esc(e["descricao"])}</b></p>'
             f'<p>Credor: {_esc(e["credor_email"])} · Devedor: {_esc(e["devedor_email"])}</p>'
             f'<p>Principal: <b>{_reais(e["valor_centavos"])}</b> · Restante: '
             f'<b>{_reais(saldo)}</b> · Vencimento: {_esc(e["vencimento"] or "-")}</p>'
             f'<p>Estado: <b>{_esc(_estado_label(e, saldo))}</b> · Versão {int(e["versao"] or 1)}</p>')
    with _conn() as c:
        linked = _usuario_por_pid(c, pid) is not None
    if not linked:
        corpo += ('<p class="aviso">Confirme o vínculo com o Meu Auto Financeiro '
                  'no financeiro para aceitar, enviar comprovantes ou confirmar.</p>'
                  '<p><a class="btn secondary" href="/financeiro">Voltar ao financeiro</a></p>')
        return '<section><h2>Empréstimo #' + str(e['id']) + '</h2>' + corpo + '</section>'
    if e['contestado_em']:
        corpo += f'<p class="aviso">Contestado: {_esc(e["motivo_contestacao"])}</p>'
    def form(acao, conteudo, rotulo='Confirmar', multipart=False):
        enc = ' enctype="multipart/form-data"' if multipart else ''
        return (f'<form method="post" action="/financeiro/maf-emprestimo/{e["id"]}/{acao}"{enc}>'
                f'<input type="hidden" name="csrf" value="{_esc(csrf)}">'
                + conteudo + f'<button type="submit">{_esc(rotulo)}</button></form>')
    if is_devedor and estado == 'aguardando_aceite':
        corpo += '<h3>Aceitar empréstimo</h3>' + form('aceitar', '', 'Aceitar')
        corpo += form('recusar', '<label>Motivo da recusa</label><input name="motivo">', 'Recusar')
    if is_credor and estado == 'recusado':
        corpo += '<h3>Aceite recusado</h3>' + form('reenviar-aceite', '', 'Reenviar aceite')
    if is_credor and estado not in ('cancelado', 'quitado'):
        corpo += '<h3>Comprovante do empréstimo (opcional)</h3>' + form('enviar',
            '<label>Comprovante</label><input type="file" name="comprovante" accept="application/pdf,image/jpeg,image/png" required>',
            'Anexar/atualizar comprovante', True)
    if is_devedor and e['aceito_em'] and estado not in ('cancelado', 'quitado') and saldo > 0:
        corpo += '<h3>Confirmar devolução e enviar comprovante Pix</h3>' + form('devolver',
            '<label>Valor (R$)</label><input name="valor" inputmode="decimal" required>'
            '<label>Comprovante Pix</label><input type="file" name="comprovante" accept="application/pdf,image/jpeg,image/png" required>',
            'Confirmar devolução', True)
    if alt:
        if str(alt['proposto_por']) != '':
            corpo += (f'<h3>Alteração pendente</h3><p>{_reais(alt["valor_centavos"] or e["valor_centavos"])} · '
                      f'{_esc(alt["vencimento"] or "-")}</p>'
                      + form('aceitar-alteracao', '', 'Aceitar alteração')
                      + form('recusar-alteracao', '', 'Recusar alteração'))
    elif estado not in ('cancelado', 'quitado'):
        corpo += ('<h3>Propor alteração</h3>' + form('alterar',
            '<label>Novo valor (R$)</label><input name="valor" inputmode="decimal">'
            '<label>Novo vencimento</label><input type="date" name="vencimento">'
            '<label>Nova descrição</label><input name="descricao">',
            'Propor alteração'))
    if estado not in ('cancelado', 'quitado'):
        if e['contestado_em']:
            corpo += '<h3>Contestação</h3>' + form('resolver',
                '<label>Como foi resolvido?</label><input name="nota">', 'Marcar resolvido')
        else:
            corpo += '<h3>Contestar</h3>' + form('contestar',
                '<label>Motivo</label><input name="motivo" required>', 'Registrar contestação')
        if is_credor and estado in ('aguardando_aceite', 'recusado'):
            corpo += '<h3>Cancelar</h3>' + form('cancelar',
                '<label>Motivo</label><input name="motivo">', 'Cancelar')
        else:
            corpo += '<h3>Propor cancelamento</h3>' + form('cancelar',
                '<label>Motivo</label><input name="motivo" required>', 'Propor cancelamento')
    linhas_dev = []
    for d in devs:
        acao = ''
        if is_credor and not d['confirmado_em'] and not d['contestado_em']:
            acao = form('confirmar', f'<input type="hidden" name="devolucao" value="{d["id"]}">',
                        'Aceitar pagamento')
            acao += form('recusar-pagamento',
                f'<input type="hidden" name="devolucao" value="{d["id"]}">'
                '<label>Motivo da recusa</label><input name="motivo" required>',
                'Recusar comprovante')
        comp = (f'<a href="/financeiro/maf-comprovante/{d["id"]}">Comprovante</a>'
                if d['comprovante'] else '—')
        situacao = ('Confirmado' if d['confirmado_em']
                    else 'Recusado' if d['contestado_em'] else 'Aguardando análise')
        linhas_dev.append(f'<tr><td>{_reais(d["valor_centavos"])}</td><td>{_esc(d["enviado_em"])}</td>'
                          f'<td>{situacao}</td><td>{comp}{acao}</td></tr>')
    corpo += ('<h3>Devoluções</h3><div class="tabela"><table><thead><tr><th>Valor</th>'
              '<th>Envio</th><th>Situação</th><th>Comprovante</th></tr></thead><tbody>'
              + ''.join(linhas_dev) + '</tbody></table></div>')
    corpo += ('<h3>Histórico</h3>' + ''.join(
        f'<p><small>{_esc(x["criado_em"][:16].replace("T", " "))}</small> '
        f'<b>{_esc(x["acao"])}</b> — {_esc(x["detalhe"])}</p>' for x in eventos))
    return ('<section><h2>Empréstimo #' + str(e['id']) + '</h2>'
            + corpo + '<p><a class="btn secondary" href="/financeiro">Voltar ao financeiro</a></p></section>')
