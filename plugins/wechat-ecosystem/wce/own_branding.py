"""Packaged Jiusera artwork; no network, account state or generated graphics."""
import base64
from functools import cache
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[1]
# The existing builder copies the Codex template to the package root.
_PACKAGE = _ROOT / 'integrations/codex' if (_ROOT / 'integrations/codex/plugin.json').is_file() else _ROOT
_ASSETS = _PACKAGE / 'assets/jiusera'
HORIZONTAL = (_ASSETS / 'Jiusera-horizontal-color.svg').read_text()


@cache
def video_model_mark():
    raw = (_PACKAGE / 'assets/models/minimax-color-black.png').read_bytes()
    return 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')


def _dark_deer(artwork):
    return artwork.replace(b'fill="#111111"', b'fill="#FFFFFF"', 1)


def _svg_data(artwork):
    return 'data:image/svg+xml;base64,' + base64.b64encode(artwork).decode('ascii')


def jiusera_symbols():
    artwork = (_ASSETS / 'Jiusera-symbol-color.svg').read_bytes()
    return _svg_data(artwork), _svg_data(_dark_deer(artwork))


def icons():
    return list(host_icons())


@cache
def host_icons():
    return tuple({'src': 'data:image/png;base64,' +
                         base64.b64encode((_PACKAGE / 'assets/jiusera' / f'jiusera-host-{theme}-128.png').read_bytes()).decode('ascii'),
                  'mimeType': 'image/png', 'sizes': ['128x128'], 'theme': theme}
                 for theme in ('light', 'dark'))


@cache
def jiusera_header(trim=False):
    artwork = HORIZONTAL.encode('utf-8')
    if trim:
        # Balance the official wordmark's asymmetric transparent margins in the notch.
        artwork = artwork.replace(b'width="1420" height="485" viewBox="0 0 1420 485"',
                                  b'width="1196" height="485" viewBox="96 0 1196 485"', 1)
    images = ''.join(f'<img src="{_svg_data(svg)}" alt="">' for svg in (artwork, _dark_deer(artwork)))
    return '<span class="oa-brand-logo oa-jiusera-logo" role="img" aria-label="Jiusera">' + images + '</span>'


def header(artwork=HORIZONTAL):
    # Pages have a fixed light background, independent of the host theme.
    # Artwork includes its wordmark; a second text label would duplicate it.
    if artwork.startswith('<?xml '):
        artwork = artwork.partition('?>')[2].lstrip()
    return '<span class="oa-brand-logo" role="img" aria-label="Jiusera"><span aria-hidden="true">' + artwork + '</span></span>'


@cache
def openahoy_symbol():
    images = []
    for variant in ('color', 'inverse'):
        raw = (_PACKAGE / 'assets/openahoy-v1' / f'openahoy-symbol-{variant}.svg').read_bytes()
        src = 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode('ascii')
        images.append(f'<img src="{src}" alt="">')
    return '<span class="wb-openahoy-mark" aria-hidden="true">' + ''.join(images) + '</span>'


@cache
def l_unify_symbol():
    raw = (_PACKAGE / 'assets/l-unify/l-unify-studio-mark.svg').read_bytes()
    src = 'data:image/svg+xml;base64,' + base64.b64encode(raw).decode('ascii')
    return f'<span class="wb-unify-mark" aria-hidden="true" style="--wb-unify-mask:url({src})"></span>'
