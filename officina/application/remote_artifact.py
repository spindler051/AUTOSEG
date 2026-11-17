"""B2b: authenticated desktop artifact delivery without arbitrary path reads.

The API must validate a live bearer session and the OS/object permission
BEFORE invoking this helper. This helper binds the artifact name to that OS,
allows only known file types and refuses traversal and symlinks out of scope.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from officina.application.contracts import NaoEncontradoError, ValidacaoError
from officina.core import prestadores_ext as ext

MAX_ARTIFACT_BYTES = 24 * 1024 * 1024
_KINDS = {'email': ('eml','message/rfc822'),
          'nota': ('json','application/json'),
          'pdf': ('pdf','application/pdf')}


def resolve_draft(banco, os_id: int, kind: str, name: str):
    """Strict filename/OS binding; user-supplied filesystem paths never pass."""
    if kind not in ('email','nota'):
        raise NaoEncontradoError('Artefato indisponível.')
    if not isinstance(name, str) or not name or name != Path(name).name or len(name)>180:
        raise NaoEncontradoError('Artefato indisponível.')
    with ext.db(banco) as connection:
        os_row = connection.execute('SELECT numero_os FROM ordens_servico WHERE id=?',
                                    (int(os_id),)).fetchone()
    if os_row is None:
        raise NaoEncontradoError('Artefato indisponível.')
    number = re.sub(r'[^A-Za-z0-9_-]','_',str(os_row['numero_os'] or '')).strip('_')
    if not number:
        raise NaoEncontradoError('Artefato indisponível.')
    pattern = (rf'email_{re.escape(number)}_p[0-9]+_[0-9a-f]{{8}}\.eml'
               if kind == 'email' else rf'nota_fiscal_rascunho_{re.escape(number)}\.json')
    if not re.fullmatch(pattern, name):
        raise NaoEncontradoError('Artefato indisponível.')
    root = ext.RASCUNHOS.resolve()
    candidate = root / name
    try:
        if candidate.is_symlink() or candidate.resolve().parent != root or not candidate.is_file():
            raise NaoEncontradoError('Artefato indisponível.')
    except OSError as error:
        raise NaoEncontradoError('Artefato indisponível.') from error
    if candidate.stat().st_size > MAX_ARTIFACT_BYTES:
        raise NaoEncontradoError('Artefato indisponível.')
    if kind == 'nota':
        # Ensure the JSON draft has not been replaced with a different OS.
        try:
            payload = json.loads(candidate.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError, OSError) as error:
            raise NaoEncontradoError('Artefato indisponível.') from error
        if (not isinstance(payload, dict) or
                payload.get('ordem_servico_id') != int(os_id) or
                payload.get('status') != 'RASCUNHO_NAO_EMITIDO'):
            raise NaoEncontradoError('Artefato indisponível.')
    return candidate


def load_artifact(path: Path, kind: str):
    if kind not in _KINDS or path.suffix.lower() != '.' + _KINDS[kind][0]:
        raise NaoEncontradoError('Tipo de artefato não autorizado.')
    size = path.stat().st_size
    if size < 1 or size > MAX_ARTIFACT_BYTES:
        raise ValidacaoError('Arquivo vazio ou maior que 24 MB.')
    content = path.read_bytes()
    if len(content) != size:
        raise ValidacaoError('Arquivo alterado durante a transferência.')
    if kind == 'pdf' and not content.startswith(b'%PDF-'):
        raise ValidacaoError('PDF inválido.')
    return content, _KINDS[kind][1]
