"""Fixed isolated connection-only broker entry; no setup or business mode."""
from pathlib import Path
import sys

if sys.version_info < (3, 11):
    raise SystemExit('WCE_PYTHON_311_REQUIRED')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wce.own_base_domain import main

if __name__ == '__main__':
    main()
