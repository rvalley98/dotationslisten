#!/bin/bash
# Builds Dotationslisten.app and Dotationslisten-<version>.dmg (Apple Silicon, macOS >= 13).
#
#   macos/build_app.sh
#
# Needs: Xcode command line tools, cmake and uv (brew install cmake uv).
# The app contains Python, the app code and Tesseract. LibreOffice and Ollama are separate
# (free) Mac apps - the app shows download links if they are missing.
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

"$PY" "$ROOT/desktop/make_icons.py" "$BUILD"
SRC="$BUILD/src"
"$PY" "$ROOT/desktop/collect_licenses.py" "$BUILD/THIRD_PARTY_LICENSES.txt" \
    "Tesseract OCR und Sprachdaten (Apache-2.0)=$SRC/tesseract/LICENSE" \
    "Leptonica (BSD-2-Clause)=$SRC/leptonica/leptonica-license.txt" \
    "libpng (libpng License)=$SRC/libpng/LICENSE"

rm -rf "$DIST" "$BUILD/pyinstaller"
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN \
    --distpath "$DIST" --workpath "$BUILD/pyinstaller" "$HERE/Dotationslisten.spec"
APP="$DIST/Dotationslisten.app"

# ad-hoc signature (no Apple Developer ID): required on Apple Silicon, macOS asks once on first start
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

# every binary must run on the minimum macOS
MIN_OK=13.0
bad=0
while IFS= read -r f; do
    v="$(otool -l "$f" 2>/dev/null | awk '/LC_BUILD_VERSION/ {b=1} b && /minos/ {print $2; exit}')"
    [ -z "$v" ] && continue
    if [ "$(printf '%s\n%s\n' "$v" "$MIN_OK" | sort -V | tail -1)" != "$MIN_OK" ] && [ "$v" != "$MIN_OK" ]; then
        echo "zu neu (macOS $v): $f"; bad=1
    fi
done < <(find "$APP" -type f \( -perm -u+x -o -name "*.dylib" -o -name "*.so" \))
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
