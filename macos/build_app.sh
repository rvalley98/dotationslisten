#!/bin/bash
# Builds Dotationslisten.app and Dotationslisten-<version>.dmg (Apple Silicon, macOS >= 13).
#
#   macos/build_app.sh
#
# Needs: Xcode command line tools, cmake and uv (brew install cmake uv).
# The app contains Python, the app code, Tesseract and Ollama (handwriting; the model itself
# is downloaded from the app). LibreOffice is a separate (free) app, only needed for .xls.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
BUILD="$HERE/build"
DIST="$HERE/dist"
VERSION="$(cat "$ROOT/VERSION")"
PY="$BUILD/venv/bin/python"

[ -x "$BUILD/tesseract/bin/tesseract" ] || "$HERE/build_tesseract.sh"

if [ ! -x "$PY" ]; then
    # python-build-standalone via uv: runs on macOS >= 11 (Homebrew's Python only on the build machine's macOS)
    uv venv --python 3.12 --python-preference only-managed "$BUILD/venv"
fi
uv pip install --quiet --python "$PY" -r "$ROOT/requirements.txt" pyinstaller rumps
"$PY" "$ROOT/desktop/fetch_ollama.py" mac "$BUILD"

"$PY" "$ROOT/desktop/make_icons.py" "$BUILD"
SRC="$BUILD/src"
"$PY" "$ROOT/desktop/collect_licenses.py" "$BUILD/THIRD_PARTY_LICENSES.txt" \
    "Tesseract OCR und Sprachdaten (Apache-2.0)=$SRC/tesseract/LICENSE" \
    "Leptonica (BSD-2-Clause)=$SRC/leptonica/leptonica-license.txt" \
    "libpng (libpng License)=$SRC/libpng/LICENSE" \
    "Ollama (MIT) und mitgelieferte Bibliotheken=$BUILD/ollama-licenses"

rm -rf "$DIST" "$BUILD/pyinstaller"
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
    --distpath "$DIST" --workpath "$BUILD/pyinstaller" "$HERE/Dotationslisten.spec"
APP="$DIST/Dotationslisten.app"
# Ollama as shipped (its own binaries find their libraries next to them), not through PyInstaller
cp -R "$BUILD/ollama" "$APP/Contents/Resources/ollama"
rm -f "$APP/Contents/Resources/ollama/.version"

# ad-hoc signature (no Apple Developer ID): required on Apple Silicon, macOS asks once on first start
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

# every binary must run on the minimum macOS - except Ollama, which needs macOS 14 (the launcher
# only starts it there; on macOS 13 the values are entered by hand)
MIN_OK=13.0
bad=0
while IFS= read -r f; do
    # read all of otool's output (an early awk exit -> SIGPIPE -> pipefail would end the script)
    v="$(otool -l "$f" 2>/dev/null | awk '/LC_BUILD_VERSION/ {b=1} b && /minos/ && !done {print $2; done=1}' || true)"
    [ -z "$v" ] && continue
    if [ "$(printf '%s\n%s\n' "$v" "$MIN_OK" | sort -V | tail -1)" != "$MIN_OK" ] && [ "$v" != "$MIN_OK" ]; then
        echo "zu neu (macOS $v): $f"; bad=1
    fi
done < <(find "$APP" -type f \( -perm -u+x -o -name "*.dylib" -o -name "*.so" \) -not -path "*/Resources/ollama/*")
[ "$bad" = 0 ] || { echo "Abbruch: Bestandteile laufen erst auf neuerem macOS"; exit 1; }

# disk image: app + Applications link + instructions
STAGE="$BUILD/dmg"
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Programme"
cp "$HERE/INSTALLATION.txt" "$STAGE/Bitte lesen – Installation.txt"
cp "$ROOT/LICENSE" "$STAGE/Lizenz.txt"
cp "$BUILD/THIRD_PARTY_LICENSES.txt" "$STAGE/Lizenzen Dritter.txt"
DMG="$DIST/Dotationslisten-$VERSION.dmg"
hdiutil create -quiet -volname "Dotationslisten $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"

du -sh "$APP" "$DMG"
echo "Fertig: $DMG"
