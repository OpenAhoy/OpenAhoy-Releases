"""Keep the build's bundled import checks tied to actual source entries."""
from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_relative_imports import check_relative_imports, findings


def entries(files):
    return {path: (text.encode(), 0o644) for path, text in files.items()}


class RelativeImports(TestCase):
    def test_definite_missing_module_export_and_level(self):
        files = entries({
            'wce/__init__.py': 'from . import missing_child\n',
            'wce/sub/probe.py': 'from .missing import item\nfrom ..exports import typo\nfrom ... import outside',
            'wce/exports.py': 'item = 1\n',
        })
        with self.assertRaisesRegex(ValueError, '(?s)missing export .*missing_child.*missing module .*wce.sub.missing.*missing export .*typo'):
            check_relative_imports(files, frozenset())
        self.assertEqual(set(findings(files)), {
            ('wce/__init__.py',1,'wce','missing_child','export'),
            ('wce/sub/probe.py',1,'wce.sub.missing','item','module'),
            ('wce/sub/probe.py',2,'wce.exports','typo','export'),
            ('wce/sub/probe.py',3,'...','outside','module'),
        })

    def test_static_alias_unpacking_submodule_and_conditional_exports(self):
        files = entries({
            'wce/__init__.py': 'from . import child as child_alias\nfrom .exports import FIRST as EXPORTED',
            'wce/exports.py': 'FIRST, (SECOND, THIRD) = (1, (2, 3))\nif True:\n    LATER = 4\n'
                              '_ = [(BOUND := x) for x in range(1)]',
            'wce/child/__init__.py': 'from .deep import API',
            'wce/child/deep.py': 'async def API(): pass',
            'wce/child/probe.py': 'from .. import EXPORTED, child, child_alias\n'
                       'from ..exports import SECOND, THIRD, LATER, BOUND, __name__\nfrom . import API',
        })
        check_relative_imports(files, frozenset())

    def test_dynamic_exports_and_injected_submodule_are_indeterminate(self):
        files = entries({
            'wce/__init__.py': 'import sys\nsys.modules["wce.external"] = object()\n',
            'wce/lazy.py': '__getattr__ = lambda name: object()',
            'wce/star.py': 'from .lazy import *',
            'wce/probe.py': 'import sys\nsys.modules["wce.virtual"] = object()\n'
                            'from .lazy import generated\nfrom .star import dynamic\n'
                            'from .external import module_export\nfrom .virtual import virtual_export',
        })
        check_relative_imports(files, frozenset())
        files['wce/unrelated.py'] = (b'from .nonexistent import typo',0o644)
        with self.assertRaisesRegex(ValueError, 'missing module .*wce.nonexistent'):
            check_relative_imports(files, frozenset())

    def test_self_import_does_not_justify_missing_aliases_or_annotations(self):
        files = entries({'wce/__init__.py': 'from . import *\nfrom . import b as a\nfrom . import a as b\n'
                                           'annotation_only: int\nfrom . import annotation_only'})
        self.assertEqual(set(findings(files)), {
            ('wce/__init__.py',2,'wce','b','export'),
            ('wce/__init__.py',3,'wce','a','export'),
            ('wce/__init__.py',5,'wce','annotation_only','export'),
        })

    def test_baseline_allows_only_exact_retired_sites(self):
        files = entries({'wce/legacy.py': 'from .old import gone\n'})
        baseline = frozenset({('wce/legacy.py',1,'wce.old','gone','module')})
        check_relative_imports(files, baseline)
        files['wce/legacy.py'] = (b'from .old import gone\nfrom .old import gone\n', 0o644)
        with self.assertRaisesRegex(ValueError, 'legacy.py:2: missing module'):
            check_relative_imports(files, baseline)
        files['wce/legacy.py'] = (b'from .old import gone, gone\n', 0o644)
        with self.assertRaisesRegex(ValueError, 'legacy.py:1: missing module'):
            check_relative_imports(files, baseline)
        files['wce/legacy.py'] = (b'',0o644)
        with self.assertRaisesRegex(ValueError, 'retired baseline no longer matches'):
            check_relative_imports(files, baseline)
