"""Compact overview sampled from a verified local PCM WAV."""
from array import array
from functools import lru_cache
import math
import os
import sys
import wave

from .bounded_file import FileSource
from .studio_projects import media_pin


@lru_cache(maxsize=128)
def sampled_waveform(root, relative, pin):
    with FileSource(root).open_pinned(relative, expected_state=pin) as (fd, _):
        with os.fdopen(fd, 'rb', closefd=False) as stream, wave.open(stream) as pcm:
            frames, rate = pcm.getnframes(), pcm.getframerate()
            channels, width = pcm.getnchannels(), pcm.getsampwidth()
            if not frames or not 1 <= channels <= 8 or not 1 <= width <= 4 or not 1 <= rate <= 384000:
                raise wave.Error('Unsupported waveform format')
            scale = 1 << (8 * width - 1)
            bins = min(1024, frames)
            values = []
            for index in range(bins):
                start = index * frames // bins
                end = (index + 1) * frames // bins
                count = min(48, end - start)
                for_part = []
                # Take real PCM windows across the bucket, including on long sources.
                positions = {start + (end - start - count) * numerator // 4 for numerator in (1, 2, 3)}
                for position in sorted(positions):
                    pcm.setpos(position)
                    raw = pcm.readframes(count)
                    if len(raw) != count * channels * width:
                        raise wave.Error('Truncated WAV data')
                    if width == 2:
                        signed = array('h')
                        signed.frombytes(raw)
                        if sys.byteorder != 'little':
                            signed.byteswap()
                        for_part.extend(signed)
                    elif width == 1:
                        for_part.extend(sample - 128 for sample in raw)
                    else:
                        for_part.extend(int.from_bytes(raw[i:i + width], 'little', signed=True)
                                        for i in range(0, len(raw), width))
                rms = math.sqrt(sum(sample * sample for sample in for_part) / len(for_part))
                values.extend(round(value * 32767 / scale) for value in (min(for_part), max(for_part), rms))
    return {'rate': rate, 'frames': frames, 'peaks': values}


def waveform(root, relative, wanted):
    path, pin = media_pin(root, relative, wanted)
    if path.suffix.lower() != '.wav':
        return {'available': False}
    try:
        return {'available': True, 'sha256': wanted} | sampled_waveform(root, relative, pin)
    except (EOFError, wave.Error):
        # Unsupported headers still get the normal full-audio decoder attempt.
        return {'available': False}
