"""Reject definite relative-import failures in the exact plugin build input."""
import ast
from collections import Counter
from pathlib import PurePosixPath

# Exact retired import sites from the public 0.6.91 tree. A new site, target,
# or name is always checked. Remove a row when its retired import disappears.
LEGACY_IMPORTS = frozenset({
    ('wce/current_publication_continuation.py', 570, 'wce.current_publication_service', 'content_claims', 'export'),
    ('wce/current_publication_slot_execution.py', 14, 'wce.current_publication_service', 'content_claims', 'export'),
    ('wce/current_publication_slot_stage.py', 8, 'wce.current_publication_service', 'content_claims', 'export'),
    ('wce/current_publication_store.py', 635, 'wce.current_publication_service', 'content_claims', 'export'),
    ('wce/current_publication_store.py', 782, 'wce.current_publication_service', 'content_claims', 'export'),
    ('wce/draft_revision_scan.py', 109, 'wce.current_publication_service', '_ACCOUNT_GUARD', 'export'),
    ('wce/draft_revision_scan.py', 109, 'wce.current_publication_service', '_BROKER_GUARD', 'export'),
    ('wce/draft_revision_scan.py', 109, 'wce.current_publication_service', '_POLICY_CHECK', 'export'),
    ('wce/own_authority_history.py', 146, 'wce.own_compatible_upgrade', 'registry_path', 'export'),
    ('wce/own_authority_history.py', 392, 'wce.own_body5_upgrade', 'SOURCE_SHA', 'export'),
    ('wce/own_body5_family.py', 91, 'wce.own_replacement_batch', 'base', 'export'),
    ('wce/own_body5_namespace.py', 96, 'wce.own_replacement_batch', 'base', 'export'),
    ('wce/own_body5_namespace.py', 209, 'wce.own_replacement_executor', 'AdmissionPermit', 'export'),
    ('wce/own_body5_preview.py', 12, 'wce.own_replacement_batch', '_preview', 'export'),
    ('wce/own_history_locators.py', 379, 'wce.own_replacement_batch', 'base', 'export'),
    ('wce/own_lineage_replacement.py', 151, 'wce.own_replacement_batch', 'registry_from_db', 'export'),
    ('wce/own_lineage_replacement.py', 228, 'wce.own_replacement_batch', 'validate_history', 'export'),
    ('wce/own_lineage_replacement.py', 260, 'wce.own_replacement_batch', 'registry_from_db', 'export'),
    ('wce/own_replacement_namespace.py', 96, 'wce.own_replacement_batch', 'base', 'export'),
    ('wce/own_replacement_namespace.py', 112, 'wce.own_replacement_batch', 'base', 'export'),
    ('wce/own_replacement_namespace.py', 241, 'wce.own_replacement_executor', 'AdmissionPermit', 'export'),
    ('wce/own_replacement_unrelated.py', 268, 'wce.own_replacement_batch', 'resolve', 'export'),
    ('wce/own_replacement_unrelated_v2.py', 301, 'wce.own_replacement_batch', 'resolve', 'export'),
    ('wce/own_replacement_unrelated_v3.py', 452, 'wce.own_replacement_batch', 'resolve', 'export'),
    ('wce/own_revision_relocation.py', 430, 'wce.own_replacement_batch', '_maintenance_pointers', 'export'),
    ('wce/own_revision_relocation.py', 430, 'wce.own_replacement_batch', 'base', 'export'),
    ('wce/publication_qa.py', 19, 'wce.publication_cli_config', 'OfficialRuntime', 'export'),
    ('wce/publication_qa.py', 19, 'wce.publication_cli_config', 'RuntimeUnavailable', 'export'),
    ('wce/publication_service.py', 278, 'wce.publication_render.publication_renderer', 'RenderUnavailable', 'module'),
    ('wce/publication_service.py', 278, 'wce.publication_render.publication_renderer', 'render_current', 'module'),
})
_IMPLICIT_EXPORTS = frozenset({'__builtins__', '__cached__', '__doc__', '__file__',
                              '__loader__', '__name__', '__package__', '__spec__'})


def _target(package, node):
    count = len(package) - node.level + 1
    if count < 1:
        return None
    base = package[:count]
    return '.'.join((*base, node.module) if node.module else base)


class _Exports(ast.NodeVisitor):
    """Possible module bindings, including names defined conditionally."""

    def __init__(self, module, package):
        self.module = module
        self.package = package
        self.names = set()
        self.aliases = set()
        self.dynamic = False
        self.known_children = set()
        self.dynamic_children = False

    def visit_FunctionDef(self, node):
        self.names.add(node.name)
        for expression in (*node.decorator_list, *node.args.defaults, *node.args.kw_defaults):
            if expression is not None:
                self.visit(expression)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self.names.add(node.name)
        for expression in (*node.decorator_list, *node.bases, *node.keywords):
            self.visit(expression)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Store):
            self.names.add(node.id)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self.generic_visit(node)

    def visit_Import(self, node):
        self.names.update(alias.asname or alias.name.split('.')[0] for alias in node.names)

    def visit_ImportFrom(self, node):
        same_module = bool(node.level and _target(self.package, node) == self.module)
        for alias in node.names:
            if alias.name == '*':
                self.dynamic |= not same_module
            elif same_module:
                self.aliases.add((alias.name, alias.asname or alias.name))
            else:
                self.names.add(alias.asname or alias.name)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    def visit_MatchAs(self, node):
        if node.name:
            self.names.add(node.name)
        self.generic_visit(node)

    visit_MatchStar = visit_MatchAs

    def visit_MatchMapping(self, node):
        if node.rest:
            self.names.add(node.rest)
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in {'exec', 'eval', 'globals', 'setattr'} or (
                    node.func.id in {'locals', 'vars'} and not node.args and not node.keywords):
                self.dynamic = True
        self.generic_visit(node)

    def visit_Subscript(self, node):
        if (isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Attribute)
                and node.value.attr == 'modules' and isinstance(node.value.value, ast.Name)
                and node.value.value.id == 'sys'):
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                name = node.slice.value
                if name == self.module:
                    self.dynamic = True
                else:
                    self.known_children.add(name)
            else:
                self.dynamic = True
                self.dynamic_children = True
        self.generic_visit(node)

    # These scopes do not export their ordinary local bindings.
    def visit_Lambda(self, node):
        pass

    def visit_comprehension(self, node):
        self.visit(node.iter)
        for condition in node.ifs:
            self.visit(condition)


def findings(entries):
    trees = {}
    modules = {}
    extensions = set()
    packages = set()
    for path, (raw, _) in sorted(entries.items()):
        entry = PurePosixPath(path)
        directory = entry.parts[:-1]
        if not all(part.isidentifier() for part in directory):
            continue
        packages.update('.'.join(directory[:size]) for size in range(1, len(directory) + 1))
        if entry.suffix in {'.so', '.pyd'} and entry.name.split('.')[0].isidentifier():
            extensions.add('.'.join((*directory, entry.name.split('.')[0])))
        if entry.suffix != '.py':
            continue
        tree = ast.parse(raw, filename=path)
        init = entry.name == '__init__.py'
        module = '.'.join(directory if init else (*directory, entry.stem))
        exports = _Exports(module, directory)
        exports.visit(tree)
        trees[path] = directory, tree, exports
        if init or module not in modules:
            modules[module] = (init, exports)

    problems = []

    def is_package(module):
        return modules[module][0] if module in modules else module in packages and module not in extensions

    def exists(module):
        if module not in modules and module not in packages and module not in extensions:
            return False
        parts = module.split('.')
        return all(is_package('.'.join(parts[:i])) for i in range(1, len(parts)))

    def injected(module, exports):
        return any(module == child or module.startswith(child + '.') for child in exports.known_children)

    def dynamic_child(module):
        parent = module.rpartition('.')[0]
        while parent:
            if parent in modules and is_package(parent):
                exports = modules[parent][1]
                if exports.dynamic_children or '__path__' in exports.names or injected(module, exports):
                    return True
            parent = parent.rpartition('.')[0]
        return False

    def indeterminate_exports(exports):
        return exports is not None and (exports.dynamic or '__getattr__' in exports.names)

    def bound(module, exports, symbol, caller):
        child = f'{module}.{symbol}'
        return (symbol in _IMPLICIT_EXPORTS or exports is not None and symbol in exports.names
                or is_package(module) and (
                    symbol == '__path__' or exists(child) or injected(child, caller) or dynamic_child(child)))

    for module, (_, exports) in modules.items():
        pending = exports.aliases
        # A self-import may alias an actual child or name, but a cycle of
        # aliases cannot introduce its own bindings.
        while pending:
            resolved = {(source, alias) for source, alias in pending
                        if indeterminate_exports(exports) or bound(module, exports, source, exports)}
            if not resolved:
                break
            exports.names.update(alias for _, alias in resolved)
            pending = pending - resolved

    for path, (package, tree, caller) in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.level:
                continue
            target = _target(package, node)
            if target is None:
                target_label = '.' * node.level + (node.module or '')
                problems.extend((path, node.lineno, target_label, alias.name, 'module') for alias in node.names)
                continue
            if injected(target, caller):
                continue
            if not exists(target):
                if dynamic_child(target):
                    continue
                problems.extend((path, node.lineno, target, alias.name, 'module') for alias in node.names)
                continue
            exports = modules[target][1] if target in modules else None
            if target in extensions or indeterminate_exports(exports):
                continue
            for alias in node.names:
                symbol = alias.name
                if symbol == '*' or bound(target, exports, symbol, caller):
                    continue
                problems.append((path, node.lineno, target, symbol, 'export'))
    return problems


def check_relative_imports(entries, legacy=LEGACY_IMPORTS):
    observed = Counter(findings(entries))
    baseline = Counter(legacy)
    errors = [f'{path}:{line}: missing {kind} ({target} import {symbol})'
              for path, line, target, symbol, kind in sorted((observed - baseline).elements())]
    errors.extend(f'{path}:{line}: retired baseline no longer matches ({target} import {symbol}, {kind})'
                  for path, line, target, symbol, kind in sorted((baseline - observed).elements()))
    if errors:
        raise ValueError('Plugin relative import check failed:\n' + '\n'.join(errors))
