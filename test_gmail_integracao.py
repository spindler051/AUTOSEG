"""Testes da integração automática do Gmail na conclusão de OS.

Não envia e-mails reais: `enviar_email_gmail` é substituído por um mock.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path

import atendimento_os as aten
import cadastros_v9 as cad9
import fluxo_os as fluxo
import prestadores_ext as ext
import portal_negocios as neg
from banco import criar_banco
import gmail_service


class GmailIntegracao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoseg_gmail_')
        self.banco = str(Path(self.tmp.name) / 'teste.db')
        criar_banco(self.banco)
        for modulo in (ext, fluxo, aten, cad9):
            modulo.instalar(self.banco)
        import produtividade_os as prod
        prod.instalar(self.banco)
        self.env_anterior = os.environ.get('AUTOSEG_GMAIL_DESATIVADO')

    def tearDown(self):
        if self.env_anterior is None:
            os.environ.pop('AUTOSEG_GMAIL_DESATIVADO', None)
        else:
            os.environ['AUTOSEG_GMAIL_DESATIVADO'] = self.env_anterior
        self.tmp.cleanup()

    def _concluir_com_pdf(self):
        pid = ext.cadastrar(self.banco, 'Técnico Teste', 'tec@example.org', 'senha-bem-segura-2026')
        dados = {k: '' for k in neg.CLIENTE_CAMPOS}
        dados.update(nome='Cliente Email', tipo_pessoa='Física', status='Ativo',
                     email='cliente@example.org', cidade='Porto Alegre')
        cid = neg.cliente_salvar(self.banco, dados, pid)
        d = {'cliente_id': str(cid), 'descricao': 'Serviço de teste Gmail',
             'tecnico': 'Técnico Teste', 'forma_pagamento': 'PIX',
             'valor_mao_obra': '100', 'valor_materiais_manual': '0',
             'relatorio_tecnico': 'Relatório técnico final.',
             'materiais_presentes': '1', 'acao_status': 'salvar'}
        oid = neg.os_salvar(self.banco, d, pid)
        ext.atribuir(self.banco, oid, pid)
        conclusao = dict(d)
        conclusao['acao_status'] = 'Concluída'
        neg.os_salvar(self.banco, conclusao, pid, oid)
        # publica o PDF para o envio ter um anexo
        fluxo.publicar_relatorio(self.banco, oid)
        return oid

    def test_envio_automatico_registra_enviado(self):
        os.environ.pop('AUTOSEG_GMAIL_DESATIVADO', None)
        oid = self._concluir_com_pdf()
        original = gmail_service.enviar_email_gmail
        chamadas = []
        detalhes = {}
        def fake_enviar(destinatario, assunto, corpo_html, cc=None,
                        caminho_pdf_relatorio=None, caminho_pdf_nf=None, usar_bcc=False):
            detalhes.update(destinatario=destinatario, corpo=corpo_html, nf=caminho_pdf_nf,
                            bcc=usar_bcc)
            chamadas.append((destinatario, assunto, caminho_pdf_relatorio))
            return 'msg-fake-123'
        gmail_service.enviar_email_gmail = fake_enviar
        try:
            gmail_service.enviar_relatorio_os_concluida(self.banco, oid)
            import produtividade_os as prod
            status = None
            for _ in range(50):
                with ext.db(self.banco) as c:
                    r = c.execute('SELECT status,message_id,destinatarios_json FROM produtividade_email WHERE os_id=?',
                                  (oid,)).fetchone()
                if r and r['status'] in ('enviado', 'falhou'):
                    status = r
                    break
                time.sleep(0.05)
            self.assertIsNotNone(status, 'envio não concluiu')
            self.assertEqual(status['status'], 'enviado')
            self.assertEqual(status['message_id'], 'msg-fake-123')
            self.assertIn('cliente@example.org', status['destinatarios_json'])
            self.assertEqual(len(chamadas), 1)
            self.assertIn('cliente@example.org', chamadas[0][0])
            self.assertTrue(chamadas[0][2].endswith('.pdf'))
        finally:
            gmail_service.enviar_email_gmail = original

    def test_falha_de_envio_nao_trava_e_registra_falhou(self):
        os.environ.pop('AUTOSEG_GMAIL_DESATIVADO', None)
        oid = self._concluir_com_pdf()
        original = gmail_service.enviar_email_gmail
        def fake_erro(*args, **kwargs):
            raise RuntimeError('sem conexão')
        gmail_service.enviar_email_gmail = fake_erro
        try:
            gmail_service.enviar_relatorio_os_concluida(self.banco, oid)
            import produtividade_os as prod
            status = None
            for _ in range(50):
                with ext.db(self.banco) as c:
                    r = c.execute('SELECT status,erro FROM produtividade_email WHERE os_id=?', (oid,)).fetchone()
                if r and r['status'] == 'falhou':
                    status = r
                    break
                time.sleep(0.05)
            self.assertIsNotNone(status)
            self.assertIn('sem conexão', status['erro'])
        finally:
            gmail_service.enviar_email_gmail = original

    def test_modo_desativado_nao_envia(self):
        os.environ['AUTOSEG_GMAIL_DESATIVADO'] = '1'
        oid = self._concluir_com_pdf()
        original = gmail_service.enviar_email_gmail
        chamou = []
        def fake(*args, **kwargs):
            chamou.append(1)
            return 'x'
        gmail_service.enviar_email_gmail = fake
        try:
            gmail_service.enviar_relatorio_os_concluida(self.banco, oid)
            time.sleep(0.2)
            self.assertEqual(chamou, [])
            import produtividade_os as prod
            with ext.db(self.banco) as c:
                r = c.execute('SELECT status FROM produtividade_email WHERE os_id=?', (oid,)).fetchone()
            self.assertEqual(r['status'], 'pendente')
        finally:
            gmail_service.enviar_email_gmail = original

    def test_multiplos_destinatarios_nota_fiscal_e_dados_bancarios(self):
        os.environ.pop('AUTOSEG_GMAIL_DESATIVADO', None)
        oid = self._concluir_com_pdf()
        import produtividade_os as prod
        with ext.db(self.banco) as c:
            pid = c.execute('SELECT prestador_id FROM os_responsaveis WHERE os_id=?', (oid,)).fetchone()['prestador_id']
            c.execute('UPDATE clientes SET email=?,sindico_email=?,administradora_email=? WHERE id=(SELECT cliente_id FROM ordens_servico WHERE id=?)',
                      ('cliente@example.org', 'sindico@example.org', 'adm@example.org', oid))
        ext.salvar_config_prestador(self.banco, pid, {
            'banco_titular': 'Favorecido Teste', 'banco_nome': 'Banco Exemplo',
            'banco_agencia': '1234', 'banco_conta': '56789-0', 'chave_pix': 'pix-teste'})
        nf = b'%PDF-1.4\n% nota fiscal ficticia\n%%EOF\n'
        ext.salvar_nota_fiscal(self.banco, oid, pid, 'nf_teste.pdf', nf)
        original = gmail_service.enviar_email_gmail
        capturado = {}
        def fake(destinatario, assunto, corpo_html, cc=None, caminho_pdf_relatorio=None,
                 caminho_pdf_nf=None, usar_bcc=False):
            capturado.update(destinatario=destinatario, corpo=corpo_html,
                             nf=caminho_pdf_nf, bcc=usar_bcc)
            return 'msg-multi-1'
        gmail_service.enviar_email_gmail = fake
        try:
            destinatarios = prod.destinatarios_para_os(
                self.banco, oid, ['cliente', 'sindico', 'administradora'], 'extra@example.org')
            self.assertEqual(len(destinatarios), 4)
            gmail_service.enviar_relatorio_os_concluida(self.banco, oid, destinatarios)
            status = None
            for _ in range(50):
                with ext.db(self.banco) as c:
                    r = c.execute('SELECT status,message_id,destinatarios_json FROM produtividade_email WHERE os_id=?',
                                  (oid,)).fetchone()
                if r and r['status'] in ('enviado', 'falhou'):
                    status = r
                    break
                time.sleep(0.05)
            self.assertEqual(status['status'], 'enviado')
            self.assertEqual(status['message_id'], 'msg-multi-1')
            for email in ('cliente@example.org', 'sindico@example.org',
                          'adm@example.org', 'extra@example.org'):
                self.assertIn(email, status['destinatarios_json'])
            self.assertEqual(len(capturado['destinatario']), 4)
            self.assertTrue(capturado['bcc'])
            self.assertTrue(str(capturado['nf']).endswith('.pdf'))
            self.assertIn('Favorecido Teste', capturado['corpo'])
            self.assertIn('pix-teste', capturado['corpo'])
        finally:
            gmail_service.enviar_email_gmail = original


if __name__ == '__main__':
    unittest.main(verbosity=2)
