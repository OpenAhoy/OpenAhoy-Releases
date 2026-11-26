#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
mkdir -p "$here/build"
TMPDIR="$here/build" xcrun clang++ -std=c++20 -arch arm64 -mmacosx-version-min=14.0 -O2 -ffp-contract=off -fobjc-arc \
    -Wall -Wextra "$here/bus.mm" -framework AudioToolbox -framework Foundation -o "$here/build/render"
