"""C2 review-only regression coverage. No tests were run when authored.

The reviewer executes the suite on Arch with the complete Step 0 / B1 / C1
base. UI render smoke checks still require a real Arch GTK environment.
"""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules.autoseg_form_contracts import WORK, work_fields
from officina.application.contracts import OSInput
from officina.application.local_service import LocalService
from officina.application.object_policy import Principal
from officina.application.os_write_service import OSCommand, write_data, _recipient_refs
from officina.application.work_rateio_service import contexto, definir
from officina.core import (atendimento_os, banco, cadastros_v9, composicao,
                          estoque_materiais, fluxo_os, prestadores_ext as ext,
                          produtividade_os)


class C2ContractTest(unittest.TestCase):
    def test_all_five_c2_groups_share_web_gtk_descriptors(self):
        for name in ('material_item[]', 'material_qtd[]', 'material_unidade[]',
                     'material_unit[]', 'material_total', 'base_percentuais',
                     'aplicar_composicao', 'cobrar_visita', 'composicao_yaml',
                     'composicao_preview', 'destinatario_sel[]',
                     'destinatarios_presente', 'sem_destinatario',
                     'sem_nota_fiscal', 'nota_fiscal', 'rateio_manual_tecnico',
                     'rateio_manual_valor'):
            field = WORK.field(name)
            self.assertIn('web', field.surfaces)
            self.assertIn('gtk', field.surfaces)
            self.assertTrue(field.label)
        self.assertEqual(WORK.field('destinatario_sel[]').options,
                         ('cliente', 'sindico', 'administradora'))
        self.assertEqual([f.id for f in WORK.on('gtk')],
                         [f.id for f in WORK.on('web')])

    @staticmethod
    def entrada(**mudancas):
        fields = dict(os_id=10, cliente_id=11, tecnico='', descricao='C2',
                      valor_mao_obra=20.0, valor_materiais=0.0,
                      custo_materiais=0.0, valor_total=40.0,
                      forma_pagamento='PIX', urgencia='Normal', observacoes='',
                      texto_adicional='', dados_incompletos=0, tempo_horas=0.0,
                      composicao_json='', base_percentuais='total',
                      materiais=(), acao='salvar', relato='', motivo='')
        fields.update(mudancas)
        return OSInput(**fields)

    def test_material_without_quantity_uses_canonical_empty_web_value(self):
        command = OSCommand.from_desktop(self.entrada(
            materiais=({'item': 'Rolo', 'quantidade': None, 'unidade': 'un',
                        'valor_unitario': 20.0},)), actor_id=3)
        self.assertEqual(command.fields['material_qtd[]'], [''])
        self.assertEqual(command.fields['material_item[]'], ['Rolo'])
        self.assertEqual(command.fields['material_unit[]'], ['20.0'])
        self.assertNotIn('valor_total_override', command.fields)

    def test_declarative_yaml_and_json_use_same_service_parser(self):
        yaml_source = '- id: servico_c2\n  nome: Serviço\n  valor: 40.00\n'
        json_source = '[{"id":"servico_c2","nome":"Serviço","valor":40.0}]'
        self.assertEqual(composicao.parse_declarativa(yaml_source),
                         composicao.parse_declarativa(json_source))
        with self.assertRaises(ValueError):
            composicao.parse_declarativa('[' * 65537)

    def test_explicit_recipient_refs_invoice_and_conclusion_rateio(self):
        command = OSCommand.from_desktop(self.entrada(
            acao='Concluída', relato='Concluída',
            destinatarios=('cliente', 'administradora'),
            nota_fiscal=('nota.pdf', b'%PDF-1.7\n'),
            rateio_manual_tecnico=('6',), rateio_manual_valor=('12,50',)), actor_id=2)
        self.assertEqual(command.fields['destinatarios_presente'], '1')
        self.assertEqual(command.fields['destinatario_sel[]'],
                         ['cliente', 'administradora'])
        self.assertEqual(command.fields['rateio_tecnico[]'], ['6'])
        self.assertEqual(command.fields['rateio_valor[]'], ['12,50'])
        self.assertEqual(command.fields['nota_fiscal'][0], 'nota.pdf')
        self.assertNotIn('email', command.fields)
        self.assertNotIn('destinatario_email', command.fields)

    def test_explicit_no_recipient_and_no_invoice_are_preserved(self):
        command = OSCommand.from_desktop(self.entrada(
            destinatarios=(), sem_destinatario=True, sem_nota_fiscal=True),
            actor_id=2)
        self.assertEqual(command.fields['destinatarios_presente'], '1')
        self.assertEqual(command.fields['destinatario_sel[]'], [])
        self.assertEqual(command.fields['sem_destinatario'], '1')
        self.assertEqual(command.fields['sem_nota_fiscal'], '1')

    def test_declarative_composition_submitted_as_source_not_saved_json(self):
        declaration = [{'id': 'servico_c2', 'nome': 'Serviço', 'valor': '40.00'}]
        command = OSCommand.from_desktop(self.entrada(
            composicao_yaml=declaration), actor_id=2)
        self.assertEqual(command.fields['composicao_yaml'], declaration)
        self.assertNotIn('composicao_json', command.fields)

    def test_step_zero_is_only_command_writer(self):
        command = OSCommand.from_desktop(self.entrada(), actor_id=2)
        with patch('officina.application.os_write_service.business.os_salvar',
                   return_value=101) as sql_writer:
            self.assertEqual(write_data('test.db', command), 101)
        sql_writer.assert_called_once()


class C2LiveServiceTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix='autoseg_c2_')
        self.addCleanup(self.tempdir.cleanup)
        self.db = str(Path(self.tempdir.name) / 'c2.db')
        banco.criar_banco(self.db)
        for module in (ext, fluxo_os, atendimento_os, cadastros_v9,
                       estoque_materiais, produtividade_os):
            module.instalar(self.db)
        composicao.instalar()
        composicao.instalar_banco(self.db)
        self.admin = ext.cadastrar(self.db, 'Admin C2',
                                   'c2-admin@invalid.test', 'Password12345')
        self.worker = ext.cadastrar(self.db, 'Worker C2',
                                    'c2-worker@invalid.test', 'Password12345')
        self.stranger = ext.cadastrar(self.db, 'Stranger C2',
                                      'c2-stranger@invalid.test', 'Password12345')
        cadastros_v9.definir_admin(self.db, self.admin, True)
        self.admin_actor = Principal(self.admin, 'admin',
                                     organization_id='autoseg', provider_id=self.admin)
        self.worker_actor = Principal(self.worker, 'employee',
                                      organization_id='autoseg', provider_id=self.worker)
        self.stranger_actor = Principal(self.stranger, 'employee',
                                        organization_id='autoseg', provider_id=self.stranger)
        self.service = LocalService(self.db)
        with ext.db(self.db) as conn:
            cust = conn.execute("INSERT INTO clientes(nome,status,email,sindico_email) "
                                "VALUES('Cliente C2','Ativo','client@invalid.test',"
                                "'sindico@invalid.test')").lastrowid
            self.os_id = conn.execute('''INSERT INTO ordens_servico
                (numero_os,cliente_id,status,descricao,valor_total)
                VALUES('C2-1',?,'Aberta','Teste C2',100)''', (cust,)).lastrowid
            self.foreign_id = conn.execute('''INSERT INTO ordens_servico
                (numero_os,cliente_id,status,descricao,valor_total)
                VALUES('C2-2',?,'Aberta','Teste alheio',100)''', (cust,)).lastrowid
            conn.execute('''INSERT INTO os_responsaveis(os_id,prestador_id,assumido_em)
                VALUES(?,?,?)''', (self.os_id, self.worker, ext.agora()))

    def test_authenticated_projection_reaches_same_fields(self):
        form = work_fields(self.db, self.worker_actor, os_id=self.os_id)
        self.assertEqual([f.id for f in form], [f.id for f in WORK.fields])
        ctx = self.service.contexto_os(self.os_id, principal=self.worker_actor)['c2']
        self.assertEqual(ctx['contatos']['cliente'], 'client@invalid.test')
        self.assertEqual(ctx['contatos']['sindico'], 'sindico@invalid.test')
        self.assertEqual(ctx['contatos']['administradora'], '')
        self.assertTrue(ctx['rateio_editavel'])

    def test_stranger_cannot_read_or_modify_foreign_order(self):
        with self.assertRaises(PermissionError):
            work_fields(self.db, self.stranger_actor, os_id=self.os_id)
        with self.assertRaises(PermissionError):
            contexto(self.db, self.os_id, self.stranger_actor)
        with self.assertRaises(PermissionError):
            definir(self.db, self.stranger_actor, self.os_id, self.admin, '5')
        with ext.db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM produtividade_rateios '
                                          'WHERE os_id=?', (self.os_id,)).fetchone()[0], 0)

    def test_admin_can_set_and_remove_without_second_rateio_writer(self):
        self.assertEqual(self.service.definir_rateio_os(
            self.os_id, self.stranger, '15,00', principal=self.admin_actor), 1500)
        with ext.db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT valor_centavos FROM produtividade_rateios '
                                          'WHERE os_id=? AND tecnico_id=?',
                                          (self.os_id, self.stranger)).fetchone()[0], 1500)
        self.assertEqual(self.service.definir_rateio_os(
            self.os_id, self.stranger, '0', principal=self.admin_actor), 0)

    def test_over_budget_rateio_rolls_back(self):
        with self.assertRaises(ValueError):
            self.service.definir_rateio_os(
                self.os_id, self.stranger, '101', principal=self.admin_actor)
        with ext.db(self.db) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM produtividade_rateios '
                                          'WHERE os_id=?', (self.os_id,)).fetchone()[0], 0)

    def test_invoice_pdf_header_and_limit_share_domain_validator(self):
        with self.assertRaisesRegex(ValueError, 'PDF válido'):
            ext.salvar_nota_fiscal(self.db, self.os_id, self.worker,
                                  'invalida.pdf', b'nao e um PDF')
        with self.assertRaisesRegex(ValueError, '20 MB'):
            ext.salvar_nota_fiscal(self.db, self.os_id, self.worker,
                                  'grande.pdf', b'%PDF-' + b'x' * (20 * 1024 * 1024))

    def test_admin_can_attach_invoice_to_another_providers_os(self):
        with tempfile.TemporaryDirectory() as notas, \
             patch.object(ext, 'NOTAS', Path(notas)):
            nota_id = ext.salvar_nota_fiscal(
                self.db, self.os_id, self.admin, 'admin.pdf',
                b'%PDF-1.4\n% admin invoice\n%%EOF\n')
            with ext.db(self.db) as conn:
                row = conn.execute(
                    'SELECT prestador_id,nome_original FROM os_notas_fiscais WHERE id=?',
                    (nota_id,)).fetchone()
            self.assertEqual(row['prestador_id'], self.admin)
            self.assertEqual(row['nome_original'], 'admin.pdf')
            with self.assertRaises(PermissionError):
                ext.salvar_nota_fiscal(
                    self.db, self.os_id, self.stranger, 'stranger.pdf',
                    b'%PDF-1.4\n% denied\n%%EOF\n')

    def test_explicit_recipient_refs_must_have_existing_contact(self):
        with ext.db(self.db) as conn:
            cust = conn.execute('SELECT cliente_id FROM ordens_servico WHERE id=?',
                                (self.os_id,)).fetchone()['cliente_id']
            self.assertEqual(_recipient_refs(conn, cust, {
                'destinatarios_presente': '1',
                'destinatario_sel[]': ['cliente', 'sindico'],
            }), ['cliente', 'sindico'])
            with self.assertRaises(ValueError):
                _recipient_refs(conn, cust, {
                    'destinatarios_presente': '1',
                    'destinatario_sel[]': ['administradora'],
                })
            with self.assertRaises(ValueError):
                _recipient_refs(conn, cust, {
                    'destinatarios_presente': '1',
                    'destinatario_sel[]': [],
                })

    def test_closed_archived_order_projection_is_readonly_and_rateio_denied(self):
        with ext.db(self.db) as conn:
            conn.execute("UPDATE ordens_servico SET status='Cancelada' WHERE id=?",
                         (self.os_id,))
        fields = work_fields(self.db, self.admin_actor, os_id=self.os_id)
        self.assertTrue(all(field.visibility == 'readonly' for field in fields))
        with self.assertRaises(ValueError):
            self.service.definir_rateio_os(
                self.os_id, self.stranger, '5', principal=self.admin_actor)

    def test_revoked_provider_cannot_read_or_write_rateio(self):
        with ext.db(self.db) as conn:
            conn.execute('UPDATE prestadores SET ativo=0 WHERE id=?', (self.worker,))
        with self.assertRaises(PermissionError):
            work_fields(self.db, self.worker_actor, os_id=self.os_id)
        with self.assertRaises(PermissionError):
            contexto(self.db, self.os_id, self.worker_actor)
        with self.assertRaises(PermissionError):
            definir(self.db, self.worker_actor, self.os_id, self.stranger, '5')

    def test_stale_admin_claim_does_not_expand_permissions(self):
        stale_admin = replace(self.stranger_actor, role='admin')
        with self.assertRaises(PermissionError):
            work_fields(self.db, stale_admin, os_id=self.os_id)
        with self.assertRaises(PermissionError):
            definir(self.db, stale_admin, self.os_id, self.worker, '5')


if __name__ == '__main__':
    unittest.main(verbosity=2)
