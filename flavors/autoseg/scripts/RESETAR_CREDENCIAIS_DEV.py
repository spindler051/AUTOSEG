"""Restaura as credenciais fictícias de DEV a partir do arquivo local.

- Lê CREDENCIAIS_FICTICIAS_DEV.txt ao lado do banco de testes.
- Se houver login repetido (gerações antigas), mantém a ÚLTIMA senha.
- Reescreve o arquivo sem duplicatas (backup .bak).
- Atualiza os hashes no SQLite de testes e confere cada login.
Nunca use este script contra o banco de produção.
"""
import sys as _sys
from pathlib import Path as _Path
if __package__ in (None, ''):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

from officina.core import runtime_config

if os.environ.get('AUTOSEG_DEV') == '1':
    runtime_config.configure_server()

from officina.core import cadastros_v9 as cad  # noqa: E402
from officina.core import prestadores_ext as ext  # noqa: E402


def main():
    if os.environ.get('AUTOSEG_DEV') != '1':
        print('BLOQUEADO: este reset só roda com AUTOSEG_DEV=1.')
        return 2
    runtime_config.configure_server()
    banco = Path(os.environ['GESTAO_BANCO']).expanduser()
    arquivo = banco.parent / 'CREDENCIAIS_FICTICIAS_DEV.txt'
    if not arquivo.is_file():
        print(f'Arquivo não encontrado: {arquivo}')
        return 1
    if not banco.is_file():
        print(f'Banco de testes não encontrado: {banco}')
        return 1
    linhas = [l.strip() for l in arquivo.read_text(encoding='utf-8').splitlines() if l.strip()]
    unicos = {}
    ordem = []
    for linha in linhas:
        m = re.search(r'login\s+(\S+)\s+\|\s+senha\s+(\S+)', linha)
        if not m:
            continue
        login, senha = m.group(1), m.group(2)
        if login not in unicos:
            ordem.append(login)
        unicos[login] = (linha.split('|')[0].strip(), senha)
    if not unicos:
        print('Nenhuma credencial válida encontrada.')
        return 1
    shutil.copy2(arquivo, arquivo.with_suffix('.txt.bak'))
    novas = []
    con = sqlite3.connect(banco)
    pf = pr = 0
    for login in ordem:
        tipo, senha = unicos[login]
        nome = ''
        if tipo.startswith('PF'):
            cur = con.execute('UPDATE v9_usuarios SET senha_hash=? WHERE cpf=?',
                              (ext.senha_hash(senha), cad.digitos(login)))
            pf += cur.rowcount
            row = con.execute('SELECT nome FROM v9_usuarios WHERE cpf=?', (cad.digitos(login),)).fetchone()
            nome = row[0] if row else ''
        else:
            cur = con.execute('UPDATE prestadores SET senha_hash=? WHERE email=?',
                              (ext.senha_hash(senha), login))
            pr += cur.rowcount
            row = con.execute('SELECT nome FROM prestadores WHERE email=?', (login,)).fetchone()
            nome = row[0] if row else ''
        novas.append(f'{tipo} | {nome} | login {login} | senha {senha}')
    con.commit()
    con.close()
    arquivo.write_text('\n'.join(novas) + '\n', encoding='utf-8')
    print(f'Credenciais atualizadas: {pf} conta(s) PF e {pr} prestador(es).')
    falhas = []
    for login in ordem:
        tipo, senha = unicos[login]
        if tipo.startswith('PF'):
            ok = bool(cad.autenticar(str(banco), login, senha))
        else:
            ok = bool(ext.autenticar(str(banco), login, senha))
        print(('OK  ' if ok else 'FALHA ') + login)
        if not ok:
            falhas.append(login)
    return 0 if not falhas else 2


if __name__ == '__main__':
    raise SystemExit(main())
