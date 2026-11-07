#!/usr/bin/env python3
"""Audit Python comments for prompt leakage and generated-code smells.

This is a reporting tool, not a behaviour test. It looks for comments that
repeat a user request/spec, mention AI tools in product code, carry revision
history that belongs in Git, or hide shortcuts behind vague notes.

Usage:
    python3 scripts/audit_comments.py
    python3 scripts/audit_comments.py --include-tests
    python3 scripts/audit_comments.py --strict
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {'.git', '.venv', '.venv-gtk', '__pycache__', 'backups', 'build',
             'dist', 'workaholic', 'scripts'}
# The feedback feature legitimately discusses prompts, AI providers and
# provider names. Its comments are not prompt leakage.
SKIP_FILES = {'feedback_ai.py', 'feedback_portal.py'}

HIGH_PATTERNS = (
    (re.compile(r'\b(prompt|opencode|chatgpt|claude|deepseek)\b', re.I),
     'ferramenta/prompt de IA citado no comentário'),
    (re.compile(r'\b(IA|AI)\b'),
     'IA citada no comentário de produto'),
    (re.compile(r'\b(conforme solicitado|como solicitado|implemente|'
                r'não se esqueça|nao se esqueca|lembre-se|lembre se)\b', re.I),
     'texto de solicitação/instrução no comentário'),
    (re.compile(r'\bREV\d+\b', re.I),
     'histórico de revisão no código; use Git/CHANGELOG'),
    (re.compile(r'\b(shortcut|workaround|gambiarra|hack)\b', re.I),
     'atalho/gambiarra sem issue ou condição de remoção'),
    (re.compile(r'\b(importante|atenção|atencao|regra|requisito)\s*:', re.I),
     'linguagem de especificação/prompt no comentário'),
)

LOW_PATTERNS = (
    (re.compile(r'\b(deve|devem|nunca|sempre|obrigatório|obrigatorio)\b', re.I),
     'linguagem imperativa; confirme se é invariante ou apenas especificação'),
)


def _iter_python_files(include_tests: bool):
    for path in ROOT.rglob('*.py'):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not include_tests and path.name.startswith('test_'):
            continue
        if path.name in SKIP_FILES:
            continue
        yield path


def _comments(path: Path):
    try:
        texto = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return
    try:
        for token in tokenize.generate_tokens(io.StringIO(texto).readline):
            if token.type == tokenize.COMMENT:
                yield token.start[0], token.string
    except (tokenize.TokenError, IndentationError):
        return


def _find(comment: str, patterns):
    for pattern, reason in patterns:
        if pattern.search(comment):
            yield reason


def _docstrings(path: Path):
    try:
        texto = path.read_text(encoding='utf-8')
        tree = ast.parse(texto)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node, clean=False)
        if not doc:
            continue
        fallback = getattr(node, 'lineno', 1)
        linha = getattr(node.body[0], 'lineno', fallback) if node.body else fallback
        yield linha, doc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-tests', action='store_true',
                        help='também auditar arquivos test_*.py')
    parser.add_argument('--strict', action='store_true',
                        help='sair com código 1 se houver achados altos')
    args = parser.parse_args(argv)

    altos = baixos = 0
    for path in sorted(_iter_python_files(args.include_tests)):
        for linha, comment in _comments(path):
            for motivo in _find(comment, HIGH_PATTERNS):
                altos += 1
                print(f'{path.relative_to(ROOT)}:{linha}: [ALTO] {motivo}: {comment.strip()[:180]}')
            for motivo in _find(comment, LOW_PATTERNS):
                baixos += 1
                print(f'{path.relative_to(ROOT)}:{linha}: [BAIXO] {motivo}: {comment.strip()[:180]}')
        for linha, doc in _docstrings(path):
            for motivo in _find(doc, HIGH_PATTERNS):
                altos += 1
                print(f'{path.relative_to(ROOT)}:{linha}: [ALTO][DOC] {motivo}: {doc.strip().splitlines()[0][:180]}')

    print(f'\nResumo: {altos} achado(s) alto(s), {baixos} achado(s) baixo(s).')
    if args.strict and altos:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
