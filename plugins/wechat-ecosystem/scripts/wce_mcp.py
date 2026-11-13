"""The packaged Python runtime is resolved independently of the caller's cwd."""
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    print('WCE_PYTHON_311_REQUIRED', file=sys.stderr)
    raise SystemExit(1)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wce.own_plugin import main

if __name__ == '__main__':
    main()
