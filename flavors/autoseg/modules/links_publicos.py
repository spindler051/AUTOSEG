"""Consulta local dos túneis gerenciados. Nunca confia no cabeçalho Host como URL pública."""
from pathlib import Path
from urllib.parse import urlsplit
import json,os,re,subprocess

from officina.core import runtime_config
BASE=runtime_config.base_dir()
DEV=os.environ.get('AUTOSEG_DEV')=='1'
PORTAS=('8865','8866') if DEV else ('8765','8766')
TUNEIS=BASE/('tuneis_dev' if DEV else 'tuneis')
ARQUIVO=TUNEIS/'estado.json'
URL_RE=re.compile(r'https://[a-z0-9-]+\.trycloudflare\.com',re.I)

def vivo(pid):
    try:
        if not isinstance(pid,int) or pid<=0:return False
        os.kill(pid,0)
        resultado=subprocess.run(['ps','-p',str(pid),'-o','comm='],capture_output=True,text=True,timeout=2)
        return resultado.returncode==0 and 'cloudflared' in resultado.stdout.lower()
    except (OSError,TypeError,ValueError):return False

def estado():
    try: d=json.loads(ARQUIVO.read_text(encoding='utf8'))
    except (ValueError,OSError): d={}
    saida={}
    for porta in PORTAS:
        item=d.get(porta) or {};pid=item.get('pid')
        if not vivo(pid):continue
        # A URL e o registro da conexão aparecem no início do log; depois o
        # arquivo cresce com erros de requisição. Lê as duas pontas para não
        # perder o link quando o log fica grande.
        partes=[]
        try:
            with (TUNEIS/f'{porta}.log').open(encoding='utf8',errors='replace') as arquivo:
                partes.append(arquivo.read(30000))
                try:
                    arquivo.seek(-30000,2);partes.append(arquivo.read())
                except OSError:
                    pass
        except OSError:
            pass
        texto='\n'.join(partes)
        urls=URL_RE.findall(texto)
        if urls and 'Registered tunnel connection' in texto:
            saida[porta]={'url':urls[-1],'pid':pid,'origem':'gerenciado'}
    return saida

def quadro_html():
    import html
    s=estado_com_manuais();parts=[]
    for porta,nome in [(PORTAS[0],'Portal do Cliente'),(PORTAS[1],'Portal do Prestador')]:
        url=s.get(porta,{}).get('url','')
        link=(f'<a href="{html.escape(url,quote=True)}" rel="noopener noreferrer" target="_blank">{html.escape(url)}</a>'
              if url else '<span class="muted">Sem link público verificado</span>')
        parts.append(f'<div><b>{html.escape(nome)} · {porta}</b><p style="overflow-wrap:anywhere">{link}</p></div>')
    return ('<section class="card"><h2>Links públicos atuais</h2>'+''.join(parts)+
        '<small>Os links são obtidos dos processos Cloudflare ativos. Em DEV, use somente dados fictícios; o login do AUTOSEG continua necessário.</small></section>')

# URLs de túneis iniciados em outros Terminais podem ser informadas manualmente.
# Só são exibidas como atuais após verificação HTTP recente; leitura de texto não basta.
import time
import threading
import urllib.request
import urllib.error
REGISTRO_MANUAL=TUNEIS/'enderecos_manuais.json'
_CACHE={}
_MUTEX=threading.Lock()

def registrar_manual(porta,url):
    if DEV:raise ValueError('Registro manual desativado no ambiente DEV protegido.')
    if str(porta) not in PORTAS:raise ValueError('Porta inválida.')
    parsed=urlsplit(str(url).strip())
    if parsed.scheme!='https' or not URL_RE.fullmatch(str(url).strip()) or parsed.username or parsed.password:
        raise ValueError('URL precisa ser um link HTTPS trycloudflare.com exato.')
    if not _verificar(url):
        raise ValueError('O link não respondeu como portal ativo; confirme que o túnel e os servidores continuam em execução.')
    try:d=json.loads(REGISTRO_MANUAL.read_text('utf8'))
    except (OSError,ValueError):d={}
    d[str(porta)]=url
    REGISTRO_MANUAL.write_text(json.dumps(d,indent=2),encoding='utf8')
    with _MUTEX:_CACHE[str(porta)]=(time.time(),True,url)

def _verificar(url):
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'AUTOSEG-v9-link-check'},method='GET')
        with urllib.request.urlopen(request,timeout=3) as r:return 200<=r.status<400
    except urllib.error.HTTPError:return False
    except (OSError,ValueError):return False

def estado_com_manuais():
    # Exibe somente URLs com resposta HTTPS confirmada (cache curto, sem URL falsa).
    descobertos=estado()
    data={}
    agora=time.time()
    for porta,info in descobertos.items():
        url=info['url']
        chave='gerenciado:'+porta
        with _MUTEX:achado=_CACHE.get(chave)
        if achado and achado[2]==url and agora-achado[0]<30:ok=achado[1]
        else:
            ok=True if DEV else _verificar(url)  # link DEV vem do processo do túnel
            with _MUTEX:_CACHE[chave]=(agora,ok,url)
        if ok or DEV:data[porta]=info
    try:reg=json.loads(REGISTRO_MANUAL.read_text('utf8'))
    except (OSError,ValueError):return data
    agora=time.time()
    for porta,url in reg.items():
        if DEV or porta not in PORTAS or porta in data or not URL_RE.fullmatch(str(url)):continue
        with _MUTEX:achado=_CACHE.get(porta)
        if achado and achado[2]==url and agora-achado[0]<60:ok=achado[1]
        else:
            ok=_verificar(url)
            with _MUTEX:_CACHE[porta]=(agora,ok,url)
        if ok:data[porta]={'url':url,'origem':'manual_verificado'}
    return data
