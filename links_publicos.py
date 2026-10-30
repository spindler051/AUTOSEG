"""Consulta local dos túneis gerenciados. Nunca confia no cabeçalho Host como URL pública."""
from pathlib import Path
from urllib.parse import urlsplit
import json,os,re,subprocess

BASE=Path(__file__).resolve().parent
TUNEIS=BASE/'tuneis'
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
    for porta in ('8765','8766'):
        item=d.get(porta) or {};pid=item.get('pid')
        if not vivo(pid):continue
        try: texto=(TUNEIS/f'{porta}.log').read_text(encoding='utf8')[-20000:]
        except OSError: texto=''
        urls=URL_RE.findall(texto)
        if urls and 'Registered tunnel connection' in texto:saida[porta]={'url':urls[-1],'pid':pid,'origem':'gerenciado'}
    return saida

def quadro_html():
    import html
    s=estado_com_manuais();parts=[]
    for porta,nome in [('8765','Portal do Cliente'),('8766','Portal do Prestador')]:
        url=s.get(porta,{}).get('url','')
        link=(f'<a href="{html.escape(url,quote=True)}" rel="noopener noreferrer" target="_blank">{html.escape(url)}</a>'
              if url else '<span class="muted">Sem link público verificado</span>')
        parts.append(f'<div><b>{html.escape(nome)} · {porta}</b><p style="overflow-wrap:anywhere">{link}</p></div>')
    return ('<section class="card"><h2>Links públicos atuais</h2>'+''.join(parts)+
        '<small>Os links são identificados nos logs do Cloudflare e conferidos por HTTPS. Links indisponíveis deixam de aparecer.</small></section>')

# URLs de túneis iniciados em outros Terminais podem ser informadas manualmente.
# Só são exibidas como atuais após verificação HTTP recente, nunca por mera leitura de texto.
import time
import threading
import urllib.request
import urllib.error
REGISTRO_MANUAL=TUNEIS/'enderecos_manuais.json'
_CACHE={}
_MUTEX=threading.Lock()

def registrar_manual(porta,url):
    if str(porta) not in ('8765','8766'):raise ValueError('Porta inválida.')
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
            ok=_verificar(url)
            with _MUTEX:_CACHE[chave]=(agora,ok,url)
        if ok:data[porta]=info
    try:reg=json.loads(REGISTRO_MANUAL.read_text('utf8'))
    except (OSError,ValueError):return data
    agora=time.time()
    for porta,url in reg.items():
        if porta not in ('8765','8766') or porta in data or not URL_RE.fullmatch(str(url)):continue
        with _MUTEX:achado=_CACHE.get(porta)
        if achado and achado[2]==url and agora-achado[0]<60:ok=achado[1]
        else:
            ok=_verificar(url)
            with _MUTEX:_CACHE[porta]=(agora,ok,url)
        if ok:data[porta]={'url':url,'origem':'manual_verificado'}
    return data
