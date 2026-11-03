"""Envio de e-mail pela Gmail API, com credenciais fora do repositório.

As bibliotecas do Google são importadas sob demanda (lazy), para que o módulo
possa ser importado sem dependências instaladas e a interface nunca trave: o
envio ocorre em thread separada e qualquer falha é registrada no banco.
"""
import os
import base64
import threading
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

CONFIG_DIR = os.path.expanduser('~/.config/autoseg/gmail')
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(CONFIG_DIR, 'token.json')


def _google_libs():
    """Importa as bibliotecas do Google somente quando forem necessárias."""
    from google.auth.transport.requests import Request  # noqa: F401
    from google.oauth2.credentials import Credentials  # noqa: F401
    from googleapiclient.discovery import build  # noqa: F401
    from googleapiclient.errors import HttpError  # noqa: F401
    return Request, Credentials, build, HttpError


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
    if not isinstance(campo, str) or len(campo) > 254 or any(c in campo for c in '\r\n'):
        raise ValueError('Destinatário inválido.')
    nome, email = parseaddr(campo.strip())
    if nome or email != campo.strip() or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        raise ValueError('Destinatário inválido.')
    return email


def _dominio_reservado(email):
    """Bloqueia domínios de teste/exemplo que sempre geram retorno de erro."""
    dominio = str(email or '').rsplit('@', 1)[-1].strip().lower()
    return (dominio in {'example.com', 'example.net', 'example.org', 'example.edu'}
            or dominio.endswith(('.example', '.test', '.invalid', '.localhost')))


def obter_credenciais(interativo=False):
    Request, Credentials, build, HttpError = _google_libs()
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

        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES)
        flow.run_local_server(port=0, open_browser=True,
                              authorization_prompt_message='Autorize o AUTOSEG no navegador: {url}')
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
    caminho_pdf_nf=None,
    usar_bcc=False,
    nome_pdf_relatorio=None,
    nome_pdf_nf=None
):
    HttpError = None
    try:
        if not isinstance(assunto, str) or any(c in assunto for c in '\r\n'):
            raise ValueError('Assunto inválido.')
        if isinstance(destinatario, (list, tuple)):
            para_lista = [_validar_email(e) for e in destinatario]
        else:
            para_lista = [_validar_email(e.strip()) for e in destinatario.split(',') if e.strip()]
        if not para_lista:
            raise ValueError('Informe ao menos um destinatário.')
        copia = cc or []
        if isinstance(copia, str):
            copia = [x.strip() for x in copia.replace(';', ',').split(',') if x.strip()]
        copia = [_validar_email(e) for e in copia]
        bloqueados = [e for e in para_lista + copia if _dominio_reservado(e)]
        if bloqueados:
            raise ValueError('Destinatário de teste/exemplo bloqueado para evitar devoluções: '
                             + ', '.join(bloqueados))

        Request, Credentials, build, HttpError = _google_libs()
        creds = obter_credenciais(interativo=False)
        service = build('gmail', 'v1', credentials=creds)

        message = MIMEMultipart()
        if usar_bcc and len(para_lista) > 1:
            # Evita expor os endereços entre os destinatários.
            message['To'] = para_lista[0]
            message['Bcc'] = ', '.join(para_lista[1:])
        else:
            message['To'] = ', '.join(para_lista)
        message['Subject'] = assunto
        if copia:
            message['Cc'] = ', '.join(copia)

        message.attach(MIMEText(corpo_html, 'html', 'utf-8'))

        anexos = [caminho_pdf_relatorio, caminho_pdf_nf]
        for indice, caminho in enumerate(anexos):
            if caminho:
                if not os.path.isfile(caminho):
                    raise FileNotFoundError(f'Anexo PDF não encontrado: {caminho}')
                if not str(caminho).lower().endswith('.pdf') or os.path.getsize(caminho) > 20 * 1024 * 1024:
                    raise ValueError('Anexo deve ser PDF de até 20 MB.')
                with open(caminho, 'rb') as verificar:
                    if verificar.read(5) != b'%PDF-':
                        raise ValueError('Anexo não é PDF válido.')
                with open(caminho, 'rb') as f:
                    part = MIMEBase('application', 'pdf')
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    nome_arquivo = ((nome_pdf_relatorio if indice == 0 else nome_pdf_nf)
                                    or os.path.basename(caminho))
                    part.add_header('Content-Disposition', f'attachment; filename="{Path(nome_arquivo).name}"')
                    message.attach(part)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        send_message = service.users().messages().send(userId="me", body={'raw': raw_message}).execute()
        msg_id = send_message.get('id')
        print(f"[Gmail] E-mail enviado com sucesso. ID da mensagem: {msg_id}")
        return msg_id

    except Exception as error:
        if HttpError is not None and isinstance(error, HttpError):
            erro_detalhe = error.resp.reason if hasattr(error, 'resp') else str(error)
            raise RuntimeError(f"[Gmail] Erro da API do Google: {erro_detalhe}") from error
        raise RuntimeError(f"[Gmail] Erro ao enviar mensagem: {error}") from error


def _dados_pagamento_html(banco, os_id):
    """Dados bancários do prestador responsável pela OS, sem usar dados fixos."""
    import html as _html
    import prestadores_ext as ext
    with ext.db(banco) as c:
        pid = ext.responsavel_atual(c, os_id)
    if not pid:
        return ''
    config = ext.obter_config_prestador(banco, pid)
    itens = []
    for rotulo, chave in (('Favorecido', 'banco_titular'), ('Instituição', 'banco_nome'),
                          ('Agência', 'banco_agencia'), ('Conta', 'banco_conta'),
                          ('Chave Pix', 'chave_pix')):
        valor = str(config.get(chave) or '').strip()
        if valor:
            itens.append(f'<li><b>{rotulo}:</b> {_html.escape(valor)}</li>')
    texto = str(config.get('dados_bancarios_texto') or '').strip()
    if texto:
        itens.append('<li><b>Dados bancários:</b> '
                     + _html.escape(texto).replace('\n', '<br>') + '</li>')
    if not itens:
        return '<h4>Dados para pagamento</h4><p>Dados bancários do prestador responsável ainda não cadastrados.</p>'
    return '<h4>Dados para pagamento</h4><ul>' + ''.join(itens) + '</ul>'


def email_teste_dev():
    """Em DEV, centraliza os envios em um endereço de teste (evita example.com)."""
    if os.environ.get('AUTOSEG_DEV') != '1':
        return ''
    escolhido = os.environ.get('AUTOSEG_EMAIL_TESTE', '').strip()
    if escolhido:
        return escolhido
    try:
        import prestadores_ext as ext
        arquivo = ext.BASE / 'dados_teste' / 'email_teste.txt'
        if arquivo.is_file():
            return arquivo.read_text(encoding='utf-8').strip().splitlines()[0].strip()
    except Exception:
        pass
    return ''


def _enviar_relatorio_os_concluida(banco, os_id, destinatarios=None):
    """Thread de envio: resolve destinatários, publica o PDF se necessário e envia."""
    import produtividade_os as prod
    if destinatarios is None:
        try:
            destinatarios = prod.destinatarios_conclusao(banco, os_id)
        except Exception:
            # Sem e-mail válido cadastrado não há o que enviar.
            return
    else:
        destinatarios = [str(x) for x in destinatarios if str(x).strip()]
        if not destinatarios:
            return
    teste = email_teste_dev()
    if teste:
        # Em desenvolvimento, nunca dispara para example.com/.invalid.
        destinatarios = [teste]
    prod.registrar_envio(banco, os_id, destinatarios, 'pendente')
    try:
        import fluxo_os as fluxo
        import prestadores_ext as ext
        documento = fluxo.ultimo_documento(banco, os_id)
        if not documento:
            fluxo.publicar_relatorio(banco, os_id)
            documento = fluxo.ultimo_documento(banco, os_id)
        if not documento:
            raise ValueError('PDF do relatório não foi publicado.')
        arquivo = fluxo.validar_pdf_publicado(documento)
        with ext.db(banco) as c:
            dados = c.execute(
                "SELECT o.numero_os, cl.nome FROM ordens_servico o "
                "JOIN clientes cl ON cl.id=o.cliente_id WHERE o.id=?", (os_id,)).fetchone()
        numero = dados['numero_os'] if dados else f'#{os_id}'
        nome = (dados['nome'] or 'Cliente') if dados else 'Cliente'
        nota = ext.ultima_nota_fiscal(banco, os_id)
        caminho_nf = None
        if nota:
            try:
                _, caminho_nf = ext.obter_nota_fiscal(banco, os_id, nota['id'])
            except Exception:
                caminho_nf = None
        assunto = f"Ordem de Serviço {numero} Concluída - AUTOSEG"
        corpo = (f"<h3>Olá {nome},</h3><p>Sua OS {numero} foi concluída.</p>"
                 f"<p>Segue em anexo o relatório técnico do atendimento.</p>")
        if caminho_nf:
            corpo += '<p>A nota fiscal está anexada a este e-mail.</p>'
        corpo += _dados_pagamento_html(banco, os_id)
        msg_id = enviar_email_gmail(destinatarios, assunto, corpo,
                                    caminho_pdf_relatorio=arquivo,
                                    caminho_pdf_nf=caminho_nf, usar_bcc=True,
                                    nome_pdf_nf=(nota['nome_original'] if nota else None))
        prod.registrar_envio(banco, os_id, destinatarios, 'enviado', msg_id)
    except Exception as erro:
        try:
            import produtividade_os as prod
            prod.registrar_envio(banco, os_id, destinatarios, 'falhou', erro=str(erro))
        except Exception:
            pass


def enviar_relatorio_os_concluida(banco, os_id, destinatarios=None):
    """Dispara em segundo plano o e-mail do relatório de uma OS concluída.

    Nunca bloqueia a interface nem a resposta HTTP. Se AUTOSEG_GMAIL_DESATIVADO=1,
    não envia (apenas registra a pendência), útil para testes sem rede.
    """
    if os.environ.get('AUTOSEG_GMAIL_DESATIVADO') == '1':
        try:
            import produtividade_os as prod
            if destinatarios is None:
                destinatarios = prod.destinatarios_conclusao(banco, os_id)
            teste = email_teste_dev()
            if teste:
                destinatarios = [teste]
            prod.registrar_envio(banco, os_id, destinatarios, 'pendente')
        except Exception:
            pass
        return
    threading.Thread(target=_enviar_relatorio_os_concluida, args=(banco, os_id, destinatarios),
                     daemon=True, name='AUTOSEG-Gmail').start()
