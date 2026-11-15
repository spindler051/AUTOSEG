"""Read-only source divergence analysis for the static customer surface registry.

This is an offline, conservative source-marker analyzer, NOT an authorization
engine, route detector, or behavioral security proof. Nothing imports it at
runtime. It never writes files and never imports application service modules.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = 'flavors/autoseg/config/surface_registry.yaml'
POLICY = 'flavors/autoseg/config/policy.yaml'
WEB = 'flavors/autoseg/modules/portal_prestador.py'
API = 'flavors/autoseg/modules/api_desktop.py'
GTK = ('flavors/autoseg/modules/gtk_app.py',
       'flavors/autoseg/modules/gtk_dialogos.py')
LOCAL = 'officina/application/local_service.py'
SEVERITIES = ('high', 'medium', 'low')
EXPECTED = frozenset({
    'customer.create', 'customer.edit', 'customer.deactivate',
    'customer.delete', 'customer.merge', 'customer.password',
    'customer.list', 'customer.detail',
})


@dataclass(frozen=True)
class Finding:
    id: str
    severity: str
    action: str
    surface: str
    kind: str
    evidence: str
    test_reference: str


def _function_source(content: str, name: str) -> tuple[str, frozenset[str]]:
    """Return the actual module-level function body and AST argument names."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return '', frozenset()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            args = node.args
            names = [part.arg for part in (args.posonlyargs + args.args + args.kwonlyargs)]
            if args.vararg is not None:
                names.append(args.vararg.arg)
            if args.kwarg is not None:
                names.append(args.kwarg.arg)
            return ast.get_source_segment(content, node) or '', frozenset(names)
    return '', frozenset()


def _gtk_admin_condition(source: str, marker: str) -> bool:
    """Check the AST ancestors of the registered button, not a nearby comment.

    This only reasons about an explicit conditional around a ui.botao call;
    it cannot establish runtime GTK permissions.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    parents = {child: parent for parent in ast.walk(tree)
               for child in ast.iter_child_nodes(parent)}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        segment = ast.get_source_segment(source, node) or ''
        if marker not in segment:
            continue
        parent = parents.get(node)
        while parent is not None:
            if isinstance(parent, ast.If):
                condition = ast.unparse(parent.test)
                if 'admin' in condition and 'sessao' in condition:
                    return True
            parent = parents.get(parent)
    return False


def _api_password_edge(source: str) -> bool:
    marker = "if resto == ['senha'] and metodo == 'POST':"
    if marker not in source:
        return False
    # Explicitly bound to the matching route branch, not an arbitrary admin
    # check elsewhere in the large API module.
    block = source.split(marker, 1)[1].split("    raise NaoEncontradoError", 1)[0]
    return '_exigir_admin(info)' in block[:250]


def analyze(root: Path = ROOT, *,
            registry_data: Mapping | None = None,
            read_source: Callable[[str], str] | None = None) -> tuple[Finding, ...]:
    """Re-derive signatures, source guards and surface evidence from code.

    read_source and registry_data allow hermetic synthetic tests. The analyzer
    treats missing source files as absent evidence, never as successful checks.
    """
    root = Path(root)
    if read_source is None:
        def read_source(relative: str) -> str:
            try:
                return (root / relative).read_text(encoding='utf-8')
            except (FileNotFoundError, UnicodeError):
                return ''
    cache: dict[str, str] = {}

    def src(relative: str) -> str:
        if relative not in cache:
            cache[relative] = read_source(relative)
        return cache[relative]

    if registry_data is None:
        registry_data = yaml.safe_load(src(REGISTRY))
    if not isinstance(registry_data, dict) or registry_data.get('version') != 1:
        raise ValueError('Unsupported or missing surface registry')
    rows = registry_data.get('actions')
    if not isinstance(rows, list):
        raise ValueError('Registry actions must be a list')
    policy = yaml.safe_load(src(POLICY)) or {}
    roles = policy.get('roles', {})
    permissions = {permission for name, entry in roles.items() if name != 'admin'
                   for permission in entry.get('permissions', ()) if permission != '*'}
    web, api = src(WEB), src(API)
    gtk_app, gtk_dialogos = (src(item) for item in GTK)
    local = src(LOCAL)
    findings: list[Finding] = []

    def record(action: dict, surface: str, kind: str, severity: str,
               evidence: str) -> None:
        identifier = f"{action['id']}:{surface}:{kind}"
        tests = ', '.join(action.get('negative_tests') or ()) or 'none (gap)'
        findings.append(Finding(identifier, severity, action['id'],
                                surface, kind, evidence, tests))

    for action in rows:
        ident = action['id']
        before = len(findings)
        module, function = action['service'].rsplit('.', 1)
        service_file = module.replace('.', '/') + '.py'
        func_body, params = _function_source(src(service_file), function)
        needed = set(action.get('required_params') or ())
        if not func_body or not needed.issubset(params):
            record(action, 'service', 'service_signature', 'high',
                   f'{service_file}:def {function}(...); missing {sorted(needed - params)}')
        capability = action.get('capability')
        if capability is not None and capability not in permissions:
            record(action, 'policy', 'capability_undefined', 'high',
                   f'{POLICY}:{capability}')

        if action.get('admin_only'):
            # AST calls and string literals cannot be satisfied by a comment
            # containing `require_admin_locked(...)` or `BEGIN IMMEDIATE`.
            try:
                writer_tree = ast.parse(func_body) if func_body else ast.parse('pass')
            except SyntaxError:
                writer_tree = ast.parse('pass')
            has_guard = any(isinstance(node, ast.Call) and
                            isinstance(node.func, ast.Name) and
                            node.func.id == 'require_admin_locked'
                            for node in ast.walk(writer_tree))
            has_txn = any(isinstance(node, ast.Constant) and
                          isinstance(node.value, str) and
                          'BEGIN IMMEDIATE' in node.value
                          for node in ast.walk(writer_tree))
            locked = has_guard and has_txn
            state = action.get('writer_guard')
            if state == 'locked' and not locked:
                record(action, 'service', 'missing_writer_guard', 'high',
                       f'{service_file}:def {function}(...) / require_admin_locked + BEGIN IMMEDIATE')
            elif state == 'edge_only_gap':
                web_edge = "if (senha_nova or confirmar) and not s.get('admin'):" in web
                api_edge = _api_password_edge(api)
                if not has_guard and web_edge and api_edge:
                    record(action, 'service', 'edge_only_authorization', 'high',
                           f'{service_file}:def {function}(...) without require_admin_locked; '
                           f'{WEB}:if (senha_nova or confirmar) and not s.get(\'admin\'); '
                           f'{API}:_exigir_admin(info)')
                elif not locked:
                    record(action, 'service', 'missing_writer_guard', 'high',
                           f'{service_file}:def {function}(...) / no verified locked or edge guard')

        for surface, markers, sources in (
            ('web', action.get('web_markers') or [], ((WEB, web),)),
            ('api', action.get('api_markers') or [], ((API, api),)),
            ('gtk', action.get('gtk_markers') or [], tuple(zip(GTK, (gtk_app, gtk_dialogos)))),
        ):
            if not markers:
                record(action, surface, 'missing_surface', 'medium',
                       f'{sources[0][0]}:[] (no registered {surface} marker)')
            else:
                missing = [marker for marker in markers
                           if not any(marker in content for _, content in sources)]
                if missing:
                    record(action, surface, 'missing_surface', 'medium',
                           f'{sources[0][0]}:{missing[0]} (marker missing)')

        tests = action.get('negative_tests') or []
        markers = action.get('negative_markers') or []
        valid = bool(tests) and bool(markers)
        for marker in markers:
            path, needle = marker['file'], marker['contains']
            if path not in tests or needle not in src(path):
                valid = False
        if not valid:
            record(action, 'tests', 'missing_negative_test', 'high',
                   f"{tests[0] if tests else REGISTRY}:negative_markers absent or mismatch")

        if action.get('risk') == 'destructive' and action.get('admin_only'):
            ui_markers = action.get('gtk_markers') or []
            button_markers = [m for m in ui_markers if 'ui.botao(' in m]
            if button_markers and all(m in gtk_app for m in button_markers):
                if not all(_gtk_admin_condition(gtk_app, m) for m in button_markers):
                    record(action, 'gtk', 'affordance_mismatch', 'medium',
                           f'{GTK[0]}:{button_markers[0]} / no enclosing admin condition')

        # Specific source-derived parity rules. Each condition checks both
        # the local path and a *real* scoped web/API path, not just a YAML tag.
        if ident == 'customer.create':
            if ('read_access.require_customer_create(actor)' in web
                    and 'neg.cliente_salvar(banco,d,pid,editar,principal=actor)' in web
                    and 'BEGIN IMMEDIATE' in func_body
                    and 'require_customer_create(' not in func_body):
                record(action, 'web', 'create_preflight_outside_writer', 'medium',
                       f'{WEB}:read_access.require_customer_create(actor); '
                       f'{service_file}:BEGIN IMMEDIATE without require_customer_create')
        if ident == 'customer.list':
            if ('self.service.listar_clientes(termo)' in gtk_app
                    and 'clientes_core.listar(' in local
                    and 'read_access.involved_customer_field_scopes(principal)' in web
                    and '_scoped_customer_list(' in api):
                record(action, 'gtk_local', 'read_scope_divergence', 'medium',
                       f'{LOCAL}:clientes_core.listar( versus '
                       f'{WEB}:involved_customer_field_scopes')
        if ident == 'customer.detail':
            if ('self.servico.obter_cliente(cliente_id)' in gtk_dialogos
                    and 'clientes_core.obter(' in local
                    and 'read_access.require_customer_read(' in web
                    and '_scoped_customer_detail(' in api):
                record(action, 'gtk_local', 'read_scope_divergence', 'medium',
                       f'{LOCAL}:clientes_core.obter( versus '
                       f'{WEB}:require_customer_read')
        if (action.get('state') == 'active'
                and any(item.severity == 'high' for item in findings[before:])):
            # Medium cross-surface UX gaps do not invalidate a verified writer.
            record(action, 'registry', 'state_inconsistent', 'high',
                   f'{REGISTRY}:state: active (high-severity source findings detected)')

    rank = {label: i for i, label in enumerate(SEVERITIES)}
    findings.sort(key=lambda item: (rank[item.severity], item.action,
                                    item.surface, item.kind, item.id))
    ids = [item.id for item in findings]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate stable finding IDs')
    return tuple(findings)


def baseline_ids(baseline: Mapping) -> frozenset[str]:
    return frozenset(entry['id'] for entry in baseline.get('accepted', ()))


def compare_baseline(findings: tuple[Finding, ...], baseline: Mapping) -> tuple[tuple[str, ...], tuple[str, ...]]:
    actual = {entry.id for entry in findings}
    expected = baseline_ids(baseline)
    return tuple(sorted(actual - expected)), tuple(sorted(expected - actual))


def render_report(findings: tuple[Finding, ...], baseline: Mapping) -> str:
    """Deterministic Markdown; no timestamps or line-dependent finding IDs."""
    accepted = {entry['id']: entry['justification'] for entry in baseline.get('accepted', ())}
    lines = ['# Surface divergence report', '', '## Summary', '',
             f'- High: {sum(f.severity == "high" for f in findings)}',
             f'- Medium: {sum(f.severity == "medium" for f in findings)}',
             f'- Low: {sum(f.severity == "low" for f in findings)}',
             f'- Total: {len(findings)}', '',
             'Static source evidence only; not a behavioral penetration test.', '']
    def esc(value: str) -> str:
        return value.replace('|', '\\|').replace('\n', ' ')
    header = '| Finding ID | Action | Surface | Kind | Evidence (`file:marker`) | Negative test |'
    divider = '|---|---|---|---|---|---|'
    for severity in SEVERITIES:
        lines.extend((f'## {severity.title()}', '', header, divider))
        lines.extend(f'| `{f.id}` | `{f.action}` | `{f.surface}` | `{f.kind}` | '
                     f'{esc(f.evidence)} | {esc(f.test_reference)} |'
                     for f in findings if f.severity == severity)
        lines.append('')
    lines.extend(('## Accepted gaps', '', '| Finding ID | Justification |', '|---|---|'))
    for ident in sorted(accepted):
        lines.append(f'| `{ident}` | {esc(accepted[ident])} |')
    lines.append('')
    new, resolved = compare_baseline(findings, baseline)
    if new or resolved:
        lines.extend(('## Baseline drift (requires review)', '',
                      f'New: {", ".join(new) or "none"}',
                      f'Resolved: {", ".join(resolved) or "none"}', ''))
    return '\n'.join(lines)
