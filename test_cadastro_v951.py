"""Smoke test HTTP real do cadastro AUTOSEG na porta de teste, sem tocar dados.db."""
import http.cookiejar
import re
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError

from servidor_web import ServidorPortal
from test_portal_v4 import schema
from test_v94_correcoes import cpf


def request(browser, base, route, data=None):
    payload = urlencode(data).encode() if data is not None else None
    try:
        with browser.open(Request(base + route, data=payload), timeout=10) as response:
            return response.status, response.read().decode('utf-8', 'replace'), response.geturl()
    except HTTPError as error:
        return error.code, error.read().decode('utf-8', 'replace'), error.geturl()


def main():
    with tempfile.TemporaryDirectory(prefix='autosseg_cadastro_') as temporary:
        db = str(Path(temporary) / 'test.db')
        schema(db)
        portal = ServidorPortal(caminho_banco=db, host='127.0.0.1', porta=0)
        portal.iniciar()
        base = f'http://127.0.0.1:{portal.porta}'
        browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        try:
            status, html, _ = request(browser, base, '/')
            assert status == 200 and 'name="cpf"' in html and 'name="senha"' in html
            print('PASSOU: login CPF e senha no portal 8765')
            status, html, _ = request(browser, base, '/cadastro')
            assert status == 200 and 'confirmar_senha' in html and 'name="telefone"' not in html
            print('PASSOU: formulário Criar conta, sem telefone obrigatório')
            doc = cpf(987654321)
            status, html, url = request(browser, base, '/cadastrar', {'cpf':doc,'senha':'Senha-Temporaria-123', 'confirmar_senha':'Senha-Temporaria-123'})
            assert status == 200 and url.endswith('/painel') and 'Meu painel' in html, (status,url,html[-400:])
            print('PASSOU: POST cadastro salva e autentica; redireciona para painel')
            with sqlite3.connect(db) as conn:
                assert conn.execute('SELECT COUNT(*) FROM v9_usuarios WHERE cpf=?',(doc,)).fetchone()[0] == 1
            print('PASSOU: usuário persistido no SQLite')
            status, html, _ = request(browser, base, '/nova')
            assert status == 200 and 'Complete seu cadastro' in html
            print('PASSOU: OS particular exige completar perfil')
            status, html, _ = request(browser, base, '/nova-organizacao')
            assert status == 200 and 'unidade' in html and 'cnpj' in html
            print('PASSOU: pré-cadastro PJ disponível sem perfil PF completo')
            status, html, _ = request(browser, base, '/cadastrar', {'cpf':doc,'senha':'Senha-Temporaria-123', 'confirmar_senha':'Senha-Temporaria-123'})
            assert status == 400 and 'CPF já cadastrado' in html, (status, html[-400:])
            print('PASSOU: CPF duplicado bloqueado sem travar servidor')
            status, html, _ = request(browser, base, '/')
            assert status == 200
            print('PASSOU: servidor continua atendendo após erro de cadastro')
        finally:
            portal.parar()


if __name__ == '__main__':
    main()
