"""Shared OS customer resolution and ticket-link helpers.

This is not a data writer; service-order SQL remains in portal_negocios.
"""
from __future__ import annotations
from contextlib import nullcontext
from officina.core import prestadores_ext as ext, portal_negocios as neg
from officina.integration import clientes as clientes_core

class OsBusinessSupport:
    """Business-side compatibility helpers moved out of HTTP Handler."""
    def __init__(self,banco):
        self.banco=banco
    def _cliente_por_nome(self, nome, *, connection=None):
        banco = self.banco
        return clientes_core.criar_provisorio(nome, banco=banco, connection=connection)


    def _resolver_cliente_os(self, d, oid=None, *, connection=None):
        banco = self.banco
        """Existing selected id, new client typed by name, or current OS client."""
        bruto = str(d.get('cliente_id', '')).strip()
        if bruto:
            try:
                cliente_id = int(bruto)
            except (TypeError, ValueError):
                raise ValueError('Cliente selecionado inválido.') from None
            with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
                ativo = c.execute("SELECT 1 FROM clientes WHERE id=? AND status NOT IN ('Inativo','A definir')", (cliente_id,)).fetchone()
            if ativo:
                return cliente_id
            # "Cliente a definir" is intentionally allowed on an OS.
            with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
                linha = c.execute('SELECT status FROM clientes WHERE id=?',
                                  (cliente_id,)).fetchone()
            if linha and linha['status'] == 'A definir':
                return cliente_id
            raise ValueError('Cliente selecionado não encontrado ou inativo.')
        nome = str(d.get('cliente_busca', '')).strip()
        if len(nome) >= 2:
            return self._cliente_por_nome(nome,connection=connection)
        if oid is not None:
            with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
                atual = c.execute('SELECT cliente_id FROM ordens_servico WHERE id=?',
                                  (oid,)).fetchone()
            if atual and atual['cliente_id']:
                return int(atual['cliente_id'])
        raise ValueError('Selecione um cliente existente ou digite o nome de um novo cliente.')


    def _cliente_a_definir(self, *, connection=None):
        banco = self.banco
        """Cadastro provisório para OS aberta antes de escolher o cliente."""
        with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
            linha=c.execute("SELECT id FROM clientes WHERE status='A definir' "
                            "ORDER BY id LIMIT 1").fetchone()
            if linha:
                return int(linha['id'])
            cur=c.execute("""INSERT INTO clientes
                (tipo_pessoa,documento,nome,bairro,cidade,observacoes,status,criado_em)
                VALUES('Física','','Cliente a definir','','',
                'Criado automaticamente para uma OS aberta sem cliente. Associe o cliente depois.',
                'A definir',?)""",(ext.agora(),))
            return int(cur.lastrowid)


    def _exigir_cliente_os(self, oid, acao, cliente_id=None, *, connection=None):
        banco = self.banco
        with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
            if cliente_id:
                linha=c.execute("SELECT nome,status FROM clientes WHERE id=?",
                                (int(cliente_id),)).fetchone()
            else:
                linha=c.execute("""SELECT c.nome,c.status FROM ordens_servico o
                    JOIN clientes c ON c.id=o.cliente_id WHERE o.id=?""",(oid,)).fetchone()
        if not linha or linha['status'] in ('A definir','Inativo'):
            raise ValueError(f'Escolha o cliente da OS antes de {acao}.')


    def _persist_form_client(self, d, oid, pid, actor, rule, *, connection=None):
        banco = self.banco
        """Persist the client chosen in a workflow form before its action.

        Workflow buttons submit the whole OS form, but only the regular
        save route used to persist the client. Without this, selecting
        a client and clicking "Iniciar OS" still validated the previous
        client stored on the OS. ``rule`` mirrors the authorization of
        each action so a denied action never changes the client.
        """
        if 'cliente_id' not in d and 'cliente_busca' not in d:
            return None
        with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
            linha=c.execute('SELECT status FROM ordens_servico WHERE id=?',(oid,)).fetchone()
            if not linha:
                raise ValueError('OS não encontrada.')
            if linha['status'] not in ext.ATIVAS:
                raise ValueError('Esta OS não está ativa.')
            responsavel=ext.responsavel_atual(c,oid)
        if rule=='route' and responsavel is None:
            raise ValueError('Atribua um técnico antes de marcar Em rota.')
        # ObjectPolicy already checked the exact command before this helper.
        cliente_id=int(self._resolver_cliente_os(d,oid,connection=connection))
        with (nullcontext(connection) if connection is not None else ext.db(banco)) as c:
            if connection is None:
                c.execute('BEGIN IMMEDIATE')
            atual=c.execute('SELECT cliente_id FROM ordens_servico WHERE id=?',(oid,)).fetchone()
            anterior=int(atual['cliente_id'] or 0) if atual else 0
            if anterior!=cliente_id:
                c.execute('UPDATE ordens_servico SET cliente_id=?,atualizado_em=? WHERE id=?',
                          (cliente_id,ext.agora(),oid))
                nome=c.execute('SELECT nome FROM clientes WHERE id=?',(cliente_id,)).fetchone()
                rotulo=nome['nome'] if nome else str(cliente_id)
                ext.evento(c,oid,'Cliente definido',
                           f'{anterior} -> {cliente_id} ({rotulo})',pid,actor)
                neg.audit(c,pid,'Cliente da OS alterado',oid,
                          f'{anterior} -> {cliente_id} ({rotulo})')
            if connection is None:
                c.commit()
        return cliente_id

