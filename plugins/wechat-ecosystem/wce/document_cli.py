"""Explicit local document/image preview. Never initializes a connection."""
import argparse
import os
from pathlib import Path
import signal
import threading

from .bounded_file import FileSource
from .contracts import WCEError
from .documents import assets, normalize
from .document_preview import PreviewServer, html
from .prepared_draft_fixture import decode_json


def read_json(path):
    path = Path(os.path.abspath(path))
    # The existing reader rejects symlinks, non-regular files and escapes.
    data = FileSource(path.parent).read(path.name)
    return decode_json(data, 128 * 1024)


def read_document_json(path):
    """Larger decoding only for an actually validated imported group."""
    path = Path(os.path.abspath(path))
    data = FileSource(path.parent).read(path.name)
    try:
        return decode_json(data, 128 * 1024)
    except WCEError:
        from .own_group_json import GROUP_BYTES, GROUP_NODES
        from .import_styles import POLICY
        value = decode_json(data, GROUP_BYTES, max_nodes=GROUP_NODES)
        if (type(value) is not dict or value.get('format') != 3 or value.get('policy') != POLICY
                or type(value.get('articles')) is not list or not 2 <= len(value['articles']) <= 8):
            raise WCEError('DOCUMENT_INVALID') from None
        normalize(value)
        return value


def prepare(document_path, asset_manifest_path, image_root):
    document = normalize(read_document_json(document_path))
    records = read_json(asset_manifest_path)
    from .import_styles import POLICY
    maximum = 48 if document.get('format') == 3 and document.get('policy') == POLICY else 40
    if type(records) is not list or not 1 <= len(records) <= maximum:
        raise WCEError('DOCUMENT_INVALID_ASSETS')
    source, mapping = FileSource(Path(os.path.abspath(image_root))), {}
    for item in records:
        if (type(item) is not dict or set(item) != {'asset_ref', 'declared_type', 'relative_path'}
                or item['declared_type'] not in ('image/png', 'image/jpeg')
                or type(item['asset_ref']) is not str or item['asset_ref'] in mapping):
            raise WCEError('DOCUMENT_INVALID_ASSETS')
        mapping[item['asset_ref']] = (item['declared_type'], source.read(item['relative_path']))
    required = {ref for _, ref, _ in assets(document)}
    if set(mapping) != required:
        raise WCEError('DOCUMENT_INVALID_ASSETS')
    images = {slot: mapping[ref] for slot, ref, _ in assets(document)}
    return html(document, images)


def main():
    parser = argparse.ArgumentParser(description='Jiusera local preview; no token or WeChat request')
    parser.add_argument('--document', required=True)
    parser.add_argument('--assets', required=True)
    parser.add_argument('--images', required=True)
    args = parser.parse_args()
    try:
        server = PreviewServer(prepare(args.document, args.assets, args.images))
    except WCEError as error:
        from .document_errors import location
        import json
        parser.exit(1, error.code + ' ' + json.dumps(location(error), sort_keys=True) + '\n')
    except OSError:
        parser.exit(1, 'DOCUMENT_PREVIEW_INPUT_REJECTED\n')
    stop = threading.Event()
    def terminate(*_):
        stop.set()
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    print(server.url, flush=True)
    try:
        stop.wait(300)
    finally:
        server.close()


if __name__ == '__main__':
    main()
