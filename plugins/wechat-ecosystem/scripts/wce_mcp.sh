#!/bin/sh
# Target-local Python discovery. No developer-machine interpreter or PATH injection.
if [ "$(/usr/bin/uname -s)" != Darwin ] || [ "$(/usr/bin/uname -m)" != arm64 ]; then
    echo 'OPENAHOY_MACOS_ARM64_REQUIRED' >&2
    exit 78
fi
selected=''
if [ -n "${OPENAHOY_PYTHON:-}" ]; then
    candidates="$OPENAHOY_PYTHON"
else
    candidates='/opt/homebrew/bin/python3 /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 python3'
fi
# Explicit OPENAHOY_PYTHON is one path, including spaces; otherwise probe known target candidates.
probe() {
    "$1" -I -B -c 'import sys,platform; raise SystemExit(0 if sys.platform == "darwin" and platform.machine() == "arm64" and sys.version_info >= (3,11) else 1)' >/dev/null 2>&1
}
if [ -n "${OPENAHOY_PYTHON:-}" ]; then
    if probe "$OPENAHOY_PYTHON"; then selected="$OPENAHOY_PYTHON"; fi
else
    for candidate in $candidates; do
        if probe "$candidate"; then selected="$candidate"; break; fi
    done
fi
if [ -z "$selected" ]; then
    echo 'OPENAHOY_NATIVE_PYTHON_311_REQUIRED: install arm64 Python 3.11+ or configure OPENAHOY_PYTHON' >&2
    exit 78
fi
exec "$selected" -I -B "${0%/*}/wce_mcp.py" "$@"
