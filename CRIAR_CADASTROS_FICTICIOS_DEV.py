"""Gera exatamente 5 clientes PJ, 5 clientes PF e 3 prestadores FICTÍCIOS.
Somente AUTOSEG_DEV=1 e banco dentro de ./dados_teste. Nunca altera produção.
Idempotente: não exclui nada, nem modifica senhas de contas preexistentes.
As senhas novas são aleatórias e mostradas somente no Terminal.
"""
import os
import secrets
import sys
from pathlib import Path

import cadastros_v9 as cad
import atendimento_os as atendimento
import fluxo_os
import prestadores_ext as ext
from banco import criar_banco, proximo_numero_os

BASE = Path(__file__).resolve().parent
PJ = [
    ('Condomínio Horizonte Simulado', 'Condomínio', '975310420001'),
    ('Condomínio Pôr do Sol Demo', 'Condomínio', '975310420002'),
    ('Condomínio Jardim Virtual', 'Condomínio', '975310420003'),
    ('Oficina Atlas Exemplo', 'Empresa', '975310420004'),
    ('Logística Ápice Simulada', 'Empresa', '975310420005'),
]
PF = [
    ('Alex Teste (síndico)', '987654320'),
    ('Bruna Exemplo (síndica)', '987654321'),
    ('Caio Demo (gestor)', '987654322'),
    ('Dani Simulação (moradora)', '987654323'),
    ('Eva Homologação (funcionária)', '987654324'),
]
PRESTADORES = [
    ('Prestador Alfa DEV', 'prestador.alfa@example.invalid'),
    ('Prestadora Beta DEV', 'prestadora.beta@example.invalid'),
    ('Prestador Gama DEV', 'prestador.gama@example.invalid'),
]


def cpf_ficticio(base):
    doc=str(base)
    for n in (9,10):
        d=(sum(int(doc[i])*(n+1-i) for i in range(n))*10)%11
        doc+=str(0 if d==10 else d)
    assert cad.cpf_valido(doc)
    return doc


def cnpj_ficticio(base):
    doc=str(base)
    for pesos in ((5,4,3,2,9,8,7,6,5,4,3,2), (6,5,4,3,2,9,8,7,6,5,4,3,2)):
        resto=sum(int(x)*y for x,y in zip(doc,pesos))%11
        doc+=str(0 if resto<2 else 11-resto)
    assert cad.cnpj_valido(doc)
    return doc


def senha_aleatoria():
    return 'DEV-' + secrets.token_urlsafe(16)


def executar():
    caminho = Path(os.environ.get('GESTAO_BANCO','')).expanduser().resolve()
    esperada = BASE / 'dados_teste'
    if os.environ.get('AUTOSEG_DEV') != '1' or esperada not in caminho.parents or caminho.suffix != '.db':
        raise SystemExit('BLOQUEADO: execute somente o lançador DEV, com GESTAO_BANCO dentro de dados_teste/*.db.')
    if caminho.exists() and caminho.stat().st_size > 50*1024*1024:
        raise SystemExit('BLOQUEADO: banco de testes muito grande para este gerador. Revise o caminho.')
    caminho.parent.mkdir(parents=True,exist_ok=True)
    criar_banco(str(caminho));ext.instalar(str(caminho));fluxo_os.instalar(str(caminho));atendimento.instalar(str(caminho));cad.instalar(str(caminho))
    # Se houver interrupção após criar uma conta, as credenciais de TESTE não se perdem.
    credenciais=caminho.parent/'CREDENCIAIS_FICTICIAS_DEV.txt'
    if credenciais.is_symlink():raise SystemExit('Arquivo de credenciais é link simbólico: operação bloqueada.')
    def guardar(tipo,nome,usuario,senha):
        fd=os.open(str(credenciais),os.O_CREAT|os.O_APPEND|os.O_WRONLY,0o600)
        try:
            os.chmod(credenciais,0o600)
            os.write(fd,f'{tipo} | {nome} | login {usuario} | senha {senha}\n'.encode('utf-8'))
        finally:os.close(fd)
    senhas=[];pjs=[];pfs=[]
    with ext.db(str(caminho)) as c:
        for nome,tipo,base in PJ:
            doc=cnpj_ficticio(base)
            reg=c.execute("SELECT id FROM clientes WHERE documento=? AND tipo_pessoa='Jurídica'",(doc,)).fetchone()
            if reg: cid=reg['id']
            else:
                cid=c.execute('''INSERT INTO clientes(tipo_pessoa,documento,nome,cidade,uf,status,criado_em)
                    VALUES('Jurídica',?,?, 'Porto Alegre','RS','Ativo',?)''',(doc,nome,ext.agora())).lastrowid
            org=cad.sincronizar_cliente_pj(c,cid)
            c.execute("UPDATE v9_organizacoes SET tipo=?,situacao='Validado' WHERE id=?",(tipo,org))
            pjs.append((cid,org,nome,doc))
        for nome,base in PF:
            doc=cpf_ficticio(base)
            reg=c.execute('SELECT id FROM clientes WHERE documento=? AND tipo_pessoa=?',(doc,'Física')).fetchone()
            if reg: cid=reg['id']
            else:
                cid=c.execute('''INSERT INTO clientes(tipo_pessoa,documento,nome,cidade,uf,status,criado_em)
                    VALUES('Física',?,?, 'Porto Alegre','RS','Ativo',?)''',(doc,nome,ext.agora())).lastrowid
            conta=c.execute('SELECT id FROM v9_usuarios WHERE cpf=?',(doc,)).fetchone()
            if conta:uid=conta['id']
            else:
                senha=senha_aleatoria()
                uid=c.execute('''INSERT INTO v9_usuarios(nome,cpf,telefone,email,senha_hash,criado_em,cliente_pf_id)
                    VALUES(?,?,?,?,?,?,?)''',(nome,doc,'51999000000',
                    'pf'+str(len(pfs)+1)+'@example.invalid',ext.senha_hash(senha),ext.agora(),cid)).lastrowid
                senhas.append(('PF cliente',nome,doc,senha));guardar('PF cliente',nome,doc,senha)
            c.execute('UPDATE v9_usuarios SET cliente_pf_id=? WHERE id=?',(cid,uid))
            pfs.append((cid,uid,nome,doc))
    for nome,email in PRESTADORES:
        with ext.db(str(caminho)) as c:
            reg=c.execute('SELECT id FROM prestadores WHERE email=?',(email,)).fetchone()
        if not reg:
            senha=senha_aleatoria()
            ext.cadastrar(str(caminho),nome,email,senha,especialidade='Testes e manutenção')
            senhas.append(('Prestador',nome,email,senha));guardar('Prestador',nome,email,senha)
    for idx,idxpf in ((0,0),(1,1),(3,2)):
        # Primeiro condomínio, segundo condomínio e primeira empresa com responsável.
        with ext.db(str(caminho)) as c:
            atual=c.execute('SELECT usuario_id FROM v9_responsaveis WHERE organizacao_id=?',(pjs[idx][1],)).fetchone()
        if atual is None:
            cad.atribuir_responsavel(str(caminho),pjs[idx][1],pfs[idxpf][1],'Gerador de teste DEV')
    for org_i,pf_i,papel,unidade in ((0,3,'Morador','Apartamento 101'),(3,4,'Funcionário','Recepção')):
        with ext.db(str(caminho)) as c:
            vinc=c.execute('SELECT id FROM v9_vinculos WHERE organizacao_id=? AND usuario_id=?',
                           (pjs[org_i][1],pfs[pf_i][1])).fetchone()
        if not vinc:
            cad.solicitar_vinculo(str(caminho),pfs[pf_i][1],pjs[org_i][1],papel,unidade)
            with ext.db(str(caminho)) as c:
                vid=c.execute('SELECT id FROM v9_vinculos WHERE organizacao_id=? AND usuario_id=?',
                               (pjs[org_i][1],pfs[pf_i][1])).fetchone()['id']
            cad.alterar_vinculo(str(caminho),vid,True,'Gerador DEV')
    # Cria dois chamados legítimos e uma OS do prestador para testar a visão da organização.
    for org_i,pf_i,papel,unidade,descricao in ((0,3,'Morador','Apartamento 101',
                    'A porta automática de teste não está abrindo.'),
                 (3,4,'Funcionário','Recepção',
                    'Solicitação simulada de revisão da iluminação.')):
        with ext.db(str(caminho)) as c:
            reg=c.execute('SELECT id FROM v9_chamados WHERE organizacao_id=? AND usuario_id=? AND descricao=?',
                          (pjs[org_i][1],pfs[pf_i][1],descricao)).fetchone()
        if not reg:
            cad.registrar_chamado(str(caminho),pfs[pf_i][1],pjs[org_i][1],descricao,'Normal',unidade,papel,pfs[pf_i][2],'51999990000')
    with ext.db(str(caminho)) as c:
        cliente_id=pjs[0][0]
        existe=c.execute("SELECT id FROM ordens_servico WHERE cliente_id=? AND descricao=?",(cliente_id,
                         'OS administrativa de demonstração — fechadura')).fetchone()
        if not existe:
            c.execute('''INSERT INTO ordens_servico(numero_os,cliente_id,descricao,data_abertura,criado_em,origem,status)
                VALUES(?,?,?,?,?,'App','Aberta')''',
                (proximo_numero_os(c.cursor()),cliente_id,'OS administrativa de demonstração — fechadura',
                 ext.agora(),ext.agora()))
    with ext.db(str(caminho)) as c:
        print('Banco:',caminho)
        for t in ('clientes','v9_organizacoes','v9_usuarios','prestadores','v9_responsaveis','ordens_servico'):
            print(f'{t}:',c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0])
    print('\nCADASTROS PJ (100% fictícios):')
    for _,org,nome,cnpj in pjs:print(f'  org #{org} {nome} | CNPJ teste {cnpj}')
    print('\nCADASTROS PF (100% fictícios):')
    for _,uid,nome,cpf in pfs:print(f'  PF #{uid} {nome} | CPF teste {cpf}')
    print('\nPRESTADORES DE TESTE:')
    for nome,email in PRESTADORES:print(' ',nome,'|',email)
    print('\nCREDENCIAIS CRIADAS AGORA (somente no Terminal; não estão no ZIP):')
    for tipo,nome,usuario,senha in senhas:
        print(f'  {tipo} | {nome} | login {usuario} | senha {senha}')
    if not senhas:print('  Nenhuma conta nova: não alteramos senhas já existentes.')
    print('Credenciais fictícias guardadas localmente em:',credenciais)
    print('\nNÃO ENVIE senhas reais a ninguém. Este gerador não envia e-mails e não acessa a internet.')


if __name__=='__main__':executar()
