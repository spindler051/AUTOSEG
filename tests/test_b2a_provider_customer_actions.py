"""B2a regression scenarios; author did not execute tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from officina.core import banco, prestadores_ext as ext, cadastros_v9
from flavors.autoseg.modules.action_sections.providers import ACTIONS
from flavors.autoseg.modules.action_sections.customers import ACTIONS as CUSTOMER_ACTIONS


class B2aTests(unittest.TestCase):
    def test_admin_role_is_not_provider_edit(self):
        actions = {a.id: a for a in ACTIONS}
        self.assertEqual(actions['providers.edit'].gtk_handler, '_editar_prestador')
        self.assertEqual(actions['providers.edit'].service, 'atualizar_prestador')
        self.assertEqual(actions['providers.admin_role'].gtk_handler, '_admin_prestador')
        self.assertEqual(next(a for a in CUSTOMER_ACTIONS if a.id == 'customers.deactivate').gtk_handler,
                         '_desativar_cliente')

    def test_provider_update_does_not_change_password_role_or_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'b2a.db')
            banco.criar_banco(path)
            ext.instalar(path)
            cadastros_v9.instalar(path)
            provider = ext.cadastrar(path, 'Nome A','abc@example.net','senha_com_mais_10')
            with ext.db(path) as con:
                before = con.execute('SELECT senha_hash,ativo FROM prestadores WHERE id=?',
                                     (provider,)).fetchone()
            updated = ext.atualizar_cadastro_prestador(path, provider, {
                'nome':'Nome B','email':'novo@example.net','telefone':'51999990000',
                'documento':'','especialidade':'CFTV','admin':True,'senha':'wrong'})
            self.assertEqual(updated['nome'],'Nome B')
            with ext.db(path) as con:
                after = con.execute('SELECT senha_hash,ativo FROM prestadores WHERE id=?',
                                    (provider,)).fetchone()
            self.assertEqual(tuple(before),tuple(after))

    def test_duplicate_email_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'b2a.db')
            banco.criar_banco(path); ext.instalar(path)
            a = ext.cadastrar(path,'A','a@example.org','long_password_1')
            ext.cadastrar(path,'B','b@example.org','long_password_2')
            with self.assertRaises(ValueError):
                ext.atualizar_cadastro_prestador(path,a,{
                    'nome':'A','email':'b@example.org','telefone':'',
                    'documento':'','especialidade':''})
