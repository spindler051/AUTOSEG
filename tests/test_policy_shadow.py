"""Tests for the non-blocking object-policy shadow adapter."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from officina.core import cadastros_v9 as cad
from officina.core import fluxo_os as fluxo
from officina.core import prestadores_ext as ext
from officina.core import produtividade_os as prod
from officina.core.banco import criar_banco
from flavors.autoseg.modules import policy_shadow


class PolicyShadowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='policy_shadow_')
        self.dir = Path(self.tmp.name)
        self.db = str(self.dir / 'teste.db')
        criar_banco(self.db)
        for modulo in (ext, cad, prod, fluxo):
            modulo.instalar(self.db)
        self._base_anterior = os.environ.get('AUTOSEG_BASE')
        self._shadow_anterior = os.environ.get('AUTOSEG_POLICY_SHADOW')
        os.environ['AUTOSEG_BASE'] = str(self.dir)
        os.environ.pop('AUTOSEG_POLICY_SHADOW', None)
        self.admin = self._prestador('Admin Shadow', 'admin.shadow@example.com')
        self.responsavel = self._prestador(
            'Responsável Shadow', 'resp.shadow@example.com')
        self.participante = self._prestador(
            'Participante Shadow', 'part.shadow@example.com')
        self.fora = self._prestador(
            'Fora Shadow', 'fora.shadow@example.com')
        cad.definir_admin(self.db, self.admin, True)
        self.cliente = self._cliente('Cliente Shadow')
        self.os_id = self._os(self.cliente, self.responsavel)
        self.outro_cliente = self._cliente('Outro Cliente Shadow')
        self.usuario = self._usuario('Usuário Shadow', self.cliente)
        self.outro_usuario = self._usuario(
            'Outro Usuário Shadow', self.outro_cliente)

    def tearDown(self):
        if self._base_anterior is None:
            os.environ.pop('AUTOSEG_BASE', None)
        else:
            os.environ['AUTOSEG_BASE'] = self._base_anterior
        if self._shadow_anterior is None:
            os.environ.pop('AUTOSEG_POLICY_SHADOW', None)
        else:
            os.environ['AUTOSEG_POLICY_SHADOW'] = self._shadow_anterior
        self.tmp.cleanup()

    def _prestador(self, nome, email):
        return ext.cadastrar(
            self.db, nome, email, 'senha-bem-segura-2026')

    def _cliente(self, nome):
        with ext.db(self.db) as c:
            return c.execute(
                "INSERT INTO clientes(nome,tipo_pessoa,status,criado_em) "
                "VALUES(?,?,?,?)",
                (nome, 'Jurídica', 'Ativo', ext.agora()),
            ).lastrowid

    def _os(self, cliente_id, responsavel_id):
        with ext.db(self.db) as c:
            oid = c.execute(
                "INSERT INTO ordens_servico(numero_os,cliente_id,descricao,"
                "status,valor_total,criado_em,atualizado_em,origem) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ('SHADOW-1', cliente_id, 'OS de teste', 'Aberta', 100.0,
                 ext.agora(), ext.agora(), 'App'),
            ).lastrowid
            c.execute(
                "INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em) "
                "VALUES(?,?,?)",
                (oid, responsavel_id, ext.agora()),
            )
            c.execute(
                "INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo) "
                "VALUES(?,?,?,1)",
                (oid, responsavel_id, ext.agora()),
            )
            c.execute(
                "INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo) "
                "VALUES(?,?,?,1)",
                (oid, self.participante, ext.agora()),
            )
            c.execute(
                "INSERT INTO os_prestadores(os_id,prestador_id,atribuido_em,ativo) "
                "VALUES(?,?,?,0)",
                (oid, self.fora, ext.agora()),
            )
            c.execute(
                "INSERT INTO os_encerramentos(os_id,situacao,relatorio,ator,"
                "prestador_id,encerrado_em) VALUES(?,?,?,?,?,?)",
                (oid, 'Concluída', 'Teste', 'Teste', responsavel_id, ext.agora()),
            )
            return oid

    def _usuario(self, nome, cliente_id):
        with ext.db(self.db) as c:
            return c.execute(
                "INSERT INTO v9_usuarios(nome,cpf,telefone,email,senha_hash,"
                "ativo,criado_em,cliente_pf_id) VALUES(?,?,?,?,?,?,?,?)",
                (nome, f'{cliente_id:011d}', '51999999999',
                 f'user{cliente_id}@example.com', 'hash', 1,
                 ext.agora(), cliente_id),
            ).lastrowid

    def _log(self):
        arquivo = self.dir / 'logs' / 'policy_shadow.jsonl'
        if not arquivo.exists():
            return []
        return [json.loads(linha) for linha in arquivo.read_text(
            encoding='utf-8').splitlines() if linha.strip()]

    def test_principal_provider_maps_admin_and_employee(self):
        admin = policy_shadow.principal_provider(self.db, self.admin)
        funcionario = policy_shadow.principal_provider(self.db, self.fora)
        self.assertEqual(admin.role, 'admin')
        self.assertEqual(funcionario.role, 'employee')
        self.assertTrue(admin.active)
        self.assertTrue(funcionario.active)

    def test_principal_client_maps_owner(self):
        usuario = policy_shadow.principal_client(self.db, self.usuario)
        self.assertEqual(usuario.role, 'customer')
        self.assertEqual(usuario.client_id, self.cliente)
        self.assertTrue(usuario.active)

    def test_resource_maps_owner_participants_and_finalizer(self):
        recurso = policy_shadow.resource_work_item(self.db, self.os_id)
        self.assertEqual(recurso.kind, 'work_item')
        self.assertEqual(recurso.owner_id, self.responsavel)
        self.assertEqual(recurso.client_id, self.cliente)
        self.assertEqual(recurso.participant_ids,
                         frozenset({self.responsavel, self.participante}))
        self.assertEqual(recurso.attributes['finalizer_id'], self.responsavel)
        self.assertIn(self.fora, recurso.attributes['legacy_participant_ids'])

    def test_unlinked_provider_view_records_divergence(self):
        os.environ['AUTOSEG_POLICY_SHADOW'] = '1'
        principal = policy_shadow.principal_provider(self.db, self.fora)
        recurso = policy_shadow.resource_work_item(self.db, self.os_id)
        decisao = policy_shadow.evaluate(
            principal, 'view', recurso, True, 'test_unlinked')
        self.assertFalse(decisao.allowed)
        registros = self._log()
        self.assertEqual(len(registros), 1)
        self.assertFalse(registros[0]['policy'])
        self.assertTrue(registros[0]['actual'])
        self.assertTrue(registros[0]['divergence'])
        self.assertTrue(registros[0]['tenant_unknown'])

    def test_admin_edit_does_not_diverge(self):
        os.environ['AUTOSEG_POLICY_SHADOW'] = '1'
        principal = policy_shadow.principal_provider(self.db, self.admin)
        recurso = policy_shadow.resource_work_item(self.db, self.os_id)
        decisao = policy_shadow.evaluate(
            principal, 'edit', recurso, True, 'test_admin')
        self.assertTrue(decisao.allowed)
        registro = self._log()[0]
        self.assertTrue(registro['policy'])
        self.assertTrue(registro['actual'])
        self.assertFalse(registro['divergence'])

    def test_client_owner_can_view_but_other_client_cannot(self):
        os.environ['AUTOSEG_POLICY_SHADOW'] = '1'
        dono = policy_shadow.principal_client(self.db, self.usuario)
        outro = policy_shadow.principal_client(self.db, self.outro_usuario)
        recurso = policy_shadow.resource_work_item(self.db, self.os_id)
        self.assertTrue(policy_shadow.evaluate(
            dono, 'view', recurso, True, 'client_owner').allowed)
        self.assertFalse(policy_shadow.evaluate(
            outro, 'view', recurso, True, 'client_other').allowed)
        registros = self._log()
        self.assertEqual(len(registros), 2)
        self.assertFalse(registros[0]['divergence'])
        self.assertTrue(registros[1]['divergence'])

    def test_shadow_disabled_writes_no_log(self):
        principal = policy_shadow.principal_provider(self.db, self.fora)
        recurso = policy_shadow.resource_work_item(self.db, self.os_id)
        self.assertIsNone(policy_shadow.evaluate(
            principal, 'view', recurso, True, 'disabled'))
        self.assertEqual(self._log(), [])

    def test_log_contains_no_pii(self):
        os.environ['AUTOSEG_POLICY_SHADOW'] = '1'
        principal = policy_shadow.principal_provider(self.db, self.fora)
        recurso = policy_shadow.resource_work_item(self.db, self.os_id)
        policy_shadow.evaluate(principal, 'view', recurso, True, 'pii')
        texto = (self.dir / 'logs' / 'policy_shadow.jsonl').read_text(
            encoding='utf-8')
        for proibido in ('Admin Shadow', 'Responsável Shadow',
                         'Cliente Shadow', '@example.com', '51999999999'):
            self.assertNotIn(proibido, texto)


if __name__ == '__main__':
    unittest.main()
