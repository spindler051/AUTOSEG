"""Envio Gmail via OAuth já configurado no computador servidor.
Nunca solicita autorização interativa numa requisição web.
Credenciais em ~/.config/autoseg/gmail (fora do repositório).
"""
import base64
from email.message import EmailMessage
from pathlib import Path

SCOPES=['https://www.googleapis.com/auth/gmail.send']
TOKEN=Path.home()/'.config'/'autoseg'/'gmail'/'token.json'


def enviar_email_gmail(destinatarios,assunto,corpo_html,caminho_pdf_relatorio=None):
    if not isinstance(destinatarios,(list,tuple)) or not destinatarios:
        raise ValueError('Destinatários obrigatórios.')
    from produtividade_os import _email_validado
    destinos=list(dict.fromkeys(_email_validado(x) for x in destinatarios))
    if any(not x for x in destinos):
        raise ValueError('Destinatários inválidos.')
    if '\n' in assunto or '\r' in assunto:
        raise ValueError('Assunto inválido.')
    if not TOKEN.is_file():
        raise RuntimeError('Gmail não autorizado neste Mac; configure o token OAuth fora do Git.')
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError('Instale dependências do Gmail: google-api-python-client google-auth-oauthlib') from e
    creds=Credentials.from_authorized_user_file(str(TOKEN),SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Token rotacionado somente em arquivo privado fora do projeto.
        import os
        import tempfile
        fd,temp=tempfile.mkstemp(prefix='.gmail_',dir=str(TOKEN.parent))
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as arquivo:
                arquivo.write(creds.to_json())
            os.chmod(temp,0o600)
            os.replace(temp,TOKEN)
        finally:
            if os.path.exists(temp):os.unlink(temp)
    if not creds.valid:
        raise RuntimeError('Token Gmail sem autorização válida.')
    email=EmailMessage()
    email['To']=', '.join(destinos)
    email['Subject']=assunto
    email.set_content('Segue o relatório técnico da ordem de serviço em anexo.')
    email.add_alternative(corpo_html,subtype='html')
    if caminho_pdf_relatorio:
        pdf=Path(caminho_pdf_relatorio)
        if not pdf.is_file() or pdf.stat().st_size>20*1024*1024:
            raise ValueError('PDF não encontrado ou maior que 20 MB.')
        dados=pdf.read_bytes()
        if not dados.startswith(b'%PDF-'):
            raise ValueError('Documento inválido; não é PDF.')
        email.add_attachment(dados,maintype='application',subtype='pdf',filename=pdf.name)
    api=build('gmail','v1',credentials=creds,cache_discovery=False)
    resposta=api.users().messages().send(
        userId='me',body={'raw':base64.urlsafe_b64encode(email.as_bytes()).decode('ascii')}
    ).execute()
    ident=resposta.get('id')
    if not ident:raise RuntimeError('Gmail não confirmou ID da mensagem.')
    return ident
