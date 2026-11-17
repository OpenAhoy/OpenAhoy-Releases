"""Packaged OpenAhoy artwork; no network, account state or generated graphics."""
import base64
from functools import cache
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
# The existing builder copies the Codex template to the package root.
_PACKAGE = _ROOT / 'integrations/codex' if (_ROOT / 'integrations/codex/plugin.json').is_file() else _ROOT
_ASSETS = _PACKAGE / 'assets/openahoy-v1'
HORIZONTAL = (_ASSETS / 'openahoy-horizontal-color.svg').read_text()


@cache
def video_model_mark():
    raw = (_PACKAGE / 'assets/models/minimax-color-black.png').read_bytes()
    return 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')


def icons():
    result = []
    for variant, theme in (('color', 'light'), ('inverse', 'dark')):
        raw = (_ASSETS / ('openahoy-symbol-' + variant + '.svg')).read_bytes()
        result.append({'src': 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode('ascii'),
            'mimeType': 'image/svg+xml', 'sizes': ['any'], 'theme': theme})
    return result


@cache
def host_icons():
    return tuple({'src': 'data:image/png;base64,' +
                         base64.b64encode((_ASSETS / f'openahoy-host-{theme}-128.png').read_bytes()).decode('ascii'),
                  'mimeType': 'image/png', 'sizes': ['128x128'], 'theme': theme}
                 for theme in ('light', 'dark'))


def header(artwork=HORIZONTAL):
    # Pages have a fixed light background, independent of the host theme.
    # Artwork includes its wordmark; a second text label would duplicate it.
    if artwork.startswith('<?xml '):
        artwork = artwork.partition('?>')[2].lstrip()
    return '<span class="oa-brand-logo" role="img" aria-label="OpenAhoy"><span aria-hidden="true">' + artwork + '</span></span>'
