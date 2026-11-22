"""Exercise the old-readable character index and its recoverable appearance commit."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from wce import character_library as library
from wce.own_connection_policy import atomic_write


class CharacterIndexRollbackTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = 'test-character'
        self.parent = library.path_check(self.root, True)

    def index(self, version, chosen='front'):
        def asset(name, view, status):
            return {'id': name, 'character': {'id': 'tester', 'name': 'Sample', 'series': 'Example',
                                             'aliases': [], 'profile': {'height': '168 cm'}},
                    'use': 'full_body', 'initial_status': status, 'label': name, 'description': '',
                    'source': '', 'path': 'fixture.png', 'sha256': 'a' * 64,
                    'appearance': {'group': 'base', 'item_id': view, 'item_name': view, 'view': view,
                                   'format': 'individual'}}
        items = {'front': asset('front', 'front', 'current'),
                 'back': asset('back', 'back', 'current'),
                 'alternate': asset('alternate', 'front', 'candidate')}
        current = {library.slot(items[key]): key for key in (chosen, 'back')}
        return {'schema': 3, 'project_id': self.project, 'revision': version,
                'assets': items, 'current': current, 'primary': {}}

    def check_same_index(self, index):
        self.assertEqual(library.read_index(self.project, self.root), index)

    def test_interrupted_prepare_retains_previous_snapshot(self):
        original = self.index(1)
        library.write_index(self.root, original, None, self.parent)
        _, (_, prior) = library.read_index(self.project, self.root, with_storage=True)
        updated = self.index(2, 'alternate')

        def stop_before_switch(path, *args, **kwargs):
            if path.name == library.INDEX:
                raise OSError('interrupted before the commit point')
            return atomic_write(path, *args, **kwargs)

        with patch.object(library, 'atomic_write', side_effect=stop_before_switch), self.assertRaises(OSError):
            library.write_index(self.root, updated, prior, self.parent)
        self.check_same_index(original)

    def test_interrupted_finalize_reads_the_committed_snapshot(self):
        original = self.index(1)
        library.write_index(self.root, original, None, self.parent)
        _, (_, prior) = library.read_index(self.project, self.root, with_storage=True)
        updated = self.index(2, 'alternate')

        def stop_after_switch(path, value, *args, **kwargs):
            if path.name == library.APPEARANCE_INDEX and value['next'] is None:
                raise OSError('interrupted after the commit point')
            return atomic_write(path, value, *args, **kwargs)

        with patch.object(library, 'atomic_write', side_effect=stop_after_switch), self.assertRaises(OSError):
            library.write_index(self.root, updated, prior, self.parent)
        self.check_same_index(updated)

    def test_old_preview_schema_three_is_converted_when_browsed(self):
        original = self.index(1)
        atomic_write(self.root / library.INDEX, original)
        director = Mock()
        director.registered.return_value = [{'id': self.project}]
        director.project.return_value = (self.root, self.parent)
        director.storage.return_value = self.root
        projects = library.CharacterLibrary(director).list()['projects']
        self.assertEqual(len(projects[0]['assets']), 3)
        plain = library.index_document(self.root, library.INDEX)
        self.assertEqual(plain['schema'], 2)
        self.assertEqual(len(plain['current']), 1)
        self.assertNotIn('appearance', plain['assets']['front'])
        self.assertNotIn('profile', plain['assets']['front']['character'])
        self.check_same_index(original)
