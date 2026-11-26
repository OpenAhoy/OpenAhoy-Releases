"""Read one presentation frame from a previously verified local movie."""
from base64 import b64encode
from bisect import bisect_right
from fractions import Fraction
from functools import lru_cache
import json

from .audio_jobs import invoke
from .bounded_file import file_state
from .video_director import require

INPUT = ['-v', 'error', '-protocol_whitelist', 'file,pipe', '-f', 'mov']
FIT = "scale=w='min(960,iw)':h='min(960,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"


@lru_cache(maxsize=8)
def index(path, pin):
    # Packet timestamps come from the MP4 sample tables. Decode only the requested image.
    raw = invoke('ffprobe', [*INPUT, '-select_streams', 'v:0', '-show_entries',
                 'packet=pts:stream=time_base:format=start_time', '-of', 'json', str(path)], 30)
    data = json.loads(raw)
    points = sorted(packet['pts'] for packet in data.get('packets', ()) if type(packet.get('pts')) is int)
    require(points and file_state(path.lstat()) == pin, 'DIRECTOR_PREVIEW_UNAVAILABLE')
    return points, Fraction(data['streams'][0]['time_base']), Fraction(data['format'].get('start_time', '0'))


@lru_cache(maxsize=16)
def image_at(path, pin, pts, base, origin):
    # Seek near the sample's GOP. copyts preserves its exact original presentation timestamp.
    time = float(pts * base - origin)
    seek = ['-ss', f'{time-.15:.6f}'] if time > .15 else []
    options = ['-i', str(path), '-map', '0:v:0', '-an', '-sn', '-dn',
               '-vf', f'select=eq(pts\\,{pts}),{FIT}', '-frames:v', '1', '-fps_mode', 'passthrough',
               '-c:v', 'mjpeg', '-q:v', '4', '-f', 'image2pipe', 'pipe:1']
    jpeg = invoke('ffmpeg', ['-nostdin', '-copyts', *INPUT, *seek, *options], 30)
    if not jpeg and seek:
        # Open GOPs and unusual edit lists may need an earlier decoder start.
        jpeg = invoke('ffmpeg', ['-nostdin', '-copyts', *INPUT, *options], 60)
    require(jpeg.startswith(b'\xff\xd8\xff') and len(jpeg) <= 768 * 1024, 'DIRECTOR_PREVIEW_UNAVAILABLE')
    return b64encode(jpeg).decode('ascii')


def read(path, pin, sha256, time_us, seconds):
    require(0 <= time_us < round(seconds * 1000000), 'VIDEO_ASSET_OFFSET_INVALID')
    require(file_state(path.lstat()) == pin, 'DIRECTOR_ASSET_CHANGED')
    points, base, origin = index(path, pin)
    # Frontend sends nearest integer microseconds. Include a boundary rounded down by < 0.5 μs.
    moment = (origin + Fraction(2*time_us+1, 2000000)) / base
    i = bisect_right(points, moment) - 1
    require(i >= 0, 'DIRECTOR_PREVIEW_UNAVAILABLE')
    pts = points[i]
    jpeg = image_at(path, pin, pts, base, origin)
    require(file_state(path.lstat()) == pin, 'DIRECTOR_ASSET_CHANGED')
    return {'sha256': sha256, 'time_us': time_us, 'pts': pts, 'time_base': str(base), 'jpeg': jpeg}
