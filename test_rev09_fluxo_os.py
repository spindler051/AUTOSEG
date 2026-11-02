"""Testes de aceitação REV09 — fluxo de OS no Portal Prestador/Cliente.

Banco e arquivos sempre temporários; nenhum dado real é acessado.
Cobre: assumir, em rota, início, rascunho persistente, encerramentos,
YAML sem gravação, PDF autorizado e bloqueio de terceiros.
"""
import http.cookiejar
import re
import sys
import tempfile
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import atendimento_os as aten
import cadastros_v9 as cad9
import fluxo_os as fluxo
import prestadores_ext as ext
from portal_prestador import PortalPrestador
from servidor_web import ServidorPortal
from test_portal_v4 import schema
from test_v9 import cpf


def browser():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def req(client, base, path, data=None, binary=False):
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    request = urllib.request.Request(base + path, body)
    try:
        with client.open(request, timeout=20) as response:
            raw = response.read()
            return response.status, (raw if binary else raw.decode('utf-8', 'replace'))
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def csrf(html):
    found = re.search(r'name="csrf" value="([^"]+)"', html)
    assert found, 'CSRF não encontrado'
    return found.group(1)


def check(nome, condicao):
    assert condicao, nome
    print('OK:', nome)


def preparar_banco(tmp):
    banco = str(tmp / 'teste.db')
    schema(banco)
    for atributo, pasta in (('ANEXOS', 'anexos'), ('RELATORIOS', 'relatorios'), ('RASCUNHOS', 'rascunhos')):
        destino = tmp / pasta
        destino.mkdir()
        setattr(ext, atributo, destino)
    sys.modules['banco'] = types.SimpleNamespace(
        proximo_numero_os=lambda cursor: 'OS-' + str(
            cursor.execute('SELECT COALESCE(MAX(id),0)+1 FROM ordens_servico').fetchone()[0]).zfill(4))
    ext.instalar(banco)
    fluxo.instalar(banco)
    aten.instalar(banco)
    cad9.instalar(banco)
    return banco


def criar_usuario_cliente(base_url, nome, doc):
    cliente = browser()
    status, body = req(cliente, base_url, '/cliente/cadastrar',
                       {'cpf': doc, 'senha': 'Senha-Boa-123456', 'confirmar_senha': 'Senha-Boa-123456'})
    assert status == 200 and 'Meu painel' in body, body[-400:]
    status, body = req(cliente, base_url, '/cliente/perfil')
    assert status == 200
    status, body = req(cliente, base_url, '/cliente/perfil', {
        'csrf': csrf(body), 'nome': nome, 'telefone': '51999998888',
        'email': f'{doc}@example.org', 'endereco': 'Rua de Teste, 100', 'numero': '100',
        'bairro': 'Centro', 'cidade': 'Porto Alegre', 'uf': 'RS', 'cep': '90000000'})
    assert status == 200 and 'Meu painel' in body
    return cliente


def main():
    with tempfile.TemporaryDirectory(prefix='autoseg_rev09_') as pasta:
        tmp = Path(pasta)
        banco = preparar_banco(tmp)
        pid = ext.cadastrar(banco, 'Prestador Teste', 'prestador@example.org', 'senha-bem-segura-2026')
        servidor = PortalPrestador(banco, '127.0.0.1', 0)
        servidor.iniciar()
        base = 'http://127.0.0.1:' + str(servidor.servidor.server_port)
        cliente_servidor = ServidorPortal(caminho_banco=banco, porta=0, host='127.0.0.1')
        cliente_servidor.iniciar()
        base_cli = 'http://127.0.0.1:' + str(cliente_servidor.porta)
        staff = browser()
        try:
            status, body = req(staff, base, '/login', {'email': 'prestador@example.org', 'senha': 'senha-bem-segura-2026'})
            check('login do prestador', status == 200)
            token = csrf(body)

            cliente = criar_usuario_cliente(base_cli, 'Cliente Particular Teste', cpf(345678901))
            status, body = req(cliente, base_cli, '/cliente/nova')
            check('formulário de OS particular', status == 200 and 'action="/os/nova"' in body)
            status, body = req(cliente, base_cli, '/cliente/os/nova', {
                'csrf': csrf(body), 'descricao': 'Revisar o portão da garagem particular', 'urgencia': 'Normal'})
            check('OS particular criada', status == 200 and 'Revisar o portão da garagem particular' in body)
            with ext.db(banco) as cursor:
                os_id = cursor.execute(
                    "SELECT id FROM ordens_servico WHERE descricao LIKE '%garagem particular%'").fetchone()['id']
                check('OS particular nasce ativa', cursor.execute(
                    'SELECT status FROM ordens_servico WHERE id=?', (os_id,)).fetchone()['status'] in ext.ATIVAS)

            # 1. Assumir sem iniciar.
            status, body = req(staff, base, f'/os/{os_id}')
            check('botão ASSUMIR OS visível', status == 200 and 'ASSUMIR OS' in body)
            check('botão SALVAR RASCUNHO visível', 'SALVAR RASCUNHO' in body)
            check('fluxo antigo removido', 'INICIAR OS — ASSUMIR AUTOMATICAMENTE' not in body)
            status, body = req(staff, base, f'/os/{os_id}/assumir', {'csrf': token})
            check('assumir responde', status == 200)
            with ext.db(banco) as cursor:
                check('responsável registrado', ext.responsavel_atual(cursor, os_id) == pid)
                linhas = cursor.execute(
                    'SELECT iniciado_em FROM os_atendimentos WHERE os_id=?', (os_id,)).fetchone()
                check('assumir não inicia atendimento', not (linhas and linhas['iniciado_em']))
                check('evento de assunção', cursor.execute(
                    "SELECT COUNT(*) FROM os_eventos WHERE os_id=? AND acao IN ('Assunção','Retomada')",
                    (os_id,)).fetchone()[0] == 1)

            # 2. Em rota e idempotência.
            status, body = req(staff, base, f'/os/{os_id}')
            check('botão EM ROTA visível', status == 200 and 'EM ROTA' in body)
            req(staff, base, f'/os/{os_id}/em-rota', {'csrf': token})
            req(staff, base, f'/os/{os_id}/em-rota', {'csrf': token})
            with ext.db(banco) as cursor:
                check('um único deslocamento ativo', cursor.execute(
                    'SELECT COUNT(*) FROM os_deslocamentos WHERE os_id=? AND finalizado_em IS NULL',
                    (os_id,)).fetchone()[0] == 1)
                check('evento Em rota auditado', cursor.execute(
                    "SELECT COUNT(*) FROM os_eventos WHERE os_id=? AND acao='Em rota'", (os_id,)).fetchone()[0] == 1)

            # 3. Cliente vê Em rota.
            status, body = req(cliente, base_cli, f'/cliente/os/{os_id}')
            check('cliente vê Em rota', status == 200 and 'Em rota' in body)

            # 4. Iniciar encerra o deslocamento.
            status, body = req(staff, base, f'/os/{os_id}/iniciar', {'csrf': token})
            check('iniciar responde', status == 200)
            with ext.db(banco) as cursor:
                check('atendimento iniciado', cursor.execute(
                    'SELECT iniciado_em FROM os_atendimentos WHERE os_id=?', (os_id,)).fetchone()['iniciado_em'])
                check('deslocamento encerrado', cursor.execute(
                    'SELECT COUNT(*) FROM os_deslocamentos WHERE os_id=? AND finalizado_em IS NULL',
                    (os_id,)).fetchone()[0] == 0)
            req(staff, base, f'/os/{os_id}/iniciar', {'csrf': token})
            with ext.db(banco) as cursor:
                check('início idempotente', cursor.execute(
                    "SELECT COUNT(*) FROM os_eventos WHERE os_id=? AND acao='Atendimento iniciado'",
                    (os_id,)).fetchone()[0] == 1)

            # 5. Salvar rascunho com todos os campos e recuperar após reiniciar o servidor.
            status, body = req(staff, base, f'/os/{os_id}')
            token = csrf(body)
            status, body = req(staff, base, f'/os/{os_id}/salvar', {
                'csrf': token, 'cliente_id': '1', 'descricao': 'Revisar o portão da garagem particular',
                'tecnico': 'Cliente Particular Teste', 'forma_pagamento': 'PIX',
                'valor_mao_obra': '120', 'valor_materiais_manual': '0',
                'material_item[]': ['Parafuso'], 'material_qtd[]': ['2'], 'material_unit[]': ['3,50'],
                'materiais_presentes': '1',
                'v9_diagnostico': 'Diagnóstico salvo no rascunho',
                'v9_execucao': 'Execução parcial salva no rascunho',
                'v9_resultado': 'Resultado parcial',
                'relatorio_tecnico': 'RASCUNHO PERSISTENTE REV09',
                'modo_envio': 'rascunho'})
            check('SALVAR RASCUNHO responde', status == 200 and 'Rascunho salvo' in body)
            with ext.db(banco) as cursor:
                check('rascunho no SQLite', cursor.execute(
                    'SELECT COUNT(*) FROM os_rascunhos_web WHERE os_id=?', (os_id,)).fetchone()[0] == 1)
                check('status permanece ativo', cursor.execute(
                    'SELECT status FROM ordens_servico WHERE id=?', (os_id,)).fetchone()['status'] in ext.ATIVAS)

            servidor.parar()
            servidor = PortalPrestador(banco, '127.0.0.1', 0)
            servidor.iniciar()
            base = 'http://127.0.0.1:' + str(servidor.servidor.server_port)
            staff = browser()
            status, body = req(staff, base, '/login', {'email': 'prestador@example.org', 'senha': 'senha-bem-segura-2026'})
            token = csrf(body)
            status, body = req(staff, base, f'/os/{os_id}')
            check('rascunho recuperado após reiniciar', status == 200 and 'RASCUNHO PERSISTENTE REV09' in body)

            # 6. Encerrar como Concluída e gerar/publicar PDF.
            status, body = req(staff, base, f'/os/{os_id}/salvar', {
                'csrf': token, 'cliente_id': '1', 'descricao': 'Revisar o portão da garagem particular',
                'tecnico': 'Cliente Particular Teste', 'forma_pagamento': 'PIX',
                'valor_mao_obra': '120', 'valor_materiais_manual': '7',
                'materiais_presentes': '1',
                'v9_diagnostico': 'Diagnóstico final', 'v9_execucao': 'Serviço executado e testado',
                'v9_resultado': 'Portão funcionando', 'relatorio_tecnico': 'Relatório final concluído',
                'acao_status': 'Concluída', 'modo_envio': 'encerrar'})
            check('conclusão da OS', status == 200)
            with ext.db(banco) as cursor:
                check('status concluída', cursor.execute(
                    'SELECT status FROM ordens_servico WHERE id=?', (os_id,)).fetchone()['status'] == 'Concluída')
                check('PDF publicado no servidor', cursor.execute(
                    "SELECT COUNT(*) FROM os_documentos WHERE os_id=? AND tipo='relatorio_pdf'",
                    (os_id,)).fetchone()[0] == 1)

            status, pdf = req(staff, base, f'/os/{os_id}/pdf', binary=True)
            check('PDF do prestador', status == 200 and pdf[:5] == b'%PDF-')
            status, pdf = req(cliente, base_cli, f'/cliente/os/{os_id}/pdf', binary=True)
            check('PDF autorizado ao cliente', status == 200 and pdf[:5] == b'%PDF-')

            outro = criar_usuario_cliente(base_cli, 'Outro Cliente Teste', cpf(445678901))
            status, corpo = req(outro, base_cli, f'/cliente/os/{os_id}/pdf', binary=True)
            check('PDF bloqueado para terceiro', status in (403, 404) and not corpo.startswith(b'%PDF'))
            status, corpo = req(browser(), base_cli, f'/cliente/os/{os_id}/pdf', binary=True)
            check('PDF bloqueado sem sessão', not corpo.startswith(b'%PDF'))

            # 7. OS Pendente permanece ativa/retomável.
            status, body = req(cliente, base_cli, '/cliente/nova')
            status, body = req(cliente, base_cli, '/cliente/os/nova', {
                'csrf': csrf(body), 'descricao': 'Segunda OS para teste de pendência', 'urgencia': 'Normal'})
            check('segunda OS criada', status == 200)
            with ext.db(banco) as cursor:
                os2 = cursor.execute(
                    "SELECT id FROM ordens_servico WHERE descricao LIKE '%Segunda OS%'").fetchone()['id']
            req(staff, base, f'/os/{os2}/assumir', {'csrf': token})
            status, body = req(staff, base, f'/os/{os2}')
            token = csrf(body)
            status, body = req(staff, base, f'/os/{os2}/salvar', {
                'csrf': token, 'cliente_id': '1', 'descricao': 'Segunda OS para teste de pendência',
                'tecnico': 'Cliente Particular Teste', 'forma_pagamento': 'PIX',
                'valor_mao_obra': '80', 'valor_materiais_manual': '0', 'materiais_presentes': '1',
                'relatorio_tecnico': 'Atendimento parcial', 'acao_status': 'Pendente', 'modo_envio': 'encerrar'})
            check('OS marcada pendente', status == 200)
            with ext.db(banco) as cursor:
                check('pendente continua ativa', cursor.execute(
                    'SELECT status FROM ordens_servico WHERE id=?', (os2,)).fetchone()['status'] == 'Pendente')
                check('atendimento preservado ao ficar pendente', cursor.execute(
                    'SELECT rascunho FROM os_atendimentos WHERE os_id=?', (os2,)).fetchone()['rascunho'] == 'Atendimento parcial')

            # 8. Cancelamento exige motivo.
            status, body = req(cliente, base_cli, '/cliente/nova')
            status, body = req(cliente, base_cli, '/cliente/os/nova', {
                'csrf': csrf(body), 'descricao': 'Terceira OS para cancelamento', 'urgencia': 'Normal'})
            with ext.db(banco) as cursor:
                os3 = cursor.execute(
                    "SELECT id FROM ordens_servico WHERE descricao LIKE '%cancelamento%'").fetchone()['id']
            req(staff, base, f'/os/{os3}/assumir', {'csrf': token})
            status, body = req(staff, base, f'/os/{os3}')
            token = csrf(body)
            status, erro = req(staff, base, f'/os/{os3}/salvar', {
                'csrf': token, 'cliente_id': '1', 'descricao': 'Terceira OS para cancelamento',
                'tecnico': 'Cliente Particular Teste', 'forma_pagamento': 'PIX',
                'valor_mao_obra': '50', 'valor_materiais_manual': '0', 'materiais_presentes': '1',
                'relatorio_tecnico': 'Não foi possível executar', 'acao_status': 'Cancelada',
                'modo_envio': 'encerrar'})
            check('cancelamento sem motivo rejeitado', status == 400 and 'motivo' in str(erro).lower())
            status, body = req(staff, base, f'/os/{os3}/salvar', {
                'csrf': token, 'cliente_id': '1', 'descricao': 'Terceira OS para cancelamento',
                'tecnico': 'Cliente Particular Teste', 'forma_pagamento': 'PIX',
                'valor_mao_obra': '50', 'valor_materiais_manual': '0', 'materiais_presentes': '1',
                'relatorio_tecnico': 'Não foi possível executar', 'motivo_encerramento': 'Cliente desistiu',
                'acao_status': 'Cancelada', 'modo_envio': 'encerrar'})
            check('cancelamento registrado', status == 200)
            with ext.db(banco) as cursor:
                check('motivo do cancelamento', cursor.execute(
                    'SELECT motivo FROM os_encerramentos WHERE os_id=?', (os3,)).fetchone()['motivo'] == 'Cliente desistiu')

            # 9. YAML apenas pré-visualiza, sem gravar.
            yaml = ('versao: 1\nos:\n  diagnostico: DIAGNOSTICO YAML PREVIA\n'
                    '  execucao: Execucao YAML\n  materiais:\n    - item: Cabo YAML\n      quantidade: 1\n'
                    '      valor_unitario: 10\n').encode()
            fronteira = '----autosegrev09'
            corpo = (f'--{fronteira}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{token}\r\n'
                     f'--{fronteira}\r\nContent-Disposition: form-data; name="yaml"; filename="relatorio.yaml"\r\n'
                     'Content-Type: application/x-yaml\r\n\r\n').encode() + yaml + f'\r\n--{fronteira}--\r\n'.encode()
            pedido = urllib.request.Request(base + f'/os/{os2}/yaml', corpo,
                                            {'Content-Type': f'multipart/form-data; boundary={fronteira}'})
            with staff.open(pedido, timeout=20) as resposta:
                pagina = resposta.read().decode('utf-8', 'replace')
            check('prévia YAML exibida', 'DIAGNOSTICO YAML PREVIA' in pagina)
            with ext.db(banco) as cursor:
                check('prévia YAML não gravou', 'DIAGNOSTICO YAML PREVIA' not in str(cursor.execute(
                    'SELECT * FROM os_atendimentos WHERE os_id=?', (os2,)).fetchone() or ''))

            print('PASSOU: fluxo completo de OS REV09')
        finally:
            try:
                cliente_servidor.parar()
            except Exception:
                pass
            servidor.parar()


if __name__ == '__main__':
    main()
