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
    nome_pdf_nf=None,
    operation_key=None
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
        if operation_key:
            message['Message-ID'] = f'<{operation_key}@officina.local>'
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
    from officina.core import prestadores_ext as ext
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


def _enviar_relatorio_os_concluida(banco, os_id, destinatarios=None, *, outbox_operation_key=None):
    """Thread de envio: resolve destinatários, publica o PDF se necessário e envia."""
    from officina.core import produtividade_os as prod
    if outbox_operation_key and os.environ.get('AUTOSEG_GMAIL_DESATIVADO') == '1':
        from officina.core.os_effect_outbox import PreDispatchError
        raise PreDispatchError('Gmail disabled before provider dispatch.')
    if destinatarios is None:
        try:
            destinatarios = prod.destinatarios_conclusao(banco, os_id)
        except Exception as exc:
            if outbox_operation_key:
                from officina.core.os_effect_outbox import PreDispatchError
                raise PreDispatchError('No usable recipients before dispatch.') from exc
            return
    else:
        destinatarios = [str(x) for x in destinatarios if str(x).strip()]
        if not destinatarios:
            if outbox_operation_key:
                from officina.core.os_effect_outbox import PreDispatchError
                raise PreDispatchError('No recipients before dispatch.')
            return
    if not outbox_operation_key:
        prod.registrar_envio(banco, os_id, destinatarios, 'pendente')
    try:
        from officina.core import fluxo_os as fluxo
        from officina.core import prestadores_ext as ext
        documento = fluxo.ultimo_documento(banco, os_id)
        if not documento:
            if outbox_operation_key:
                from officina.core.os_effect_outbox import PreDispatchError
                raise PreDispatchError('PDF not published before sending.')
            fluxo.publicar_relatorio(banco, os_id)
            documento = fluxo.ultimo_documento(banco, os_id)
        if not documento:
            raise ValueError('PDF do relatório não foi publicado.')
        arquivo = fluxo.validar_pdf_publicado(documento)
        with ext.db(banco) as c:
            dados = c.execute(
                "SELECT o.numero_os, cl.nome, o.status, o.valor_total FROM ordens_servico o "
                "JOIN clientes cl ON cl.id=o.cliente_id WHERE o.id=?", (os_id,)).fetchone()
        numero = dados['numero_os'] if dados else f'#{os_id}'
        nome = (dados['nome'] or 'Cliente') if dados else 'Cliente'
        situacao = (dados['status'] if dados else '') or ''
        diagnostico = situacao == 'Pendente' and float((dados['valor_total'] if dados else 0) or 0) == 0
        orcamento = situacao == 'Pendente' and float((dados['valor_total'] if dados else 0) or 0) > 0
        nota = ext.ultima_nota_fiscal(banco, os_id)
        caminho_nf = None
        if nota:
            # Se há nota fiscal associada à OS, ela precisa ser anexada. Falha ao
            # ler o arquivo é erro real: não enviar sem o anexo nem marcar a nota
            # como entregue por causa do relatório.
            _, caminho_nf = ext.obter_nota_fiscal(banco, os_id, nota['id'])
        if diagnostico:
            assunto = f"Ordem de Serviço {numero} — diagnóstico - AUTOSEG"
            corpo = (f"<h3>Olá {nome},</h3><p>A OS {numero} foi encerrada como pendente "
                     f"e o diagnóstico técnico segue em anexo.</p>")
        elif orcamento:
            assunto = f"Ordem de Serviço {numero} — orçamento - AUTOSEG"
            corpo = (f"<h3>Olá {nome},</h3><p>A OS {numero} está pendente e o orçamento "
                     f"segue em anexo.</p>")
        else:
            assunto = f"Ordem de Serviço {numero} Concluída - AUTOSEG"
            corpo = (f"<h3>Olá {nome},</h3><p>Sua OS {numero} foi concluída.</p>"
                     f"<p>Segue em anexo o relatório técnico do atendimento.</p>")
        if caminho_nf:
            corpo += ('<p>A nota fiscal também está anexada a este e-mail.</p>')
        else:
            corpo += '<p>Nenhuma nota fiscal foi anexada a esta OS.</p>'
        if not diagnostico:
            corpo += _dados_pagamento_html(banco, os_id)
        send_options = {'operation_key': outbox_operation_key} if outbox_operation_key else {}
        msg_id = enviar_email_gmail(destinatarios, assunto, corpo,
                                    caminho_pdf_relatorio=arquivo,
                                    caminho_pdf_nf=caminho_nf,
                                    nome_pdf_nf=(nota['nome_original'] if nota else None),
                                    **send_options)
        if not outbox_operation_key:
            prod.registrar_envio(banco, os_id, destinatarios, 'enviado', msg_id)
        return msg_id
    except Exception as erro:
        if outbox_operation_key:
            raise
        try:
            from officina.core import produtividade_os as prod
            prod.registrar_envio(banco, os_id, destinatarios, 'falhou', erro=str(erro))
        except Exception:
            pass


def enviar_operacao_outbox(banco, os_id, operation):
    '''Resolve committed references at dispatch; email addresses stay in domain data.'''
    import json
    from officina.core import prestadores_ext as ext, produtividade_os as prod
    from officina.core.os_effect_outbox import PreDispatchError
    with ext.db(banco) as c:
        effect=c.execute('''SELECT os_id,payload_json FROM os_effect_outbox
            WHERE operation_key=? AND effect_type='email' ''',(operation,)).fetchone()
    if not effect or int(effect['os_id'])!=int(os_id):
        raise PreDispatchError('missing_email_operation')
    try:
        payload=json.loads(effect['payload_json'])
    except (TypeError,ValueError):
        raise PreDispatchError('invalid_email_operation') from None
    refs=payload.get('recipient_refs')
    if (not isinstance(refs,list) or any(ref not in
         ('cliente','sindico','administradora') for ref in refs)):
        raise PreDispatchError('invalid_recipient_references')
    recipients=[]
    contacts=prod.contatos_email_os(banco,os_id)
    for ref in refs:
        address=contacts.get(ref,'')
        if not address:
            raise PreDispatchError('recipient_no_longer_available')
        try:
            address=prod._email_validado(address)
        except ValueError:
            raise PreDispatchError('invalid_recipient') from None
        if address not in recipients:
            recipients.append(address)
    if not recipients:
        raise PreDispatchError('sem_destinatario')
    return _enviar_relatorio_os_concluida(banco,os_id,recipients,
                                          outbox_operation_key=operation)


def enviar_relatorio_os_concluida(banco, os_id, destinatarios=None):
    """Dispara em segundo plano o e-mail do relatório de uma OS concluída.

    Nunca bloqueia a interface nem a resposta HTTP. Se AUTOSEG_GMAIL_DESATIVADO=1,
    não envia (apenas registra a pendência), útil para testes sem rede.
    """
    if os.environ.get('AUTOSEG_GMAIL_DESATIVADO') == '1':
        try:
            from officina.core import produtividade_os as prod
            if destinatarios is None:
                destinatarios = prod.destinatarios_conclusao(banco, os_id)
            prod.registrar_envio(banco, os_id, destinatarios, 'pendente')
        except Exception:
            pass
        return
    threading.Thread(target=_enviar_relatorio_os_concluida, args=(banco, os_id, destinatarios),
                     daemon=True, name='AUTOSEG-Gmail').start()
