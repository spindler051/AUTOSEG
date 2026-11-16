"""Cross-surface characterization for the canonical service-order writer.

These checks compare persisted business state, not HTTP rendering or GTK widgets.
They use independent disposable SQLite databases and real domain adapters.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from officina.application.contracts import OSInput
from officina.application.local_service import LocalService
from officina.application.object_policy import Principal
from officina.core import (atendimento_os as aten, banco, cadastros_v9 as cad9,
                          composicao, estoque_materiais as estoque, fluxo_os as fluxo,
                          prestadores_ext as ext, produtividade_os as prod)
from flavors.autoseg.modules import os_commands


class OneWriterCharacterization(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='os_one_writer_')
        self.addCleanup(self.temp.cleanup)
        self.config = patch.object(composicao, 'carregar', return_value={})
        self.config.start()
        self.addCleanup(self.config.stop)
        self.databases = {}
        for surface in ('web', 'local'):
            filename = str(Path(self.temp.name) / f'{surface}.sqlite')
            banco.criar_banco(filename)
            for installer in (ext.instalar, cad9.instalar, aten.instalar,
                              fluxo.instalar, estoque.instalar, prod.instalar):
                installer(filename)
            composicao.instalar_banco(filename)
            pid = ext.cadastrar(filename, 'Responsible',
                                'responsible@example.invalid', 'Password12345')
            cad9.definir_admin(filename, pid, True)
            with ext.db(filename) as connection:
                cid = connection.execute('''INSERT INTO clientes
                    (nome,status,tipo_pessoa,email) VALUES
                    ('Example','Ativo','Física','client@example.invalid')''').lastrowid
            principal = Principal(pid, 'admin', organization_id='autoseg',
                                  provider_id=pid)
            self.databases[surface] = filename, pid, cid, principal

    @staticmethod
    def payload(cid, *, acao='salvar', **overrides):
        data = {'cliente_id': str(cid), 'descricao': 'Conserto de CFTV',
                'tecnico': 'Porteiro', 'forma_pagamento': 'PIX',
                'valor_mao_obra': '18', 'material_item[]': ['Conector'],
                'material_qtd[]': ['2'], 'material_unidade[]': ['un'],
                'material_unit[]': ['3'], 'custo_materiais': '2',
                'tempo_horas': '1', 'texto_adicional': 'Relato da equipe',
                'urgencia': 'Normal', 'acao_status': acao}
        data.update(overrides)
        return data

    @staticmethod
    def input(cid, *, os_id=None, acao='salvar', **overrides):
        data = dict(os_id=os_id, cliente_id=cid, tecnico='Porteiro',
                    descricao='Conserto de CFTV', valor_mao_obra=18.,
                    valor_materiais=6., custo_materiais=2., valor_total=24.,
                    forma_pagamento='PIX', urgencia='Normal', observacoes='',
                    texto_adicional='Relato da equipe', dados_incompletos=0,
                    tempo_horas=1., composicao_json='', base_percentuais='total',
                    materiais=({'item': 'Conector', 'quantidade': 2.,
                                'unidade': 'un', 'valor_unitario': 3.},),
                    acao=acao, relato='', motivo='', imagens=())
        data.update(overrides)
        return OSInput(**data)

    @staticmethod
    def snapshot(filename, oid):
        with ext.db(filename) as c:
            order = c.execute('''SELECT cliente_id,status,tecnico,descricao,
                valor_mao_obra,valor_materiais,custo_materiais,valor_total,
                forma_pagamento,tempo_horas,texto_adicional FROM ordens_servico
                WHERE id=?''', (oid,)).fetchone()
            materials = c.execute('''SELECT item,quantidade,unidade,
                valor_unitario,valor_total FROM materiais_os WHERE os_id=?
                ORDER BY id''', (oid,)).fetchall()
            events = c.execute('''SELECT acao FROM os_eventos WHERE os_id=?
                ORDER BY id''', (oid,)).fetchall()
            closing = c.execute('''SELECT situacao FROM os_encerramentos
                WHERE os_id=?''', (oid,)).fetchone()
            return (tuple(order), tuple(map(tuple, materials)),
                    tuple(event[0] for event in events),
                    closing['situacao'] if closing else None)

    def _web_create(self):
        filename, pid, cid, principal = self.databases['web']
        ui = Mock()
        ui.redir.return_value = 'redirect'
        result = os_commands.execute_http(ui, filename, principal,
            '/os/nova/salvar', self.payload(cid),
            {'pid': pid, 'nome': 'Responsible'})
        self.assertEqual(result, 'redirect')
        with ext.db(filename) as c:
            return c.execute('SELECT id FROM ordens_servico ORDER BY id DESC').fetchone()[0]

    def _local_create(self):
        filename, _pid, cid, actor = self.databases['local']
        return LocalService(filename).salvar_os(self.input(cid), principal=actor).os_id

    @unittest.expectedFailure  # Lift when GTK/API use the web's canonical writer.
    def test_create_has_the_same_business_rows_and_audit_events(self):
        web_id = self._web_create()
        local_id = self._local_create()
        self.assertEqual(self.snapshot(self.databases['web'][0], web_id),
                         self.snapshot(self.databases['local'][0], local_id))

    @unittest.expectedFailure  # The previous desktop path did not enforce web closing gates.
    def test_close_without_invoice_opt_out_is_denied_on_both_surfaces(self):
        web_id = self._web_create()
        local_id = self._local_create()
        web, pid, cid, actor = self.databases['web']
        with self.assertRaisesRegex(ValueError, 'nota fiscal'):
            os_commands.execute_http(Mock(), web, actor,
                f'/os/{web_id}/salvar', self.payload(cid,
                    acao='Concluída', modo_envio='encerrar',
                    relatorio_tecnico='Executado', sem_destinatario='1'),
                {'pid': pid, 'nome': 'Responsible'})
        local, _pid, cid, actor = self.databases['local']
        with self.assertRaisesRegex(ValueError, 'nota fiscal'):
            LocalService(local).salvar_os(self.input(cid, os_id=local_id,
                acao='Concluída', relato='Executado'), principal=actor)

    def test_foreign_object_is_rejected_before_any_write(self):
        filename, pid, cid, actor = self.databases['local']
        oid = self._local_create()
        other_pid = ext.cadastrar(filename, 'Foreign',
                                  'foreign@example.invalid', 'Password12345')
        foreign = Principal(other_pid, 'employee', organization_id='autoseg',
                            provider_id=other_pid)
        before = self.snapshot(filename, oid)
        with self.assertRaises(PermissionError):
            LocalService(filename).salvar_os(self.input(cid, os_id=oid,
                descricao='Unauthorized change'), principal=foreign)
        self.assertEqual(before, self.snapshot(filename, oid))

    def test_missing_actor_cannot_create(self):
        filename, _pid, cid, _actor = self.databases['local']
        with self.assertRaises(PermissionError):
            LocalService(filename).salvar_os(self.input(cid))


if __name__ == '__main__':
    unittest.main()
