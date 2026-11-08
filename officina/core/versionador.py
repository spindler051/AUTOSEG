#!/usr/bin/env python3
"""Versionador do AUTOSEG. Sem dependencias externas e sem mexer no SQLite."""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARQUIVO = ROOT / 'versao.json'
SEMVER = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(dev|rc)\.([1-9]\d*))?$')

def analisar_versao(valor):
    match = SEMVER.fullmatch(str(valor))
    if not match:
        raise ValueError('Versao invalida: use X.Y.Z, X.Y.Z-dev.N ou X.Y.Z-rc.N')
    return (int(match[1]), int(match[2]), int(match[3]), match[4],
            int(match[5]) if match[5] else None)

def proxima_versao(valor, tipo):
    major, minor, patch, canal, numero = analisar_versao(valor)
    if tipo == 'dev':
        if canal != 'dev':
            raise ValueError('Somente versoes dev podem incrementar dev')
        return f'{major}.{minor}.{patch}-dev.{numero + 1}'
    if tipo == 'rc':
        if canal not in ('dev', 'rc'):
            raise ValueError('RC so pode partir de uma versao em desenvolvimento')
        return f'{major}.{minor}.{patch}-rc.{numero + 1 if canal == "rc" else 1}'
    if tipo == 'stable':
        if canal not in ('rc', 'dev'):
            raise ValueError('Versao ja estavel')
        return f'{major}.{minor}.{patch}'
    if canal is not None:
        raise ValueError('Para mudar major/minor/patch, finalize a versao atual primeiro')
    if tipo == 'major':
        return f'{major + 1}.0.0-dev.1'
    if tipo == 'minor':
        return f'{major}.{minor + 1}.0-dev.1'
    if tipo == 'patch':
        return f'{major}.{minor}.{patch + 1}-dev.1'
    raise ValueError('Tipo de versao desconhecido')

def carregar():
    data = json.loads(ARQUIVO.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('produto') != 'AUTOSEG':
        raise ValueError('versao.json nao corresponde ao AUTOSEG')
    _, _, _, sufixo, _ = analisar_versao(data['versao'])
    canal = 'stable' if sufixo is None else sufixo
    if data.get('canal') != canal:
        raise ValueError(f'Canal incoerente: esperado {canal}')
    if data.get('homologado') is not False and canal != 'stable':
        raise ValueError('Uma versao preliminar nao pode ser homologada')
    return data

def executar_git(*args):
    try:
        resultado = subprocess.run(['git', '-C', str(ROOT), *args],
                                  text=True, capture_output=True, check=True)
        return resultado.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None

def diagnostico():
    data = carregar()
    branch = executar_git('branch', '--show-current')
    dirty = executar_git('status', '--porcelain')
    esperado = {'dev': 'develop', 'stable': 'main', 'rc': 'develop'}[data['canal']]
    return {
        **data,
        'branch': branch,
        'branch_esperado': esperado,
        'branch_correto': branch == esperado,
        'alteracoes_locais': None if dirty is None else len(dirty.splitlines()) if dirty else 0,
        'commit': executar_git('rev-parse', '--short', 'HEAD'),
        'diretorio': str(ROOT),
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description='AUTOSEG - controle de versoes')
    parser.add_argument('acao', choices=['info', 'verificar', 'proxima', 'avancar'], nargs='?', default='info')
    parser.add_argument('--tipo', choices=['dev', 'rc', 'stable', 'major', 'minor', 'patch'])
    parser.add_argument('--json', action='store_true', dest='como_json')
    args = parser.parse_args(argv)
    try:
        d = diagnostico()
        if args.acao in ('proxima', 'avancar'):
            if not args.tipo:
                parser.error('Informe --tipo para simular a proxima versao')
            nova = proxima_versao(d['versao'], args.tipo)
            if args.acao == 'avancar':
                if d['branch'] != 'develop' or args.tipo != 'dev':
                    raise ValueError('Avanco automatico permitido apenas em develop com --tipo dev')
                if executar_git('status', '--porcelain', '--', 'versao.json') is None:
                    raise ValueError('Nao foi possivel conferir o estado Git de versao.json')
                if executar_git('status', '--porcelain', '--', 'versao.json'):
                    raise ValueError('versao.json tem alteracoes locais; revise antes')
                nova_info = carregar()
                nova_info['versao'] = nova
                fd, temporario = tempfile.mkstemp(dir=str(ROOT), prefix='.versao_', suffix='.json')
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as arquivo:
                        json.dump(nova_info, arquivo, ensure_ascii=False, indent=2)
                        arquivo.write('\n')
                    os.replace(temporario, ARQUIVO)
                finally:
                    if os.path.exists(temporario):
                        os.unlink(temporario)
                print(f'Versao atualizada para {nova}. Revise git diff e faca commit quando pronto.')
            else:
                print(nova)
            return 0
        if args.como_json:
            print(json.dumps(d, ensure_ascii=False, indent=2))
        else:
            print(f"AUTOSEG {d['versao']} | {d['revisao']} | {d['canal']}")
            print(f"Branch: {d['branch'] or 'desconhecido'} (esperado: {d['branch_esperado']})")
            print(f"Commit: {d['commit'] or 'nao disponivel'}")
            print(f"Arquivos locais alterados: {d['alteracoes_locais'] if d['alteracoes_locais'] is not None else 'nao verificado'}")
            print(f"Banco: esquema {d['schema_banco']} | homologado: {d['homologado']}")
        if args.acao == 'verificar':
            if d['branch'] is not None and not d['branch_correto']:
                print('ERRO: versao e branch nao combinam', file=sys.stderr)
                return 2
            if d['alteracoes_locais']:
                print('AVISO: ha alteracoes locais; nao faca pull/reset/clean sem backup', file=sys.stderr)
        return 0
    except (ValueError, KeyError, json.JSONDecodeError, OSError) as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
