#!/usr/bin/env python3
"""Baseline audit for code rot in production Python.

It reports, without changing code:
- broad exception handlers (``except Exception`` / bare ``except``);
- long functions and classes;
- TODO/FIXME comments without an issue reference;
- direct SQL in the known UI/HTTP entry points.

This is a triage tool, not a linter or a correctness proof. Run it before a
cleanup wave and compare the summary.
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {'.git', '.venv', '.venv-gtk', '__pycache__', 'backups', 'build',
             'dist', 'workaholic', 'scripts'}
SQL_UI_FILES = {'gtk_app.py', 'gtk_dialogos.py', 'portal_prestador.py',
                'servidor_web.py'}
SQL_RE = re.compile(r'(\.execute\s*\(|SELECT\s|INSERT\s|UPDATE\s|DELETE\s)', re.I)
ISSUE_RE = re.compile(r'(#\d+|https?://\S+|GH-\d+|KI-\d+)')


@dataclass
class FileStats:
    broad: int = 0
    silent_broad: list[int] = field(default_factory=list)
    long_functions: list[tuple[int, str, int]] = field(default_factory=list)
    long_classes: list[tuple[int, str, int]] = field(default_factory=list)
    todos: list[tuple[int, str]] = field(default_factory=list)
    sql_lines: int = 0


def _files(include_tests: bool):
    for path in ROOT.rglob('*.py'):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not include_tests and path.name.startswith('test_'):
            continue
        yield path


def _ast_stats(path: Path) -> FileStats:
    stats = FileStats()
    try:
        texto = path.read_text(encoding='utf-8')
        tree = ast.parse(texto)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return stats
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            linhas = (getattr(node, 'end_lineno', node.lineno) or node.lineno) - node.lineno + 1
            if linhas >= 60:
                stats.long_functions.append((node.lineno, node.name, linhas))
        elif isinstance(node, ast.ClassDef):
            linhas = (getattr(node, 'end_lineno', node.lineno) or node.lineno) - node.lineno + 1
            if linhas >= 400:
                stats.long_classes.append((node.lineno, node.name, linhas))
        elif isinstance(node, ast.ExceptHandler):
            tipo = node.type
            amplo = tipo is None or (isinstance(tipo, ast.Name) and tipo.id == 'Exception')
            if not amplo:
                continue
            stats.broad += 1
            corpo = node.body
            silencioso = bool(corpo) and all(
                isinstance(item, (ast.Pass, ast.Continue, ast.Break))
                or (isinstance(item, ast.Return)
                    and (item.value is None
                         or (isinstance(item.value, ast.Constant) and item.value.value is None)))
                for item in corpo)
            if silencioso:
                stats.silent_broad.append(node.lineno)
    return stats


def _comment_stats(path: Path, stats: FileStats):
    try:
        texto = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return
    try:
        for token in tokenize.generate_tokens(io.StringIO(texto).readline):
            if token.type != tokenize.COMMENT:
                continue
            linha, comment = token.start[0], token.string
            if re.search(r'\b(TODO|FIXME)\b', comment, re.I) and not ISSUE_RE.search(comment):
                stats.todos.append((linha, comment.strip()[:160]))
    except (tokenize.TokenError, IndentationError):
        pass
    if path.name in SQL_UI_FILES:
        for line in texto.splitlines():
            if line.lstrip().startswith('#'):
                continue
            if SQL_RE.search(line):
                stats.sql_lines += 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-tests', action='store_true')
    parser.add_argument('--top', type=int, default=15)
    args = parser.parse_args(argv)

    total_broad = total_silent = total_long = total_classes = total_todos = total_sql = 0
    long_funcs = []
    long_classes = []
    todos = []
    sql = []
    for path in sorted(_files(args.include_tests)):
        stats = _ast_stats(path)
        _comment_stats(path, stats)
        total_broad += stats.broad
        total_silent += len(stats.silent_broad)
        total_long += len(stats.long_functions)
        total_classes += len(stats.long_classes)
        total_todos += len(stats.todos)
        total_sql += stats.sql_lines
        rel = path.relative_to(ROOT)
        if stats.broad:
            print(f'{rel}: {stats.broad} broad exception(s)')
        if stats.silent_broad:
            print(f'  silenciosos: linhas {stats.silent_broad}')
        for linha, nome, linhas in stats.long_functions:
            long_funcs.append((linhas, rel, linha, nome))
        for linha, nome, linhas in stats.long_classes:
            long_classes.append((linhas, rel, linha, nome))
        for linha, comment in stats.todos:
            todos.append((rel, linha, comment))
        if stats.sql_lines:
            sql.append((stats.sql_lines, rel))

    print('\nFunções longas (>= 60 linhas):')
    for linhas, rel, linha, nome in sorted(long_funcs, reverse=True)[:args.top]:
        print(f'  {rel}:{linha} {nome} ({linhas} linhas)')
    print('\nClasses longas (>= 400 linhas):')
    for linhas, rel, linha, nome in sorted(long_classes, reverse=True)[:args.top]:
        print(f'  {rel}:{linha} {nome} ({linhas} linhas)')
    print('\nTODO/FIXME sem issue:')
    for rel, linha, comment in todos[:args.top]:
        print(f'  {rel}:{linha} {comment}')
    print('\nSQL direto em UI/HTTP:')
    for linhas, rel in sorted(sql, reverse=True):
        print(f'  {rel}: {linhas} linha(s) com SQL')

    print('\nResumo:')
    print(f'  broad_exceptions={total_broad}')
    print(f'  silent_broad_exceptions={total_silent}')
    print(f'  long_functions={total_long}')
    print(f'  long_classes={total_classes}')
    print(f'  todos_without_issue={total_todos}')
    print(f'  ui_sql_lines={total_sql}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
