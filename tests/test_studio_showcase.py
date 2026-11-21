"""The packaged case uses fixed decoded bytes and never relies on project state."""
from base64 import b64decode
from hashlib import sha256
import unittest

from wce.contracts import WCEError
from wce.own_connection_tools import ConnectionRouter
from wce.own_plugin import PersonalStdioServer
from wce.own_updates_protocol import RESOURCE
from wce.studio_showcase import chunk, index


class StudioShowcaseTests(unittest.TestCase):
    def test_each_asset_reads_complete_verified_bytes(self):
        model = index()
        self.assertEqual(len(model['media']), 14)
        self.assertEqual([row['version'] for row in model['articles']], [1, 2])
        for key, meta in model['media'].items():
            with self.subTest(media=key):
                self.assertNotIn('file', meta)
                offset, repeated, blocks = 0, sha256(), 0
                while offset < meta['bytes']:
                    report = chunk(key, offset)
                    raw = b64decode(report['data'], validate=True)
                    self.assertEqual(report['next'], offset + len(raw))
                    self.assertEqual((report['media_id'], report['offset']), (key, offset))
                    repeated.update(raw)
                    offset = report['next']
                    blocks += 1
                self.assertEqual(repeated.hexdigest(), meta['sha256'])
                if key == 'gif':
                    self.assertGreater(blocks, 1)

    def test_unknown_id_traversal_and_bad_offsets_are_refused(self):
        cases = [('../manifest.json', 0), ('unknown', 0), ('score', -1),
                 ('score', index()['media']['score']['bytes'])]
        for key, offset in cases:
            with self.subTest(media=key, offset=offset), self.assertRaisesRegex(
                    WCEError, 'STUDIO_SHOWCASE_MEDIA_NOT_FOUND'):
                chunk(key, offset)

    def test_real_management_resource_has_one_case_surface_and_app_tool(self):
        server = PersonalStdioServer(ConnectionRouter())
        descriptors = server._listed_tools()
        tool, = [row for row in descriptors if row['name'] == 'wce.ui.video.director.media']
        self.assertEqual(tool['_meta']['ui']['visibility'], ['app'])
        self.assertIn('showcase_index', [row['properties']['action'].get('const')
                                         for row in tool['inputSchema']['oneOf']])
        resource = server.resource('resources/read', {'uri': RESOURCE})['contents'][0]['text']
        self.assertEqual(resource.count('id="studioShowcase"'), 1)
        self.assertEqual(resource.count('</body>'), 1)
        self.assertNotIn('127.0.0.1:62112', resource)
        self.assertNotIn('u2-showcase/', resource)
