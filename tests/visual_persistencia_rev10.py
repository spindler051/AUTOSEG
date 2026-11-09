"""Confere no navegador, após reiniciar o servidor, que fotos e legendas persistem."""
import os
from playwright.sync_api import sync_playwright
from pathlib import Path

BASE = 'http://127.0.0.1:8866'
SENHA = os.environ.get('AUTOSEG_DEV_PROVIDER_PASSWORD', '')
if not SENHA:
    raise SystemExit('Defina AUTOSEG_DEV_PROVIDER_PASSWORD para executar o teste visual.')
EVID = Path.home() / 'AUTOSEG_DIST' / 'evidencias'
with sync_playwright() as p:
    nav = p.chromium.launch(channel='chrome', headless=True)
    pg = nav.new_page(viewport={'width': 1280, 'height': 900})
    pg.goto(BASE + '/login')
    pg.fill('input[name="email"]', 'prestador.alfa@example.invalid')
    pg.fill('input[name="senha"]', SENHA)
    pg.click('button[type="submit"]')
    pg.wait_for_url(BASE + '/')
    pg.goto(BASE + '/os/3')
    campos = pg.locator('input[name="anexo_legenda[]"]')
    assert campos.count() == 2, campos.count()
    valores = [campos.nth(i).input_value() for i in range(campos.count())]
    assert 'Legenda visual ANTES do reparo' in valores, valores
    assert 'Legenda visual editada DEPOIS' in valores, valores
    assert pg.locator('img[alt="Foto da OS"]').count() == 2
    pg.screenshot(path=str(EVID / '07-persistencia-apos-restart.png'), full_page=True)
    print('PASSOU: legendas e fotos persistem após reiniciar o servidor:', valores)
    nav.close()
