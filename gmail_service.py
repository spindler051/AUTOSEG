import os
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

CONFIG_DIR = os.path.expanduser('~/.config/autoseg/gmail')
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(CONFIG_DIR, 'token.json')


def _salvar_token(creds):
    """Escrita atômica com permissões privadas, fora do Git."""
    import tempfile
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    fd, temporario = tempfile.mkstemp(prefix='.gmail_token_', dir=CONFIG_DIR)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as arq:
            arq.write(creds.to_json())
        os.chmod(temporario, 0o600)
        os.replace(temporario, TOKEN_FILE)
    finally:
        if os.path.exists(temporario):
            os.unlink(temporario)


def _validar_email(campo):
    import re
    from email.utils import parseaddr
    if not isinstance(campo, str) or len(campo)>254 or any(c in campo for c in '\r\n'):
        raise ValueError('Destinatário inválido.')
    nome, email = parseaddr(campo.strip())
    if nome or email != campo.strip() or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ValueError('Destinatário inválido.')
    return email


def obter_credenciais(interativo=False):
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _salvar_token(creds)
        except Exception as e:
            print(f"[Gmail] Falha ao renovar o token automaticamente: {e}")
            creds = None

    if not creds or not creds.valid:
        if not interativo:
            raise RuntimeError(
                "[Gmail] Autenticação necessária. Nenhuma credencial válida ou refresh token disponível."
            )

        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(f"[Gmail] Arquivo de credenciais não encontrado em: {CREDENTIALS_FILE}")

        # Fluxo desktop localhost. O antigo redirect_uri=urn:ietf:wg:oauth:2.0:oob foi desativado pelo Google.
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES)
        flow.run_local_server(port=0, open_browser=True, authorization_prompt_message='Autorize o AUTOSEG no navegador: {url}')
        creds = flow.credentials

        _salvar_token(creds)
        print("[Gmail] Token gerado e salvo com sucesso!")

    return creds


def enviar_email_gmail(
    destinatario,
    assunto,
    corpo_html,
    cc=None,
    caminho_pdf_relatorio=None,
    caminho_pdf_nf=None
):
    try:
        creds = obter_credenciais(interativo=False)
        service = build('gmail', 'v1', credentials=creds)

        if not isinstance(assunto,str) or any(c in assunto for c in '\r\n'):
            raise ValueError('Assunto inválido.')
        if isinstance(destinatario, (list, tuple)):
            para=', '.join(_validar_email(e) for e in destinatario)
        else:
            para=', '.join(_validar_email(e.strip()) for e in destinatario.split(','))
        copia = cc or []
        if isinstance(copia,str): copia=[x.strip() for x in copia.replace(';',',').split(',') if x.strip()]
        copia=[_validar_email(e) for e in copia]
        message = MIMEMultipart()
        message['To'] = para
        message['Subject'] = assunto

        if copia:
            message['Cc'] = ', '.join(copia)

        message.attach(MIMEText(corpo_html, 'html', 'utf-8'))

        anexos = [caminho_pdf_relatorio, caminho_pdf_nf]
        for caminho in anexos:
            if caminho:
                if not os.path.isfile(caminho):
                    raise FileNotFoundError(f'Anexo PDF não encontrado: {caminho}')
                if not str(caminho).lower().endswith('.pdf') or os.path.getsize(caminho)>20*1024*1024:
                    raise ValueError('Anexo deve ser PDF de até 20 MB.')
                with open(caminho,'rb') as verificar:
                    if verificar.read(5)!=b'%PDF-':
                        raise ValueError('Anexo não é PDF válido.')
                with open(caminho, 'rb') as f:
                    part = MIMEBase('application', 'pdf')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    
                    nome_arquivo = os.path.basename(caminho)
                    part.add_header('Content-Disposition', f'attachment; filename="{nome_arquivo}"')
                    message.attach(part)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        body = {'raw': raw_message}

        send_message = service.users().messages().send(userId="me", body=body).execute()
        msg_id = send_message.get('id')
        print(f"[Gmail] E-mail enviado com sucesso. ID da mensagem: {msg_id}")
        return msg_id

    except HttpError as error:
        erro_detalhe = error.resp.reason if hasattr(error, 'resp') else str(error)
        raise RuntimeError(f"[Gmail] Erro da API do Google: {erro_detalhe}")
    except Exception as e:
        raise RuntimeError(f"[Gmail] Erro ao enviar mensagem: {e}") from e
