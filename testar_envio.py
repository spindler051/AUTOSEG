"""Teste de envio Gmail MANUAL. Nunca executa ao ser importado pelo unittest.

Exige comando explícito --enviar e destinatário informado na execução.
"""
import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description='AUTOSEG: envio Gmail apenas com confirmação explícita')
    parser.add_argument('--enviar', action='store_true', help='Autorizar um envio real de teste')
    parser.add_argument('--destinatario', help='E-mail do destinatário de teste')
    args = parser.parse_args(argv)
    if not args.enviar or not args.destinatario:
        parser.error('Nenhum envio realizado. Use --enviar --destinatario EMAIL somente em ambiente autorizado.')
    import gmail_service
    ident = gmail_service.enviar_email_gmail(
        destinatario=args.destinatario,
        assunto='AUTOSEG — Teste de integração Gmail',
        corpo_html='<p>Teste solicitado manualmente pelo operador AUTOSEG.</p>'
    )
    print('Mensagem enviada; identificador:', ident)


if __name__ == '__main__':
    main()
