"""Transactional intent and recoverable external effects for work orders.

Call ``install`` only during the authorized DEV migration, after verifying a
backup. Call ``enqueue_*`` with the caller's active BEGIN IMMEDIATE connection.
The dispatcher never executes an effect before that transaction commits.
"""
from __future__ import annotations

from contextlib import closing
from hashlib import sha256
from pathlib import Path
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from typing import Callable

from officina.core import prestadores_ext as ext

VALID_STATES = ('pending', 'processing', 'done', 'failed', 'unknown')
VALID_EFFECTS = ('pdf', 'file', 'email')
LEASE_SECONDS = 120.0


class OutboxUnavailable(RuntimeError):
    """The DEV-only migration has not been installed."""


class DispatchUncertain(RuntimeError):
    """The effect may have happened; automatic retry is forbidden."""


class PreDispatchError(RuntimeError):
    """The external effect is known not to have started."""


def backup_database(banco, destination):
    """Create and verify a consistent backup before enabling the migration."""
    source = Path(banco).resolve()
    target = Path(destination).resolve()
    if not source.is_file() or source == target or target.exists():
        raise ValueError('Backup source/destination unavailable or already present.')
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(source))) as original:
        with closing(sqlite3.connect(str(target))) as backup:
            original.backup(backup)
            if backup.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Backup integrity check failed.')
    return str(target)


def install(banco):
    """Add only os_effect_outbox and its indexes (no existing table changes)."""
    with ext.db(banco) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS os_effect_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            os_id INTEGER NOT NULL,
            operation_key TEXT NOT NULL UNIQUE,
            effect_type TEXT NOT NULL CHECK(effect_type IN ('pdf','file','email')),
            action TEXT NOT NULL,
            version_reserved INTEGER,
            payload_json TEXT NOT NULL DEFAULT '{}',
            state TEXT NOT NULL DEFAULT 'pending'
                CHECK(state IN ('pending','processing','done','failed','unknown')),
            claimed_at REAL,
            claim_token TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_os_effect_state ON os_effect_outbox(state,claimed_at)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_os_effect_os ON os_effect_outbox(os_id,effect_type)')
        c.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_os_effect_pdf_version
                     ON os_effect_outbox(os_id,version_reserved)
                     WHERE effect_type='pdf' AND version_reserved IS NOT NULL''')


def installed(c):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='os_effect_outbox'").fetchone() is not None


def require_installed(c):
    if not installed(c):
        raise OutboxUnavailable('Run the DEV-only outbox installation after a verified backup.')


def operation_key(os_id, revision, action, effect):
    if effect not in VALID_EFFECTS:
        raise ValueError('Unsupported external effect.')
    if not str(revision).strip() or not str(action).strip():
        raise ValueError('Revision and action must be explicit.')
    raw = json.dumps([int(os_id), str(revision), str(action), effect],
                     separators=(',', ':'), ensure_ascii=True)
    return sha256(raw.encode('utf-8')).hexdigest()


def _queue(c, os_id, revision, action, effect_type, *, payload=None, version=None):
    if not c.in_transaction:
        raise RuntimeError('Outbox intent requires an active OS transaction.')
    require_installed(c)
    payload = payload or {}
    if set(payload) - {'source_id', 'source_sha256', 'document_id', 'reason_code'}:
        raise ValueError('Outbox payload contains unsupported fields.')
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    key = operation_key(os_id, revision, action, effect_type)
    old = c.execute('SELECT * FROM os_effect_outbox WHERE operation_key=?', (key,)).fetchone()
    if old:
        if (old['os_id'] != int(os_id) or old['effect_type'] != effect_type
                or old['action'] != action or old['payload_json'] != encoded):
            raise ValueError('Conflicting outbox operation key.')
        return dict(old)
    if effect_type == 'pdf' and version is None:
        published = c.execute('''SELECT COALESCE(MAX(versao),0) FROM os_documentos
                                  WHERE os_id=? AND tipo='relatorio_pdf' ''', (os_id,)).fetchone()[0]
        pending = c.execute("""SELECT COALESCE(MAX(version_reserved),0)
                               FROM os_effect_outbox WHERE os_id=? AND effect_type='pdf'""",
                            (os_id,)).fetchone()[0]
        version = max(int(published), int(pending)) + 1
    if effect_type != 'pdf' and version is not None:
        raise ValueError('Only PDF effects reserve a version.')
    now = time.time()
    c.execute('''INSERT INTO os_effect_outbox
                 (os_id,operation_key,effect_type,action,version_reserved,
                  payload_json,state,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,'pending',?,?)''',
              (int(os_id), key, effect_type, action, version, encoded, now, now))
    return dict(c.execute('SELECT * FROM os_effect_outbox WHERE operation_key=?', (key,)).fetchone())


def enqueue_pdf(c, os_id, revision, action='publish'):
    return _queue(c, os_id, revision, action, 'pdf')


def enqueue_email(c, os_id, revision, action='send'):
    return _queue(c, os_id, revision, action, 'email')


def enqueue_file(c, os_id, revision, action, source_id, source_sha256):
    if not re.fullmatch(r'[0-9a-f]{64}', str(source_sha256)):
        raise ValueError('Invalid source digest.')
    return _queue(c, os_id, revision, action, 'file',
                  payload={'source_id': int(source_id), 'source_sha256': source_sha256})


def get(banco, operation):
    with ext.db(banco) as c:
        require_installed(c)
        row = c.execute('SELECT * FROM os_effect_outbox WHERE operation_key=?',
                        (operation,)).fetchone()
        return dict(row) if row else None


def claim(banco, operation, *, now=None, lease_seconds=LEASE_SECONDS):
    """Atomically claim exactly one effect; never auto-retry uncertain email."""
    now = time.time() if now is None else float(now)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        require_installed(c)
        row = c.execute('SELECT * FROM os_effect_outbox WHERE operation_key=?',
                        (operation,)).fetchone()
        if not row or row['state'] in ('done', 'unknown'):
            return None
        expired = (row['state'] == 'processing' and row['claimed_at'] is not None
                   and row['claimed_at'] + lease_seconds <= now)
        if row['state'] == 'processing' and not expired:
            return None
        if expired and row['effect_type'] == 'email':
            c.execute("""UPDATE os_effect_outbox SET state='unknown',
                        claim_token=NULL,last_error=?,updated_at=? WHERE id=?""",
                      ('Provider outcome not known after lease expiration.', now, row['id']))
            return None
        if row['state'] not in ('pending', 'failed') and not expired:
            return None
        token = secrets.token_hex(16)
        c.execute('''UPDATE os_effect_outbox SET state='processing',claimed_at=?,
                     claim_token=?,attempts=attempts+1,last_error='',updated_at=? WHERE id=?''',
                  (now, token, now, row['id']))
        claimed = dict(c.execute('SELECT * FROM os_effect_outbox WHERE id=?', (row['id'],)).fetchone())
        return claimed


def finish(banco, operation, claim_token, *, state, result=None, error=''):
    if state not in ('done', 'failed', 'unknown'):
        raise ValueError('Invalid terminal effect state.')
    if result is None:
        result = {}
    if set(result) - {'sha256', 'document_id', 'provider_message_id'}:
        raise ValueError('Unexpected outbox result metadata.')
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        updated = c.execute('''UPDATE os_effect_outbox SET state=?,result_json=?,
             last_error=?,claim_token=NULL,claimed_at=NULL,updated_at=?
             WHERE operation_key=? AND claim_token=? AND state='processing' ''',
            (state, json.dumps(result, sort_keys=True), str(error)[:350],
             time.time(), operation, claim_token))
        if updated.rowcount != 1:
            raise RuntimeError('Outbox lease was superseded.')


def reconcile(banco, *, now=None, lease_seconds=LEASE_SECONDS):
    """Make expired email attempts unknown; return retryable PDF/file keys."""
    now = time.time() if now is None else float(now)
    with ext.db(banco) as c:
        c.execute('BEGIN IMMEDIATE')
        require_installed(c)
        c.execute('''UPDATE os_effect_outbox SET state='unknown', claim_token=NULL,
            claimed_at=NULL,updated_at=?,last_error=?
            WHERE effect_type='email' AND state='processing'
              AND claimed_at<=?''',
            (now, 'Uncertain provider outcome after worker restart.', now - lease_seconds))
        keys = c.execute('''SELECT operation_key FROM os_effect_outbox
            WHERE state IN ('pending','failed') OR
            (effect_type!='email' AND state='processing' AND claimed_at<=?)
            ORDER BY id''', (now - lease_seconds,)).fetchall()
        return [row['operation_key'] for row in keys]


def _safe_pdf_name(number, version):
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', str(number or '')).strip('_')
    if not safe:
        raise ValueError('OS without public number.')
    return f'{safe}_relatorio_v{int(version)}.pdf'


def _validate_pdf(path):
    path = Path(path)
    with path.open('rb') as doc:
        head = doc.read(5)
    if head != b'%PDF-' or path.stat().st_size < 100:
        raise ValueError('Generated document is not a valid PDF.')
    digest = sha256()
    with path.open('rb') as doc:
        for chunk in iter(lambda: doc.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def publish_pdf(banco, operation, *, generate=None, after_publish=None,
                now=None, lease_seconds=LEASE_SECONDS):
    """Publish one reserved PDF version; never overwrite a published file.

    A crash after atomic file publication but before DB confirmation is
    recovered from the deterministic filename and verified content hash.
    """
    claimed = claim(banco, operation, now=now, lease_seconds=lease_seconds)
    if not claimed:
        return get(banco, operation)
    if claimed['effect_type'] != 'pdf':
        finish(banco, operation, claimed['claim_token'], state='failed', error='Wrong effect type.')
        raise ValueError('Not a PDF operation.')
    from officina.core import fluxo_os
    with ext.db(banco) as c:
        order = c.execute('SELECT numero_os,status FROM ordens_servico WHERE id=?',
                          (claimed['os_id'],)).fetchone()
    if not order or order['status'] not in fluxo_os.PUBLICAVEIS:
        finish(banco, operation, claimed['claim_token'], state='failed',
               error='OS status does not allow publication.')
        raise ValueError('OS status does not allow publication.')
    directory = Path(ext.RELATORIOS) / 'publicados'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / _safe_pdf_name(order['numero_os'], claimed['version_reserved'])
    stage = directory / ('.stage-' + claimed['operation_key'] + '.pdf')
    try:
        if not target.exists():
            generator = generate or ext.gerar_pdf
            source = Path(generator(banco, claimed['os_id']))
            _validate_pdf(source)
            try:
                with source.open('rb') as incoming, stage.open('xb') as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
            except FileExistsError:
                # An interrupted attempt can have left a stage file.
                if not stage.is_file() or _validate_pdf(stage) != _validate_pdf(source):
                    stage.unlink(missing_ok=True)
                    with source.open('rb') as incoming, stage.open('xb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
                        outgoing.flush()
                        os.fsync(outgoing.fileno())
            _validate_pdf(stage)
            try:
                os.link(stage, target)
            except FileExistsError:
                pass
        digest = _validate_pdf(target)
        with ext.db(banco) as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT state,claim_token FROM os_effect_outbox WHERE operation_key=?',
                            (operation,)).fetchone()
            if not row or row['state'] != 'processing' or row['claim_token'] != claimed['claim_token']:
                raise RuntimeError('Outbox lease changed during PDF publication.')
            existing = c.execute('''SELECT id,sha256,caminho FROM os_documentos
                 WHERE os_id=? AND tipo='relatorio_pdf' AND versao=?''',
                (claimed['os_id'], claimed['version_reserved'])).fetchone()
            if existing:
                if existing['sha256'] != digest or Path(existing['caminho']) != target:
                    raise RuntimeError('Reserved PDF version conflicts with another document.')
                document_id = existing['id']
            else:
                document_id = c.execute('''INSERT INTO os_documentos
                    (os_id,tipo,versao,caminho,sha256,publicado_em)
                    VALUES(?,'relatorio_pdf',?,?,?,?)''',
                    (claimed['os_id'], claimed['version_reserved'], str(target),
                     digest, ext.agora())).lastrowid
            # Existing delivery relation is reused, not a second delivery table.
            customer = c.execute('''SELECT cl.email,o.status FROM clientes cl
                JOIN ordens_servico o ON o.cliente_id=cl.id WHERE o.id=?''',
                (claimed['os_id'],)).fetchone()
            email = (customer['email'] or '').strip() if customer else ''
            c.execute('''INSERT INTO os_entregas
                (os_id,documento_id,destinatario,email_status,nf_status,atualizado_em)
                VALUES(?,?,?,?,?,?) ON CONFLICT(os_id) DO UPDATE SET
                documento_id=excluded.documento_id,destinatario=excluded.destinatario,
                email_status=excluded.email_status,nf_status=excluded.nf_status,
                atualizado_em=excluded.atualizado_em''',
                (claimed['os_id'], document_id, email,
                 'aguardando_api' if email else 'email_nao_cadastrado',
                 'aguardando_api' if customer and customer['status'] == 'Concluída'
                 else 'nao_aplicavel', ext.agora()))
            c.execute('''UPDATE os_effect_outbox SET state='done',claimed_at=NULL,
                claim_token=NULL,last_error='',result_json=?,updated_at=?
                WHERE operation_key=? AND claim_token=?''',
                (json.dumps({'document_id': document_id, 'sha256': digest}),
                 time.time(), operation, claimed['claim_token']))
        if after_publish:
            after_publish(str(target))
        return get(banco, operation)
    except Exception as exc:
        try:
            finish(banco, operation, claimed['claim_token'], state='failed', error=type(exc).__name__)
        except RuntimeError:
            pass
        raise
    finally:
        stage.unlink(missing_ok=True)


def deliver_email(banco, operation, sender: Callable, *, now=None,
                  lease_seconds=LEASE_SECONDS):
    """Call sender(os_id, operation_key) once; result uncertainty stays unknown.

    ``sender`` resolves recipients at dispatch time. It must provide its own
    provider idempotency key support when available. If it raises after entry,
    the outcome is unknown, never an automatic retry.
    """
    claimed = claim(banco, operation, now=now, lease_seconds=lease_seconds)
    if not claimed:
        return get(banco, operation)
    if claimed['effect_type'] != 'email':
        finish(banco, operation, claimed['claim_token'], state='failed', error='Wrong effect type.')
        raise ValueError('Not an email operation.')
    try:
        message_id = sender(claimed['os_id'], claimed['operation_key'])
    except PreDispatchError as exc:
        finish(banco, operation, claimed['claim_token'], state='failed', error=type(exc).__name__)
        raise
    except Exception as exc:
        finish(banco, operation, claimed['claim_token'], state='unknown', error=type(exc).__name__)
        raise DispatchUncertain('Email outcome unknown; reconciliation required.') from exc
    finish(banco, operation, claimed['claim_token'], state='done',
           result={'provider_message_id': str(message_id or '')[:150]})
    return get(banco, operation)


def manual_email_retry(c, os_id, revision, action, *, duplicate_acknowledged):
    if not duplicate_acknowledged:
        raise PermissionError('Explicit duplicate-delivery warning must be acknowledged.')
    return enqueue_email(c, os_id, revision, action)


def stage_bytes(directory, operation, data):
    """Write private upload staging bytes; final attachment is not yet visible.

    The caller removes uncommitted stages via ``cleanup_orphan_stages``.
    Bytes never enter the outbox SQLite payload.
    """
    if not re.fullmatch(r'[0-9a-f]{64}', operation):
        raise ValueError('Invalid operation key.')
    if not isinstance(data, bytes) or not data:
        raise ValueError('Cannot stage an empty attachment.')
    directory = Path(directory)
    stage_dir = directory / '.outbox-staging'
    stage_dir.mkdir(parents=True, exist_ok=True)
    stage = stage_dir / operation
    digest = sha256(data).hexdigest()
    try:
        with stage.open('xb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError:
        current = sha256(stage.read_bytes()).hexdigest()
        if current != digest:
            raise ValueError('Conflicting staged attachment content.')
    return str(stage), digest


def publish_file(banco, operation, *, now=None, lease_seconds=LEASE_SECONDS):
    """Promote staged attachment once and confirm its content hash.

    The committed source row supplies the destination; no user-controlled path
    is loaded from the outbox payload.
    """
    claimed = claim(banco, operation, now=now, lease_seconds=lease_seconds)
    if not claimed:
        return get(banco, operation)
    if claimed['effect_type'] != 'file':
        finish(banco, operation, claimed['claim_token'], state='failed', error='Wrong type.')
        raise ValueError('Not an attachment operation.')
    payload = json.loads(claimed['payload_json'])
    is_invoice = claimed['action'].startswith('invoice-')
    table = 'os_notas_fiscais' if is_invoice else 'os_anexos'
    root = Path(ext.NOTAS if is_invoice else ext.ANEXOS).resolve()
    try:
        with ext.db(banco) as c:
            row = c.execute(f'SELECT caminho,sha256 FROM {table} WHERE id=? AND os_id=?',
                            (payload['source_id'], claimed['os_id'])).fetchone()
        if not row or row['sha256'] != payload['source_sha256']:
            raise RuntimeError('Staged attachment source no longer matches.')
        target = Path(row['caminho']).resolve()
        if not target.is_relative_to(root) or target.parent != root:
            raise ValueError('Attachment destination leaves its managed root.')
        staged = root / '.outbox-staging' / operation
        if not target.exists():
            if not staged.is_file():
                raise FileNotFoundError('Attachment stage missing; manual recovery required.')
            if sha256(staged.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('Staged attachment digest mismatch.')
            try:
                os.link(staged, target)
            except FileExistsError:
                pass
        if sha256(target.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Published attachment digest mismatch.')
        finish(banco, operation, claimed['claim_token'], state='done',
               result={'sha256': row['sha256']})
        staged.unlink(missing_ok=True)
        return get(banco, operation)
    except Exception as exc:
        try:
            finish(banco, operation, claimed['claim_token'], state='failed', error=type(exc).__name__)
        except RuntimeError:
            pass
        raise


def cleanup_orphan_stages(banco, root, *, minimum_age=3600, now=None):
    """Remove only old private stages whose key has no committed intent."""
    now = time.time() if now is None else float(now)
    stage_dir = Path(root) / '.outbox-staging'
    if not stage_dir.is_dir():
        return 0
    with ext.db(banco) as c:
        require_installed(c)
        count = 0
        for stage in stage_dir.iterdir():
            if (not stage.is_file() or stage.is_symlink()
                    or not re.fullmatch('[0-9a-f]{64}', stage.name)
                    or stage.stat().st_mtime > now - minimum_age):
                continue
            if c.execute('SELECT 1 FROM os_effect_outbox WHERE operation_key=?',
                         (stage.name,)).fetchone():
                continue
            stage.unlink(missing_ok=True)
            count += 1
        return count


def dispatch_retryable(banco, *, generate_pdf=None):
    """Recover PDF/file effects after restart; never dispatch uncertain email."""
    results = []
    for operation in reconcile(banco):
        row = get(banco, operation)
        if row['effect_type'] == 'pdf':
            results.append(publish_pdf(banco, operation, generate=generate_pdf))
        elif row['effect_type'] == 'file':
            results.append(publish_file(banco, operation))
        # Email delivery is opt-in via an authenticated operator/worker; a
        # claimed/uncertain email is never automatically replayed.
    return results
