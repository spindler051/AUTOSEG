"""Regressao: navegacao do cliente sem links //cadastro (Safari). Banco temporario."""
import http.cookiejar
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, build_opener

from servidor_web import ServidorPortal
from test_portal_v4 import schema


class Navegacao(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        key = 'href' if tag == 'a' else 'action' if tag == 'form' else None
        if key and props.get(key):
            self.links.append((tag, props[key]))


def main():
    with tempfile.TemporaryDirectory(prefix='autosseg_links_') as folder:
        db = str(Path(folder) / 'test.db')
        schema(db)
        portal = ServidorPortal(caminho_banco=db, host='127.0.0.1', porta=0)
        portal.iniciar()
        browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        base = f'http://127.0.0.1:{portal.porta}'
        try:
            for route in ('/', '/cadastro', '/cadastro-pj'):
                with browser.open(base + route, timeout=10) as response:
                    content = response.read().decode('utf-8')
                    assert response.status == 200
                links = Navegacao(); links.feed(content)
                for tag, link in links.links:
                    if link.startswith('//'):
                        raise AssertionError(f'{route}: URL perigosa: {tag} {link}')
                    if link.startswith('/'):
                        assert urlsplit(urljoin(base, link)).netloc == urlsplit(base).netloc, (route, link)
                print(f'PASSOU: {route} — {len(links.links)} links/formularios sem //')
            with browser.open(base + '/', timeout=10) as response:
                html = response.read().decode('utf-8')
            assert 'href="/cadastro"' in html, 'Botao Criar conta deve usar /cadastro'
            assert 'action="/entrar-pf"' in html, 'Login deve enviar para mesma origem'
            with browser.open(base + '/cadastro', timeout=10) as response:
                assert 'confirmar_senha' in response.read().decode('utf-8')
            print('PASSOU: botao Criar conta abre formulario real')
        finally:
            portal.parar()

if __name__ == '__main__':
    main()
