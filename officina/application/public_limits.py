"""Bound public HTTP work with independent per-IP budgets and active slots.

Budgets use a monotonic clock to avoid bypass when wall-clock time changes.
These defenses supplement (not replace) the authentication-specific limiter.
Only the peer socket address is used; untrusted forwarding headers cannot
manufacture independent IP budgets.
"""
from __future__ import annotations

from collections import deque
from math import ceil
from threading import BoundedSemaphore, Lock
import time


class PublicBudget:
    def __init__(self, *, clock=time.monotonic, period=60,
                 limits=None, max_concurrent=32):
        self.clock = clock
        self.period = float(period)
        self.limits = dict(limits or {'login': 40, 'public': 180, 'read': 480})
        self._requests = {}
        self._lock = Lock()
        self._slots = BoundedSemaphore(int(max_concurrent))

    def reserve(self, peer_ip: str, category: str) -> int:
        """Return zero when allowed, or integral seconds for Retry-After."""
        key = (str(peer_ip or 'unknown')[:128], str(category or 'public'))
        limit = max(1, int(self.limits.get(category, self.limits.get('public', 180))))
        now = self.clock()
        with self._lock:
            if len(self._requests) > 2048:
                self._requests = {k:v for k,v in self._requests.items()
                                  if v and now-v[-1] < self.period}
            history = self._requests.setdefault(key, deque())
            while history and now - history[0] >= self.period:
                history.popleft()
            if len(history) >= limit:
                return max(1, ceil(self.period-(now-history[0])))
            history.append(now)
            return 0

    def enter(self) -> bool:
        return self._slots.acquire(blocking=False)

    def leave(self) -> None:
        self._slots.release()


def category(method: str, path: str) -> str | None:
    """Treat only unauthenticated entry points and APIs as public work."""
    from urllib.parse import urlsplit
    clean = urlsplit(str(path or '')).path.rstrip('/') or '/'
    if (clean in ('/login', '/entrar', '/solicitar')
            or clean.endswith('/desktop/login')) and method == 'POST':
        return 'login' if clean != '/solicitar' else 'public'
    if (clean.startswith('/api/v1/') or clean == '/api/v1'
            or clean in ('/pj-publicas', '/solicitar', '/login', '/')):
        return 'read' if method in ('GET', 'HEAD', 'OPTIONS') else 'public'
    return None


def reject_overload(handler, retry: int) -> None:
    """Return a complete 429 with retry advice without reading the request."""
    import json
    content = json.dumps({'error': {'code': 'rate_limited',
        'message': 'Limite temporário de solicitações. Tente novamente.'}}
    ).encode('utf-8')
    handler.send_response(429)
    handler.send_header('Retry-After', str(max(1, int(retry))))
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def guarded(method, budget: PublicBudget):
    """Wrap an HTTP handler without changing its routing or body-limit rules."""
    from functools import wraps
    @wraps(method)
    def wrapper(handler, *args, **kwargs):
        kind = category(str(handler.command), str(handler.path))
        if kind is None:
            return method(handler, *args, **kwargs)
        if not budget.enter():
            return reject_overload(handler, 2)
        try:
            peer = handler.client_address[0] if handler.client_address else ''
            retry = budget.reserve(peer, kind)
            if retry:
                return reject_overload(handler, retry)
            return method(handler, *args, **kwargs)
        finally:
            budget.leave()
    return wrapper
