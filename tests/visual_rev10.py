"""Teste visual real do Portal Prestador com Chrome (Playwright)."""
import os
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8866'
EMAIL = 'prestador.alfa@example.invalid'
SENHA = os.environ.get('AUTOSEG_DEV_PROVIDER_PASSWORD', '')
OS = 3
EVID = Path.home() / 'AUTOSEG_DIST' / 'evidencias'
EVID.mkdir(parents=True, exist_ok=True)


def imagem(cor, destino):
    Image.new('RGB', (320, 240), cor).save(destino, format='PNG')


def main():
    foto1 = EVID / 'antes.png'
    foto2 = EVID / 'depois.png'
    imagem('red', foto1)
    imagem('blue', foto2)
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox'])
        pagina = navegador.new_page(viewport={'width': 1280, 'height': 900})
        pagina.goto(BASE + '/login')
        pagina.fill('input[name="email"]', EMAIL)
        pagina.fill('input[name="senha"]', SENHA)
        pagina.click('button[type="submit"]')
        pagina.wait_for_url(BASE + '/')
        pagina.goto(f'{BASE}/os/{OS}')
        assert pagina.get_by_role('button', name='ASSUMIR OS').is_visible(), 'ASSUMIR OS ausente'
        pagina.screenshot(path=str(EVID / '01-os-nao-atribuida.png'), full_page=True)
        pagina.get_by_role('button', name='ASSUMIR OS').click()
        pagina.wait_for_load_state('networkidle')
        assert 'EM ROTA' in pagina.content(), 'EM ROTA ausente após assumir'
        assert 'INICIAR OS' in pagina.content(), 'INICIAR OS ausente após assumir'
        assert 'SALVAR RASCUNHO' in pagina.content(), 'SALVAR RASCUNHO ausente'
        assert 'Fotos do relatório e legendas' in pagina.content(), 'Seção de fotos ausente'
        pagina.screenshot(path=str(EVID / '02-assumida-botoes.png'), full_page=True)

        pagina.get_by_role('button', name='EM ROTA').click()
        pagina.wait_for_load_state('networkidle')
        assert 'EM ROTA — deslocamento iniciado' in pagina.content(), 'Indicador Em rota ausente'
        pagina.get_by_role('button', name='INICIAR OS').click()
        pagina.wait_for_load_state('networkidle')
        assert 'Atendimento iniciado' in pagina.content(), 'Início não registrado'

        pagina.set_input_files('#fotos-relatorio', [str(foto1), str(foto2)])
        pagina.wait_for_selector('input[name="foto_legenda[]"]')
        legendas = pagina.locator('input[name="foto_legenda[]"]')
        assert legendas.count() == 2, f'Esperadas 2 legendas, encontradas {legendas.count()}'
        legendas.nth(0).fill('Legenda visual ANTES do reparo')
        legendas.nth(1).fill('Legenda visual DEPOIS do reparo')
        assert pagina.locator('img[alt^="Prévia de antes"]').count() == 1, 'Prévia da primeira foto ausente'
        assert pagina.locator('img[alt^="Prévia de depois"]').count() == 1, 'Prévia da segunda foto ausente'
        pagina.screenshot(path=str(EVID / '03-previa-legendas.png'), full_page=True)

        pagina.get_by_role('button', name='SALVAR RASCUNHO').first.click()
        pagina.wait_for_load_state('networkidle')
        assert 'Rascunho salvo' in pagina.content(), 'Confirmação de rascunho ausente'
        pagina.screenshot(path=str(EVID / '04-rascunho-salvo.png'), full_page=True)
        pagina.get_by_role('link', name='Voltar à OS').click()
        pagina.wait_for_load_state('networkidle')
        valores = pagina.locator('input[name="anexo_legenda[]"]')
        assert valores.count() == 2, f'Esperadas 2 legendas salvas, encontradas {valores.count()}'
        assert valores.nth(0).input_value() == 'Legenda visual ANTES do reparo', valores.nth(0).input_value()
        assert valores.nth(1).input_value() == 'Legenda visual DEPOIS do reparo', valores.nth(1).input_value()
        pagina.screenshot(path=str(EVID / '05-legendas-recuperadas.png'), full_page=True)

        # Edita a legenda e salva de novo para provar que a associação não depende da ordem.
        valores.nth(1).fill('Legenda visual editada DEPOIS')
        pagina.get_by_role('button', name='SALVAR RASCUNHO').first.click()
        pagina.wait_for_load_state('networkidle')
        pagina.get_by_role('link', name='Voltar à OS').click()
        pagina.wait_for_load_state('networkidle')
        valores = pagina.locator('input[name="anexo_legenda[]"]')
        assert valores.nth(1).input_value() == 'Legenda visual editada DEPOIS', valores.nth(1).input_value()
        pagina.screenshot(path=str(EVID / '06-legenda-editada.png'), full_page=True)
        print('PASSOU: teste visual completo de SALVAR RASCUNHO, prévias e legendas.')
        navegador.close()


if __name__ == '__main__':
    main()
