"""Non-destructive clip looks, rendered on the output canvas with local system tools."""
from math import ceil
import subprocess
from unicodedata import east_asian_width
from xml.etree import ElementTree as ET

from .contracts import WCEError
from .tools import schema


def text_field(limit):
    return {'type': 'string', 'minLength': 1, 'maxLength': limit, 'x-wce-maxUtf8Bytes': limit * 4}


def choices(*items):
    return {'type': 'string', 'enum': list(items)}


def look_schema(ms):
    strength = {'type': 'integer', 'minimum': -100, 'maximum': 100}
    zoom = {'type': 'integer', 'minimum': 100, 'maximum': 200}
    cue = schema({'in_ms': ms, 'out_ms': ms, 'text': text_field(200)})
    return schema({}, {'title': text_field(80), 'caption': text_field(200),
                       'cues': {'type': 'array', 'maxItems': 128, 'items': cue},
                       'filter': choices('mono', 'warm', 'cool'), 'effect': choices('blur', 'vignette'),
                       'transition': choices('fade', 'white'),
                       'brightness': strength, 'contrast': strength, 'mirror': {'type': 'boolean'},
                       'zoom': zoom, 'zoom_end': zoom, 'mask': choices('circle', 'letterbox'),
                       'rotation': {'type': 'integer', 'enum': [90, 180, 270]}})


def validate_cues(look, source_ms):
    # XML 1.0 excludes these two Unicode characters; reject at save rather than in the renderer.
    labels = [look.get('title', ''), look.get('caption', ''), *(cue['text'] for cue in look.get('cues', ()))]
    if any('\ufffe' in value or '\uffff' in value for value in labels):
        raise WCEError('DIRECTOR_TEXT_INVALID')
    previous = 0
    for cue in look.get('cues', ()):
        if not previous <= cue['in_ms'] < cue['out_ms'] <= source_ms:
            raise WCEError('DIRECTOR_CAPTION_RANGE_INVALID')
        previous = cue['out_ms']


def image_filters(look, dimensions, frames, fps):
    width, height = dimensions
    filters = []
    if look.get('mirror'):
        filters.append('hflip')
    rotation = look.get('rotation')
    if rotation == 180:
        filters.extend(['hflip', 'vflip'])
    elif rotation in (90, 270):
        filters.append('transpose=' + ('clock' if rotation == 90 else 'cclock'))
        filters.extend([f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1',
                        f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2', 'setsar=1'])
    z0 = look.get('zoom', 100) / 100
    z1 = look.get('zoom_end', z0 * 100) / 100
    if z0 != 1 or z1 != 1:
        filters.append(f"zoompan=z='{z0}+({z1}-{z0})*on/{max(1, frames-1)}':"
                       f"x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={width}x{height}:fps={fps}")
    palette = look.get('filter')
    if palette == 'mono':
        filters.append('colorchannelmixer=' + ':'.join(['.2126:.7152:.0722:0'] * 3))
    gains = {'warm': (1.08, 1, .90), 'cool': (.90, 1, 1.08)}.get(palette, (1, 1, 1))
    if gains != (1, 1, 1) or look.get('contrast') or look.get('brightness'):
        contrast = 1 + look.get('contrast', 0) / 100
        brightness = 255 * look.get('brightness', 0) / 200
        channels = [f"{ch}='(val*{gain}-127.5)*{contrast}+127.5+{brightness}'"
                    for ch, gain in zip('rgb', gains)]
        filters.append('format=rgb24,lutrgb=' + ':'.join(channels))
    if look.get('effect') == 'blur':
        filters.append(f'gblur=sigma={height*.009:.4f}')
    return filters


def entry_filter(look, frames, fps):
    transition = look.get('transition')
    if not transition or frames < 2:
        return ''
    duration = min(.35, frames / (fps * 2))
    return f"fade=t=in:st=0:d={duration:.6f}:color={'white' if transition == 'white' else 'black'}"


def wrap(text, units):
    lines = []
    for paragraph in text.splitlines() or ['']:
        line, length = '', 0
        for char in paragraph:
            step = 1 if east_asian_width(char) in ('F', 'W') else .33 if char.isspace() else .65
            if line and length + step > units:
                lines.append(line)
                line, length = '', 0
            line += char
            length += step
        lines.append(line)
    return lines


def lettering(svg, value, width, height, title=False):
    size = height * (.075 if title else .052)
    # Keep user line breaks; collapse extra paragraphs to keep both text bands inside the canvas.
    paragraphs = value.splitlines()
    if len(paragraphs) > 3:
        value = '\n'.join(paragraphs[:2] + [' '.join(paragraphs[2:])])
    lines = wrap(value, width * .86 / size)
    while len(lines) > 3:
        size *= .9
        lines = wrap(value, width * .86 / size)
    y = height * (.19 if title else .91) - (0 if title else (len(lines)-1)*size*1.2)
    for line in lines:
        attrs = {'x': str(width/2), 'y': str(y), 'text-anchor': 'middle', 'font-size': str(size),
                 'font-weight': '600', 'font-family': 'PingFang SC, sans-serif', 'fill': '#fff'}
        # Separate stroke and fill works with the macOS system SVG rasterizer.
        ET.SubElement(svg, 'text', attrs | {'stroke': '#171717', 'stroke-width': str(size*.08),
                                            'stroke-linejoin': 'round'}).text = line
        ET.SubElement(svg, 'text', attrs).text = line
        y += size * 1.2


def overlay_png(path, look, caption, dimensions):
    width, height = dimensions
    svg = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg', 'width': str(width), 'height': str(height)})
    if look.get('effect') == 'vignette':
        gradient = ET.SubElement(ET.SubElement(svg, 'defs'), 'radialGradient', {'id': 'v', 'r': '50%'})
        for offset, alpha in [('55%', '0'), ('100%', '.58')]:
            ET.SubElement(gradient, 'stop', {'offset': offset, 'stop-color': 'black', 'stop-opacity': alpha})
        ET.SubElement(svg, 'rect', {'width': '100%', 'height': '100%', 'fill': 'url(#v)'})
    if look.get('mask') == 'circle':
        cx, cy, r = width / 2, height / 2, min(width, height) * .48
        path_data = (f'M0 0H{width}V{height}H0z M{cx-r} {cy} '
                     f'a{r} {r} 0 1 0 {2*r} 0 a{r} {r} 0 1 0 {-2*r} 0z')
        ET.SubElement(svg, 'path', {'d': path_data, 'fill': '#000', 'fill-rule': 'evenodd'})
    elif look.get('mask') == 'letterbox':
        band = max(0, (height - width / 2.39) / 2)
        for y in (0, height - band):
            ET.SubElement(svg, 'rect', {'width': str(width), 'height': str(band), 'y': str(y), 'fill': '#000'})
    if look.get('title'):
        lettering(svg, look['title'], width, height, title=True)
    if caption:
        lettering(svg, caption, width, height)
    # The user supplies text nodes only. ElementTree encodes markup, attributes and external references.
    source = path.with_suffix('.svg')
    ET.ElementTree(svg).write(source, encoding='utf-8', xml_declaration=True)
    try:
        subprocess.run(['/usr/bin/sips', '-s', 'format', 'png', str(source), '--out', str(path)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=20, check=True)
    except (OSError, subprocess.SubprocessError):
        raise WCEError('DIRECTOR_OVERLAY_RENDER_FAILED') from None


def overlay_input(folder, clip, dimensions, frames, fps):
    look = clip.get('look', {})
    cues = look.get('cues')
    if not any(look.get(key) for key in ('title', 'caption', 'cues', 'mask')) and look.get('effect') != 'vignette':
        return []
    # Caption intervals are expressed on the original source clock. Map them to the
    # first matching output frame and keep the exact output duration across trims.
    changes = {0: '' if cues else look.get('caption', '')}
    for cue in cues or ():
        first = max(0, ceil((cue['in_ms'] - clip['in_ms']) * fps / 1000))
        end = min(frames, ceil((cue['out_ms'] - clip['in_ms']) * fps / 1000))
        if first < end:
            changes[first] = cue['text']
            if end < frames:
                changes[end] = ''
    images, plan = {}, ['ffconcat version 1.0']
    marks = sorted(changes)
    for first, end in zip(marks, marks[1:] + [frames]):
        value = changes[first]
        if value not in images:
            image = folder / f'layer-{len(images)}.png'
            overlay_png(image, look, value, dimensions)
            images[value] = image
        image = images[value]
        plan.extend([f"file '{image.name}'", f'option framerate {fps}', f'duration {(end-first)/fps:.9f}'])
    if len(marks) == 1:
        return ['-f', 'image2', '-pattern_type', 'none', '-i', str(image)]
    plan.append(f"file '{image.name}'")
    plan.append(f'option framerate {fps}')
    recipe = folder / 'layers.ffconcat'
    recipe.write_text('\n'.join(plan) + '\n')
    return ['-protocol_whitelist', 'file,pipe', '-f', 'concat', '-safe', '0', '-i', str(recipe)]
