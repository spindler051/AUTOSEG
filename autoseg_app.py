"""Bootstrap do AUTOSEG.app (PyInstaller).

Mantém o banco, anexos, PDFs, rascunhos e logs fora do bundle, na pasta
MAIN (~/gestaoservicos_MAIN) ou na pasta indicada por AUTOSEG_BASE.
Não inicia uma segunda instância concorrente na mesma pasta.
"""
import fcntl
import os
import sys
import traceback
from pathlib import Path


def _base():
    return Path(os.environ.get('AUTOSEG_BASE') or (Path.home() / 'gestaoservicos_MAIN')).expanduser()


def _mostrar_erro(titulo, texto):
    try:
        import tkinter as tk
        from tkinter import messagebox
        raiz = tk.Tk()
        raiz.withdraw()
        messagebox.showerror(titulo, texto)
        raiz.destroy()
    except Exception:
        print(f'{titulo}: {texto}', file=sys.stderr)


def main():
    base = _base()
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as erro:
        _mostrar_erro('AUTOSEG', f'Não foi possível acessar a pasta de dados:\n{base}\n\n{erro}')
        return 1
    os.environ['AUTOSEG_BASE'] = str(base)
    os.environ.setdefault('GESTAO_BANCO', str(base / 'dados.db'))
    (base / 'logs').mkdir(parents=True, exist_ok=True)

    # Trava exclusiva no sistema de arquivos: evita duas instâncias da mesma pasta.
    trava = open(base / '.autoseg.lock', 'a+')
    try:
        fcntl.flock(trava.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        _mostrar_erro('AUTOSEG', 'O AUTOSEG já está aberto nesta pasta.\nFeche a outra janela antes de abrir novamente.')
        return 0
    trava.seek(0)
    trava.truncate()
    trava.write(str(os.getpid()))
    trava.flush()

    def registrar_falha(tipo, valor, tb):
        try:
            with open(base / 'logs' / 'autoseg_app_erros.log', 'a', encoding='utf-8') as arquivo:
                traceback.print_exception(tipo, valor, tb, file=arquivo)
        except Exception:
            pass
        _mostrar_erro('AUTOSEG — falha', f'{tipo.__name__}: {valor}')

    sys.excepthook = registrar_falha

    try:
        import app as autoseg
        aplicativo = autoseg.App()
        aplicativo.mainloop()
    except Exception as erro:
        registrar_falha(type(erro), erro, erro.__traceback__)
        return 1
    finally:
        try:
            fcntl.flock(trava.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        trava.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
