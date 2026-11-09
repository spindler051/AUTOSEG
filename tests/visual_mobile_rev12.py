"""Teste visual mobile (Chrome/Playwright) dos portais DEV."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

SENHA_CLIENTE = os.environ.get('AUTOSEG_DEV_CLIENT_PASSWORD', '')
SENHA_PRESTADOR = os.environ.get('AUTOSEG_DEV_PROVIDER_PASSWORD', '')
if not SENHA_CLIENTE or not SENHA_PRESTADOR:
    raise SystemExit('Defina AUTOSEG_DEV_CLIENT_PASSWORD e AUTOSEG_DEV_PROVIDER_PASSWORD para executar o teste visual.')
EVID = Path.home() / 'AUTOSEG_DIST' / 'evidencias'
EVID.mkdir(parents=True, exist_ok=True)
CLI = 'http://127.0.0.1:8865'
PRE = 'http://127.0.0.1:8866'


def sem_scroll_horizontal(pagina):
    largura = pagina.evaluate('document.documentElement.scrollWidth')
    janela = pagina.evaluate('window.innerWidth')
    return largura <= janela + 1, largura, janela


with sync_playwright() as p:
    nav = p.chromium.launch(channel='chrome', headless=True)
    ctx = nav.new_context(viewport={'width': 390, 'height': 844},
                          device_scale_factor=2, is_mobile=True, has_touch=True)
    pg = ctx.new_page()

    pg.goto(CLI + '/pj-rapido')
    ok, largura, janela = sem_scroll_horizontal(pg)
    assert ok, f'overflow horizontal no PJ rápido: {largura}>{janela}'
    assert pg.locator('input[name="q"]').count() == 1
    assert pg.locator('a:has-text("Pedir serviço neste local")').count() >= 1
    pg.screenshot(path=str(EVID / 'rev12_mobile_pj_rapido.png'), full_page=True)
    pg.locator('a:has-text("Pedir serviço neste local")').first.click()
    assert pg.locator('input[name="nome"]').count() == 1
    assert pg.locator('input[name="telefone"]').count() == 1
    ok, largura, janela = sem_scroll_horizontal(pg)
    assert ok, f'overflow no formulário PJ: {largura}>{janela}'
    pg.screenshot(path=str(EVID / 'rev12_mobile_pj_form.png'), full_page=True)

    pg.goto(CLI + '/cliente')
    pg.fill('input[name="cpf"]', '98765432290')
    pg.fill('input[name="senha"]', SENHA_CLIENTE)
    pg.click('button[type="submit"]')
    pg.wait_for_load_state('networkidle')
    assert 'Meu painel' in pg.content()
    ok, largura, janela = sem_scroll_horizontal(pg)
    assert ok, f'overflow no painel cliente: {largura}>{janela}'
    assert pg.locator('a:has-text("Chamado rápido")').count() >= 1
    pg.screenshot(path=str(EVID / 'rev12_mobile_cliente_painel.png'), full_page=True)

    pg.goto(PRE + '/login')
    pg.fill('input[name="email"]', 'prestador.alfa@example.invalid')
    pg.fill('input[name="senha"]', SENHA_PRESTADOR)
    pg.click('button[type="submit"]')
    pg.wait_for_load_state('networkidle')
    pg.goto(PRE + '/os')
    ok, largura, janela = sem_scroll_horizontal(pg)
    assert ok, f'overflow na lista de OS: {largura}>{janela}'
    cabecalho_oculto = pg.evaluate(
        "getComputedStyle(document.querySelector('#conteudo table thead') || document.querySelector('table thead')).display")
    assert cabecalho_oculto == 'none', cabecalho_oculto
    pg.screenshot(path=str(EVID / 'rev12_mobile_prestador_os.png'), full_page=True)
    pg.goto(PRE + '/pj-publicas')
    ok, largura, janela = sem_scroll_horizontal(pg)
    assert ok, f'overflow em Solicitações PJ: {largura}>{janela}'
    pg.screenshot(path=str(EVID / 'rev12_mobile_prestador_pj.png'), full_page=True)
    print('PASSOU: layouts mobile sem rolagem horizontal e tabelas empilhadas.')
    nav.close()
