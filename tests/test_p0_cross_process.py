"""Cross-process proof that desktop OS authorization and mutation serialize."""
from __future__ import annotations

import multiprocessing
import os
import sqlite3
import unittest
from unittest.mock import patch

from flavors.autoseg.modules import api_desktop
from officina.application.local_service import LocalService
from officina.core import prestadores_ext as ext
from tests import test_p0_desktop_auth as base_tests


def _writer(db, os_id, provider_id, session_id, pipe):
    """Preflight deliberately precedes the separately coordinated writer lock."""
    try:
        principal = api_desktop._desktop_session_context(db, {'id': provider_id})[1]
        guard = api_desktop._os_writer_authorize(
            principal, os_id, 'start', session_id=session_id)
        pipe.send('preflight')
        mode = pipe.recv()

        def in_transaction(connection):
            guard(connection)
            if mode == 'hold':
                pipe.send('writer_locked')
                if pipe.recv() != 'release':
                    raise RuntimeError('Invalid release handshake.')

        LocalService(db).iniciar_os(os_id, authorize=in_transaction)
        pipe.send(('result', 'committed'))
    except Exception as exc:
        pipe.send(('result', 'denied', type(exc).__name__, str(exc)))
    finally:
        pipe.close()


def _revoker(db, os_id, provider_id, pipe):
    """Attempt a nonblocking write first, then revoke in a real transaction."""
    try:
        pipe.send('revoker_ready')
        mode = pipe.recv()
        if mode == 'probe':
            with sqlite3.connect(db, timeout=0) as connection:
                connection.execute('PRAGMA busy_timeout=0')
                try:
                    connection.execute('BEGIN IMMEDIATE')
                except sqlite3.OperationalError as exc:
                    if 'locked' not in str(exc).lower():
                        raise
                    pipe.send('lock_busy')
                else:
                    connection.rollback()
                    raise AssertionError('Revoker acquired a lock while writer held it.')
            pipe.send('waiting_for_lock')
        elif mode != 'revoke':
            raise RuntimeError('Invalid revocation mode.')
        with ext.db(db) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('DELETE FROM os_responsaveis WHERE os_id=? AND prestador_id=?',
                               (os_id, provider_id))
            connection.execute('UPDATE os_prestadores SET ativo=0 WHERE os_id=? AND prestador_id=?',
                               (os_id, provider_id))
        pipe.send('revoked')
    except Exception as exc:
        pipe.send(('revoker_error', type(exc).__name__, str(exc)))
    finally:
        pipe.close()


class DesktopCrossProcessAuthorizationTest(unittest.TestCase):
    setUp = base_tests.DesktopObjectAuthorizationTest.setUp

    def _session_id(self):
        with ext.db(self.db) as connection:
            return connection.execute('SELECT id FROM desktop_sessoes WHERE prestador_id=? '
                                      'ORDER BY id DESC LIMIT 1',
                                      (self.users['first'],)).fetchone()[0]

    def _snapshot(self):
        with ext.db(self.db) as connection:
            record = connection.execute(
                'SELECT status,descricao,valor_total FROM ordens_servico WHERE id=?',
                (self.own,)).fetchone()
            return (tuple(record),
                    connection.execute('SELECT COUNT(*) FROM os_eventos WHERE os_id=?',
                                       (self.own,)).fetchone()[0],
                    connection.execute('SELECT COUNT(*) FROM materiais_os WHERE os_id=?',
                                       (self.own,)).fetchone()[0])

    def _launch(self, context, target):
        parent, child = context.Pipe()
        worker = context.Process(target=target,
                                 args=(self.db, self.own, self.users['first'],
                                       self._session_id(), child)
                                 if target is _writer else
                                 (self.db, self.own, self.users['first'], child))
        worker.start()
        child.close()
        self.addCleanup(self._cleanup_worker, worker, parent)
        return worker, parent

    @staticmethod
    def _cleanup_worker(worker, pipe):
        if worker.is_alive():
            worker.terminate()
        worker.join(5)
        if worker.is_alive():
            worker.kill()
            worker.join(5)
        pipe.close()

    def _expect(self, pipe, expected, *, timeout=12):
        self.assertTrue(pipe.poll(timeout), f'Timed out waiting for {expected!r}')
        message = pipe.recv()
        self.assertEqual(message, expected)

    def test_revocation_committed_before_writer_lock_denies_without_mutation(self):
        context = multiprocessing.get_context('spawn')
        for flag in ('0', '1'):
            with self.subTest(flag=flag), patch.dict(os.environ,
                    {'AUTOSEG_OBJECT_POLICY_ENFORCEMENT': flag}):
                with ext.db(self.db) as connection:
                    connection.execute("UPDATE ordens_servico SET status='Aberta' WHERE id=?", (self.own,))
                    connection.execute('INSERT OR REPLACE INTO os_responsaveis '
                                       '(os_id,prestador_id,assumido_em) VALUES (?,?,?)',
                                       (self.own, self.users['first'], ext.agora()))
                    connection.execute('UPDATE os_prestadores SET ativo=1 '
                                       'WHERE os_id=? AND prestador_id=?',
                                       (self.own, self.users['first']))
                writer, writer_pipe = self._launch(context, _writer)
                self._expect(writer_pipe, 'preflight')
                revoker, revoke_pipe = self._launch(context, _revoker)
                self._expect(revoke_pipe, 'revoker_ready')
                revoke_pipe.send('revoke')
                self._expect(revoke_pipe, 'revoked')
                revoker.join(5)
                self.assertEqual(revoker.exitcode, 0)
                before = self._snapshot()
                writer_pipe.send('write')
                self.assertTrue(writer_pipe.poll(12))
                outcome = writer_pipe.recv()
                self.assertEqual(outcome[:2], ('result', 'denied'), outcome)
                self.assertIn(outcome[2], ('PermissionError', 'PermissionDenied',
                                           'NaoEncontradoError'))
                writer.join(5)
                self.assertEqual(writer.exitcode, 0)
                self.assertEqual(self._snapshot(), before)

    def test_revocation_after_writer_lock_serializes_across_processes(self):
        context = multiprocessing.get_context('spawn')
        writer, writer_pipe = self._launch(context, _writer)
        self._expect(writer_pipe, 'preflight')
        writer_pipe.send('hold')
        self._expect(writer_pipe, 'writer_locked')
        revoker, revoke_pipe = self._launch(context, _revoker)
        self._expect(revoke_pipe, 'revoker_ready')
        revoke_pipe.send('probe')
        self._expect(revoke_pipe, 'lock_busy')
        self._expect(revoke_pipe, 'waiting_for_lock')
        self.assertEqual(self._snapshot()[0][0], 'Aberta')
        self.assertFalse(revoke_pipe.poll(.1), 'Revoker changed the OS while writer held the lock.')
        writer_pipe.send('release')
        self._expect(writer_pipe, ('result', 'committed'))
        writer.join(5)
        self.assertEqual(writer.exitcode, 0)
        self._expect(revoke_pipe, 'revoked')
        revoker.join(5)
        self.assertEqual(revoker.exitcode, 0)
        self.assertEqual(self._snapshot()[0][0], 'Iniciada')
        with ext.db(self.db) as connection:
            self.assertIsNone(ext.responsavel_atual(connection, self.own))


if __name__ == '__main__':
    unittest.main()
