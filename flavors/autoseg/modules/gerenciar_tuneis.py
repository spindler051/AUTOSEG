"""Túneis temporários de TESTE, inicialização explícita (não publica automaticamente)."""
import sys as _sys
from pathlib import Path as _Path
if __package__ in (None, ''):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))
import argparse,json,os,re,shutil,signal,subprocess,sys,time
from pathlib import Path
from flavors.autoseg.modules import links_publicos as links
DIR=links.TUNEIS
DIR.mkdir(exist_ok=True)

def iniciar():
    if os.environ.get("AUTOSEG_DEV") == "1":
        raise RuntimeError("AUTOSEG DEV: publicação Cloudflare bloqueada.")
    exe=shutil.which('cloudflared') or '/usr/local/bin/cloudflared'
    if not Path(exe).is_file():raise RuntimeError('cloudflared não encontrado. Instale primeiro pelo Terminal.')
    atual=links.estado()
    try:d=json.loads(links.ARQUIVO.read_text())
    except (OSError,ValueError):d={}
    for porta in ('8765','8766'):
        if porta in atual:
            print(f'Porta {porta}: túnel v9 já conectado: {atual[porta]["url"]}');continue
        arquivo=DIR/f'{porta}.log'
        with arquivo.open('w',encoding='utf8') as log:
            p=subprocess.Popen([exe,'tunnel','--url',f'http://127.0.0.1:{porta}'],
                               stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                               start_new_session=True,cwd=str(links.BASE))
        d[porta]={'pid':p.pid};links.ARQUIVO.write_text(json.dumps(d),encoding='utf8')
        print(f'Porta {porta}: túnel de TESTE iniciado (PID {p.pid}).')
    # Não inventar link; lê somente aquele efetivamente emitido pelo cloudflared.
    for _ in range(30):
        e=links.estado()
        if len(e)==2:break
        time.sleep(0.5)
    print('Links detectados:')
    for porta,inf in links.estado().items():print(porta,inf['url'])
    print('IMPORTANTE: links públicos sem autenticação adicional. Use APENAS dados fictícios em testes.')

def parar():
    try:d=json.loads(links.ARQUIVO.read_text())
    except (OSError,ValueError):d={}
    for porta,inf in d.items():
        pid=inf.get('pid')
        if links.vivo(pid):
            try:os.killpg(pid,signal.SIGTERM)
            except OSError:pass
        print('Túnel gerenciado '+porta+' encerrado.')
    links.ARQUIVO.write_text('{}',encoding='utf8')

if __name__=='__main__':
    op=argparse.ArgumentParser();op.add_argument('acao',choices=['iniciar','parar','estado','registrar']);args=op.parse_args()
    if args.acao=='iniciar':iniciar()
    elif args.acao=='parar':parar()
    elif args.acao=='registrar':
        for porta in ('8765','8766'):
            u=input('Link HTTPS ativo da porta '+porta+' (deixe vazio para ignorar): ').strip()
            if u:
                try:links.registrar_manual(porta,u);print('Verificado e registrado:',u)
                except ValueError as ex:print('Não registrado:',ex)
    else:
        e=links.estado_com_manuais()
        for porta in ('8765','8766'):print(porta,e.get(porta,{}).get('url','sem túnel gerenciado ativo'))
