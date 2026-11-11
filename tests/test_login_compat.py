"""HTTP compatibility tests for logout, reset, deactivation and rollback."""
from __future__ import annotations

import http.cookiejar
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

from flavors.autoseg.modules import accounts, auth, web_session
from flavors.autoseg.modules import portal_prestador as portal_module
from flavors.autoseg.modules.portal_prestador import PortalPrestador
from officina.core import cadastros_v9 as cad
from officina.core import prestadores_ext as ext
from officina.core.banco import criar_banco


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
        try:
            body = error.read()
        except (ConnectionError, OSError):
            body = b''
        return (error.code, error.headers,
                body.decode('utf-8', 'replace'))


def _flag(value):
    return patch.dict(os.environ, {'AUTOSEG_UNIFIED_LOGIN': value})


def _cookie(headers, name):
    for value in headers.get_all('Set-Cookie') or ():
        if value.startswith(name + '='):
            return value.split(';', 1)[0]
    return None


def _all_cookies(headers):
    return [value for value in headers.get_all('Set-Cookie') or ()
            if value.startswith(('autosseg_unified=', 'autosseg_session='))]


def _token(cookie):
    return cookie.split('=', 1)[1]


def _csrf(body):
    match = re.search(r'name="csrf" value="([^"]+)"', body)
    if match is None:
        raise AssertionError('CSRF field missing')
    return match.group(1)


class LoginCompatHttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='login_compat_http_')
        self.addCleanup(self.tmp.cleanup)
        self.db = str(Path(self.tmp.name) / 'app.db')
        criar_banco(self.db)
        ext.instalar(self.db)
        cad.instalar(self.db)
        accounts.install(self.db)
        self.admin_password = 'AdminPassword123'
        self.provider_password = 'ProviderPassword123'
        self.client_password = 'ClientPassword123'
        self.admin_id = ext.cadastrar(
            self.db, 'Admin Provider', 'admin@example.test',
            self.admin_password)
        with ext.db(self.db) as connection:
            connection.execute(
                'INSERT INTO v9_admin_prestadores(prestador_id, autorizado_em) '
                'VALUES(?,?)', (self.admin_id, ext.agora()))
        self.provider_id = ext.cadastrar(
            self.db, 'Provider Example', 'provider@example.test',
            self.provider_password)
        self.client_id = cad.cadastrar_usuario(
            self.db, 'Client Example', '52998224725', '51999999999',
            self.client_password, 'client@example.test')
        accounts.migrate_legacy(self.db, dry_run=False)
        web_session.clear()
        self.addCleanup(web_session.clear)
        portal_module.SESSOES.clear()
        self.addCleanup(portal_module.SESSOES.clear)
        self._clear_attempts()
        self.addCleanup(self._clear_attempts)
        self.server = PortalPrestador(self.db, '127.0.0.1', 0)
        self.server.iniciar()
        self.addCleanup(self.server.parar)
        self.base = f'http://127.0.0.1:{self.server.porta}'

    def _clear_attempts(self):
        with portal_module.LOCK_LOGIN:
            portal_module.TENTATIVAS.clear()

    def _unified_cookie(self, identifier, password):
        with _flag('1'):
            status, headers, _body = _request(
                _browser(follow=False), self.base, '/login',
                {'identificador': identifier, 'senha': password})
        self.assertEqual(303, status)
        cookie = _cookie(headers, 'autosseg_unified')
        self.assertIsNotNone(cookie)
        return cookie

    def _legacy_cookie(self, identifier, password):
        status, headers, _body = _request(
            _browser(follow=False), self.base, '/login',
            {'email': identifier, 'senha': password})
        self.assertEqual(303, status)
        cookie = _cookie(headers, 'autosseg_session')
        self.assertIsNotNone(cookie)
        return cookie

    def _csrf_for(self, cookie):
        with _flag('1'):
            status, _headers, body = _request(
                _browser(), self.base, '/', headers={'Cookie': cookie})
        self.assertEqual(200, status)
        return _csrf(body)

    def _post(self, path, cookie, data, flag='1'):
        with _flag(flag):
            return _request(
                _browser(follow=False), self.base, path, data,
                headers={'Cookie': cookie})

    def test_unified_logout_revokes_and_clears(self):
        cookie = self._unified_cookie(
            'provider@example.test', self.provider_password)
        token = _token(cookie)
        csrf = self._csrf_for(cookie)
        status, headers, _body = self._post(
            '/sair', cookie, {'csrf': csrf})
        self.assertEqual(303, status)
        self.assertEqual('/login', headers['Location'])
        clears = _all_cookies(headers)
        self.assertEqual(2, len(clears))
        self.assertTrue(all('Max-Age=0' in value for value in clears))
        self.assertTrue(any(value.startswith('autosseg_unified=')
                            for value in clears))
        self.assertTrue(any(value.startswith('autosseg_session=')
                            for value in clears))
        self.assertIsNone(web_session.resolve(self.db, token))
        self.assertNotIn(token, web_session._SESSIONS)

    def test_legacy_logout_still_works(self):
        cookie = self._legacy_cookie(
            'provider@example.test', self.provider_password)
        token = _token(cookie)
        csrf = self._csrf_for(cookie)
        self.assertIn(token, portal_module.SESSOES)
        status, headers, _body = self._post(
            '/sair', cookie, {'csrf': csrf})
        self.assertEqual(303, status)
        self.assertEqual('/login', headers['Location'])
        self.assertEqual(2, len(_all_cookies(headers)))
        self.assertNotIn(token, portal_module.SESSOES)

    def test_dual_logout_clears_both(self):
        unified = self._unified_cookie(
            'provider@example.test', self.provider_password)
        legacy = self._legacy_cookie(
            'provider@example.test', self.provider_password)
        unified_token = _token(unified)
        legacy_token = _token(legacy)
        csrf = self._csrf_for(unified)
        both = f'{unified}; {legacy}'
        status, headers, _body = self._post(
            '/sair', both, {'csrf': csrf})
        self.assertEqual(303, status)
        self.assertEqual(2, len(_all_cookies(headers)))
        self.assertIsNone(web_session.resolve(self.db, unified_token))
        self.assertNotIn(unified_token, web_session._SESSIONS)
        self.assertNotIn(legacy_token, portal_module.SESSOES)

    def test_password_reset_revokes_unified_session(self):
        admin = self._unified_cookie('admin@example.test', self.admin_password)
        employee = self._unified_cookie(
            'provider@example.test', self.provider_password)
        employee_token = _token(employee)
        csrf = self._csrf_for(admin)
        status, headers, _body = self._post(
            f'/prestadores/{self.provider_id}/senha', admin,
            {'csrf': csrf, 'senha': 'NewProviderPassword123'})
        self.assertEqual(303, status)
        self.assertEqual('/prestadores', headers['Location'])
        self.assertIsNone(web_session.resolve(self.db, employee_token))
        self.assertNotIn(employee_token, web_session._SESSIONS)
        with self.assertRaises(auth.LoginError):
            auth.authenticate(
                self.db, 'provider@example.test', self.provider_password)
        result = auth.authenticate(
            self.db, 'provider@example.test', 'NewProviderPassword123')
        self.assertEqual(result.source, 'account')
        self.assertIsNotNone(web_session.resolve(self.db, _token(admin)))

    def test_deactivation_and_archive_revoke_unified_session(self):
        admin = self._unified_cookie('admin@example.test', self.admin_password)
        csrf = self._csrf_for(admin)
        employee = self._unified_cookie(
            'provider@example.test', self.provider_password)
        employee_token = _token(employee)
        status, _headers, _body = self._post(
            f'/prestadores/{self.provider_id}/alternar', admin,
            {'csrf': csrf})
        self.assertEqual(303, status)
        self.assertIsNone(web_session.resolve(self.db, employee_token))
        # Reactivation must allow a fresh unified login again.
        status, _headers, _body = self._post(
            f'/prestadores/{self.provider_id}/alternar', admin,
            {'csrf': csrf})
        self.assertEqual(303, status)
        employee = self._unified_cookie(
            'provider@example.test', self.provider_password)
        employee_token = _token(employee)
        status, _headers, _body = self._post(
            f'/prestadores/{self.provider_id}/arquivar', admin,
            {'csrf': csrf})
        self.assertEqual(303, status)
        self.assertIsNone(web_session.resolve(self.db, employee_token))
        self.assertNotIn(employee_token, web_session._SESSIONS)

    def test_admin_role_change_revokes_and_refreshes_role(self):
        admin = self._unified_cookie('admin@example.test', self.admin_password)
        employee = self._unified_cookie(
            'provider@example.test', self.provider_password)
        employee_token = _token(employee)
        csrf = self._csrf_for(admin)
        status, _headers, _body = self._post(
            f'/prestadores/{self.provider_id}/admin', admin,
            {'csrf': csrf})
        self.assertEqual(303, status)
        self.assertIsNone(web_session.resolve(self.db, employee_token))
        self.assertNotIn(employee_token, web_session._SESSIONS)
        refreshed = self._unified_cookie(
            'provider@example.test', self.provider_password)
        session = web_session.resolve(self.db, _token(refreshed))
        self.assertIsNotNone(session)
        self.assertEqual('admin', session.principal.role)

    def test_flag_off_ignores_unified_cookie(self):
        cookie = self._unified_cookie(
            'provider@example.test', self.provider_password)
        with _flag(''):
            status, _headers, body = _request(
                _browser(follow=False), self.base, '/login')
            self.assertEqual(200, status)
            self.assertIn('action="/login"', body)
            self.assertIn('name="email"', body)
            status, _headers, body = _request(
                _browser(), self.base, '/',
                headers={'Cookie': cookie})
        self.assertEqual(200, status)
        self.assertIn('action="/login"', body)
        self.assertNotIn('Visão geral', body)

    def test_flag_on_legacy_login_and_client_auth_unchanged(self):
        cookie = self._legacy_cookie(
            'provider@example.test', self.provider_password)
        self.assertIsNotNone(cookie)
        authenticated = cad.autenticar(
            self.db, '52998224725', self.client_password)
        self.assertIsNotNone(authenticated)
        self.assertEqual(authenticated['id'], self.client_id)


if __name__ == '__main__':
    unittest.main()
