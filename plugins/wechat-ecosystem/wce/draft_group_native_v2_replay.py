"""Group-only 2GiB RAM replay; old revision/V1 ceiling stays unchanged."""
import zlib

from .draft_revision_stream import _RawReplay
from .draft_revision_native_source import MAX_LINE, SourceHold, checked_guard, require


class GroupRawReplayV2(_RawReplay):
    def __init__(self, expected):
        # Only the constructor differs. Original capture/seal/compare/finish
        # and independent 2MiB compression blocks remain the exact old code.
        require(type(expected) is int and 0 < expected <= 2147483648, 'GROUP_NATIVE_V2_REPLAY_LIMIT')
        self.expected = expected
        self.captured = self.decoded = self.stored = 0
        self.pending = bytearray()
        self.blocks = []
        self.index = 0
        self.buffer = b''
        self.position = 0
        self.sealed = False

    def read_captured_range(self, start, end, guard):
        """Independent cursor; never consumes or rebases the compare cursor."""
        require(type(start) is int and type(end) is int and 0 <= start < end <= self.captured
                and end-start <= MAX_LINE, 'GROUP_NATIVE_V2_REPLAY_RANGE')
        chunks = []
        at = start
        while at < end:
            checked_guard(guard)
            number, inside = divmod(at, self.BLOCK)
            if number < len(self.blocks):
                block = self.blocks[number]
                require(type(block) is tuple and len(block) == 3, 'SOURCE_PREFIX_CHANGED')
                compressed, size, data = block
                require(type(compressed) is bool and type(size) is int
                        and 0 < size <= self.BLOCK and type(data) is bytes
                        and 0 < len(data) <= size, 'SOURCE_PREFIX_CHANGED')
                if compressed:
                    decoder = zlib.decompressobj(-15)
                    raw = decoder.decompress(data, size+1)
                    require(len(raw) == size and decoder.eof and not decoder.unused_data
                            and not decoder.unconsumed_tail, 'SOURCE_PREFIX_CHANGED')
                else:
                    require(len(data) == size, 'SOURCE_PREFIX_CHANGED')
                    raw = data
                expected = min(self.BLOCK, self.expected-number*self.BLOCK)
                require(size == expected or not self.sealed and size == self.BLOCK,
                        'SOURCE_PREFIX_CHANGED')
            else:
                require(not self.sealed and number == len(self.blocks), 'SOURCE_PREFIX_CHANGED')
                raw = bytes(self.pending)
            size = min(end-at, len(raw)-inside)
            require(size > 0, 'SOURCE_PREFIX_CHANGED')
            chunks.append(raw[inside:inside+size])
            at += size
        checked_guard(guard)
        return b''.join(chunks)

    def discard(self):
        self.blocks.clear()
        self.pending.clear()
        self.buffer = b''
