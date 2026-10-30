"""Testes obrigatórios da correção v9.4.1 — portal do cliente na rota real /cliente.

Cobre os 16 cenários pedidos contra um servidor HTTP real (porta efêmera) e
confere também a renderização na porta 8766. Usa banco temporário; não toca em
dados.db. Não inicia túneis nem publica nada.
"""
import html as html_lib
import http.cookiejar
import json
import re
import sys
import tempfile
import types
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import atendimento_os as aten
import cadastros_v9 as cad
import fluxo_os
import prestadores_ext as ext
from portal_prestador import PortalPrestador
from servidor_web import ServidorPortal
from test_portal_v4 import schema

PASTA = Path(__file__).resolve().parent
WHATSAPP = '5551992692007'
RESULTADOS = []


def cpf(n):
    a = [int(i) for i in f'{n:09d}']
    for k in (9, 10):
        d = sum(a[i] * (k + 1 - i) for i in range(k)) * 10 % 11
        a.append(0 if d == 10 else d)
    return ''.join(map(str, a))


def cnpj(base='123456780001'):
    a = [int(i) for i in base]
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2],
                  [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        d = sum(x * y for x, y in zip(a, pesos)) % 11
        a.append(0 if d < 2 else 11 - d)
    return ''.join(map(str, a))


def navegador():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def req(cliente, base, caminho, dados=None):
    corpo = urllib.parse.urlencode(dados).encode() if dados is not None else None
    r = urllib.request.Request(base + caminho, corpo)
    try:
        with cliente.open(r, timeout=15) as x:
            return x.status, x.read().decode('utf-8', 'replace'), x.geturl()
    except urllib.error.HTTPError as x:
        return x.code, x.read().decode('utf-8', 'replace'), x.geturl()


def csrf(texto):
    m = re.search('name="csrf" value="([^"]+)"', texto)
    assert m, 'CSRF não encontrado'
    return m.group(1)


def verificar(cenario, condicao, detalhe=''):
    if condicao:
        RESULTADOS.append((True, cenario))
        print('OK:', cenario)
    else:
        RESULTADOS.append((False, cenario + (' — ' + detalhe if detalhe else '')))
        print('FALHOU:', cenario, detalhe)


def link_whatsapp(texto):
    """Extrai o primeiro href wa.me e valida destino + mensagem decodificada."""
    m = re.search(r'href="(https://wa\.me/' + WHATSAPP + r'\?text=[^"]+)"', texto)
    if not m:
        return None, ''
    href = html_lib.unescape(m.group(1))
    partes = urllib.parse.urlsplit(href)
    mensagem = urllib.parse.parse_qs(partes.query).get('text', [''])[0]
    return href, mensagem


def exigir_whatsapp(nome, texto, protocolo, tipo, organizacao=''):
    href, msg = link_whatsapp(texto)
    ok = (href is not None and partes_destino(href) == WHATSAPP
          and 'Acabei de abrir uma nova ordem de serviço' in msg
          and ('Protocolo: ' + protocolo) in msg
          and ('Tipo de solicitação: ' + tipo) in msg
          and (('Organização: ' + organizacao) in msg if organizacao else True)
          and 'Gostaria de confirmar o recebimento da minha solicitação.' in msg
          and not re.search(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}', msg))
    verificar(nome, ok, 'href/mensagem inesperados: ' + repr(msg))


def partes_destino(href):
    return urllib.parse.urlsplit(href).path.strip('/')


def principal():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        db = str(tmp / 'teste_v94.db')
        schema(db)
        for attr, pasta in (('ANEXOS', 'anexos'), ('RELATORIOS', 'relatorios'), ('RASCUNHOS', 'rascunhos')):
            setattr(ext, attr, tmp / pasta)
            (tmp / pasta).mkdir()
        sys.modules['banco'] = types.SimpleNamespace(
            proximo_numero_os=lambda cur: 'OS-' + str(cur.execute(
                'SELECT COALESCE(MAX(id),0)+1 FROM ordens_servico').fetchone()[0]).zfill(4))
        ext.instalar(db)
        fluxo_os.instalar(db)
        aten.instalar(db)
        cad.instalar(db)
        cad.instalar(db)  # idempotência da migração

        servidor = PortalPrestador(db, '127.0.0.1', 0)
        servidor.iniciar()
        base = 'http://127.0.0.1:' + str(servidor.servidor.server_port)
        try:
            portal_fluxo(base, db)
            legado_e_bridge(db)
            porta_real_8766(db)
        finally:
            servidor.parar()

    falhas = [x for ok, x in RESULTADOS if not ok]
    print()
    print('TOTAL:', len(RESULTADOS), '| APROVADOS:', len(RESULTADOS) - len(falhas), '| FALHAS:', len(falhas))
    if falhas:
        for f in falhas:
            print(' -', f)
        raise SystemExit(1)
    print('PASSOU: correções v9.4.1 do portal do cliente')


def portal_fluxo(base, db):
    # 16. Rota real /cliente (servidor em execução) com os novos campos.
    a = navegador()
    st, body, _ = req(a, base, '/cliente')
    verificar('16. /cliente renderiza login CPF+senha',
              st == 200 and 'name="cpf"' in body and 'name="senha"' in body
              and 'Criar conta' in body)
    verificar('16b. /cliente não exibe login antigo',
              not any(x in body for x in ('name="documento"', 'name="acesso"',
                                          'name="cnpj"', 'name="telefone"', 'name="email"')))

    # 3. Login antigo por telefone/e-mail sem senha é rejeitado.
    st, body, _ = req(a, base, '/cliente/entrar-pf', {'cpf': 'cliente@teste.local', 'senha': ''})
    verificar('3. login por e-mail/telefone sem senha rejeitado',
              st == 200 and 'CPF ou senha incorretos' in body)

    # 1. Cadastro apenas com CPF + senha (sem telefone/e-mail/endereço).
    doc1 = cpf(312345678)
    st, body, _ = req(a, base, '/cliente/cadastro')
    verificar('1. cadastro inicial pede só CPF e senha',
              st == 200 and 'name="cpf"' in body and 'confirmar_senha' in body
              and not any(x in body for x in ('name="telefone"', 'name="email"', 'name="endereco"')))
    st, body, _ = req(a, base, '/cliente/cadastrar',
                      {'cpf': doc1, 'senha': 'Senha-Cliente-123', 'confirmar_senha': 'Senha-Cliente-123'})
    verificar('1b. cadastro PF autentica imediatamente', st == 200 and 'Meu painel' in body)

    # Duplicidade de conta bloqueada.
    st, body, _ = req(navegador(), base, '/cliente/cadastrar',
                      {'cpf': doc1, 'senha': 'Outra-Senha-123', 'confirmar_senha': 'Outra-Senha-123'})
    verificar('1c. CPF duplicado bloqueado', st == 400 and 'já cadastrado' in body)

    # 4. OS particular bloqueada sem perfil completo.
    st, body, _ = req(a, base, '/cliente/nova')
    verificar('4. OS particular bloqueada sem perfil',
              st == 200 and 'Complete seu cadastro' in body and 'action="/cliente/os/nova"' not in body)

    # 7. Perfil completo (nome, telefone, e-mail, endereço).
    st, body, _ = req(a, base, '/cliente/perfil')
    st, body, _ = req(a, base, '/cliente/perfil', {
        'csrf': csrf(body), 'nome': 'Cliente Particular Teste', 'telefone': '51999998888',
        'email': 'cliente@teste.local', 'endereco': 'Rua das Flores', 'numero': '123',
        'bairro': 'Centro', 'cidade': 'Porto Alegre', 'uf': 'RS', 'cep': '90000000'})
    verificar('7. perfil PF salvo', st == 200 and 'Meu painel' in body)

    # 2. Login por CPF e senha em sessão limpa.
    b = navegador()
    st, body, _ = req(b, base, '/cliente/entrar-pf', {'cpf': doc1, 'senha': 'Senha-Cliente-123'})
    verificar('2. login por CPF e senha', st == 200 and 'Meu painel' in body)

    # 5 + 12. Abrir OS particular, persistir no SQLite e exibir acompanhamento.
    st, body, _ = req(b, base, '/cliente/nova')
    st, body, _ = req(b, base, '/cliente/os/nova', {
        'csrf': csrf(body), 'descricao': 'Revisar o portão de garagem particular', 'urgencia': 'Normal'})
    with ext.db(db) as c:
        os_reg = c.execute("SELECT id,numero_os,cliente_id,origem FROM ordens_servico "
                           "WHERE descricao LIKE '%garagem particular%'").fetchone()
        os_id = os_reg['id'] if os_reg else 0
        numero_os = os_reg['numero_os'] if os_reg else ''
    verificar('5. OS particular aberta com perfil completo', st == 200 and 'Solicitação salva' in body)
    verificar('12. OS persistida no SQLite', bool(os_reg and os_reg['cliente_id'] and os_reg['origem'] == 'Portal'))
    st, body, _ = req(b, base, '/cliente/painel')
    verificar('13. OS aparece no acompanhamento do cliente', st == 200 and numero_os in body)

    # 14. Botão WhatsApp com número, texto e ID real.
    st, body, _ = req(b, base, '/cliente/os/' + str(os_id))
    verificar('14. botão WhatsApp exibido após salvar a OS',
              st == 200 and 'Avisar AUTOSEG pelo WhatsApp' in body)
    exigir_whatsapp('14b. WhatsApp usa 5551992692007, texto e protocolo real',
                    body, numero_os or str(os_id), 'PARTICULAR')
    verificar('14c. WhatsApp não vaza CPF', doc1 not in body and 'CPF' not in link_whatsapp(body)[1])

    # 6. Cadastro de organização após login PF + 7. vínculo pendente.
    doc_pj = cnpj('123456780001')
    st, body, _ = req(a, base, '/cliente/administrar-organizacao')
    verificar('6. formulário PJ disponível após login', st == 200 and 'name="cnpj"' in body and 'name="funcao"' in body)
    st, body, _ = req(a, base, '/cliente/administrar-organizacao', {
        'csrf': csrf(body), 'tipo': 'Condomínio', 'nome': 'Condomínio Correção V94',
        'endereco': 'Av. Central 500, Porto Alegre/RS', 'cidade': 'Porto Alegre',
        'cnpj': doc_pj, 'funcao': 'Síndico'})
    with ext.db(db) as c:
        org = c.execute("SELECT id,cnpj FROM v9_organizacoes WHERE nome='Condomínio Correção V94'").fetchone()
        vinc = c.execute("SELECT papel,situacao,funcao_declarada FROM v9_vinculos "
                         "WHERE organizacao_id=?", (org['id'],)).fetchone() if org else None
    verificar('6b. organização criada uma única vez', bool(org and org['cnpj'] == doc_pj))
    verificar('7. vínculo administrativo fica pendente',
              bool(vinc and vinc['papel'] == 'Síndico' and vinc['situacao'] == 'Pendente'
                   and vinc['funcao_declarada'] == 'Síndico'))

    # 8. Morador sem permissão de administrador abre chamado.
    morador = navegador()
    doc2 = cpf(412345678)
    req(morador, base, '/cliente/cadastrar',
        {'cpf': doc2, 'senha': 'Senha-Morador-123', 'confirmar_senha': 'Senha-Morador-123'})
    st, body, _ = req(morador, base, '/cliente/chamado/novo?org=' + str(org['id']))
    st, body, _ = req(morador, base, '/cliente/chamado/novo', {
        'csrf': csrf(body), 'org_id': str(org['id']), 'papel': 'Morador',
        'solicitante_nome': 'Morador Teste', 'unidade': 'Apartamento 203',
        'descricao': 'Portão eletrônico não abre desde ontem', 'urgencia': 'Alta'})
    with ext.db(db) as c:
        ch = c.execute("SELECT id,status,unidade,papel,os_id FROM v9_chamados ORDER BY id DESC LIMIT 1").fetchone()
    verificar('8. morador abre chamado sem ser administrador',
              st == 200 and ch and ch['status'] == 'Aguardando AUTOSEG'
              and ch['papel'] == 'Morador' and ch['unidade'] == 'Apartamento 203')
    verificar('8b. morador não recebe acesso de síndico',
              req(morador, base, '/cliente/sindico?org=' + str(org['id']))[0] == 403)
    st, body, _ = req(morador, base, '/cliente/chamado/' + str(ch['id']))
    verificar('8c. chamado aparece no acompanhamento',
              st == 200 and 'Solicitação registrada' in body and 'Apartamento 203' in body)
    exigir_whatsapp('14d. WhatsApp do condomínio com protocolo real',
                    body, 'Chamado #' + str(ch['id']), 'CONDOMÍNIO', 'Condomínio Correção V94')

    # 9. Porteiro/funcionário com campo apartamento/cargo.
    st, body, _ = req(morador, base, '/cliente/chamado/novo?org=' + str(org['id']))
    st, body, _ = req(morador, base, '/cliente/chamado/novo', {
        'csrf': csrf(body), 'org_id': str(org['id']), 'papel': 'Funcionário',
        'solicitante_nome': 'Porteiro Teste', 'unidade': 'Zelador',
        'descricao': 'Lâmpada queimada na garagem do prédio', 'urgencia': 'Normal'})
    with ext.db(db) as c:
        cargo = c.execute("SELECT unidade,papel,solicitante_nome FROM v9_chamados ORDER BY id DESC LIMIT 1").fetchone()
    verificar('9. funcionário/porteiro registra apartamento ou cargo',
              cargo and cargo['unidade'] == 'Zelador' and cargo['papel'] == 'Funcionário'
              and cargo['solicitante_nome'] == 'Porteiro Teste',
              repr(dict(cargo)) if cargo else 'sem registro')

    # 10. Pesquisa por nome (sem revelar CNPJ) e por CNPJ exato.
    st, body, _ = req(morador, base, '/cliente/organizacoes?q=' + urllib.parse.quote('Correção V94'))
    verificar('10. pesquisa por nome encontra a organização sem CNPJ',
              st == 200 and 'Condomínio Correção V94' in body and doc_pj not in body)
    st, body, _ = req(morador, base, '/cliente/organizacoes?q=' + doc_pj)
    verificar('10b. pesquisa por CNPJ tem correspondência exata',
              st == 200 and 'Condomínio Correção V94' in body and doc_pj not in body)

    # 11. Pré-cadastro sem CNPJ + sem duplicidade.
    st, body, _ = req(morador, base, '/cliente/nova-organizacao',
                      {'csrf': csrf(req(morador, base, '/cliente/nova-organizacao')[1]),
                       'tipo': 'Empresa', 'nome': 'Empresa Sem CNPJ V94',
                       'endereco': 'Rua Sem Documento 77, Canoas/RS', 'cidade': 'Canoas',
                       'bairro': 'Centro', 'cnpj': '', 'papel': 'Funcionário',
                       'unidade': 'Auxiliar administrativo'})
    with ext.db(db) as c:
        sem = c.execute("SELECT id,cnpj FROM v9_organizacoes WHERE nome='Empresa Sem CNPJ V94'").fetchone()
    verificar('11. pré-cadastro sem CNPJ', st == 200 and sem is not None and sem['cnpj'] is None)
    req(morador, base, '/cliente/nova-organizacao',
        {'csrf': csrf(req(morador, base, '/cliente/nova-organizacao')[1]),
         'tipo': 'Empresa', 'nome': 'Empresa Sem CNPJ V94',
         'endereco': 'Rua Sem Documento 77, Canoas/RS', 'cidade': 'Canoas',
         'bairro': 'Centro', 'cnpj': '', 'papel': 'Funcionário',
         'unidade': 'Auxiliar administrativo'})
    with ext.db(db) as c:
        qtd = c.execute("SELECT COUNT(*) FROM v9_organizacoes WHERE nome='Empresa Sem CNPJ V94'").fetchone()[0]
    verificar('11b. pré-cadastro não duplica organização', qtd == 1, 'total=' + str(qtd))

    # 15. Portal do prestador sem regressões (e área administrativa vê a OS).
    ext.cadastrar(db, 'Prestador Teste', 'prestador@teste.local', 'Senha-Prestador-123')
    p = navegador()
    st, body, _ = req(p, base, '/login', {'email': 'prestador@teste.local', 'senha': 'Senha-Prestador-123'})
    verificar('15. login do prestador', st == 200 and 'Painel principal' in body)
    st, body, _ = req(p, base, '/os')
    verificar('15b. área administrativa lista a OS particular', st == 200 and numero_os in body)
    for caminho in ('/clientes', '/financeiro', '/historico', '/'):
        st, body, _ = req(p, base, caminho)
        verificar('15c. prestador ' + caminho, st == 200)
    st, body, _ = req(navegador(), base, '/cliente/legado')
    verificar('15e. acesso legado por ID+senha ainda disponível', st == 200 and 'cliente_id' in body)


def legado_e_bridge(db):
    # 3b. Servidor antigo (8765) não autentica mais por telefone/e-mail.
    antigo = ServidorPortal(db, str(PASTA), porta=0)
    info = antigo.iniciar()
    try:
        url = info['url_local']
        st, body, _ = req(navegador(), url, '/')
        verificar('3b. porta 8765 encaminha para o portal único',
                  st == 200 and '8766/cliente' in body and 'name="documento"' not in body)
        st, body, _ = req(navegador(), url, '/api/login', {'documento': 'teste@teste.local', 'acesso': ''})
        verificar('3c. /api/login antigo responde 410', st == 410 and 'encerrado' in body)
        st, body, _ = req(navegador(), url, '/api/cadastro', {'documento': '', 'acesso': ''})
        verificar('3d. /api/cadastro antigo responde 410', st == 410)
        st, body, _ = req(navegador(), url, '/api/health')
        verificar('15d. /api/health preservado', st == 200)
    finally:
        antigo.parar()


def porta_real_8766(db):
    # 16. Execução real na porta 8766 exigida pelo projeto.
    try:
        real = PortalPrestador(db, '127.0.0.1', 8766)
        real.iniciar()
    except Exception as exc:
        # Se outro processo já estiver em 8766, ele é o servidor efetivamente usado.
        base = 'http://127.0.0.1:8766'
        st, body, _ = req(navegador(), base, '/api/versao')
        st2, body2, _ = req(navegador(), base, '/cliente')
        verificar('16c. servidor já ativo na porta 8766 usa a versão correta',
                  st == 200 and '9.4.1' in body and st2 == 200 and 'name="cpf"' in body2,
                  'processo antigo em 8766: ' + str(exc))
        return
    try:
        base = 'http://127.0.0.1:8766'
        st, body, _ = req(navegador(), base, '/api/versao')
        verificar('16c. /api/versao identifica a correção v9.4.1',
                  st == 200 and json.loads(body).get('portal_cliente') == '9.4.1')
        st, body, _ = req(navegador(), base, '/cliente')
        verificar('16d. http://127.0.0.1:8766/cliente mostra CPF e senha',
                  st == 200 and 'name="cpf"' in body and 'name="senha"' in body
                  and 'name="documento"' not in body and 'AUTOSEG v9.4.1' in body)
    finally:
        real.parar()


if __name__ == '__main__':
    principal()
