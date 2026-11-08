"""Cloudflare Quick Tunnels DEV sob demanda, sem PIN/Access adicional.

Os endereços são públicos: os portais exigem seus próprios logins.
Publica somente cliente 8865 e prestador 8866, sem expor desktop/produção.
NUNCA use informações reais no banco de testes.
"""
from __future__ import annotations
import sys as _sys
from pathlib import Path as _Path
if __package__ in (None, ''):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))

import argparse
import json
import os
import re
import shutil
import signal
import socket
import urllib.request
import subprocess
import time
from pathlib import Path

BASE=Path(__file__).resolve().parent
DIR=BASE/'tuneis_dev'
ESTADO=DIR/'estado.json'
PORTAS=(8865,8866)


def verificar_ambiente():
    if os.getenv('AUTOSEG_DEV')!='1':
        raise RuntimeError('Execute exclusivamente com AUTOSEG_DEV=1.')
    banco=Path(os.environ.get('GESTAO_BANCO', str(BASE/'dados_teste'/'autoseg_teste.db'))).resolve()
    esperado=(BASE/'dados_teste'/'autoseg_teste.db').resolve()
    if banco!=esperado or not banco.is_file():
        raise RuntimeError('Banco DEV fictício ausente ou divergente; publicação bloqueada.')
    if not esperado.is_relative_to((BASE/'dados_teste').resolve()):
        raise RuntimeError('Banco DEV está fora da pasta de testes; publicação bloqueada.')
    for porta in PORTAS:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{porta}/',timeout=2) as resp:
                cabecalho=resp.headers.get('X-AUTOSEG-Portal','')
                if not cabecalho.startswith('9.'):
                    raise RuntimeError(f'A porta {porta} não responde como portal AUTOSEG; publicação bloqueada.')
        except OSError as exc:
            raise RuntimeError(f'Portal DEV 127.0.0.1:{porta} indisponível. Inicie o AUTOSEG DEV primeiro.') from exc


def obter_executavel():
    exe=shutil.which('cloudflared') or ('/usr/local/bin/cloudflared' if Path('/usr/local/bin/cloudflared').is_file() else None)
    if not exe:raise RuntimeError('cloudflared não encontrado; instale/atualize-o no Mac.')
    info=subprocess.run([exe,'--version'],capture_output=True,text=True,timeout=8)
    if info.returncode!=0:raise RuntimeError('Não foi possível identificar a versão do cloudflared.')
    return exe


def _processo_valido(pid,porta):
    if not isinstance(pid,int) or pid<=0:return False
    try:
        cp=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=3)
        return cp.returncode==0 and 'cloudflared' in cp.stdout and f'127.0.0.1:{porta}' in cp.stdout 
    except (OSError,subprocess.TimeoutExpired):return False


def _ler_estado():
    try:return json.loads(ESTADO.read_text(encoding='utf8'))
    except (OSError,ValueError):return {}


def iniciar():
    verificar_ambiente()
    exe=obter_executavel()
    DIR.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(DIR,0o700)
    d=_ler_estado()
    for porta in PORTAS:
        anterior=d.get(str(porta),{})
        if _processo_valido(anterior.get('pid'),porta):
            print(f'[DEV] Túnel já ativo na porta {porta}; use Parar antes de recriar o túnel.')
            continue
        log_path=DIR/f'{porta}.log'
        args=[exe,'tunnel','--url',f'http://127.0.0.1:{porta}']
        with log_path.open('w',encoding='utf8') as log:
            os.chmod(log_path,0o600)
            p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                               start_new_session=True,cwd=str(BASE))
        d[str(porta)]={'pid':p.pid}
        ESTADO.write_text(json.dumps(d),encoding='utf8')
        os.chmod(ESTADO,0o600)
        print(f'[DEV] Túnel público DEV solicitado para a porta {porta} (PID {p.pid}).')
    # Apenas URLs reais emitidas pelo cloudflared; pode demorar a aparecer.
    from flavors.autoseg.modules import links_publicos as links
    for _ in range(40):
        e=links.estado()
        if len(e)==len(PORTAS):break
        time.sleep(.5)
    e=links.estado()
    for porta in PORTAS:
        inf=e.get(str(porta))
        print(f'[DEV] {"Cliente" if porta==8865 else "Prestador"}: '+(inf['url'] if inf else 'sem link disponível; confira o log'))
    print('ATENÇÃO: URL pública, sem PIN Cloudflare. Login do AUTOSEG continua obrigatório. Use somente dados fictícios.')


def parar():
    d=_ler_estado()
    for porta in PORTAS:
        item=d.get(str(porta),{})
        pid=item.get('pid')
        if _processo_valido(pid,porta):
            try:os.killpg(pid,signal.SIGTERM)
            except OSError:pass
            print(f'[DEV] Túnel da porta {porta} encerrado.')
    if DIR.exists():
        ESTADO.write_text('{}',encoding='utf8')
        os.chmod(ESTADO,0o600)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description='Compartilhar portais AUTOSEG DEV com login próprio')
    cli.add_argument('acao',choices=('iniciar','parar','status'))
    op=cli.parse_args()
    try:
        if op.acao=='iniciar':
            iniciar()
        elif op.acao=='parar':parar()
        else:
            from flavors.autoseg.modules.links_publicos import estado
            for porta,inf in estado().items():print(porta,inf['url'])
    except (ValueError,RuntimeError) as exc:
        cli.exit(1, f'Erro: {exc}\n')
