"""Provider-only unified login adapter and HTTP integration tests."""
import http.cookiejar
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flavors.autoseg.modules import accounts, auth, identity, login_web, web_session
from flavors.autoseg.modules import portal_prestador as portal_module
from flavors.autoseg.modules.portal_prestador import PortalPrestador
from officina.application.object_policy import Principal
from officina.core import cadastros_v9 as cad
from officina.core import prestadores_ext as ext
from officina.core.banco import criar_banco


class Handler:
    headers = {}
    def pagina(self, title, body, session):
        self.title, self.body, self.session = title, body, session
        return 'sent'


class LoginWebTest(unittest.TestCase):
    def setUp(self):
        self.handler = Handler()
        self.ident = identity.Identity('provider', 3, 'Fictitious Provider', 'tech@example.invalid', provider_id=3)
        self.membership = identity.Membership('provider', 3, 'employee', provider_id=3)
        self.principal = Principal(3, 'employee', provider_id=3)

    def test_render_form(self):
        self.assertEqual('sent', login_web.render_login(self.handler))
        self.assertEqual('Entrar', self.handler.title)
        self.assertIn('action="/entrar"', self.handler.body)
        self.assertIn('name="identificador"', self.handler.body)
        self.assertIn('name="senha"', self.handler.body)
        self.assertIn('autocomplete="username"', self.handler.body)
        self.assertIn('autocomplete="current-password"', self.handler.body)
        self.assertIn('href="/login"', self.handler.body)

    def test_html_escaping(self):
        login_web.render_login(self.handler, '<tag>', '<script>')
        self.assertNotIn('<tag>', self.handler.body)
        self.assertNotIn('<script>', self.handler.body)
        self.assertIn('&lt;script&gt;', self.handler.body)

    def test_provider_creates_session(self):
        result = auth.LoginResult(5, self.ident, self.membership, self.principal, 'account')
        created = ('opaque-token', SimpleNamespace(csrf='x'))
        with (patch.object(login_web.auth, 'authenticate', return_value=result),
              patch.object(login_web.web_session, 'current_credential', return_value='hash'),
              patch.object(login_web.web_session, 'create', return_value=created) as create):
            self.assertEqual(created, login_web.authenticate_and_create('db', 'tech@example.invalid', 'pw'))
            self.assertEqual('account', create.call_args.args[6])

    def test_client_rejected_before_session(self):
        client = identity.Identity('client', 8, 'Client', client_id=15)
        membership = identity.Membership('client', 8, 'customer', client_id=15)
        principal = Principal(8, 'customer', client_id=15)
        result = auth.LoginResult(None, client, membership, principal, 'legacy')
        with (patch.object(login_web.auth, 'authenticate', return_value=result),
              patch.object(login_web.web_session, 'create') as create):
            with self.assertRaises(auth.LoginError) as err:
                login_web.authenticate_and_create('db', 'cpf', 'password')
            self.assertEqual('invalid', err.exception.code)
            create.assert_not_called()

    def test_missing_credential(self):
        result = auth.LoginResult(None, self.ident, self.membership, self.principal, 'legacy')
        with (patch.object(login_web.auth, 'authenticate', return_value=result),
              patch.object(login_web.web_session, 'current_credential', return_value=None)):
            with self.assertRaises(auth.LoginError) as err:
                login_web.authenticate_and_create('db', 'id', 'pw')
            self.assertEqual('invalid', err.exception.code)

    def test_provider_session_flag_off_does_not_resolve(self):
        with (patch.object(login_web.login_flags, 'unified_login_enabled', return_value=False),
              patch.object(login_web.web_session, 'resolve') as resolver):
            self.assertIsNone(login_web.provider_session(self.handler, 'db'))
            resolver.assert_not_called()

    def test_provider_session_flag_on_maps_legacy_dict(self):
        self.handler.headers = {'Cookie': 'autosseg_unified=' + 'A' * 48}
        session = SimpleNamespace(identity=self.ident, principal=self.principal,
            csrf='csrf', credential='hash', telemetry_session='random', expires_at=123.0)
        with (patch.object(login_web.login_flags, 'unified_login_enabled', return_value=True),
              patch.object(login_web.web_session, 'resolve', return_value=session)):
            result = login_web.provider_session(self.handler, 'db')
            self.assertEqual(3, result['pid'])
            self.assertEqual('Fictitious Provider', result['nome'])
            self.assertTrue(result['unified'])
            self.assertFalse(result['admin'])
            self.assertNotIn('cred', result)

    def test_provider_session_rejects_client_and_fake_tokens(self):
        self.handler.headers = {'Cookie': 'autosseg_unified=' + 'A' * 48}
        client = identity.Identity('client', 8, 'Client', client_id=15)
        session = SimpleNamespace(identity=client, principal=Principal(8, 'customer', client_id=15))
        with (patch.object(login_web.login_flags, 'unified_login_enabled', return_value=True),
              patch.object(login_web.web_session, 'resolve', return_value=session)):
            self.assertIsNone(login_web.provider_session(self.handler, 'db'))
        self.handler.headers = {'Cookie': 'autosseg_unified=invalid'}
        with patch.object(login_web.login_flags, 'unified_login_enabled', return_value=True):
            self.assertIsNone(login_web.provider_session(self.handler, 'db'))

    def test_no_password_in_error(self):
        with patch.object(login_web.auth, 'authenticate', side_effect=auth.LoginError('invalid')):
            with self.assertRaises(auth.LoginError) as err:
                login_web.authenticate_and_create('db', 'user@example.invalid', 's3cret!')
            self.assertNotIn('s3cret!', str(err.exception))
            self.assertNotIn('user@example.invalid', str(err.exception))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _browser(follow=True):
    handlers = [urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
    if not follow:
        handlers.insert(0, _NoRedirect())
    return urllib.request.build_opener(*handlers)


def _request(client, base, path, data=None, headers=None):
    body = (urllib.parse.urlencode(data, doseq=True).encode()
            if data is not None else None)
    request = urllib.request.Request(base + path, body, headers or {})
    try:
        with client.open(request, timeout=20) as response:
            return (response.status, response.headers,
                    response.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as error:
        return (error.code, error.headers,
                error.read().decode('utf-8', 'replace'))


def _flag(value):
    return patch.dict(os.environ, {'AUTOSEG_UNIFIED_LOGIN': value})


def _unified_cookie(headers):
    for value in headers.get_all('Set-Cookie') or ():
        if value.startswith('autosseg_unified='):
            return value
    return None


def _cookie_token(header):
    return header.split(';', 1)[0].split('=', 1)[1]


class UnifiedLoginHttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='login_web_http_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'app.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        accounts.install(self.db)
        self.provider_password = 'ProviderPassword123'
        self.client_password = 'ClientPassword123'
        self.provider_id = ext.cadastrar(
            self.db, 'Provider Example', 'provider@example.test',
            self.provider_password)
        self.client_id = cad.cadastrar_usuario(
            self.db, 'Client Example', '52998224725', '51999999999',
            self.client_password, 'client@example.test')
        accounts.migrate_legacy(self.db, dry_run=False)
        web_session.clear()
        self.addCleanup(web_session.clear)
        self._clear_attempts()
        self.addCleanup(self._clear_attempts)
        self.server = PortalPrestador(self.db, '127.0.0.1', 0)
        self.server.iniciar()
        self.addCleanup(self.server.parar)
        self.base = f'http://127.0.0.1:{self.server.porta}'

    def _token(self, identifier, password):
        result = auth.authenticate(self.db, identifier, password)
        credential = web_session.current_credential(
            self.db, result.source, result.account_id, result.identity)
        token, _session = web_session.create(
            self.db, result.account_id, result.identity, result.membership,
            result.principal, credential, result.source)
        return token

    def _set_provider_active(self, active):
        with ext.db(self.db) as connection:
            connection.execute(
                'UPDATE prestadores SET ativo=? WHERE id=?',
                (int(active), self.provider_id))
            link = connection.execute(
                'SELECT account_id FROM account_links WHERE provider_id=?',
                (self.provider_id,)).fetchone()
            if link:
                connection.execute(
                    'UPDATE accounts SET active=? WHERE id=?',
                    (int(active), link['account_id']))
                connection.execute(
                    'UPDATE account_links SET active=? WHERE account_id=?',
                    (int(active), link['account_id']))

    def _clear_attempts(self):
        with portal_module.LOCK_LOGIN:
            portal_module.TENTATIVAS.clear()

    def test_flag_off_redirects_both_methods(self):
        with _flag(''):
            client = _browser(follow=False)
            status, headers, _body = _request(client, self.base, '/entrar')
            self.assertEqual(303, status)
            self.assertEqual('/login', headers['Location'])
            status, headers, _body = _request(
                client, self.base, '/entrar',
                {'identificador': 'provider@example.test',
                 'senha': self.provider_password})
            self.assertEqual(303, status)
            self.assertEqual('/login', headers['Location'])
            self.assertIsNone(_unified_cookie(headers))

    def test_flag_on_renders_unified_form(self):
        with _flag('1'):
            status, _headers, body = _request(_browser(), self.base, '/entrar')
        self.assertEqual(200, status)
        self.assertIn('name="identificador"', body)
        self.assertIn('name="senha"', body)
        self.assertIn('action="/entrar"', body)
        self.assertIn('href="/login"', body)

    def test_provider_login_opens_portal(self):
        with _flag('1'):
            status, headers, _body = _request(
                _browser(follow=False), self.base, '/entrar',
                {'identificador': 'provider@example.test',
                 'senha': self.provider_password})
            self.assertEqual(303, status)
            self.assertEqual('/', headers['Location'])
            cookie = _unified_cookie(headers)
            self.assertIsNotNone(cookie)
            for attribute in ('HttpOnly', 'SameSite=Strict', 'Path=/'):
                self.assertIn(attribute, cookie)
            token = _cookie_token(cookie)
            status, _headers, body = _request(
                _browser(), self.base, '/',
                headers={'Cookie': f'autosseg_unified={token}'})
        self.assertEqual(200, status)
        self.assertIn('Visão geral', body)

    def test_proxy_header_marks_cookie_secure(self):
        with _flag('1'):
            status, headers, _body = _request(
                _browser(follow=False), self.base, '/entrar',
                {'identificador': 'provider@example.test',
                 'senha': self.provider_password},
                headers={'CF-Ray': 'test'})
        self.assertEqual(303, status)
        self.assertIn('; Secure', _unified_cookie(headers))

    def test_wrong_password_is_generic_and_sets_no_cookie(self):
        with _flag('1'):
            status, headers, body = _request(
                _browser(follow=False), self.base, '/entrar',
                {'identificador': 'provider@example.test',
                 'senha': 'WrongPassword123'})
        self.assertEqual(200, status)
        self.assertIn('Credenciais inválidas.', body)
        self.assertIsNone(_unified_cookie(headers))
        self.assertNotIn('WrongPassword123', body)
        self.assertNotIn('Provider Example', body)
        with ext.db(self.db) as connection:
            stored = connection.execute(
                'SELECT senha_hash FROM prestadores WHERE id=?',
                (self.provider_id,)).fetchone()['senha_hash']
        self.assertNotIn(stored, body)

    def test_client_and_inactive_provider_are_rejected(self):
        with _flag('1'):
            status, headers, body = _request(
                _browser(follow=False), self.base, '/entrar',
                {'identificador': 'client@example.test',
                 'senha': self.client_password})
            self.assertEqual(200, status)
            self.assertIn('Credenciais inválidas.', body)
            self.assertIsNone(_unified_cookie(headers))
            self._set_provider_active(False)
            status, headers, body = _request(
                _browser(follow=False), self.base, '/entrar',
                {'identificador': 'provider@example.test',
                 'senha': self.provider_password})
            self.assertEqual(200, status)
            self.assertIn('Credenciais inválidas.', body)
            self.assertIsNone(_unified_cookie(headers))

    def test_client_password_correctness_is_not_revealed(self):
        with _flag('1'):
            messages = set()
            for password in (self.client_password, 'WrongPassword123'):
                status, headers, body = _request(
                    _browser(follow=False), self.base, '/entrar',
                    {'identificador': 'client@example.test',
                     'senha': password})
                self.assertEqual(200, status)
                self.assertIsNone(_unified_cookie(headers))
                messages.add(body)
        self.assertEqual(1, len(messages))
        self.assertIn('Credenciais inválidas.', messages.pop())

    def test_old_login_still_works_with_flag_on(self):
        jar = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        with _flag('1'):
            status, _headers, body = _request(
                client, self.base, '/login',
                {'email': 'provider@example.test',
                 'senha': self.provider_password})
            self.assertEqual(200, status)
            self.assertIn('Visão geral', body)
            self.assertIn('autosseg_session', {cookie.name for cookie in jar})
            status, _headers, body = _request(client, self.base, '/')
            self.assertEqual(200, status)
            self.assertIn('Visão geral', body)

    def test_flag_off_ignores_existing_unified_cookie(self):
        token = self._token('provider@example.test', self.provider_password)
        with _flag(''):
            status, _headers, body = _request(
                _browser(), self.base, '/',
                headers={'Cookie': f'autosseg_unified={token}'})
        self.assertEqual(200, status)
        self.assertIn('action="/login"', body)
        self.assertNotIn('Visão geral', body)

    def test_client_token_cannot_open_provider_portal(self):
        token = self._token('client@example.test', self.client_password)
        with _flag('1'):
            status, _headers, body = _request(
                _browser(), self.base, '/',
                headers={'Cookie': f'autosseg_unified={token}'})
        self.assertEqual(200, status)
        self.assertIn('action="/login"', body)
        self.assertNotIn('Visão geral', body)

    def test_repeated_failures_are_rate_limited(self):
        with _flag('1'):
            client = _browser(follow=False)
            for _attempt in range(10):
                status, _headers, _body = _request(
                    client, self.base, '/entrar',
                    {'identificador': 'provider@example.test',
                     'senha': 'WrongPassword123'})
                self.assertEqual(200, status)
            status, _headers, body = _request(
                client, self.base, '/entrar',
                {'identificador': 'provider@example.test',
                 'senha': self.provider_password})
        self.assertEqual(429, status)
        self.assertIn('Muitas tentativas', body)
        self.assertNotIn('autosseg_unified=', body)

    def test_old_login_rate_limiter_still_works(self):
        with _flag('1'):
            client = _browser(follow=False)
            for _attempt in range(10):
                status, _headers, _body = _request(
                    client, self.base, '/login',
                    {'email': 'provider@example.test',
                     'senha': 'WrongPassword123'})
                self.assertEqual(200, status)
            status, _headers, body = _request(
                client, self.base, '/login',
                {'email': 'provider@example.test',
                 'senha': self.provider_password})
        self.assertEqual(200, status)
        self.assertIn('Muitas tentativas', body)


if __name__ == '__main__':
    unittest.main()
