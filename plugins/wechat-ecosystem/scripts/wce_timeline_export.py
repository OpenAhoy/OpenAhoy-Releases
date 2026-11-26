"""Execute one already submitted local Director render under the caller's inherited file lease."""
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from wce.video_director_export import worker
    registry, project, work, version, fd = sys.argv[1:]
    worker(registry, project, work, version, int(fd))
