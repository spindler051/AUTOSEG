"""P0 review: one ObjectPolicy authority for organization list and downloads.

All HTTP requests use ephemeral ports and a disposable SQLite file.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from flavors.autoseg.modules import accounts, client_features
from officina.core import cadastros_v9 as cad, fluxo_os as fluxo, prestadores_ext as ext
from tests import test_officina_web as _fixture


class ReviewedDocumentsHttp(unittest.TestCase):
    def setUp(self):
        _fixture.OfficinaWebHttpTest.setUp(self)
        self.old_report_dir, self.old_note_dir = ext.RELATORIOS, ext.NOTAS
        ext.RELATORIOS = Path(self.tmp.name) / 'relatorios'
        ext.NOTAS = Path(self.tmp.name) / 'notas'
        self.addCleanup(self._restore_dirs)
        fluxo.instalar(self.db)
        self.account = accounts.find_account_by_identifier(
            self.db, 'email', 'customer@example.test').id

    def _restore_dirs(self):
        ext.RELATORIOS, ext.NOTAS = self.old_report_dir, self.old_note_dir

    def browser(self):
        return _fixture.OfficinaWebHttpTest.browser()

    def req(self, *args, **kwargs):
        return _fixture.OfficinaWebHttpTest.req(self, *args, **kwargs)

    def login(self, *args, **kwargs):
        return _fixture.OfficinaWebHttpTest.login(self, *args, **kwargs)

    def _work(self, uid, title):
        return _fixture.OfficinaWebHttpTest._create_owned_work(self, uid, title)

    def _org(self, name):
        with ext.db(self.db) as c:
            return c.execute('INSERT INTO v9_organizacoes(nome,tipo,criado_em) '
                             "VALUES(?,'Condomínio',?)", (name, ext.agora())).lastrowid

    def _call(self, org_id, os_id, uid):
        with ext.db(self.db) as c:
            return c.execute('''INSERT INTO v9_chamados(
                organizacao_id,usuario_id,descricao,urgencia,criado_em,os_id)
                VALUES(?,?,'Serviço solicitado','Normal',?,?)''',
                (org_id, uid, ext.agora(), os_id)).lastrowid

    def _report(self, os_id):
        published = ext.RELATORIOS / 'publicados'
        published.mkdir(parents=True, exist_ok=True)
        body = b'%PDF-1.4\n' + b'P0 authorized fixture\n' * 8 + b'%%EOF\n'
        filename = published / f'report_{os_id}.pdf'
        filename.write_bytes(body)
        with ext.db(self.db) as c:
            c.execute("UPDATE ordens_servico SET status='Concluída' WHERE id=?", (os_id,))
            c.execute('''INSERT INTO os_documentos(
                os_id,tipo,versao,caminho,sha256,publicado_em)
                VALUES(?,'relatorio_pdf',1,?,?,?)''',
                (os_id, str(filename), hashlib.sha256(body).hexdigest(), ext.agora()))
        return body

    def _role(self, role, org_id):
        with ext.db(self.db) as c:
            if role == 'sindico':
                c.execute('''INSERT INTO v9_responsaveis(
                    organizacao_id,usuario_id,papel,atribuido_por,atribuido_em)
                    VALUES(?,?,'Síndico','Admin',?)''',
                    (org_id, self.client_id, ext.agora()))
            elif role == 'zelador':
                c.execute('''INSERT INTO v9_vinculos(
                    organizacao_id,usuario_id,papel,situacao,criado_em)
                    VALUES(?,?,'Zelador','Aprovado',?)''',
                    (org_id, self.client_id, ext.agora()))
        accounts.set_client_role(self.db, self.account, role)

    def test_own_report_invoice_and_call_pdf_positive_other_customer_negative(self):
        oid = self._work(self.client_id, 'OS com relatório e nota próprios')
        report = self._report(oid)
        invoice_id = ext.salvar_nota_fiscal(self.db, oid, None,
                                             'nota.pdf', b'%PDF-1.4\nnota\n%%EOF\n')
        org = self._org('Condomínio do chamado pessoal')
        call_id = self._call(org, oid, self.client_id)
        mine, _, _, _ = self.login('customer@example.test', self.client_pass)
        other, _, _, _ = self.login('other@example.test', self.client_pass)
        for route in (f'/cliente/os/{oid}/pdf',
                      f'/cliente/nota/{invoice_id}',
                      f'/cliente/chamado/{call_id}/pdf'):
            with self.subTest(route=route):
                status, headers, contents = self.req(mine, route)
                self.assertEqual(status, 200)
                self.assertIn('application/pdf', headers['Content-Type'])
                self.assertTrue(contents.startswith(b'%PDF-'))
                self.assertEqual(self.req(other, route)[0], 404)
        self.assertEqual(report[:5], b'%PDF-')

    def test_organization_history_and_report_roles_and_cross_org(self):
        for role in ('sindico', 'zelador'):
            with self.subTest(role=role):
                # Independent scenarios: reassign the same account role, with
                # distinct organizations and current membership on each login.
                org_id = self._org(f'Condomínio {role}')
                oid = self._work(self.other_id, f'OS do {role}')
                self._call(org_id, oid, self.other_id)
                self._report(oid)
                self._role(role, org_id)
                client, code, _, _ = self.login('customer@example.test', self.client_pass)
                self.assertEqual(code, 303)
                page_code, _, page = self.req(client, '/')
                self.assertEqual(page_code, 200)
                self.assertIn(f'/cliente/sindico?org={org_id}'.encode(), page)
                listing_code, _, listing = self.req(client, f'/cliente/sindico?org={org_id}')
                self.assertEqual(listing_code, 200)
                self.assertIn(f'/cliente/organizacao/{org_id}/os/{oid}/pdf'.encode(), listing)
                self.assertEqual(self.req(client,
                    f'/cliente/organizacao/{org_id}/os/{oid}/pdf')[0], 200)
                other_org = self._org('Organização sem vínculo')
                other_oid = self._work(self.other_id, 'OS de outra organização')
                self._call(other_org, other_oid, self.other_id)
                self._report(other_oid)
                self.assertEqual(self.req(client,
                    f'/cliente/organizacao/{other_org}/os/{other_oid}/pdf')[0], 404)

    def test_named_customer_has_no_organization_permission(self):
        org_id = self._org('Condomínio somente responsável nomeado')
        oid = self._work(self.other_id, 'OS de condomínio protegida')
        self._call(org_id, oid, self.other_id)
        self._report(oid)
        with ext.db(self.db) as c:
            c.execute('''INSERT INTO v9_responsaveis(
                organizacao_id,usuario_id,papel,atribuido_por,atribuido_em)
                VALUES(?,?,'Síndico','Admin',?)''',
                (org_id, self.client_id, ext.agora()))
        client, code, _, _ = self.login('customer@example.test', self.client_pass)
        self.assertEqual(code, 303)
        self.assertNotIn(b'Consultar todas as OS', self.req(client, '/')[2])
        self.assertEqual(self.req(client, f'/cliente/sindico?org={org_id}')[0], 404)
        self.assertEqual(self.req(client,
            f'/cliente/organizacao/{org_id}/os/{oid}/pdf')[0], 404)


if __name__ == '__main__':
    unittest.main()
